from flask import Blueprint, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from bson import ObjectId
from datetime import datetime
import os
import re

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
        # ALWAYS VERIFY REAL OCCUPANCY
        # -------------------------------------------------

        conflicts = find_conflicts(
            [target_id],
            day,
            start_mins,
            end_mins,
            class_name
        )

        if not conflicts:

            return jsonify({
                "success": False,
                "conflict": False,
                "requestCreated": False,
                "message":
                    "No occupied lecture found for this faculty at the selected time."
            }), 400

        # Only approval-mode faculty can receive approval requests
        approval_conflicts = [
            c for c in conflicts
            if c.get("approvalMode") is True
        ]

        if not approval_conflicts:

            return jsonify({
                "success": False,
                "conflict": True,
                "requestCreated": False,
                "message":
                    "Faculty is occupied, but approval mode is disabled."
            }), 409

        conflict = approval_conflicts[0]

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
# APPROVE LECTURE REQUEST
# =========================================================

@timetable_bp.route(
    "/lecture-request/approve",
    methods=["PUT"]
)
def approve_lecture_request():
    """Approve by REPLACING the exact old lecture, never appending a duplicate."""
    try:
        data = request.get_json(silent=True) or {}
        req_id = str(data.get("requestId", "")).strip()
        if not req_id:
            return jsonify({"success": False, "message": "requestId required"}), 400
        try:
            object_id = ObjectId(req_id)
        except Exception:
            return jsonify({"success": False, "message": "Invalid requestId"}), 400

        req = db.lecture_requests.find_one({"_id": object_id, "status": "pending"})
        if not req:
            return jsonify({"success": False, "message": "Request not found or already processed"}), 404

        class_name = req.get("className")
        day = req.get("day")
        old_lecture = normalize_lecture(req.get("oldLecture") or {})
        new_lecture = normalize_lecture(req.get("newLecture") or {})

        if not class_name or not day or not new_lecture:
            return jsonify({"success": False, "message": "Request has incomplete lecture data"}), 400

        tt = db.timetables.find_one({"className": class_name})
        if not tt:
            return jsonify({"success": False, "message": "Destination class timetable not found"}), 404

        schedule = copy.deepcopy(tt.get("weeklySchedule", {}).get(day, []))

        old_id = str(old_lecture.get("_id", "")).strip()
        old_start = old_lecture.get("startTime")
        old_end = old_lecture.get("endTime")
        old_subject = old_lecture.get("subject", "")
        old_room = old_lecture.get("room", "")
        old_faculty = set(get_lecture_faculty_ids(old_lecture))

        index = -1
        for i, raw in enumerate(schedule):
            lec = normalize_lecture(raw)
            same_id = bool(old_id and str(lec.get("_id", "")).strip() == old_id)
            same_identity = (
                lec.get("startTime") == old_start and
                lec.get("endTime") == old_end and
                lec.get("subject", "") == old_subject and
                lec.get("room", "") == old_room and
                set(get_lecture_faculty_ids(lec)) == old_faculty
            )
            if same_id or same_identity:
                index = i
                break

        if index < 0:
            return jsonify({
                "success": False,
                "message": "Exact existing lecture was not found; no timetable change was made."
            }), 409

        # IMPORTANT: check other classes before changing anything.
        conflicts = find_conflicts(
            get_lecture_faculty_ids(new_lecture),
            day,
            new_lecture.get("startTimeMins"),
            new_lecture.get("endTimeMins"),
            class_name
        )
        if conflicts:
            return jsonify({
                "success": False,
                "message": "Cannot approve because the requested faculty is now occupied elsewhere.",
                "conflicts": conflicts
            }), 409

        new_lecture["status"] = "approved"
        new_lecture["facultyIds"] = get_lecture_faculty_ids(new_lecture)
        new_lecture["faculty"] = resolve_faculty(new_lecture["facultyIds"])
        new_lecture["approvedFromRequestId"] = req_id
        new_lecture["approvedAt"] = datetime.utcnow()

        # THE FIX: same class => replace exactly one array element.
        schedule[index] = new_lecture
        schedule.sort(key=lambda x: time_to_minutes(x.get("startTime", "12:00 AM")))

        result = db.timetables.update_one(
            {"_id": tt["_id"]},
            {"$set": {
                f"weeklySchedule.{day}": schedule,
                "updatedAt": datetime.utcnow()
            }}
        )
        if result.matched_count != 1:
            return jsonify({"success": False, "message": "Timetable update failed"}), 500

        db.lecture_requests.update_one(
            {"_id": object_id, "status": "pending"},
            {"$set": {
                "status": "approved",
                "processedAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
                "appliedLecture": copy.deepcopy(new_lecture)
            }}
        )

        return jsonify({
            "success": True,
            "requestId": req_id,
            "requestStatusUpdated": True,
            "timetableUpdated": True,
            "className": class_name,
            "day": day,
            "replacedOldLecture": old_lecture,
            "appliedLecture": new_lecture,
            "message": "Lecture approved and the existing lecture was replaced without duplicates."
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# Old frontend compatibility: both URLs use the same atomic replacement logic.
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

        data = request.get_json() or {}

        req_id = data.get(
            "requestId"
        )

        if not req_id:

            return jsonify({
                "success": False,
                "message":
                    "requestId required"
            }), 400

        try:

            object_id = ObjectId(
                str(req_id)
            )

        except Exception:

            return jsonify({
                "success": False,
                "message":
                    "Invalid requestId"
            }), 400

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

        db.lecture_requests.update_one(
            {
                "_id":
                    object_id
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

        return jsonify({
            "success": True,
            "message":
                "Lecture request rejected."
        })

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
        # Use SAME robust conflict engine
        # -------------------------------------------------

        conflicts = find_conflicts(
            [mentor_id],
            day,
            start_mins,
            end_mins,
            current_class=class_name
        )

        if not conflicts:

            return jsonify({

                "success":
                    True,

                "exists":
                    False,

                "message":
                    "No occupied lecture found."
            })

        conflict = conflicts[0]

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