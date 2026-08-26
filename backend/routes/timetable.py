from flask import Blueprint, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from bson import ObjectId
from datetime import datetime
import os
import re
import copy
from db import db


# =========================================================
# BLUEPRINT
# =========================================================

timetable_bp = Blueprint(
    "timetable_bp",
    __name__,
    url_prefix="/api/timetable"
)

CORS(timetable_bp)


# =========================================================
# UPLOAD CONFIG
# =========================================================

UPLOAD_FOLDER = "uploads/timetables"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {"pdf"}


# =========================================================
# MY LECTURE REQUESTS
# =========================================================
#
# Returns BOTH:
#   1. Requests received by this mentor
#   2. Requests created by this mentor
#
# Therefore the same page can show complete history:
#
#   Pending
#   Approved
#   Rejected / Disapproved
#
# =========================================================

@timetable_bp.route(
    "/lecture-requests/my/<mentor_id>",
    methods=["GET"]
)
def get_my_lecture_requests(mentor_id):

    try:

        mentor_id = str(
            mentor_id or ""
        ).strip()

        if not mentor_id:

            return jsonify({
                "success": False,
                "message":
                    "mentorId is required"
            }), 400


        requests_data = list(
            db.lecture_requests.find({

                "$or": [

                    {
                        "targetMentorId":
                            mentor_id
                    },

                    {
                        "requesterMentorId":
                            mentor_id
                    },

                    {
                        "targetFaculty":
                            mentor_id
                    }

                ]

            }).sort(
                "createdAt",
                -1
            )
        )


        result = []

        for req in requests_data:

            item = serialize_doc(
                copy.deepcopy(req)
            )

            requester_id = str(
                req.get(
                    "requesterMentorId",
                    ""
                )
            ).strip()

            target_id = str(
                req.get(
                    "targetMentorId",
                    ""
                )
            ).strip()


            # -----------------------------------------
            # WHO IS THIS REQUEST FOR?
            # -----------------------------------------

            if requester_id == mentor_id:

                item["role"] = "requester"

            elif target_id == mentor_id:

                item["role"] = "target"

            else:

                item["role"] = "unknown"


            # -----------------------------------------
            # Normalized status
            # -----------------------------------------

            status = str(
                req.get(
                    "status",
                    "pending"
                )
            ).lower().strip()


            if status == "rejected":

                item["displayStatus"] = (
                    "disapproved"
                )

            else:

                item["displayStatus"] = status


            # -----------------------------------------
            # Can requester edit?
            # -----------------------------------------

            item["canEdit"] = (
                status == "approved"
                and
                requester_id == mentor_id
                and
                not bool(
                    req.get(
                        "lectureRemoved",
                        False
                    )
                )
            )


            # -----------------------------------------
            # Can requester remove?
            # -----------------------------------------

            item["canRemove"] = (
                status == "approved"
                and
                requester_id == mentor_id
                and
                not bool(
                    req.get(
                        "lectureRemoved",
                        False
                    )
                )
            )


            # -----------------------------------------
            # Can target approve/reject?
            # -----------------------------------------

            item["canApprove"] = (
                status == "pending"
                and
                target_id == mentor_id
            )

            item["canReject"] = (
                status == "pending"
                and
                target_id == mentor_id
            )


            result.append(item)


        return jsonify({

            "success":
                True,

            "count":
                len(result),

            "requests":
                result

        }), 200


    except Exception as e:

        return jsonify({

            "success":
                False,

            "message":
                str(e)

        }), 500

# =========================================================
# APPROVE LECTURE REQUEST
# =========================================================
#
# IMPORTANT:
#
# APPROVAL ONLY changes request status.
#
# It DOES NOT modify timetable.
#
# Timetable will be modified later when requester
# clicks "Edit The Lecture Now" and saves.
#
# =========================================================

@timetable_bp.route(
    "/lecture-request/approve",
    methods=["PUT"]
)
def approve_lecture_request():

    try:

        data = request.get_json(
            silent=True
        ) or {}


        req_id = str(
            data.get(
                "requestId",
                ""
            )
        ).strip()


        approver_id = str(
            data.get(
                "mentorId",
                ""
            )
        ).strip()


        if not req_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "requestId required"

            }), 400


        if not approver_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "mentorId required"

            }), 400


        # -------------------------------------------------
        # ObjectId
        # -------------------------------------------------

        try:

            object_id = ObjectId(
                req_id
            )

        except Exception:

            return jsonify({

                "success":
                    False,

                "message":
                    "Invalid requestId"

            }), 400


        # -------------------------------------------------
        # Only target mentor can approve
        # -------------------------------------------------

        req = db.lecture_requests.find_one({

            "_id":
                object_id,

            "status":
                "pending"

        })


        if not req:

            return jsonify({

                "success":
                    False,

                "message":
                    "Request not found or already processed"

            }), 404


        target_id = str(
            req.get(
                "targetMentorId",
                ""
            )
        ).strip()


        if target_id != approver_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "Only the designated faculty can approve this request."

            }), 403


        # -------------------------------------------------
        # VERIFY TARGET FACULTY STILL OWNS THE LECTURE
        # -------------------------------------------------

        old_lecture = copy.deepcopy(
            req.get(
                "oldLecture",
                {}
            )
        )


        existing_class = str(
            req.get(
                "existingClass",
                req.get(
                    "className",
                    ""
                )
            )
        ).strip()


        day = str(
            req.get(
                "day",
                ""
            )
        ).strip()


        if not existing_class:

            return jsonify({

                "success":
                    False,

                "message":
                    "Existing class missing from request."

            }), 409


        if not day:

            return jsonify({

                "success":
                    False,

                "message":
                    "Day missing from request."

            }), 409


        normalize_lecture(
            old_lecture
        )


        # -------------------------------------------------
        # Find timetable
        # -------------------------------------------------

        timetable = db.timetables.find_one({

            "className":
                existing_class

        })


        if not timetable:

            return jsonify({

                "success":
                    False,

                "message":
                    "Original timetable no longer exists."

            }), 409


        schedule = copy.deepcopy(

            timetable.get(
                "weeklySchedule",
                {}
            ).get(
                day,
                []
            )

        )


        if not isinstance(
            schedule,
            list
        ):

            schedule = []


        old_id = str(
            old_lecture.get(
                "_id",
                ""
            )
        ).strip()


        old_start = old_lecture.get(
            "startTimeMins"
        )

        old_end = old_lecture.get(
            "endTimeMins"
        )

        old_subject = str(
            old_lecture.get(
                "subject",
                ""
            )
        ).strip()


        old_faculty_ids = set(
            get_lecture_faculty_ids(
                old_lecture
            )
        )


        found = False


        for current in schedule:

            if not isinstance(
                current,
                dict
            ):
                continue


            normalize_lecture(
                current
            )


            current_id = str(
                current.get(
                    "_id",
                    ""
                )
            ).strip()


            current_faculty_ids = set(
                get_lecture_faculty_ids(
                    current
                )
            )


            same_id = (

                old_id

                and

                current_id

                and

                old_id == current_id

            )


            same_identity = (

                current.get(
                    "startTimeMins"
                )
                ==
                old_start

                and

                current.get(
                    "endTimeMins"
                )
                ==
                old_end

                and

                str(
                    current.get(
                        "subject",
                        ""
                    )
                ).strip()
                ==
                old_subject

                and

                current_faculty_ids
                ==
                old_faculty_ids

            )


            if same_id or same_identity:

                found = True

                break


        if not found:

            return jsonify({

                "success":
                    False,

                "message":
                    "This lecture has already changed or been removed. Please reload the timetable."

            }), 409


        # -------------------------------------------------
        # IMPORTANT:
        # APPROVAL DOES NOT MODIFY TIMETABLE
        # -------------------------------------------------

        result = db.lecture_requests.update_one(

            {
                "_id":
                    object_id,

                "status":
                    "pending",

                "targetMentorId":
                    approver_id
            },

            {
                "$set": {

                    "status":
                        "approved",

                    "approvedBy":
                        approver_id,

                    "approvedAt":
                        datetime.utcnow(),

                    "updatedAt":
                        datetime.utcnow(),

                    "lectureEditAllowed":
                        True,

                    "lectureRemoved":
                        False,

                    "lectureEdited":
                        False

                }
            }

        )


        if result.modified_count != 1:

            return jsonify({

                "success":
                    False,

                "message":
                    "Request could not be approved because its status changed."

            }), 409


        return jsonify({

            "success":
                True,

            "requestId":
                req_id,

            "status":
                "approved",

            "timetableUpdated":
                False,

            "lectureEditAllowed":
                True,

            "message":
                "Lecture request approved. The timetable will remain unchanged until the requester edits and saves the lecture."

        }), 200


    except Exception as e:

        return jsonify({

            "success":
                False,

            "message":
                str(e)

        }), 500

# =========================================================
# DISAPPROVE LECTURE REQUEST
# =========================================================

@timetable_bp.route(
    "/lecture-request/reject",
    methods=["PUT"]
)
def reject_lecture_request():

    try:

        data = request.get_json(
            silent=True
        ) or {}


        req_id = str(
            data.get(
                "requestId",
                ""
            )
        ).strip()


        mentor_id = str(
            data.get(
                "mentorId",
                ""
            )
        ).strip()


        if not req_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "requestId required"

            }), 400


        if not mentor_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "mentorId required"

            }), 400


        try:

            object_id = ObjectId(
                req_id
            )

        except Exception:

            return jsonify({

                "success":
                    False,

                "message":
                    "Invalid requestId"

            }), 400


        req = db.lecture_requests.find_one({

            "_id":
                object_id,

            "status":
                "pending"

        })


        if not req:

            return jsonify({

                "success":
                    False,

                "message":
                    "Request not found or already processed"

            }), 404


        target_id = str(
            req.get(
                "targetMentorId",
                ""
            )
        ).strip()


        if target_id != mentor_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "Only the designated faculty can disapprove this request."

            }), 403


        result = db.lecture_requests.update_one(

            {
                "_id":
                    object_id,

                "status":
                    "pending",

                "targetMentorId":
                    mentor_id
            },

            {
                "$set": {

                    "status":
                        "rejected",

                    "processedBy":
                        mentor_id,

                    "processedAt":
                        datetime.utcnow(),

                    "updatedAt":
                        datetime.utcnow(),

                    "lectureEditAllowed":
                        False

                }
            }

        )


        if result.modified_count != 1:

            return jsonify({

                "success":
                    False,

                "message":
                    "Request could not be disapproved."

            }), 409


        return jsonify({

            "success":
                True,

            "requestId":
                req_id,

            "status":
                "rejected",

            "message":
                "Lecture request disapproved."

        }), 200


    except Exception as e:

        return jsonify({

            "success":
                False,

            "message":
                str(e)

        }), 500

# =========================================================
# EDIT APPROVED LECTURE
# =========================================================
#
# ONLY requester mentor can use this.
#
# Editable:
#   - Faculty
#   - Subject
#
# LOCKED:
#   - Day
#   - Start time
#   - End time
#
# =========================================================

@timetable_bp.route(
    "/lecture-request/edit",
    methods=["PUT"]
)
def edit_approved_lecture():

    try:

        data = request.get_json(
            silent=True
        ) or {}


        req_id = str(
            data.get(
                "requestId",
                ""
            )
        ).strip()


        requester_id = str(
            data.get(
                "mentorId",
                ""
            )
        ).strip()


        subject = str(
            data.get(
                "subject",
                ""
            )
        ).strip()


        faculty_ids = clean_id_list(
            data.get(
                "facultyIds",
                []
            )
        )


        if not req_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "requestId required"

            }), 400


        if not requester_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "mentorId required"

            }), 400


        if not subject:

            return jsonify({

                "success":
                    False,

                "message":
                    "Subject is required"

            }), 400


        if not faculty_ids:

            return jsonify({

                "success":
                    False,

                "message":
                    "At least one faculty is required"

            }), 400


        try:

            object_id = ObjectId(
                req_id
            )

        except Exception:

            return jsonify({

                "success":
                    False,

                "message":
                    "Invalid requestId"

            }), 400


        # -------------------------------------------------
        # Only approved request
        # -------------------------------------------------

        req = db.lecture_requests.find_one({

            "_id":
                object_id,

            "status":
                "approved"

        })


        if not req:

            return jsonify({

                "success":
                    False,

                "message":
                    "Approved lecture request not found."

            }), 404


        # -------------------------------------------------
        # ONLY REQUESTER CAN EDIT
        # -------------------------------------------------

        actual_requester = str(
            req.get(
                "requesterMentorId",
                ""
            )
        ).strip()


        if actual_requester != requester_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "Only the requesting mentor can edit this lecture."

            }), 403


        if req.get(
            "lectureRemoved",
            False
        ):

            return jsonify({

                "success":
                    False,

                "message":
                    "This lecture has already been removed."

            }), 409


        # -------------------------------------------------
        # Get original lecture
        # -------------------------------------------------

        old_lecture = copy.deepcopy(
            req.get(
                "oldLecture",
                {}
            )
        )


        existing_class = str(
            req.get(
                "existingClass",
                req.get(
                    "className",
                    ""
                )
            )
        ).strip()


        day = str(
            req.get(
                "day",
                ""
            )
        ).strip()


        if not existing_class or not day:

            return jsonify({

                "success":
                    False,

                "message":
                    "Lecture location information is missing."

            }), 409


        normalize_lecture(
            old_lecture
        )


        old_start = old_lecture.get(
            "startTimeMins"
        )

        old_end = old_lecture.get(
            "endTimeMins"
        )


        if old_start is None or old_end is None:

            return jsonify({

                "success":
                    False,

                "message":
                    "Original lecture time is invalid."

            }), 409


        # -------------------------------------------------
        # LOCK TIME
        # -------------------------------------------------
        #
        # NEVER accept startTime/endTime from frontend.
        #
        # We always use oldLecture time.
        # -------------------------------------------------

        locked_start = old_lecture.get(
            "startTime"
        )

        locked_end = old_lecture.get(
            "endTime"
        )


        # -------------------------------------------------
        # Verify new faculty
        # -------------------------------------------------

        new_faculty = resolve_faculty(
            faculty_ids
        )


        if not new_faculty:

            return jsonify({

                "success":
                    False,

                "message":
                    "Selected faculty could not be resolved."

            }), 409


        # -------------------------------------------------
        # CONFLICT CHECK
        #
        # Use OTHER classes only.
        #
        # Same class is excluded.
        # -------------------------------------------------

        conflicts = find_conflicts(

            faculty_ids,

            day,

            old_start,

            old_end,

            existing_class

        )


        # -------------------------------------------------
        # Remove accidental same-class conflicts
        # -------------------------------------------------

        filtered_conflicts = []


        for conflict in conflicts:

            if str(
                conflict.get(
                    "class",
                    ""
                )
            ).strip() == existing_class:

                continue


            filtered_conflicts.append(
                conflict
            )


        conflicts = (
            filtered_conflicts
        )


        if conflicts:

            return jsonify({

                "success":
                    False,

                "conflict":
                    True,

                "message":
                    "Selected faculty already has another lecture at this time.",

                "conflicts":
                    conflicts

            }), 409


        # -------------------------------------------------
        # Find exact lecture in timetable
        # -------------------------------------------------

        timetable = db.timetables.find_one({

            "className":
                existing_class

        })


        if not timetable:

            return jsonify({

                "success":
                    False,

                "message":
                    "Timetable not found."

            }), 404


        schedule = copy.deepcopy(

            timetable.get(
                "weeklySchedule",
                {}
            ).get(
                day,
                []
            )

        )


        if not isinstance(
            schedule,
            list
        ):

            schedule = []


        old_id = str(
            old_lecture.get(
                "_id",
                ""
            )
        ).strip()


        old_subject = str(
            old_lecture.get(
                "subject",
                ""
            )
        ).strip()


        old_faculty_ids = set(
            get_lecture_faculty_ids(
                old_lecture
            )
        )


        found_index = -1


        for index, raw in enumerate(
            schedule
        ):

            if not isinstance(
                raw,
                dict
            ):

                continue


            current = copy.deepcopy(
                raw
            )


            normalize_lecture(
                current
            )


            current_id = str(
                current.get(
                    "_id",
                    ""
                )
            ).strip()


            current_faculty_ids = set(
                get_lecture_faculty_ids(
                    current
                )
            )


            same_id = (

                old_id
                and
                current_id
                and
                old_id == current_id

            )


            same_identity = (

                current.get(
                    "startTimeMins"
                )
                ==
                old_start

                and

                current.get(
                    "endTimeMins"
                )
                ==
                old_end

                and

                str(
                    current.get(
                        "subject",
                        ""
                    )
                ).strip()
                ==
                old_subject

                and

                current_faculty_ids
                ==
                old_faculty_ids

            )


            if same_id or same_identity:

                found_index = index

                break


        if found_index < 0:

            return jsonify({

                "success":
                    False,

                "message":
                    "The original lecture is no longer available. Please reload the timetable."

            }), 409


        # -------------------------------------------------
        # BUILD UPDATED LECTURE
        # -------------------------------------------------

        updated_lecture = copy.deepcopy(
            schedule[found_index]
        )


        updated_lecture[
            "subject"
        ] = subject


        updated_lecture[
            "facultyIds"
        ] = faculty_ids


        updated_lecture[
            "faculty"
        ] = new_faculty


        # LOCK original time
        updated_lecture[
            "startTime"
        ] = locked_start


        updated_lecture[
            "endTime"
        ] = locked_end


        updated_lecture[
            "startTimeMins"
        ] = old_start


        updated_lecture[
            "endTimeMins"
        ] = old_end


        updated_lecture[
            "status"
        ] = "approved"


        updated_lecture[
            "approvedFromRequestId"
        ] = req_id


        updated_lecture[
            "lastEditedBy"
        ] = requester_id


        updated_lecture[
            "lastEditedAt"
        ] = datetime.utcnow()


        # -------------------------------------------------
        # Replace EXACT lecture
        # -------------------------------------------------

        schedule[
            found_index
        ] = updated_lecture


        # -------------------------------------------------
        # Sort by time
        # -------------------------------------------------

        schedule.sort(

            key=lambda lecture:

                time_to_minutes(

                    lecture.get(
                        "startTime",
                        "12:00 AM"
                    )

                )

        )


        # -------------------------------------------------
        # Update timetable
        # -------------------------------------------------

        result = db.timetables.update_one(

            {
                "_id":
                    timetable["_id"]
            },

            {
                "$set": {

                    f"weeklySchedule.{day}":
                        schedule,

                    "updatedAt":
                        datetime.utcnow()

                }

            }

        )


        if result.matched_count != 1:

            return jsonify({

                "success":
                    False,

                "message":
                    "Timetable could not be updated."

            }), 500


        # -------------------------------------------------
        # Update request
        # -------------------------------------------------

        db.lecture_requests.update_one(

            {
                "_id":
                    object_id
            },

            {
                "$set": {

                    "lectureEdited":
                        True,

                    "lectureEditAllowed":
                        True,

                    "editedBy":
                        requester_id,

                    "editedAt":
                        datetime.utcnow(),

                    "editedSubject":
                        subject,

                    "editedFacultyIds":
                        faculty_ids,

                    "appliedLecture":
                        copy.deepcopy(
                            updated_lecture
                        ),

                    "updatedAt":
                        datetime.utcnow()

                }

            }

        )


        return jsonify({

            "success":
                True,

            "timetableUpdated":
                True,

            "requestId":
                req_id,

            "lecture":
                updated_lecture,

            "message":
                "Lecture updated successfully without changing its approved time."

        }), 200


    except Exception as e:

        return jsonify({

            "success":
                False,

            "message":
                str(e)

        }), 500
#==============================================
# REMOVE APPROVED LECTURE
# =========================================================
#
# Allowed:
#
#   1. Original designated mentor
#   2. Requesting mentor after approval
#
# =========================================================

@timetable_bp.route(
    "/lecture-request/remove",
    methods=["DELETE"]
)
def remove_approved_lecture():

    try:

        data = request.get_json(
            silent=True
        ) or {}


        req_id = str(
            data.get(
                "requestId",
                ""
            )
        ).strip()


        mentor_id = str(
            data.get(
                "mentorId",
                ""
            )
        ).strip()


        if not req_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "requestId required"

            }), 400


        if not mentor_id:

            return jsonify({

                "success":
                    False,

                "message":
                    "mentorId required"

            }), 400


        try:

            object_id = ObjectId(
                req_id
            )

        except Exception:

            return jsonify({

                "success":
                    False,

                "message":
                    "Invalid requestId"

            }), 400


        req = db.lecture_requests.find_one({

            "_id":
                object_id,

            "status":
                "approved"

        })


        if not req:

            return jsonify({

                "success":
                    False,

                "message":
                    "Approved lecture request not found."

            }), 404


        requester_id = str(
            req.get(
                "requesterMentorId",
                ""
            )
        ).strip()


        target_id = str(
            req.get(
                "targetMentorId",
                ""
            )
        ).strip()


        # -------------------------------------------------
        # AUTHORIZATION
        # -------------------------------------------------

        if mentor_id not in {

            requester_id,
            target_id

        }:

            return jsonify({

                "success":
                    False,

                "message":
                    "You are not authorized to remove this lecture."

            }), 403


        if req.get(
            "lectureRemoved",
            False
        ):

            return jsonify({

                "success":
                    False,

                "message":
                    "Lecture has already been removed."

            }), 409


        existing_class = str(
            req.get(
                "existingClass",
                req.get(
                    "className",
                    ""
                )
            )
        ).strip()


        day = str(
            req.get(
                "day",
                ""
            )
        ).strip()


        old_lecture = copy.deepcopy(
            req.get(
                "oldLecture",
                {}
            )
        )


        applied_lecture = copy.deepcopy(
            req.get(
                "appliedLecture",
                {}
            )
        )


        # Prefer the latest applied lecture
        lecture_identity = (
            applied_lecture
            if applied_lecture
            else old_lecture
        )


        normalize_lecture(
            lecture_identity
        )


        timetable = db.timetables.find_one({

            "className":
                existing_class

        })


        if not timetable:

            return jsonify({

                "success":
                    False,

                "message":
                    "Timetable not found."

            }), 404


        schedule = copy.deepcopy(

            timetable.get(
                "weeklySchedule",
                {}
            ).get(
                day,
                []
            )

        )


        if not isinstance(
            schedule,
            list
        ):

            schedule = []


        lecture_id = str(
            lecture_identity.get(
                "_id",
                ""
            )
        ).strip()


        start_mins = lecture_identity.get(
            "startTimeMins"
        )

        end_mins = lecture_identity.get(
            "endTimeMins"
        )

        subject = str(
            lecture_identity.get(
                "subject",
                ""
            )
        ).strip()


        faculty_ids = set(
            get_lecture_faculty_ids(
                lecture_identity
            )
        )


        remove_index = -1


        for index, raw in enumerate(
            schedule
        ):

            if not isinstance(
                raw,
                dict
            ):
                continue


            current = copy.deepcopy(
                raw
            )


            normalize_lecture(
                current
            )


            current_id = str(
                current.get(
                    "_id",
                    ""
                )
            ).strip()


            current_faculty_ids = set(
                get_lecture_faculty_ids(
                    current
                )
            )


            same_id = (

                lecture_id
                and
                current_id
                and
                lecture_id == current_id

            )


            same_identity = (

                current.get(
                    "startTimeMins"
                )
                ==
                start_mins

                and

                current.get(
                    "endTimeMins"
                )
                ==
                end_mins

                and

                str(
                    current.get(
                        "subject",
                        ""
                    )
                ).strip()
                ==
                subject

                and

                current_faculty_ids
                ==
                faculty_ids

            )


            if same_id or same_identity:

                remove_index = index

                break


        if remove_index < 0:

            return jsonify({

                "success":
                    False,

                "message":
                    "Lecture is no longer present in the timetable."

            }), 409


        # -------------------------------------------------
        # REMOVE EXACT LECTURE
        # -------------------------------------------------

        schedule.pop(
            remove_index
        )


        result = db.timetables.update_one(

            {
                "_id":
                    timetable["_id"]
            },

            {
                "$set": {

                    f"weeklySchedule.{day}":
                        schedule,

                    "updatedAt":
                        datetime.utcnow()

                }

            }

        )


        if result.matched_count != 1:

            return jsonify({

                "success":
                    False,

                "message":
                    "Timetable could not be updated."

            }), 500


        # -------------------------------------------------
        # Mark request
        # -------------------------------------------------

        db.lecture_requests.update_one(

            {
                "_id":
                    object_id
            },

            {
                "$set": {

                    "lectureRemoved":
                        True,

                    "removedBy":
                        mentor_id,

                    "removedAt":
                        datetime.utcnow(),

                    "lectureEditAllowed":
                        False,

                    "updatedAt":
                        datetime.utcnow()

                }

            }

        )


        return jsonify({

            "success":
                True,

            "timetableUpdated":
                True,

            "requestId":
                req_id,

            "message":
                "Lecture removed successfully."

        }), 200


    except Exception as e:

        return jsonify({

            "success":
                False,

            "message":
                str(e)

        }), 500




# =========================================================
# BASIC HELPERS
# =========================================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def serialize_doc(doc):
    if not doc:
        return None

    if "_id" in doc:
        doc["_id"] = str(doc["_id"])

    return doc


def serialize_many(items):
    return [serialize_doc(item) for item in items]


def clean_id_list(ids):
    """
    Safely normalize faculty IDs.

    Supports:
        ["M001", "M002"]
        [" M001 ", "M002"]
        "M001"
        None
    """

    if ids is None:
        return []

    if isinstance(ids, str):
        ids = [ids]

    if not isinstance(ids, list):
        return []

    cleaned = []

    for item in ids:

        if item is None:
            continue

        # If somehow a faculty object is supplied
        if isinstance(item, dict):
            item = (
                item.get("mentorId")
                or item.get("facultyId")
                or item.get("id")
            )

        if item is None:
            continue

        value = str(item).strip()

        if value and value not in cleaned:
            cleaned.append(value)

    return cleaned


def time_to_minutes(time_str):
    """
    Converts:
        08:00 AM -> 480
        04:30 PM -> 990

    Expected format:
        hh:mm AM/PM
    """

    if not time_str:
        raise ValueError(
            "Time is required. Expected format: 'hh:mm AM/PM'"
        )

    try:

        dt = datetime.strptime(
            str(time_str).strip(),
            "%I:%M %p"
        )

        return dt.hour * 60 + dt.minute

    except ValueError:

        raise ValueError(
            f"Invalid time format: {time_str}. "
            f"Expected format: 'hh:mm AM/PM'"
        )


def normalize_time_range(lecture):
    """
    Ensures every lecture has startTimeMins and endTimeMins.
    """

    if not isinstance(lecture, dict):
        raise ValueError("Invalid lecture data")

    start_time = lecture.get("startTime")
    end_time = lecture.get("endTime")

    if not start_time or not end_time:
        raise ValueError(
            "startTime and endTime are required"
        )

    start_mins = time_to_minutes(start_time)
    end_mins = time_to_minutes(end_time)

    if start_mins >= end_mins:
        raise ValueError(
            f"Invalid time range: {start_time} - {end_time}"
        )

    lecture["startTimeMins"] = start_mins
    lecture["endTimeMins"] = end_mins

    return lecture


def lecture_is_approved(lecture):
    """
    IMPORTANT BACKWARD COMPATIBILITY

    Old timetable records may not contain 'status'.

    Therefore:

        status == "rejected"  -> not active
        status == "pending"   -> not active
        status == "approved"  -> active
        status missing        -> ACTIVE / APPROVED

    This fixes the main issue where old occupied lectures
    were being ignored during conflict detection.
    """

    if not isinstance(lecture, dict):
        return False

    status = str(
        lecture.get("status", "approved")
    ).strip().lower()

    return status not in {
        "rejected",
        "pending",
        "cancelled",
        "canceled"
    }


def lectures_overlap(
    new_start,
    new_end,
    existing_start,
    existing_end
):
    """
    Correct overlap formula:

        newStart < existingEnd
        AND
        newEnd > existingStart
    """

    try:

        return (
            int(new_start) < int(existing_end)
            and
            int(new_end) > int(existing_start)
        )

    except (TypeError, ValueError):

        return False


# =========================================================
# FACULTY HELPERS
# =========================================================

def resolve_faculty(faculty_ids):

    faculty_ids = clean_id_list(faculty_ids)

    if not faculty_ids:
        return []

    mentors = list(
        db.mentors.find(
            {
                "mentorId": {
                    "$in": faculty_ids
                }
            },
            {
                "_id": 0,
                "mentorId": 1,
                "name": 1,
                "subject": 1,
                "branch": 1,
                "approvalMode": 1
            }
        )
    )

    mentor_map = {
        str(mentor.get("mentorId")).strip(): mentor
        for mentor in mentors
        if mentor.get("mentorId") is not None
    }

    resolved = []

    for faculty_id in faculty_ids:

        mentor = mentor_map.get(
            str(faculty_id).strip()
        )

        if mentor:

            resolved.append({
                "mentorId": mentor.get("mentorId"),
                "name": mentor.get(
                    "name",
                    "Unknown Faculty"
                ),
                "subject": mentor.get(
                    "subject",
                    ""
                ),
                "branch": mentor.get(
                    "branch",
                    ""
                ),
                "approvalMode": bool(
                    mentor.get(
                        "approvalMode",
                        False
                    )
                )
            })

        else:

            resolved.append({
                "mentorId": faculty_id,
                "name": "Unknown Faculty",
                "subject": "",
                "branch": "",
                "approvalMode": False
            })

    return resolved


def get_mentor_info(mentor_id):

    if not mentor_id:
        return {
            "mentorId": "",
            "name": "Unknown Faculty",
            "approvalMode": False
        }

    mentor = db.mentors.find_one(
        {
            "mentorId": str(mentor_id).strip()
        },
        {
            "_id": 0,
            "mentorId": 1,
            "name": 1,
            "approvalMode": 1,
            "subject": 1,
            "branch": 1
        }
    )

    if not mentor:

        return {
            "mentorId": str(mentor_id).strip(),
            "name": "Unknown Faculty",
            "approvalMode": False
        }

    return {
        "mentorId": mentor.get("mentorId"),
        "name": mentor.get(
            "name",
            "Unknown Faculty"
        ),
        "approvalMode": bool(
            mentor.get(
                "approvalMode",
                False
            )
        ),
        "subject": mentor.get(
            "subject",
            ""
        ),
        "branch": mentor.get(
            "branch",
            ""
        )
    }


def get_lecture_faculty_ids(lecture):

    if not isinstance(lecture, dict):
        return []

    faculty_ids = clean_id_list(
        lecture.get("facultyIds", [])
    )

    if faculty_ids:
        return faculty_ids

    faculty = lecture.get(
        "faculty",
        []
    )

    if isinstance(faculty, list):

        extracted = []

        for item in faculty:

            if isinstance(item, dict):

                mentor_id = (
                    item.get("mentorId")
                    or item.get("facultyId")
                    or item.get("id")
                )

                if mentor_id:
                    extracted.append(
                        mentor_id
                    )

        return clean_id_list(extracted)

    return []


def normalize_lecture(lecture):
    """
    Normalizes an existing/new lecture without destroying
    unknown frontend fields.
    """

    if not isinstance(lecture, dict):
        return lecture

    lecture["facultyIds"] = get_lecture_faculty_ids(
        lecture
    )

    # Calculate minutes if missing
    if (
        lecture.get("startTime")
        and lecture.get("endTime")
    ):

        try:

            lecture["startTimeMins"] = time_to_minutes(
                lecture["startTime"]
            )

            lecture["endTimeMins"] = time_to_minutes(
                lecture["endTime"]
            )

        except ValueError:
            pass

    # Old lectures without status are treated as approved
    if not lecture.get("status"):
        lecture["status"] = "approved"

    return lecture


def populate_timetable_faculties(timetable):

    if not timetable:
        return timetable

    weekly_schedule = timetable.get(
        "weeklySchedule",
        {}
    )

    if not isinstance(
        weekly_schedule,
        dict
    ):
        return timetable

    for day, schedule in weekly_schedule.items():

        if not isinstance(schedule, list):
            continue

        for lecture in schedule:

            if not isinstance(
                lecture,
                dict
            ):
                continue

            normalize_lecture(
                lecture
            )

            faculty_ids = get_lecture_faculty_ids(
                lecture
            )

            lecture["facultyIds"] = faculty_ids
            lecture["faculty"] = resolve_faculty(
                faculty_ids
            )

    return timetable


# =========================================================
# CONFLICT DETECTION
# =========================================================

def find_conflicts(
    faculty_ids,
    day,
    start_mins,
    end_mins,
    current_class=None,
    exclude_lecture=None
):
    """
    ROBUST FACULTY CONFLICT DETECTION.

    This function intentionally scans timetable documents
    instead of relying only on MongoDB $elemMatch.

    Why?

    Existing databases may contain:
        - lectures without status
        - facultyIds as strings
        - facultyIds as arrays
        - old timetable formats

    Therefore every candidate lecture is normalized
    and checked in Python.

    Conflict exists when:

        same faculty
        AND different class
        AND same day
        AND overlapping time
        AND lecture is active
    """

    conflicts = []

    faculty_ids = clean_id_list(
        faculty_ids
    )

    if not faculty_ids:
        return conflicts

    try:
        start_mins = int(start_mins)
        end_mins = int(end_mins)
    except (TypeError, ValueError):
        return conflicts

    if start_mins >= end_mins:
        return conflicts

    # -----------------------------------------------------
    # Scan all timetable documents
    # -----------------------------------------------------

    timetables = db.timetables.find({})

    for timetable in timetables:

        timetable_class = str(
            timetable.get(
                "className",
                ""
            )
        ).strip()

        # Same class is not a faculty conflict.
        # This prevents editing the same timetable from
        # conflicting with itself.
        if (
            current_class is not None
            and timetable_class == str(
                current_class
            ).strip()
        ):
            continue

        weekly_schedule = timetable.get(
            "weeklySchedule",
            {}
        )

        if not isinstance(
            weekly_schedule,
            dict
        ):
            continue

        day_schedule = weekly_schedule.get(
            day,
            []
        )

        if not isinstance(
            day_schedule,
            list
        ):
            continue

        for lecture in day_schedule:

            if not isinstance(
                lecture,
                dict
            ):
                continue

            lecture = normalize_lecture(
                lecture
            )

            # -------------------------------------------------
            # Ignore rejected/pending/cancelled lectures
            # -------------------------------------------------

            if not lecture_is_approved(
                lecture
            ):
                continue

            existing_faculty_ids = (
                get_lecture_faculty_ids(
                    lecture
                )
            )

            # -------------------------------------------------
            # Check faculty intersection
            # -------------------------------------------------

            matching_faculty = [
                fid
                for fid in faculty_ids
                if fid in existing_faculty_ids
            ]

            if not matching_faculty:
                continue

            existing_start = lecture.get(
                "startTimeMins"
            )

            existing_end = lecture.get(
                "endTimeMins"
            )

            # Old record may not have minute fields
            if (
                existing_start is None
                or existing_end is None
            ):

                try:

                    existing_start = time_to_minutes(
                        lecture.get(
                            "startTime"
                        )
                    )

                    existing_end = time_to_minutes(
                        lecture.get(
                            "endTime"
                        )
                    )

                except (ValueError, TypeError):

                    # Cannot reliably detect this record
                    continue

            # -------------------------------------------------
            # Overlap check
            # -------------------------------------------------

            if not lectures_overlap(
                start_mins,
                end_mins,
                existing_start,
                existing_end
            ):
                continue

            # -------------------------------------------------
            # Exclude the lecture being edited
            # -------------------------------------------------

            if exclude_lecture:

                same_id = (
                    exclude_lecture.get("_id")
                    and lecture.get("_id")
                    and
                    str(
                        exclude_lecture.get("_id")
                    )
                    ==
                    str(
                        lecture.get("_id")
                    )
                )

                same_time = (
                    exclude_lecture.get(
                        "startTimeMins"
                    ) == existing_start
                    and
                    exclude_lecture.get(
                        "endTimeMins"
                    ) == existing_end
                    and
                    set(
                        get_lecture_faculty_ids(
                            exclude_lecture
                        )
                    )
                    ==
                    set(
                        existing_faculty_ids
                    )
                    and
                    exclude_lecture.get(
                        "subject",
                        ""
                    )
                    ==
                    lecture.get(
                        "subject",
                        ""
                    )
                )

                if same_id or same_time:
                    continue

            # -------------------------------------------------
            # Get mentor info
            # -------------------------------------------------

            for fid in matching_faculty:

                mentor_info = get_mentor_info(
                    fid
                )

                conflicts.append({

                    "mentorId": fid,

                    "mentorName": mentor_info.get(
                        "name",
                        "Unknown Faculty"
                    ),

                    "approvalMode": bool(
                        mentor_info.get(
                            "approvalMode",
                            False
                        )
                    ),

                    "class": timetable_class,

                    "subject": lecture.get(
                        "subject",
                        ""
                    ),

                    "day": day,

                    "room": lecture.get(
                        "room",
                        ""
                    ),

                    "lecture": lecture,

                    "start": lecture.get(
                        "startTime"
                    ),

                    "end": lecture.get(
                        "endTime"
                    ),

                    "startTimeMins": existing_start,

                    "endTimeMins": existing_end
                })

    return conflicts


# =========================================================
# PENDING REQUEST DUPLICATE CHECK
# =========================================================

def lecture_request_exists(
    class_name,
    target_mentor_id,
    day,
    start_time,
    end_time=None
):
    """
    Prevent duplicate pending requests.

    Uses the important identity:
        class
        target faculty
        day
        start
        end
    """

    query = {
        "className": class_name,
        "targetMentorId": target_mentor_id,
        "day": day,
        "startTime": start_time,
        "status": "pending"
    }

    if end_time:
        query["endTime"] = end_time

    existing = db.lecture_requests.find_one(
        query
    )

    return bool(existing)


def create_lecture_request(
    requester_mentor_id,
    target_conflict,
    class_name,
    day,
    start_time,
    end_time,
    new_lecture
):
    """
    Creates one pending request only if it does not
    already exist.
    """

    target_mentor_id = target_conflict.get(
        "mentorId"
    )

    if lecture_request_exists(
        class_name,
        target_mentor_id,
        day,
        start_time,
        end_time
    ):
        return False

    mentor_info = get_mentor_info(
        target_mentor_id
    )

    req_doc = {

        "requesterMentorId":
            requester_mentor_id or "",

        "targetMentorId":
            target_mentor_id,

        "requesterName":
            "",

        "targetName":
            mentor_info.get(
                "name",
                target_conflict.get(
                    "mentorName",
                    "Unknown Faculty"
                )
            ),

        "className":
            class_name,

        "existingClass":
            target_conflict.get(
                "class",
                ""
            ),

        "day":
            day,

        "startTime":
            start_time,

        "endTime":
            end_time,

        "subject":
            new_lecture.get(
                "subject",
                ""
            ),

        "room":
            new_lecture.get(
                "room",
                ""
            ),

        "facultyIds":
            get_lecture_faculty_ids(
                new_lecture
            ),

        "newLecture":
            dict(new_lecture),

        "oldLecture":
            dict(
                target_conflict.get(
                    "lecture",
                    {}
                )
            ),

        "status":
            "pending",

        "createdAt":
            datetime.utcnow(),

        "updatedAt":
            datetime.utcnow()
    }

    db.lecture_requests.insert_one(
        req_doc
    )

    return True


# =========================================================
# MENTOR SEARCH
# =========================================================

@timetable_bp.route(
    "/mentor/search",
    methods=["GET"]
)
def search_mentors():

    query = request.args.get(
        "q",
        ""
    ).strip()

    if not query:

        return jsonify({
            "success": True,
            "mentors": []
        })

    try:

        regex = re.compile(
            re.escape(query),
            re.IGNORECASE
        )

        mentors = list(
            db.mentors.find(
                {
                    "$or": [
                        {
                            "mentorId": regex
                        },
                        {
                            "name": regex
                        }
                    ]
                },
                {
                    "_id": 0,
                    "mentorId": 1,
                    "name": 1,
                    "subject": 1,
                    "branch": 1,
                    "approvalMode": 1
                }
            ).limit(15)
        )

        return jsonify({
            "success": True,
            "mentors": mentors
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# APPROVAL MODE
# =========================================================

@timetable_bp.route(
    "/toggle-approval-mode",
    methods=["PUT"]
)
def toggle_approval_mode():

    try:

        data = request.get_json() or {}

        mentor_id = data.get(
            "mentorId"
        )

        approval_mode = data.get(
            "approvalMode"
        )

        if (
            not mentor_id
            or approval_mode is None
        ):

            return jsonify({
                "success": False,
                "message":
                    "mentorId and approvalMode required"
            }), 400

        result = db.mentors.update_one(
            {
                "mentorId":
                    str(mentor_id).strip()
            },
            {
                "$set": {
                    "approvalMode":
                        bool(approval_mode)
                }
            }
        )

        if result.matched_count == 0:

            return jsonify({
                "success": False,
                "message":
                    "Mentor not found"
            }), 404

        return jsonify({
            "success": True,
            "message":
                "Approval mode updated",
            "approvalMode":
                bool(approval_mode)
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@timetable_bp.route(
    "/approval-mode/<mentor_id>",
    methods=["GET"]
)
def get_approval_mode(
    mentor_id
):

    try:

        mentor = db.mentors.find_one(
            {
                "mentorId":
                    str(mentor_id).strip()
            }
        )

        if not mentor:

            return jsonify({
                "success": False,
                "message":
                    "Mentor not found"
            }), 404

        return jsonify({
            "success": True,
            "approvalMode":
                bool(
                    mentor.get(
                        "approvalMode",
                        False
                    )
                )
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# EXACT OCCUPANCY LOOKUP FOR MANUAL LECTURE REQUESTS
# =========================================================

def find_occupied_lecture_for_mentor(
    mentor_id,
    day,
    start_mins,
    end_mins,
    class_name=None
):
    """
    Find the ACTUAL active lecture occupied by mentor_id.

    IMPORTANT:
    This helper intentionally DOES NOT use find_conflicts(), because
    find_conflicts() excludes current_class. That is correct for normal
    timetable posting, but WRONG when a mentor clicks "Request Lecture"
    on a lecture that already exists inside the currently loaded class.

    If class_name is supplied, the lookup is restricted to that class.
    """
    mentor_id = str(mentor_id or "").strip()
    day = str(day or "").strip()

    if not mentor_id or not day:
        return None

    try:
        start_mins = int(start_mins)
        end_mins = int(end_mins)
    except (TypeError, ValueError):
        return None

    if start_mins >= end_mins:
        return None

    wanted_class = (
        str(class_name).strip()
        if class_name is not None
        else None
    )

    for timetable in db.timetables.find({}):
        timetable_class = str(
            timetable.get("className", "")
        ).strip()

        if wanted_class is not None and timetable_class != wanted_class:
            continue

        weekly = timetable.get("weeklySchedule", {})
        if not isinstance(weekly, dict):
            continue

        day_schedule = weekly.get(day, [])
        if not isinstance(day_schedule, list):
            continue

        for raw in day_schedule:
            if not isinstance(raw, dict):
                continue

            lecture = copy.deepcopy(raw)
            normalize_lecture(lecture)

            if not lecture_is_approved(lecture):
                continue

            faculty_ids = get_lecture_faculty_ids(lecture)
            if mentor_id not in faculty_ids:
                continue

            existing_start = lecture.get("startTimeMins")
            existing_end = lecture.get("endTimeMins")

            if existing_start is None or existing_end is None:
                continue

            if not lectures_overlap(
                start_mins,
                end_mins,
                existing_start,
                existing_end
            ):
                continue

            mentor_info = get_mentor_info(mentor_id)

            return {
                "mentorId": mentor_id,
                "mentorName": mentor_info.get(
                    "name", "Unknown Faculty"
                ),
                "approvalMode": bool(
                    mentor_info.get("approvalMode", False)
                ),
                "class": timetable_class,
                "subject": lecture.get("subject", ""),
                "day": day,
                "room": lecture.get("room", ""),
                "lecture": lecture,
                "start": lecture.get("startTime"),
                "end": lecture.get("endTime"),
                "startTimeMins": existing_start,
                "endTimeMins": existing_end
            }

    return None


# =========================================================
# SAME-CLASS TIME OVERLAP VALIDATION
# =========================================================

def validate_same_class_day_schedule(lectures, day):
    """
    Allows MULTIPLE lectures on the same day, but prevents two lectures
    in the same class from occupying overlapping time ranges.

    Example allowed:
        08:00-09:00
        09:00-10:00
        10:00-11:00

    Example rejected:
        08:00-09:00
        08:30-09:30
    """
    normalized = []

    for index, raw in enumerate(lectures or []):
        if not isinstance(raw, dict):
            continue

        lecture = copy.deepcopy(raw)
        normalize_time_range(lecture)
        normalized.append((index, lecture))

    for i in range(len(normalized)):
        index_a, a = normalized[i]

        for j in range(i + 1, len(normalized)):
            index_b, b = normalized[j]

            if lectures_overlap(
                a["startTimeMins"],
                a["endTimeMins"],
                b["startTimeMins"],
                b["endTimeMins"]
            ):
                return {
                    "day": day,
                    "firstIndex": index_a,
                    "secondIndex": index_b,
                    "firstStart": a.get("startTime"),
                    "firstEnd": a.get("endTime"),
                    "secondStart": b.get("startTime"),
                    "secondEnd": b.get("endTime")
                }

    return None


# =========================================================
# MANUAL LECTURE REQUEST
# =========================================================

@timetable_bp.route(
    "/request-lecture",
    methods=["POST"]
)
def request_lecture():

    try:

        data = request.get_json() or {}

        target_id = data.get(
            "targetMentorId"
        )

        day = data.get(
            "day"
        )

        start_time = data.get(
            "startTime"
        )

        end_time = data.get(
            "endTime"
        )

        class_name = data.get(
            "className"
        )

        if not all([
            target_id,
            day,
            start_time,
            end_time,
            class_name
        ]):

            return jsonify({
                "success": False,
                "message":
                    "targetMentorId, day, startTime, endTime and className are required"
            }), 400

        start_mins = time_to_minutes(
            start_time
        )

        end_mins = time_to_minutes(
            end_time
        )

        if start_mins >= end_mins:

            return jsonify({
                "success": False,
                "message":
                    "Invalid time range"
            }), 400

        # -------------------------------------------------
        # ALWAYS VERIFY THE EXACT REAL OCCUPANCY
        # -------------------------------------------------
        #
        # DO NOT use find_conflicts() here. That function intentionally
        # excludes the current class, while Request Lecture is clicked
        # ON a lecture that already exists in the current class.
        # -------------------------------------------------

        conflict = find_occupied_lecture_for_mentor(
            target_id,
            day,
            start_mins,
            end_mins,
            class_name=class_name
        )

        if not conflict:
            return jsonify({
                "success": False,
                "conflict": False,
                "requestCreated": False,
                "message":
                    "No occupied lecture found for this faculty at the selected time."
            }), 409

        # Only approval-mode faculty can receive approval requests.
        if conflict.get("approvalMode") is not True:
            return jsonify({
                "success": False,
                "conflict": True,
                "requestCreated": False,
                "message":
                    "Faculty is occupied, but approval mode is disabled."
            }), 409

        new_lecture = data.get(
            "newLecture",
            {}
        )

        if not isinstance(
            new_lecture,
            dict
        ):
            new_lecture = {}

        new_lecture.setdefault(
            "startTime",
            start_time
        )

        new_lecture.setdefault(
            "endTime",
            end_time
        )

        new_lecture.setdefault(
            "subject",
            data.get(
                "subject",
                ""
            )
        )

        new_lecture.setdefault(
            "room",
            data.get(
                "room",
                ""
            )
        )

        new_lecture["startTimeMins"] = (
            start_mins
        )

        new_lecture["endTimeMins"] = (
            end_mins
        )

        new_lecture["facultyIds"] = (
            clean_id_list(
                data.get(
                    "facultyIds",
                    [target_id]
                )
            )
        )

        created = create_lecture_request(
            data.get(
                "requesterMentorId",
                ""
            ),
            conflict,
            class_name,
            day,
            start_time,
            end_time,
            new_lecture
        )

        return jsonify({
            "success": True,
            "conflict": True,
            "requestCreated": created,
            "message":
                "Lecture request sent successfully.",
            "conflictFacultyName":
                conflict.get(
                    "mentorName"
                ),
            "conflictFacultyId":
                conflict.get(
                    "mentorId"
                ),
            "existingClass":
                conflict.get(
                    "class"
                ),
            "existingSubject":
                conflict.get(
                    "subject"
                ),
            "existingStart":
                conflict.get(
                    "start"
                ),
            "existingEnd":
                conflict.get(
                    "end"
                )
        })

    except ValueError as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# GET PENDING LECTURE REQUESTS
# =========================================================

@timetable_bp.route(
    "/lecture-requests/<mentor_id>",
    methods=["GET"]
)
def get_lecture_requests(
    mentor_id
):

    try:

        requests_data = list(
            db.lecture_requests.find(
                {
                    "$or": [
                        {
                            "targetMentorId":
                                str(mentor_id).strip()
                        },
                        {
                            "targetFaculty":
                                str(mentor_id).strip()
                        }
                    ],
                    "status":
                        "pending"
                }
            ).sort(
                "createdAt",
                -1
            )
        )

        return jsonify({
            "success": True,
            "requests":
                serialize_many(
                    requests_data
                )
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================================================
# APPROVE LECTURE REQUEST — APPROVAL ONLY
# =========================================================
#
# NEW WORKFLOW:
#   Approving a request DOES NOT change the timetable.
#   It only changes the request status to "approved".
#
# The requester later sees the approved request in
# "My Lecture Requests" and can click "Edit the Lecture Now".
# At that point the requester can edit SUBJECT + FACULTY,
# while DAY + START + END remain locked.
# =========================================================

@timetable_bp.route(
    "/lecture-request/approve",
    methods=["PUT"]
)
def approve_lecture_request():

    try:
        data = request.get_json(silent=True) or {}

        req_id = str(
            data.get("requestId", "")
        ).strip()

        approver_mentor_id = str(
            data.get("mentorId", "")
        ).strip()

        if not req_id:
            return jsonify({
                "success": False,
                "message": "requestId required"
            }), 400

        if not approver_mentor_id:
            return jsonify({
                "success": False,
                "message": "mentorId required"
            }), 400

        try:
            object_id = ObjectId(req_id)
        except Exception:
            return jsonify({
                "success": False,
                "message": "Invalid requestId"
            }), 400

        # Only the designated / occupied faculty can approve.
        req = db.lecture_requests.find_one({
            "_id": object_id,
            "status": "pending"
        })

        if not req:
            return jsonify({
                "success": False,
                "message": "Request not found or already processed"
            }), 404

        target_mentor_id = str(
            req.get("targetMentorId", "")
        ).strip()

        if target_mentor_id != approver_mentor_id:
            return jsonify({
                "success": False,
                "message": "Only the designated mentor can approve this lecture request."
            }), 403

        old_lecture = copy.deepcopy(
            req.get("oldLecture", {})
        )

        new_lecture = copy.deepcopy(
            req.get("newLecture", {})
        )

        if not isinstance(old_lecture, dict):
            old_lecture = {}

        if not isinstance(new_lecture, dict):
            new_lecture = {}

        if not old_lecture:
            return jsonify({
                "success": False,
                "message": "Request does not contain the original lecture snapshot."
            }), 409

        if not new_lecture:
            new_lecture = copy.deepcopy(old_lecture)

        normalize_lecture(old_lecture)
        normalize_lecture(new_lecture)

        requester_mentor_id = str(
            req.get("requesterMentorId", "")
        ).strip()

        requester_class = str(
            req.get("className", "")
        ).strip()

        existing_class = str(
            req.get("existingClass", requester_class)
        ).strip()

        day = str(
            req.get("day", "")
        ).strip()

        if not requester_mentor_id:
            return jsonify({
                "success": False,
                "message": "Requester mentor ID is missing."
            }), 409

        if not requester_class:
            return jsonify({
                "success": False,
                "message": "Request className is missing."
            }), 409

        if not existing_class:
            return jsonify({
                "success": False,
                "message": "Request existingClass is missing."
            }), 409

        if not day:
            return jsonify({
                "success": False,
                "message": "Request day is missing."
            }), 409

        # -----------------------------------------------------
        # LOCKED TIME SNAPSHOT
        # -----------------------------------------------------
        start_time = old_lecture.get("startTime")
        end_time = old_lecture.get("endTime")

        if not start_time or not end_time:
            return jsonify({
                "success": False,
                "message": "Original lecture time is missing."
            }), 409

        start_mins = time_to_minutes(start_time)
        end_mins = time_to_minutes(end_time)

        # -----------------------------------------------------
        # KEEP THE REQUESTED / APPROVED LECTURE DATA.
        # Do NOT write it into timetable here.
        # -----------------------------------------------------
        approved_lecture = copy.deepcopy(new_lecture)
        approved_lecture["startTime"] = start_time
        approved_lecture["endTime"] = end_time
        approved_lecture["startTimeMins"] = start_mins
        approved_lecture["endTimeMins"] = end_mins
        approved_lecture["status"] = "approved"
        approved_lecture["requestId"] = req_id

        if not get_lecture_faculty_ids(approved_lecture):
            approved_lecture["facultyIds"] = [target_mentor_id]

        approved_lecture["facultyIds"] = clean_id_list(
            approved_lecture.get("facultyIds", [])
        )
        approved_lecture["faculty"] = resolve_faculty(
            approved_lecture["facultyIds"]
        )

        now = datetime.utcnow()

        result = db.lecture_requests.update_one(
            {
                "_id": object_id,
                "status": "pending",
                "targetMentorId": target_mentor_id
            },
            {
                "$set": {
                    "status": "approved",
                    "approvedAt": now,
                    "processedAt": now,
                    "updatedAt": now,
                    "approvedLecture": copy.deepcopy(approved_lecture),
                    "lockedDay": day,
                    "lockedStartTime": start_time,
                    "lockedEndTime": end_time,
                    "editAllowed": True,
                    "editByMentorId": requester_mentor_id
                }
            }
        )

        if result.modified_count != 1:
            return jsonify({
                "success": False,
                "message": "Request could not be approved because its status changed."
            }), 409

        return jsonify({
            "success": True,
            "requestId": req_id,
            "requestStatusUpdated": True,
            "timetableUpdated": False,
            "status": "approved",
            "editAllowed": True,
            "lockedDay": day,
            "lockedStartTime": start_time,
            "lockedEndTime": end_time,
            "requesterMentorId": requester_mentor_id,
            "targetMentorId": target_mentor_id,
            "approvedLecture": approved_lecture,
            "message": (
                "Lecture request approved. Timetable was not changed yet. "
                "The requesting mentor can now edit the lecture."
            )
        }), 200

    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# MY LECTURE REQUESTS
# =========================================================
# Returns requests CREATED BY the logged-in mentor.
# Includes pending / approved / rejected / removed.
# =========================================================

@timetable_bp.route(
    "/lecture-requests/my/<mentor_id>",
    methods=["GET"]
)
def get_my_lecture_requests(mentor_id):

    try:
        mentor_id = str(mentor_id or "").strip()

        if not mentor_id:
            return jsonify({
                "success": False,
                "message": "mentorId required"
            }), 400

        requests_data = list(
            db.lecture_requests.find({
                "requesterMentorId": mentor_id
            }).sort(
                "createdAt", -1
            )
        )

        # Add a frontend-friendly snapshot without changing DB records.
        output = []

        for item in requests_data:
            doc = copy.deepcopy(item)
            status = str(
                doc.get("status", "pending")
            ).strip().lower()

            doc["status"] = status
            doc["canEdit"] = bool(
                status == "approved"
                and doc.get("editAllowed", True)
            )

            if status == "approved":
                approved_lecture = doc.get(
                    "approvedLecture",
                    doc.get("newLecture", {})
                )
                if isinstance(approved_lecture, dict):
                    doc["lockedStartTime"] = (
                        doc.get("lockedStartTime")
                        or approved_lecture.get("startTime")
                    )
                    doc["lockedEndTime"] = (
                        doc.get("lockedEndTime")
                        or approved_lecture.get("endTime")
                    )
                    doc["lockedDay"] = (
                        doc.get("lockedDay")
                        or doc.get("day")
                    )

            output.append(
                serialize_doc(doc)
            )

        return jsonify({
            "success": True,
            "mentorId": mentor_id,
            "count": len(output),
            "requests": output
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# EDIT APPROVED LECTURE + APPLY TO TIMETABLE
# =========================================================
#
# ONLY requesterMentorId can call this route.
# Time is ALWAYS taken from the approved request and cannot
# be changed by the frontend.
# Editable fields:
#   - subject
#   - facultyMentorId
#   - facultyIds (optional alias)
#
# On final save the backend checks faculty conflicts again.
# If there is any conflict, NOTHING is changed.
# =========================================================

@timetable_bp.route(
    "/lecture-request/edit-approved",
    methods=["PUT"]
)
def edit_approved_lecture():

    try:
        data = request.get_json(silent=True) or {}

        req_id = str(
            data.get("requestId", "")
        ).strip()

        requester_mentor_id = str(
            data.get("mentorId", data.get("requesterMentorId", ""))
        ).strip()

        if not req_id:
            return jsonify({
                "success": False,
                "message": "requestId required"
            }), 400

        if not requester_mentor_id:
            return jsonify({
                "success": False,
                "message": "mentorId required"
            }), 400

        try:
            object_id = ObjectId(req_id)
        except Exception:
            return jsonify({
                "success": False,
                "message": "Invalid requestId"
            }), 400

        req = db.lecture_requests.find_one({
            "_id": object_id,
            "status": "approved",
            "requesterMentorId": requester_mentor_id,
            "editAllowed": True
        })

        if not req:
            return jsonify({
                "success": False,
                "message": "Approved lecture request not found or you are not allowed to edit it."
            }), 404

        class_name = str(
            req.get("existingClass", req.get("className", ""))
        ).strip()

        day = str(
            req.get("lockedDay", req.get("day", ""))
        ).strip()

        old_lecture = copy.deepcopy(
            req.get("oldLecture", {})
        )

        if not isinstance(old_lecture, dict) or not old_lecture:
            return jsonify({
                "success": False,
                "message": "Original lecture snapshot is missing."
            }), 409

        normalize_lecture(old_lecture)

        # -----------------------------------------------------
        # LOCK TIME — NEVER ACCEPT EDITED TIME FROM FRONTEND
        # -----------------------------------------------------
        start_time = str(
            req.get("lockedStartTime", old_lecture.get("startTime", ""))
        ).strip()

        end_time = str(
            req.get("lockedEndTime", old_lecture.get("endTime", ""))
        ).strip()

        if not class_name or not day or not start_time or not end_time:
            return jsonify({
                "success": False,
                "message": "Approved request has incomplete locked lecture information."
            }), 409

        start_mins = time_to_minutes(start_time)
        end_mins = time_to_minutes(end_time)

        # -----------------------------------------------------
        # FACULTY INPUT
        # -----------------------------------------------------
        faculty_ids = clean_id_list(
            data.get("facultyIds", [])
        )

        faculty_mentor_id = str(
            data.get("facultyMentorId", "")
        ).strip()

        if faculty_mentor_id and faculty_mentor_id not in faculty_ids:
            faculty_ids.insert(0, faculty_mentor_id)

        if not faculty_ids:
            approved_lecture = req.get(
                "approvedLecture",
                req.get("newLecture", {})
            )
            faculty_ids = get_lecture_faculty_ids(
                approved_lecture
            )

        if not faculty_ids:
            # Safe fallback: the mentor who requested the lecture.
            faculty_ids = [requester_mentor_id]

        faculty_ids = clean_id_list(faculty_ids)

        # Verify every selected faculty exists.
        for fid in faculty_ids:
            mentor = db.mentors.find_one({
                "mentorId": str(fid).strip()
            })
            if not mentor:
                return jsonify({
                    "success": False,
                    "message": f"Faculty not found: {fid}"
                }), 404

        subject = data.get("subject")
        if subject is None:
            subject = req.get("approvedLecture", {}).get(
                "subject",
                req.get("newLecture", {}).get("subject", "")
            )

        subject = str(subject or "").strip()

        # -----------------------------------------------------
        # GET CURRENT TIMETABLE
        # -----------------------------------------------------
        timetable = db.timetables.find_one({
            "className": class_name
        })

        if not timetable:
            return jsonify({
                "success": False,
                "message": "Timetable for this class no longer exists."
            }), 409

        weekly = copy.deepcopy(
            timetable.get("weeklySchedule", {})
        )

        schedule = copy.deepcopy(
            weekly.get(day, [])
        )

        if not isinstance(schedule, list):
            schedule = []

        # -----------------------------------------------------
        # FIND THE EXACT ORIGINAL LECTURE
        # -----------------------------------------------------
        old_id = str(
            old_lecture.get("_id", "")
        ).strip()

        old_faculty_ids = set(
            get_lecture_faculty_ids(old_lecture)
        )

        old_subject = str(
            old_lecture.get("subject", "")
        ).strip()

        old_room = str(
            old_lecture.get("room", "")
        ).strip()

        old_index = -1
        current_lecture = None

        for index, raw in enumerate(schedule):
            if not isinstance(raw, dict):
                continue

            lecture = copy.deepcopy(raw)
            normalize_lecture(lecture)

            current_id = str(
                lecture.get("_id", "")
            ).strip()

            same_id = bool(
                old_id
                and current_id
                and old_id == current_id
            )

            current_faculty_ids = set(
                get_lecture_faculty_ids(lecture)
            )

            same_identity = (
                lecture.get("startTimeMins") == start_mins
                and lecture.get("endTimeMins") == end_mins
                and str(lecture.get("subject", "")).strip() == old_subject
                and str(lecture.get("room", "")).strip() == old_room
                and current_faculty_ids == old_faculty_ids
            )

            if same_id or same_identity:
                old_index = index
                current_lecture = lecture
                break

        if old_index < 0 or current_lecture is None:
            return jsonify({
                "success": False,
                "message": "The original lecture has changed or was removed. Please reload your timetable."
            }), 409

        # -----------------------------------------------------
        # FINAL FACULTY CONFLICT CHECK
        # -----------------------------------------------------
        # Same class is excluded by find_conflicts(), which is correct
        # because we are replacing the current lecture in this class.
        conflicts = find_conflicts(
            faculty_ids,
            day,
            start_mins,
            end_mins,
            class_name,
            exclude_lecture=current_lecture
        )

        if conflicts:
            return jsonify({
                "success": False,
                "conflict": True,
                "message": "Cannot update lecture because the selected faculty is occupied in another class at this time.",
                "conflicts": conflicts
            }), 409

        # -----------------------------------------------------
        # BUILD UPDATED LECTURE
        # -----------------------------------------------------
        updated_lecture = copy.deepcopy(current_lecture)

        updated_lecture["startTime"] = start_time
        updated_lecture["endTime"] = end_time
        updated_lecture["startTimeMins"] = start_mins
        updated_lecture["endTimeMins"] = end_mins
        updated_lecture["subject"] = subject
        updated_lecture["facultyIds"] = faculty_ids
        updated_lecture["faculty"] = resolve_faculty(faculty_ids)
        updated_lecture["status"] = "approved"
        updated_lecture["updatedFromRequestId"] = req_id
        updated_lecture["updatedAt"] = datetime.utcnow()
        updated_lecture["editedByMentorId"] = requester_mentor_id

        # Keep room and all unknown frontend fields from current lecture.
        schedule[old_index] = updated_lecture

        same_day_overlap = validate_same_class_day_schedule(
            schedule,
            day
        )

        if same_day_overlap:
            return jsonify({
                "success": False,
                "conflict": True,
                "message": (
                    f"Cannot update lecture because lectures overlap on {day}: "
                    f"{same_day_overlap['firstStart']} - {same_day_overlap['firstEnd']} "
                    f"overlaps with {same_day_overlap['secondStart']} - {same_day_overlap['secondEnd']}."
                )
            }), 409

        schedule.sort(
            key=lambda lecture: time_to_minutes(
                lecture.get("startTime", "12:00 AM")
            )
        )

        # -----------------------------------------------------
        # ATOMIC-STYLE DB UPDATE WITH REQUEST STILL APPROVED
        # -----------------------------------------------------
        now = datetime.utcnow()

        timetable_result = db.timetables.update_one(
            {
                "_id": timetable["_id"]
            },
            {
                "$set": {
                    f"weeklySchedule.{day}": schedule,
                    "updatedAt": now
                }
            }
        )

        if timetable_result.matched_count != 1:
            return jsonify({
                "success": False,
                "message": "Timetable update failed. Nothing was marked as completed."
            }), 500

        request_result = db.lecture_requests.update_one(
            {
                "_id": object_id,
                "status": "approved",
                "requesterMentorId": requester_mentor_id,
                "editAllowed": True
            },
            {
                "$set": {
                    "status": "approved",
                    "editAllowed": False,
                    "editedAt": now,
                    "updatedAt": now,
                    "appliedLecture": copy.deepcopy(updated_lecture),
                    "approvedLecture": copy.deepcopy(updated_lecture),
                    "timetableUpdated": True,
                    "timetableUpdatedAt": now
                }
            }
        )

        if request_result.modified_count != 1:
            # The timetable has already changed. Return explicit state rather
            # than silently pretending it did not.
            return jsonify({
                "success": False,
                "message": "Timetable was updated, but request metadata could not be finalized. Please inspect this request.",
                "timetableUpdated": True,
                "requestStatusUpdated": False
            }), 500

        return jsonify({
            "success": True,
            "requestId": req_id,
            "timetableUpdated": True,
            "requestStatusUpdated": True,
            "status": "approved",
            "className": class_name,
            "day": day,
            "lockedStartTime": start_time,
            "lockedEndTime": end_time,
            "appliedLecture": updated_lecture,
            "message": "Lecture updated successfully on the timetable without conflict."
        }), 200

    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# REMOVE APPROVED LECTURE — REQUESTING MENTOR
# =========================================================
# The designated mentor originally owned the lecture. After approval,
# the requesting mentor receives the ability to remove that exact lecture.
# =========================================================

@timetable_bp.route(
    "/lecture-request/remove-approved",
    methods=["DELETE"]
)
def remove_approved_lecture():

    try:
        data = request.get_json(silent=True) or {}

        req_id = str(
            data.get("requestId", "")
        ).strip()

        requester_mentor_id = str(
            data.get("mentorId", data.get("requesterMentorId", ""))
        ).strip()

        if not req_id or not requester_mentor_id:
            return jsonify({
                "success": False,
                "message": "requestId and mentorId are required"
            }), 400

        try:
            object_id = ObjectId(req_id)
        except Exception:
            return jsonify({
                "success": False,
                "message": "Invalid requestId"
            }), 400

        req = db.lecture_requests.find_one({
            "_id": object_id,
            "status": "approved",
            "requesterMentorId": requester_mentor_id
        })

        if not req:
            return jsonify({
                "success": False,
                "message": "Approved lecture request not found or you are not allowed to remove it."
            }), 404

        class_name = str(
            req.get("existingClass", req.get("className", ""))
        ).strip()

        day = str(
            req.get("lockedDay", req.get("day", ""))
        ).strip()

        old_lecture = copy.deepcopy(
            req.get("oldLecture", {})
        )

        if not class_name or not day or not isinstance(old_lecture, dict):
            return jsonify({
                "success": False,
                "message": "Approved request has incomplete lecture information."
            }), 409

        normalize_lecture(old_lecture)

        start_mins = time_to_minutes(
            old_lecture.get("startTime")
        )
        end_mins = time_to_minutes(
            old_lecture.get("endTime")
        )

        timetable = db.timetables.find_one({
            "className": class_name
        })

        if not timetable:
            return jsonify({
                "success": False,
                "message": "Timetable not found."
            }), 404

        weekly = copy.deepcopy(
            timetable.get("weeklySchedule", {})
        )

        schedule = weekly.get(day, [])
        if not isinstance(schedule, list):
            schedule = []

        old_id = str(
            old_lecture.get("_id", "")
        ).strip()

        approved_lecture = req.get(
            "approvedLecture",
            req.get("appliedLecture", req.get("newLecture", {}))
        )

        if not isinstance(approved_lecture, dict):
            approved_lecture = {}

        approved_faculty_ids = set(
            get_lecture_faculty_ids(approved_lecture)
        )

        current_index = -1

        for index, raw in enumerate(schedule):
            if not isinstance(raw, dict):
                continue

            lecture = copy.deepcopy(raw)
            normalize_lecture(lecture)

            current_id = str(
                lecture.get("_id", "")
            ).strip()

            current_faculty_ids = set(
                get_lecture_faculty_ids(lecture)
            )

            same_id = bool(
                old_id
                and current_id
                and old_id == current_id
            )

            # After the requester has edited the lecture, faculty/subject
            # may differ from oldLecture. Therefore match primarily by the
            # locked time + the request's approved faculty snapshot.
            same_approved_slot = (
                lecture.get("startTimeMins") == start_mins
                and lecture.get("endTimeMins") == end_mins
                and (
                    not approved_faculty_ids
                    or bool(current_faculty_ids.intersection(approved_faculty_ids))
                )
            )

            same_original_slot = (
                lecture.get("startTimeMins") == start_mins
                and lecture.get("endTimeMins") == end_mins
            )

            if same_id or same_approved_slot or same_original_slot:
                current_index = index
                break

        if current_index < 0:
            return jsonify({
                "success": False,
                "message": "Approved lecture is no longer present in the timetable."
            }), 409

        del schedule[current_index]

        now = datetime.utcnow()

        result = db.timetables.update_one(
            {
                "_id": timetable["_id"]
            },
            {
                "$set": {
                    f"weeklySchedule.{day}": schedule,
                    "updatedAt": now
                }
            }
        )

        if result.matched_count != 1:
            return jsonify({
                "success": False,
                "message": "Timetable removal failed."
            }), 500

        request_result = db.lecture_requests.update_one(
            {
                "_id": object_id,
                "status": "approved",
                "requesterMentorId": requester_mentor_id
            },
            {
                "$set": {
                    "status": "removed",
                    "editAllowed": False,
                    "removedAt": now,
                    "updatedAt": now,
                    "timetableUpdated": True,
                    "timetableUpdatedAt": now
                }
            }
        )

        if request_result.modified_count != 1:
            return jsonify({
                "success": False,
                "message": "Lecture was removed from timetable, but request status could not be finalized.",
                "timetableUpdated": True,
                "requestStatusUpdated": False
            }), 500

        return jsonify({
            "success": True,
            "requestId": req_id,
            "status": "removed",
            "timetableUpdated": True,
            "message": "Approved lecture removed from the timetable."
        }), 200

    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# OLD FRONTEND COMPATIBILITY
# =========================================================
@timetable_bp.route(
    "/lecture-request/approve-update",
    methods=["PUT"]
)
def approve_update_compat():
    return approve_lecture_request()


# =========================================================
# REJECT LECTURE REQUEST
# =========================================================

@timetable_bp.route(
    "/lecture-request/reject",
    methods=["PUT"]
)
def reject_lecture_request():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        req_id = str(
            data.get(
                "requestId",
                ""
            )
        ).strip()

        if not req_id:

            return jsonify({
                "success": False,
                "message":
                    "requestId required"
            }), 400

        # -------------------------------------------------
        # OBJECT ID
        # -------------------------------------------------

        try:

            object_id = ObjectId(
                req_id
            )

        except Exception:

            return jsonify({
                "success": False,
                "message":
                    "Invalid requestId"
            }), 400

        # -------------------------------------------------
        # ONLY PENDING REQUEST CAN BE REJECTED
        # -------------------------------------------------

        req = db.lecture_requests.find_one(
            {
                "_id":
                    object_id,
                "status":
                    "pending"
            }
        )

        if not req:

            return jsonify({
                "success": False,
                "message":
                    "Request not found or already processed"
            }), 404

        # -------------------------------------------------
        # REJECT
        # -------------------------------------------------

        result = (
            db.lecture_requests.update_one(
                {
                    "_id":
                        object_id,
                    "status":
                        "pending"
                },
                {
                    "$set": {
                        "status":
                            "rejected",

                        "updatedAt":
                            datetime.utcnow(),

                        "processedAt":
                            datetime.utcnow()
                    }
                }
            )
        )

        if result.modified_count != 1:

            return jsonify({
                "success": False,
                "message":
                    "Request could not be rejected because its status changed."
            }), 409

        return jsonify({

            "success":
                True,

            "requestId":
                req_id,

            "requestStatusUpdated":
                True,

            "message":
                "Lecture request rejected."

        }), 200

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
# =========================================================
# BUILD / VALIDATE LECTURE
# =========================================================

def prepare_lecture(
    lecture,
    class_name,
    day
):
    """
    Validate and normalize one lecture.
    """

    if not isinstance(
        lecture,
        dict
    ):
        raise ValueError(
            f"Invalid lecture in {day}"
        )

    start_time = lecture.get(
        "startTime"
    )

    end_time = lecture.get(
        "endTime"
    )

    if not start_time or not end_time:

        raise ValueError(
            f"startTime and endTime required for {day}"
        )

    start_mins = time_to_minutes(
        start_time
    )

    end_mins = time_to_minutes(
        end_time
    )

    if start_mins >= end_mins:

        raise ValueError(
            f"Invalid time range in {day}: "
            f"{start_time} - {end_time}"
        )

    faculty_ids = clean_id_list(
        lecture.get(
            "facultyIds",
            []
        )
    )

    lecture["facultyIds"] = (
        faculty_ids
    )

    lecture["startTimeMins"] = (
        start_mins
    )

    lecture["endTimeMins"] = (
        end_mins
    )

    return lecture


# =========================================================
# PROCESS ONE LECTURE
# =========================================================

def process_lecture_for_save(
    lecture,
    class_name,
    day,
    requester_mentor_id
):
    """
    Returns:

        {
            "save": True/False,
            "lecture": lecture,
            "conflicts": [...],
            "requestsCreated": [...]
        }

    IMPORTANT:

    Conflict is detected FIRST.

    Only after conflict detection do we decide:

        approvalMode=True
            -> do not save
            -> create request

        approvalMode=False
            -> save normally
    """

    lecture = prepare_lecture(
        lecture,
        class_name,
        day
    )

    faculty_ids = (
        lecture.get(
            "facultyIds",
            []
        )
    )

    conflicts = []

    if faculty_ids:

        conflicts = find_conflicts(
            faculty_ids,
            day,
            lecture["startTimeMins"],
            lecture["endTimeMins"],
            class_name
        )

    # -----------------------------------------------------
    # IMPORTANT:
    # EVERY conflict is detected.
    # -----------------------------------------------------

    approval_conflicts = [
        conflict
        for conflict in conflicts
        if conflict.get(
            "approvalMode"
        ) is True
    ]

    requests_created = []

    if approval_conflicts:

        # -------------------------------------------------
        # DO NOT SAVE LECTURE
        # SEND REQUEST
        # -------------------------------------------------

        for conflict in approval_conflicts:

            created = create_lecture_request(
                requester_mentor_id,
                conflict,
                class_name,
                day,
                lecture["startTime"],
                lecture["endTime"],
                lecture
            )

            if created:

                requests_created.append(
                    conflict
                )

        return {
            "save": False,
            "lecture": lecture,
            "conflicts": conflicts,
            "approvalConflicts":
                approval_conflicts,
            "requestsCreated":
                requests_created
        }

    # -----------------------------------------------------
    # Conflict exists but approval mode disabled
    #
    # Existing intended behavior:
    # save normally.
    # -----------------------------------------------------

    lecture["status"] = (
        "approved"
    )

    lecture["faculty"] = (
        resolve_faculty(
            faculty_ids
        )
    )

    return {
        "save": True,
        "lecture": lecture,
        "conflicts": conflicts,
        "approvalConflicts": [],
        "requestsCreated": []
    }


# =========================================================
# SET COMPLETE WEEKLY TIMETABLE
# =========================================================

@timetable_bp.route(
    "/set-weekly",
    methods=["POST"]
)
def set_weekly_timetable():

    try:

        data = request.get_json() or {}

        class_name = data.get(
            "className"
        )

        mentor_id = data.get(
            "mentorID"
        )

        weekly_schedule = data.get(
            "weeklySchedule"
        )

        if not class_name:

            return jsonify({
                "success": False,
                "message":
                    "className is required"
            }), 400

        if not isinstance(
            weekly_schedule,
            dict
        ):

            return jsonify({
                "success": False,
                "message":
                    "weeklySchedule must be an object"
            }), 400

        # -------------------------------------------------
        # Existing timetable
        # -------------------------------------------------

        existing_tt = db.timetables.find_one(
            {
                "className":
                    class_name
            }
        )

        if existing_tt:

            existing_weekly = existing_tt.get(
                "weeklySchedule",
                {}
            )

        else:

            existing_weekly = {}

        final_schedule = dict(
            existing_weekly
        )

        has_conflict = False
        requests_created = []
        conflict_info = []

        # -------------------------------------------------
        # Process every submitted day
        # -------------------------------------------------

        for day, lectures in weekly_schedule.items():

            if not isinstance(
                lectures,
                list
            ):

                return jsonify({
                    "success": False,
                    "message":
                        f"Schedule for {day} must be a list"
                }), 400

            # Multiple lectures on the same day are fully supported.
            # Only overlapping time ranges inside the SAME class are rejected.
            same_day_overlap = validate_same_class_day_schedule(
                lectures,
                day
            )

            if same_day_overlap:
                return jsonify({
                    "success": False,
                    "message": (
                        f"Overlapping lectures are not allowed on {day}: "
                        f"{same_day_overlap['firstStart']} - "
                        f"{same_day_overlap['firstEnd']} overlaps with "
                        f"{same_day_overlap['secondStart']} - "
                        f"{same_day_overlap['secondEnd']}."
                    ),
                    "day": day,
                    "firstIndex": same_day_overlap["firstIndex"],
                    "secondIndex": same_day_overlap["secondIndex"]
                }), 409

            valid_day_schedule = []

            for lecture in lectures:

                result = process_lecture_for_save(
                    lecture,
                    class_name,
                    day,
                    mentor_id
                )

                if result["save"]:

                    valid_day_schedule.append(
                        result["lecture"]
                    )

                else:

                    has_conflict = True

                    # -------------------------------------------------
                    # IMPORTANT:
                    # Existing lectures are preserved.
                    #
                    # We do NOT simply delete them because a conflict
                    # exists.
                    # -------------------------------------------------

                    conflict_info.extend(
                        result[
                            "approvalConflicts"
                        ]
                    )

                    requests_created.extend(
                        result[
                            "requestsCreated"
                        ]
                    )

            # -------------------------------------------------
            # For set-weekly, replace ONLY this submitted day.
            # Other existing days remain untouched.
            #
            # If conflicts occurred, only successfully approved
            # lectures are included from submitted data.
            # -------------------------------------------------

            final_schedule[day] = (
                valid_day_schedule
            )

        timetable_data = {

            "className":
                class_name,

            "mentorID":
                mentor_id,

            "weeklySchedule":
                final_schedule,

            "updatedAt":
                datetime.utcnow()
        }

        if existing_tt:

            db.timetables.update_one(
                {
                    "className":
                        class_name
                },
                {
                    "$set":
                        timetable_data
                }
            )

        else:

            timetable_data[
                "createdAt"
            ] = datetime.utcnow()

            db.timetables.insert_one(
                timetable_data
            )

        # -------------------------------------------------
        # Response
        # -------------------------------------------------

        if has_conflict:

            first_conflict = (
                conflict_info[0]
                if conflict_info
                else {}
            )

            return jsonify({

                "success":
                    True,

                "conflict":
                    True,

                "requestCreated":
                    len(
                        requests_created
                    ) > 0,

                "requestsCreatedCount":
                    len(
                        requests_created
                    ),

                "conflictsFound":
                    len(
                        conflict_info
                    ),

                "conflictFacultyName":
                    first_conflict.get(
                        "mentorName"
                    ),

                "conflictFacultyId":
                    first_conflict.get(
                        "mentorId"
                    ),

                "existingClass":
                    first_conflict.get(
                        "class"
                    ),

                "existingSubject":
                    first_conflict.get(
                        "subject"
                    ),

                "existingStart":
                    first_conflict.get(
                        "start"
                    ),

                "existingEnd":
                    first_conflict.get(
                        "end"
                    ),

                "message":
                    "Timetable saved with conflict handling. Occupied faculty lectures requiring approval were not posted and lecture requests were created."
            }), 200

        return jsonify({

            "success":
                True,

            "conflict":
                False,

            "requestCreated":
                False,

            "message":
                "Weekly timetable saved successfully."
        }), 200

    except ValueError as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# GET CLASS TIMETABLE
# =========================================================

@timetable_bp.route(
    "/class/<class_name>",
    methods=["GET"]
)
def get_class_timetable(
    class_name
):

    try:

        timetable = db.timetables.find_one(
            {
                "className":
                    class_name
            }
        )

        if not timetable:

            return jsonify({
                "success": False,
                "message":
                    "Timetable not found"
            }), 404

        populated = (
            populate_timetable_faculties(
                timetable
            )
        )

        return jsonify({
            "success": True,
            "timetable":
                serialize_doc(
                    populated
                )
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# GET DAY TIMETABLE
# =========================================================

@timetable_bp.route(
    "/class/<class_name>/<day>",
    methods=["GET"]
)
def get_day_timetable(
    class_name,
    day
):

    try:

        timetable = db.timetables.find_one(
            {
                "className":
                    class_name
            }
        )

        if not timetable:

            return jsonify({
                "success": False,
                "message":
                    "Timetable not found"
            }), 404

        populated = (
            populate_timetable_faculties(
                timetable
            )
        )

        schedule = (
            populated
            .get(
                "weeklySchedule",
                {}
            )
            .get(
                day,
                []
            )
        )

        return jsonify({

            "success":
                True,

            "className":
                class_name,

            "day":
                day,

            "schedule":
                schedule
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# UPDATE SINGLE DAY
# =========================================================

@timetable_bp.route(
    "/update-day",
    methods=["PUT"]
)
def update_single_day():

    try:

        data = request.get_json() or {}

        class_name = data.get(
            "className"
        )

        day = data.get(
            "day"
        )

        schedule = data.get(
            "schedule"
        )

        mentor_id = data.get(
            "mentorID",
            ""
        )

        if not class_name or not day:

            return jsonify({
                "success": False,
                "message":
                    "className and day are required"
            }), 400

        if not isinstance(
            schedule,
            list
        ):

            return jsonify({
                "success": False,
                "message":
                    "schedule must be a list"
            }), 400

        # Multiple lectures on the same day are allowed, but their time
        # ranges cannot overlap within the same class.
        same_day_overlap = validate_same_class_day_schedule(
            schedule,
            day
        )

        if same_day_overlap:
            return jsonify({
                "success": False,
                "message": (
                    f"Overlapping lectures are not allowed on {day}: "
                    f"{same_day_overlap['firstStart']} - "
                    f"{same_day_overlap['firstEnd']} overlaps with "
                    f"{same_day_overlap['secondStart']} - "
                    f"{same_day_overlap['secondEnd']}."
                ),
                "day": day,
                "firstIndex": same_day_overlap["firstIndex"],
                "secondIndex": same_day_overlap["secondIndex"]
            }), 409

        valid_schedule = []

        conflicts_found = []
        requests_created = []

        # -------------------------------------------------
        # Process every submitted lecture
        # -------------------------------------------------

        for lecture in schedule:

            result = process_lecture_for_save(
                lecture,
                class_name,
                day,
                mentor_id
            )

            if result["save"]:

                valid_schedule.append(
                    result["lecture"]
                )

            else:

                conflicts_found.extend(
                    result[
                        "approvalConflicts"
                    ]
                )

                requests_created.extend(
                    result[
                        "requestsCreated"
                    ]
                )

        # -------------------------------------------------
        # IMPORTANT:
        # The submitted day is replaced by the valid
        # non-conflicting lectures.
        #
        # Frontend should send the complete edited day.
        # -------------------------------------------------

        result = db.timetables.update_one(
            {
                "className":
                    class_name
            },
            {
                "$set": {
                    f"weeklySchedule.{day}":
                        valid_schedule,

                    "updatedAt":
                        datetime.utcnow()
                }
            }
        )

        if result.matched_count == 0:

            db.timetables.insert_one({

                "className":
                    class_name,

                "weeklySchedule": {
                    day:
                        valid_schedule
                },

                "createdAt":
                    datetime.utcnow(),

                "updatedAt":
                    datetime.utcnow()
            })

        if conflicts_found:

            first_conflict = (
                conflicts_found[0]
            )

            return jsonify({

                "success":
                    True,

                "conflict":
                    True,

                "requestCreated":
                    len(
                        requests_created
                    ) > 0,

                "requestsCreatedCount":
                    len(
                        requests_created
                    ),

                "conflictsFound":
                    len(
                        conflicts_found
                    ),

                "conflictFacultyName":
                    first_conflict.get(
                        "mentorName"
                    ),

                "conflictFacultyId":
                    first_conflict.get(
                        "mentorId"
                    ),

                "existingClass":
                    first_conflict.get(
                        "class"
                    ),

                "existingSubject":
                    first_conflict.get(
                        "subject"
                    ),

                "existingStart":
                    first_conflict.get(
                        "start"
                    ),

                "existingEnd":
                    first_conflict.get(
                        "end"
                    ),

                "message":
                    f"{day} timetable updated with conflict handling. Approval requests were sent for occupied faculty."
            }), 200

        return jsonify({

            "success":
                True,

            "conflict":
                False,

            "requestCreated":
                False,

            "message":
                f"{day} timetable updated successfully."
        }), 200

    except ValueError as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# DELETE COMPLETE TIMETABLE
# =========================================================

@timetable_bp.route(
    "/delete/<class_name>",
    methods=["DELETE"]
)
def delete_timetable(
    class_name
):

    try:

        result = db.timetables.delete_one(
            {
                "className":
                    class_name
            }
        )

        if result.deleted_count == 0:

            return jsonify({
                "success": False,
                "message":
                    "Timetable not found"
            }), 404

        return jsonify({
            "success": True,
            "message":
                "Timetable deleted successfully"
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# GET ALL TIMETABLES
# =========================================================

@timetable_bp.route(
    "/all",
    methods=["GET"]
)
def get_all_timetables():

    try:

        timetables = list(
            db.timetables.find({})
        )

        result = []

        for timetable in timetables:

            populated = (
                populate_timetable_faculties(
                    timetable
                )
            )

            result.append(
                serialize_doc(
                    populated
                )
            )

        return jsonify({

            "success":
                True,

            "count":
                len(result),

            "timetables":
                result
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# UPLOAD TIMETABLE PDF
# =========================================================

@timetable_bp.route(
    "/upload-pdf",
    methods=["POST"]
)
def upload_timetable_pdf():

    try:

        if "file" not in request.files:

            return jsonify({
                "success": False,
                "message":
                    "No file uploaded"
            }), 400

        file = request.files[
            "file"
        ]

        class_name = request.form.get(
            "className"
        )

        uploaded_by = request.form.get(
            "uploadedBy"
        )

        if not class_name:

            return jsonify({
                "success": False,
                "message":
                    "className is required"
            }), 400

        if not file.filename:

            return jsonify({
                "success": False,
                "message":
                    "No selected file"
            }), 400

        if not allowed_file(
            file.filename
        ):

            return jsonify({
                "success": False,
                "message":
                    "Only PDF files allowed"
            }), 400

        filename = secure_filename(
            file.filename
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d%H%M%S"
        )

        final_filename = (
            f"{class_name}_"
            f"{timestamp}_"
            f"{filename}"
        )

        file_path = os.path.join(
            UPLOAD_FOLDER,
            final_filename
        )

        file.save(
            file_path
        )

        pdf_data = {

            "className":
                class_name,

            "uploadedBy":
                uploaded_by,

            "fileName":
                final_filename,

            "filePath":
                file_path,

            "uploadedAt":
                datetime.utcnow()
        }

        db.timetable_pdfs.insert_one(
            pdf_data
        )

        return jsonify({

            "success":
                True,

            "message":
                "PDF uploaded successfully",

            "fileName":
                final_filename,

            "filePath":
                file_path
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# GET TIMETABLE PDFs
# =========================================================

@timetable_bp.route(
    "/pdfs/<class_name>",
    methods=["GET"]
)
def get_timetable_pdfs(
    class_name
):

    try:

        pdfs = list(
            db.timetable_pdfs.find(
                {
                    "className":
                        class_name
                }
            ).sort(
                "uploadedAt",
                -1
            )
        )

        return jsonify({

            "success":
                True,

            "pdfs":
                serialize_many(
                    pdfs
                )
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# ADD HOLIDAY
# =========================================================

@timetable_bp.route(
    "/holiday/add",
    methods=["POST"]
)
def add_holiday():

    try:

        data = request.get_json() or {}

        if (
            not data.get("date")
            or not data.get("title")
        ):

            return jsonify({
                "success": False,
                "message":
                    "date and title are required"
            }), 400

        holiday_data = {

            "date":
                data.get("date"),

            "title":
                data.get("title"),

            "description":
                data.get(
                    "description",
                    ""
                ),

            "createdAt":
                datetime.utcnow()
        }

        db.holidays.insert_one(
            holiday_data
        )

        return jsonify({

            "success":
                True,

            "message":
                "Holiday added successfully"
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# GET HOLIDAYS
# =========================================================

@timetable_bp.route(
    "/holidays",
    methods=["GET"]
)
def get_holidays():

    try:

        holidays = list(
            db.holidays.find({})
            .sort(
                "date",
                1
            )
        )

        return jsonify({

            "success":
                True,

            "holidays":
                serialize_many(
                    holidays
                )
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# VERIFY CONFLICT
# =========================================================

@timetable_bp.route(
    "/verify-conflict",
    methods=["POST"]
)
def verify_conflict():

    try:

        data = request.get_json() or {}

        class_name = data.get(
            "existingClass"
        )

        day = data.get(
            "day"
        )

        mentor_id = data.get(
            "mentorId"
        )

        start_mins = data.get(
            "startTimeMins"
        )

        end_mins = data.get(
            "endTimeMins"
        )

        start_time = data.get(
            "startTime"
        )

        end_time = data.get(
            "endTime"
        )

        if not class_name:
            return jsonify({
                "success": False,
                "message":
                    "existingClass is required"
            }), 400

        if not day:
            return jsonify({
                "success": False,
                "message":
                    "day is required"
            }), 400

        if not mentor_id:
            return jsonify({
                "success": False,
                "message":
                    "mentorId is required"
            }), 400

        # -------------------------------------------------
        # Convert times if minute values were not provided
        # -------------------------------------------------

        if start_mins is None and start_time:

            start_mins = time_to_minutes(
                start_time
            )

        if end_mins is None and end_time:

            end_mins = time_to_minutes(
                end_time
            )

        if start_mins is None or end_mins is None:

            return jsonify({
                "success": False,
                "message":
                    "startTimeMins and endTimeMins are required"
            }), 400

        try:

            start_mins = int(
                start_mins
            )

            end_mins = int(
                end_mins
            )

        except (TypeError, ValueError):

            return jsonify({
                "success": False,
                "message":
                    "Invalid time values"
            }), 400

        if start_mins >= end_mins:

            return jsonify({
                "success": False,
                "message":
                    "Invalid time range"
            }), 400

        # -------------------------------------------------
        # Find the EXACT occupied lecture in this class.
        # Do not use find_conflicts() because it excludes current_class.
        # -------------------------------------------------

        conflict = find_occupied_lecture_for_mentor(
            mentor_id,
            day,
            start_mins,
            end_mins,
            class_name=class_name
        )

        if not conflict:

            return jsonify({

                "success":
                    True,

                "exists":
                    False,

                "message":
                    "No occupied lecture found."
            })

        return jsonify({

            "success":
                True,

            "exists":
                True,

            "conflict":
                True,

            "approvalMode":
                bool(
                    conflict.get(
                        "approvalMode",
                        False
                    )
                ),

            "mentorId":
                conflict.get(
                    "mentorId"
                ),

            "mentorName":
                conflict.get(
                    "mentorName"
                ),

            "existingClass":
                conflict.get(
                    "class"
                ),

            "existingSubject":
                conflict.get(
                    "subject"
                ),

            "existingStart":
                conflict.get(
                    "start"
                ),

            "existingEnd":
                conflict.get(
                    "end"
                ),

            "oldLecture":
                conflict.get(
                    "lecture"
                )
        })

    except ValueError as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500