# =========================================================
# STUDENT PROFILE BLUEPRINT
# =========================================================
#
# Features:
#
# 1. Search students by enrollment / name
# 2. Get complete student profile
# 3. Get assignment completion status
# 4. Completed / incomplete assignment counts
# 5. Get pending fees
# 6. Rewards system
# 7. Add reward
# 8. Remove reward
#
# MongoDB:
#
# users.students
# users.fees
# college_db.assignments
#
# =========================================================

from flask import Blueprint, request, jsonify
from flask_cors import CORS

from pymongo import MongoClient
from datetime import datetime

import os
import re
import uuid


# =========================================================
# BLUEPRINT
# =========================================================

student_profile_bp = Blueprint(
    "student_profile_bp",
    __name__,
    url_prefix="/api/student-profile"
)

CORS(
    student_profile_bp,
    resources={
        r"/*": {
            "origins": "*"
        }
    }
)


# =========================================================
# MONGODB
# =========================================================

# ---------------------------------------------------------
# STUDENTS DATABASE
# Same structure as students.py
# ---------------------------------------------------------

MONGO_URL = os.getenv("MONGO_URL")

if not MONGO_URL:
    raise RuntimeError(
        "MONGO_URL environment variable is not set."
    )

client = MongoClient(
    MONGO_URL,
    serverSelectionTimeoutMS=10000
)

users_db = client["users"]

students_collection = users_db["students"]

fees_collection = users_db["fees"]


# ---------------------------------------------------------
# ASSIGNMENTS DATABASE
# Same structure as assignments.py
# ---------------------------------------------------------

MONGO_COLLEGE_DB_URI = os.getenv(
    "MONGO_COLLEGE_DB_URI"
)

if not MONGO_COLLEGE_DB_URI:
    raise RuntimeError(
        "MONGO_COLLEGE_DB_URI environment variable is not set."
    )

college_client = MongoClient(
    MONGO_COLLEGE_DB_URI,
    serverSelectionTimeoutMS=10000
)

college_db = college_client["college_db"]

assignments_collection = college_db["assignments"]


# =========================================================
# HELPERS
# =========================================================

def normalize_enrollment(enrollment):
    """
    Normalize enrollment number exactly like
    assignments.py does.
    """

    if enrollment is None:
        return ""

    return str(
        enrollment
    ).strip().upper()


# ---------------------------------------------------------
# NORMALIZE CLASS
# ---------------------------------------------------------

def normalize_class_name(class_name):

    if not class_name:
        return ""

    class_name = str(
        class_name
    ).strip().upper()

    class_name = re.sub(
        r"[^A-Z0-9]",
        "",
        class_name
    )

    return class_name


# ---------------------------------------------------------
# CONVERT CLASS TO POSSIBLE ASSIGNMENT FORMAT
#
# Examples:
#
# 2IT1
# 2nd Year IT1
#
# Both become:
#
# 2NDYEARIT1
#
# after normalization.
# ---------------------------------------------------------

def get_student_class(student):

    # Primary field used by students.py
    student_class = student.get(
        "class",
        ""
    )

    if student_class:
        return str(
            student_class
        ).strip()

    # -----------------------------------------------------
    # Fallback
    #
    # Some older student documents may have:
    #
    # year
    # branch
    # section
    #
    # -----------------------------------------------------

    year = str(
        student.get(
            "year",
            ""
        )
    ).strip()

    branch = str(
        student.get(
            "branch",
            ""
        )
    ).strip()

    section = str(
        student.get(
            "section",
            ""
        )
    ).strip()

    if year and branch and section:
        return f"{year} {branch}{section}"

    if year and branch:
        return f"{year} {branch}"

    return ""


# ---------------------------------------------------------
# SERIALIZE MONGODB VALUES
# ---------------------------------------------------------

def clean_for_json(value):

    if isinstance(
        value,
        datetime
    ):
        return value.isoformat()

    if isinstance(
        value,
        list
    ):
        return [
            clean_for_json(item)
            for item in value
        ]

    if isinstance(
        value,
        dict
    ):
        cleaned = {}

        for key, item in value.items():

            # Never expose MongoDB internal ID
            if key == "_id":
                continue

            cleaned[key] = clean_for_json(
                item
            )

        return cleaned

    return value


# ---------------------------------------------------------
# GET ASSIGNMENT STATUS FOR ONE STUDENT
#
# This follows assignments.py logic:
#
# active == True
# class_normalized == student's class
#
# submission.enrollmentNumber == student enrollment
#
# submitted / done / completed
#     => done
#
# otherwise
#     => pending
# ---------------------------------------------------------

def get_assignment_status_for_student(
    student
):

    enrollment = normalize_enrollment(
        student.get(
            "enrollment",
            ""
        )
    )

    student_class = get_student_class(
        student
    )

    normalized_class = normalize_class_name(
        student_class
    )

    if not enrollment:
        return {
            "totalAssignments": 0,
            "completedAssignments": 0,
            "incompleteAssignments": 0,
            "pendingAssignments": 0,
            "assignments": []
        }

    if not normalized_class:

        return {
            "totalAssignments": 0,
            "completedAssignments": 0,
            "incompleteAssignments": 0,
            "pendingAssignments": 0,
            "assignments": [],
            "message": "Student class is not available."
        }

    # -----------------------------------------------------
    # FETCH ACTIVE ASSIGNMENTS
    # -----------------------------------------------------

    assignments = list(
        assignments_collection.find(
            {
                "class_normalized": normalized_class,
                "active": True
            },
            {
                "_id": 0
            }
        ).sort(
            "createdAt",
            -1
        )
    )

    result_assignments = []

    completed_count = 0

    # -----------------------------------------------------
    # CHECK EVERY ASSIGNMENT
    # -----------------------------------------------------

    for assignment in assignments:

        submissions = assignment.get(
            "submissions",
            []
        )

        status = "pending"

        # -------------------------------------------------
        # FIND THIS STUDENT'S SUBMISSION
        # -------------------------------------------------

        if isinstance(
            submissions,
            list
        ):

            for submission in submissions:

                if not isinstance(
                    submission,
                    dict
                ):
                    continue

                saved_enrollment = normalize_enrollment(
                    submission.get(
                        "enrollmentNumber",
                        ""
                    )
                )

                if saved_enrollment != enrollment:
                    continue

                saved_status = str(
                    submission.get(
                        "status",
                        ""
                    )
                ).strip().lower()

                # Same statuses as assignments.py
                if saved_status in [
                    "submitted",
                    "done",
                    "completed"
                ]:
                    status = "done"

                break

        # -------------------------------------------------
        # COUNT
        # -------------------------------------------------

        if status == "done":
            completed_count += 1

        # -------------------------------------------------
        # DON'T SEND ALL STUDENTS' SUBMISSIONS
        # -------------------------------------------------

        assignment_data = dict(
            assignment
        )

        assignment_data.pop(
            "submissions",
            None
        )

        assignment_data["status"] = status

        assignment_data["completed"] = (
            status == "done"
        )

        result_assignments.append(
            clean_for_json(
                assignment_data
            )
        )

    # -----------------------------------------------------
    # TOTALS
    # -----------------------------------------------------

    total_assignments = len(
        result_assignments
    )

    incomplete_count = (
        total_assignments -
        completed_count
    )

    return {
        "totalAssignments": total_assignments,
        "completedAssignments": completed_count,
        "incompleteAssignments": incomplete_count,
        "pendingAssignments": incomplete_count,
        "assignments": result_assignments
    }


# =========================================================
# GET STUDENT PROFILE
#
# GET:
#
# /api/student-profile/<enrollment>
#
# =========================================================

@student_profile_bp.route(
    "/<string:enrollment>",
    methods=["GET"]
)
def get_student_profile(enrollment):

    try:

        enrollment = normalize_enrollment(
            enrollment
        )

        if not enrollment:

            return jsonify({
                "success": False,
                "message": "Enrollment number is required."
            }), 400

        # -------------------------------------------------
        # FIND STUDENT
        # -------------------------------------------------

        student = students_collection.find_one(
            {
                "enrollment": enrollment
            },
            {
                "_id": 0,
                "password": 0
            }
        )

        if not student:

            return jsonify({
                "success": False,
                "message": "Student not found."
            }), 404

        # -------------------------------------------------
        # FEES
        # -------------------------------------------------

        fee_record = fees_collection.find_one(
            {
                "enrollment": enrollment
            },
            {
                "_id": 0
            }
        )

        pending_fees = 0

        if fee_record:

            pending_fees = fee_record.get(
                "pending_fees",
                0
            )

        # -------------------------------------------------
        # ASSIGNMENTS
        # -------------------------------------------------

        assignment_data = (
            get_assignment_status_for_student(
                student
            )
        )

        # -------------------------------------------------
        # REWARDS
        #
        # Rewards are stored inside student document:
        #
        # "rewards": [
        #     {
        #         "rewardId": "...",
        #         "title": "...",
        #         "points": 10,
        #         "reason": "...",
        #         "addedAt": "..."
        #     }
        # ]
        #
        # -------------------------------------------------

        rewards = student.get(
            "rewards",
            []
        )

        if not isinstance(
            rewards,
            list
        ):
            rewards = []

        cleaned_rewards = []

        total_reward_points = 0

        for reward in rewards:

            if not isinstance(
                reward,
                dict
            ):
                continue

            reward_data = clean_for_json(
                reward
            )

            points = reward_data.get(
                "points",
                0
            )

            try:
                points = int(points)
            except (
                TypeError,
                ValueError
            ):
                points = 0

            total_reward_points += points

            cleaned_rewards.append(
                reward_data
            )

        # -------------------------------------------------
        # STUDENT DATA
        # -------------------------------------------------

        student_data = clean_for_json(
            student
        )

        # Extra calculated fields
        student_data["pending_fees"] = (
            pending_fees
        )

        student_data["rewards"] = (
            cleaned_rewards
        )

        student_data["totalRewardPoints"] = (
            total_reward_points
        )

        student_data["assignmentStats"] = (
            assignment_data
        )

        # -------------------------------------------------
        # RESPONSE
        # -------------------------------------------------

        return jsonify({

            "success": True,

            "student": student_data,

            # Easy frontend access
            "assignments": assignment_data,

            "rewards": cleaned_rewards,

            "totalRewardPoints": (
                total_reward_points
            ),

            "pendingFees": pending_fees

        }), 200

    except Exception as e:

        print(
            "STUDENT PROFILE ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to load student profile."
        }), 500


# =========================================================
# SEARCH STUDENTS
#
# GET:
#
# /api/student-profile/search?q=0827IT2411
#
# Supports:
#
# enrollment
# name
#
# =========================================================

@student_profile_bp.route(
    "/search",
    methods=["GET"]
)
def search_students():

    try:

        query = str(
            request.args.get(
                "q",
                ""
            )
        ).strip()

        if not query:

            return jsonify({
                "success": True,
                "students": []
            }), 200

        # -------------------------------------------------
        # Escape regex so special characters don't break
        # query.
        # -------------------------------------------------

        safe_query = re.escape(
            query
        )

        students = list(
            students_collection.find(
                {
                    "$or": [
                        {
                            "enrollment": {
                                "$regex": safe_query,
                                "$options": "i"
                            }
                        },
                        {
                            "name": {
                                "$regex": safe_query,
                                "$options": "i"
                            }
                        }
                    ]
                },
                {
                    "_id": 0,
                    "password": 0,
                    "name": 1,
                    "enrollment": 1,
                    "branch": 1,
                    "class": 1,
                    "year": 1,
                    "section": 1
                }
            ).limit(20)
        )

        cleaned_students = []

        for student in students:

            cleaned_students.append(
                clean_for_json(
                    student
                )
            )

        return jsonify({

            "success": True,

            "query": query,

            "count": len(
                cleaned_students
            ),

            "students": cleaned_students

        }), 200

    except Exception as e:

        print(
            "STUDENT SEARCH ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to search students."
        }), 500


# =========================================================
# GET ASSIGNMENT STATUS ONLY
#
# GET:
#
# /api/student-profile/<enrollment>/assignments
#
# =========================================================

@student_profile_bp.route(
    "/<string:enrollment>/assignments",
    methods=["GET"]
)
def get_student_assignments(enrollment):

    try:

        enrollment = normalize_enrollment(
            enrollment
        )

        if not enrollment:

            return jsonify({
                "success": False,
                "message": "Enrollment number is required."
            }), 400

        # -------------------------------------------------
        # FIND STUDENT
        # -------------------------------------------------

        student = students_collection.find_one(
            {
                "enrollment": enrollment
            },
            {
                "_id": 0,
                "password": 0
            }
        )

        if not student:

            return jsonify({
                "success": False,
                "message": "Student not found."
            }), 404

        # -------------------------------------------------
        # GET ASSIGNMENTS
        # -------------------------------------------------

        assignment_data = (
            get_assignment_status_for_student(
                student
            )
        )

        return jsonify({

            "success": True,

            "enrollmentNumber": enrollment,

            "class": get_student_class(
                student
            ),

            "totalAssignments":
                assignment_data.get(
                    "totalAssignments",
                    0
                ),

            "completedAssignments":
                assignment_data.get(
                    "completedAssignments",
                    0
                ),

            "incompleteAssignments":
                assignment_data.get(
                    "incompleteAssignments",
                    0
                ),

            "pendingAssignments":
                assignment_data.get(
                    "pendingAssignments",
                    0
                ),

            "assignments":
                assignment_data.get(
                    "assignments",
                    []
                )

        }), 200

    except Exception as e:

        print(
            "STUDENT ASSIGNMENTS PROFILE ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to load student assignments."
        }), 500


# =========================================================
# GET REWARDS
#
# GET:
#
# /api/student-profile/<enrollment>/rewards
#
# =========================================================

@student_profile_bp.route(
    "/<string:enrollment>/rewards",
    methods=["GET"]
)
def get_student_rewards(enrollment):

    try:

        enrollment = normalize_enrollment(
            enrollment
        )

        if not enrollment:

            return jsonify({
                "success": False,
                "message": "Enrollment number is required."
            }), 400

        student = students_collection.find_one(
            {
                "enrollment": enrollment
            },
            {
                "_id": 0,
                "password": 0,
                "rewards": 1,
                "name": 1,
                "enrollment": 1
            }
        )

        if not student:

            return jsonify({
                "success": False,
                "message": "Student not found."
            }), 404

        rewards = student.get(
            "rewards",
            []
        )

        if not isinstance(
            rewards,
            list
        ):
            rewards = []

        total_points = 0

        cleaned_rewards = []

        for reward in rewards:

            if not isinstance(
                reward,
                dict
            ):
                continue

            reward_data = clean_for_json(
                reward
            )

            try:

                points = int(
                    reward_data.get(
                        "points",
                        0
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                points = 0

            total_points += points

            cleaned_rewards.append(
                reward_data
            )

        return jsonify({

            "success": True,

            "enrollment": enrollment,

            "name": student.get(
                "name",
                ""
            ),

            "rewards": cleaned_rewards,

            "totalRewardPoints":
                total_points

        }), 200

    except Exception as e:

        print(
            "GET REWARDS ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to load rewards."
        }), 500


# =========================================================
# ADD REWARD
#
# POST:
#
# /api/student-profile/<enrollment>/rewards
#
# BODY:
#
# {
#     "title": "Assignment Champion",
#     "points": 10,
#     "reason": "Completed all assignments",
#     "addedBy": "ADMIN001"
# }
#
# =========================================================

@student_profile_bp.route(
    "/<string:enrollment>/rewards",
    methods=["POST"]
)
def add_student_reward(enrollment):

    try:

        enrollment = normalize_enrollment(
            enrollment
        )

        if not enrollment:

            return jsonify({
                "success": False,
                "message": "Enrollment number is required."
            }), 400

        data = request.get_json(
            silent=True
        ) or {}

        # -------------------------------------------------
        # REWARD TITLE
        # -------------------------------------------------

        title = str(
            data.get(
                "title",
                ""
            )
        ).strip()

        if not title:

            return jsonify({
                "success": False,
                "message": "Reward title is required."
            }), 400

        # -------------------------------------------------
        # POINTS
        # -------------------------------------------------

        points = data.get(
            "points",
            0
        )

        try:

            points = int(
                points
            )

        except (
            TypeError,
            ValueError
        ):

            return jsonify({
                "success": False,
                "message": "Reward points must be a number."
            }), 400

        if points <= 0:

            return jsonify({
                "success": False,
                "message": "Reward points must be greater than 0."
            }), 400

        # -------------------------------------------------
        # REASON
        # -------------------------------------------------

        reason = str(
            data.get(
                "reason",
                ""
            )
        ).strip()

        # -------------------------------------------------
        # WHO ADDED IT
        # -------------------------------------------------

        added_by = str(
            data.get(
                "addedBy",
                ""
            )
        ).strip()

        # -------------------------------------------------
        # CHECK STUDENT
        # -------------------------------------------------

        student = students_collection.find_one(
            {
                "enrollment": enrollment
            }
        )

        if not student:

            return jsonify({
                "success": False,
                "message": "Student not found."
            }), 404

        # -------------------------------------------------
        # CREATE REWARD
        # -------------------------------------------------

        reward = {

            "rewardId": str(
                uuid.uuid4()
            ),

            "title": title,

            "points": points,

            "reason": reason,

            "addedBy": added_by,

            "addedAt": datetime.utcnow()

        }

        # -------------------------------------------------
        # ADD TO STUDENT
        # -------------------------------------------------

        result = students_collection.update_one(

            {
                "enrollment": enrollment
            },

            {
                "$push": {
                    "rewards": reward
                }
            }

        )

        if result.modified_count == 0:

            return jsonify({
                "success": False,
                "message": "Reward could not be added."
            }), 500

        # -------------------------------------------------
        # CALCULATE TOTAL
        # -------------------------------------------------

        updated_student = students_collection.find_one(
            {
                "enrollment": enrollment
            },
            {
                "_id": 0,
                "password": 0,
                "rewards": 1
            }
        )

        rewards = updated_student.get(
            "rewards",
            []
        )

        total_points = 0

        for item in rewards:

            try:

                total_points += int(
                    item.get(
                        "points",
                        0
                    )
                )

            except (
                TypeError,
                ValueError
            ):
                pass

        return jsonify({

            "success": True,

            "message":
                "Reward added successfully.",

            "enrollment":
                enrollment,

            "reward":
                clean_for_json(
                    reward
                ),

            "totalRewardPoints":
                total_points

        }), 201

    except Exception as e:

        print(
            "ADD REWARD ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to add reward."
        }), 500


# =========================================================
# REMOVE REWARD
#
# DELETE:
#
# /api/student-profile/<enrollment>/rewards/<reward_id>
#
# =========================================================

@student_profile_bp.route(
    "/<string:enrollment>/rewards/<string:reward_id>",
    methods=["DELETE"]
)
def remove_student_reward(
    enrollment,
    reward_id
):

    try:

        enrollment = normalize_enrollment(
            enrollment
        )

        reward_id = str(
            reward_id
        ).strip()

        if not enrollment:

            return jsonify({
                "success": False,
                "message": "Enrollment number is required."
            }), 400

        if not reward_id:

            return jsonify({
                "success": False,
                "message": "Reward ID is required."
            }), 400

        # -------------------------------------------------
        # FIND STUDENT
        # -------------------------------------------------

        student = students_collection.find_one(
            {
                "enrollment": enrollment
            }
        )

        if not student:

            return jsonify({
                "success": False,
                "message": "Student not found."
            }), 404

        rewards = student.get(
            "rewards",
            []
        )

        if not isinstance(
            rewards,
            list
        ):
            rewards = []

        # -------------------------------------------------
        # FIND REWARD
        # -------------------------------------------------

        reward_to_remove = None

        for reward in rewards:

            if not isinstance(
                reward,
                dict
            ):
                continue

            if str(
                reward.get(
                    "rewardId",
                    ""
                )
            ) == reward_id:

                reward_to_remove = reward

                break

        if not reward_to_remove:

            return jsonify({
                "success": False,
                "message": "Reward not found."
            }), 404

        # -------------------------------------------------
        # REMOVE REWARD
        # -------------------------------------------------

        result = students_collection.update_one(

            {
                "enrollment": enrollment
            },

            {
                "$pull": {
                    "rewards": {
                        "rewardId": reward_id
                    }
                }
            }

        )

        if result.modified_count == 0:

            return jsonify({
                "success": False,
                "message": "Reward could not be removed."
            }), 500

        # -------------------------------------------------
        # GET UPDATED REWARDS
        # -------------------------------------------------

        updated_student = students_collection.find_one(
            {
                "enrollment": enrollment
            },
            {
                "_id": 0,
                "password": 0,
                "rewards": 1
            }
        )

        updated_rewards = updated_student.get(
            "rewards",
            []
        )

        total_points = 0

        for reward in updated_rewards:

            try:

                total_points += int(
                    reward.get(
                        "points",
                        0
                    )
                )

            except (
                TypeError,
                ValueError
            ):
                pass

        return jsonify({

            "success": True,

            "message":
                "Reward removed successfully.",

            "removedReward":
                clean_for_json(
                    reward_to_remove
                ),

            "totalRewardPoints":
                total_points

        }), 200

    except Exception as e:

        print(
            "REMOVE REWARD ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to remove reward."
        }), 500