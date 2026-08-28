from flask import Blueprint, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import re
from datetime import datetime

from utils import generate_id
from routes.notifications import send_notification_to_class


# =========================================================
# BLUEPRINT
# =========================================================

assignments_bp = Blueprint(
    "assignments_bp",
    __name__,
    url_prefix="/api/assignments"
)

CORS(
    assignments_bp,
    resources={r"/*": {"origins": "*"}}
)


# =========================================================
# MONGODB
# =========================================================

MONGO_URI = os.getenv("MONGO_COLLEGE_DB_URI")

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_COLLEGE_DB_URI environment variable is not set."
    )

client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000
)

db = client["college_db"]

assignments_collection = db["assignments"]


# =========================================================
# NORMALIZE CLASS NAME
# =========================================================

def normalize_class_name(class_name):
    if not class_name:
        return ""

    class_name = str(class_name).strip().upper()

    class_name = re.sub(
        r"[^A-Z0-9]",
        "",
        class_name
    )

    return class_name


# =========================================================
# CONVERT ADMIN CLASS FORMAT
#
# Example:
# 2CSE2 -> 2nd Year CSE2
# 1IT1  -> 1st Year IT1
# =========================================================

def to_student_class_format(raw_class):

    if not raw_class:
        return ""

    raw_class = str(raw_class).strip().upper()

    # Remove spaces/special characters
    raw_class = re.sub(
        r"[^A-Z0-9]",
        "",
        raw_class
    )

    if len(raw_class) < 3:
        return raw_class

    year = raw_class[0]

    rest = raw_class[1:]

    branch = "".join(
        filter(str.isalpha, rest)
    )

    section = "".join(
        filter(str.isdigit, rest)
    )

    year_map = {
        "1": "1st Year",
        "2": "2nd Year",
        "3": "3rd Year",
        "4": "4th Year"
    }

    year_text = year_map.get(
        year,
        year
    )

    return f"{year_text} {branch}{section}"


# =========================================================
# GET ALL ACTIVE ASSIGNMENTS
#
# Used by Admin/Post Assignments page
# =========================================================

@assignments_bp.route("", methods=["GET"])
def get_all_assignments():

    try:

        assignments = list(
            assignments_collection.find(
                {
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

        return jsonify({
            "success": True,
            "assignments": assignments
        }), 200

    except Exception as e:

        print(
            "GET ALL ASSIGNMENTS ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to fetch assignments."
        }), 500


# =========================================================
# GET ASSIGNMENTS BY CLASS
#
# Example:
# /api/assignments/class/2IT1
# =========================================================

@assignments_bp.route(
    "/class/<string:class_name>",
    methods=["GET"]
)
def get_assignments_by_class(class_name):

    try:

        normalized_class = normalize_class_name(
            class_name
        )

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

        return jsonify({
            "success": True,
            "class": class_name,
            "assignments": assignments
        }), 200

    except Exception as e:

        print(
            "GET CLASS ASSIGNMENTS ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to fetch class assignments."
        }), 500


# =========================================================
# POST NEW ASSIGNMENT
#
# IMPORTANT:
# mentorId + deviceId are saved with assignment.
# =========================================================

@assignments_bp.route("", methods=["POST"])
def post_assignment():

    try:

        data = request.get_json(
            force=True
        ) or {}

        # -------------------------------------------------
        # REQUIRED FIELDS
        # -------------------------------------------------

        required_fields = [
            "class",
            "title",
            "subject",
            "deadline"
        ]

        for field in required_fields:

            value = data.get(field)

            if value is None or str(value).strip() == "":

                return jsonify({
                    "success": False,
                    "message": f"{field} is required"
                }), 400

        # -------------------------------------------------
        # MENTOR ID
        # -------------------------------------------------

        mentor_id = str(
            data.get("mentorId", "")
        ).strip()

        if not mentor_id:

            return jsonify({
                "success": False,
                "message": "Mentor ID is required."
            }), 401

        # -------------------------------------------------
        # DEVICE ID
        # -------------------------------------------------

        device_id = str(
            data.get("deviceId", "")
        ).strip()

        if not device_id:

            return jsonify({
                "success": False,
                "message": "Device ID is required."
            }), 401

        # -------------------------------------------------
        # CLASS
        # -------------------------------------------------

        raw_class = str(
            data["class"]
        ).strip()

        student_class = to_student_class_format(
            raw_class
        )

        if not student_class:

            return jsonify({
                "success": False,
                "message": "Invalid class."
            }), 400

        class_normalized = normalize_class_name(
            student_class
        )

        # -------------------------------------------------
        # TITLE / SUBJECT / DEADLINE
        # -------------------------------------------------

        title = str(
            data["title"]
        ).strip()

        subject = str(
            data["subject"]
        ).strip()

        deadline = str(
            data["deadline"]
        ).strip()

        if not title or not subject or not deadline:

            return jsonify({
                "success": False,
                "message": "Title, subject and deadline are required."
            }), 400

        # -------------------------------------------------
        # GENERATE ASSIGNMENT ID
        # -------------------------------------------------

        assignment_id = generate_id("A")

        # -------------------------------------------------
        # ASSIGNMENT DOCUMENT
        # -------------------------------------------------

        assignment = {

            "assignmentId": assignment_id,

            # Student-readable class
            "class": student_class,

            # Normalized class for searching
            "class_normalized": class_normalized,

            "title": title,

            "subject": subject,

            "deadline": deadline,

            # -------------------------------------------------
            # OWNER INFORMATION
            # -------------------------------------------------

            "mentorId": mentor_id,

            "deviceId": device_id,

            # Useful for display/debugging
            "createdBy": {
                "mentorId": mentor_id,
                "deviceId": device_id
            },

            # -------------------------------------------------
            # META
            # -------------------------------------------------

            "createdAt": datetime.utcnow(),

            "submissions": [],

            "active": True
        }

        # -------------------------------------------------
        # INSERT
        # -------------------------------------------------

        assignments_collection.insert_one(
            assignment
        )

        # -------------------------------------------------
        # NOTIFICATION
        # -------------------------------------------------

        try:

            send_notification_to_class(
                class_name=class_normalized,
                title="📚 New Assignment Posted",
                body=f"{subject}: {title}",
                url="/assignments.html"
            )

        except Exception as notification_error:

            # Assignment should NOT fail merely because
            # notification failed.

            print(
                "ASSIGNMENT NOTIFICATION ERROR:",
                str(notification_error)
            )

        # -------------------------------------------------
        # RESPONSE
        # -------------------------------------------------

        return jsonify({

            "success": True,

            "message": "Assignment posted successfully.",

            "assignmentId": assignment_id

        }), 201

    except Exception as e:

        print(
            "POST ASSIGNMENT ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to post assignment."
        }), 500


# =========================================================
# DELETE ASSIGNMENT
#
# SECURITY:
#
# Assignment can be deleted ONLY when:
#
# request mentorId == saved mentorId
#
# AND
#
# request deviceId == saved deviceId
#
# =========================================================

@assignments_bp.route(
    "/<string:assignment_id>",
    methods=["DELETE"]
)
def delete_assignment(assignment_id):

    try:

        data = request.get_json(
            silent=True
        ) or {}

        # -------------------------------------------------
        # GET REQUEST OWNER
        # -------------------------------------------------

        mentor_id = str(
            data.get("mentorId", "")
        ).strip()

        device_id = str(
            data.get("deviceId", "")
        ).strip()

        # -------------------------------------------------
        # BOTH ARE REQUIRED
        # -------------------------------------------------

        if not mentor_id:

            return jsonify({
                "success": False,
                "message": "Mentor ID is required."
            }), 401

        if not device_id:

            return jsonify({
                "success": False,
                "message": "Device ID is required."
            }), 401

        # -------------------------------------------------
        # FIND ASSIGNMENT
        # -------------------------------------------------

        assignment = assignments_collection.find_one(
            {
                "assignmentId": assignment_id,
                "active": True
            }
        )

        if not assignment:

            return jsonify({
                "success": False,
                "message": "Assignment not found."
            }), 404

        # -------------------------------------------------
        # GET SAVED OWNER
        #
        # Supports both new format and old format.
        # -------------------------------------------------

        saved_mentor_id = str(
            assignment.get(
                "mentorId",
                ""
            )
        ).strip()

        saved_device_id = str(
            assignment.get(
                "deviceId",
                ""
            )
        ).strip()

        # -------------------------------------------------
        # SECURITY CHECK
        # -------------------------------------------------

        if not saved_mentor_id or not saved_device_id:

            return jsonify({
                "success": False,
                "message": "This assignment does not have valid owner information and cannot be deleted from this panel."
            }), 403

        # Mentor must match
        if saved_mentor_id != mentor_id:

            return jsonify({
                "success": False,
                "message": "You are not authorized to delete this assignment."
            }), 403

        # Device must match
        if saved_device_id != device_id:

            return jsonify({
                "success": False,
                "message": "This assignment was posted from another authorized device."
            }), 403

        # -------------------------------------------------
        # SOFT DELETE
        # -------------------------------------------------

        result = assignments_collection.update_one(

            {
                "assignmentId": assignment_id,

                "mentorId": mentor_id,

                "deviceId": device_id,

                "active": True
            },

            {
                "$set": {
                    "active": False,
                    "deletedAt": datetime.utcnow(),
                    "deletedBy": {
                        "mentorId": mentor_id,
                        "deviceId": device_id
                    }
                }
            }
        )

        if result.modified_count == 0:

            return jsonify({
                "success": False,
                "message": "Assignment could not be deleted."
            }), 403

        return jsonify({

            "success": True,

            "message": "Assignment deleted successfully."

        }), 200

    except Exception as e:

        print(
            "DELETE ASSIGNMENT ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to delete assignment."
        }), 500


# =========================================================
# GET ASSIGNMENTS FOR STUDENT DASHBOARD
#
# /api/assignments/view/<student_class>
# =========================================================

@assignments_bp.route(
    "/view/<string:student_class>",
    methods=["GET"]
)
def view_assignments_for_student(student_class):

    try:

        normalized_class = normalize_class_name(
            student_class
        )

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

        return jsonify({

            "success": True,

            "assignments": assignments

        }), 200

    except Exception as e:

        print(
            "VIEW STUDENT ASSIGNMENTS ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to load assignments."
        }), 500


# =========================================================
# STUDENT ASSIGNMENTS VIEW
#
# /api/assignments/student/<student_class>
# =========================================================

@assignments_bp.route(
    "/student/<string:student_class>",
    methods=["GET"]
)
def student_assignments(student_class):

    try:

        normalized_class = normalize_class_name(
            student_class
        )

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

        return jsonify({

            "success": True,

            "class": student_class,

            "assignments": assignments

        }), 200

    except Exception as e:

        print(
            "STUDENT ASSIGNMENTS ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Failed to load student assignments."
        }), 500