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
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
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
    Normalize faculty IDs.

    Supports:
        ["M001", "M002"]
        [" M001 ", "M002"]
        "M001"
        [{"mentorId": "M001"}]
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
    Convert:
        08:00 AM -> 480
        04:30 PM -> 990

    Expected:
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
# LECTURE STATUS
# =========================================================

def lecture_is_active(lecture):
    """
    Backward compatible.

    status missing -> active
    approved        -> active
    pending         -> inactive
    rejected        -> inactive
    cancelled       -> inactive
    """

    if not isinstance(lecture, dict):
        return False

    status = str(
        lecture.get(
            "status",
            "approved"
        )
    ).strip().lower()

    return status not in {
        "pending",
        "rejected",
        "cancelled",
        "canceled"
    }


# =========================================================
# FACULTY HELPERS
# =========================================================

def get_mentor_info(mentor_id):

    if not mentor_id:
        return {
            "mentorId": "",
            "name": "Unknown Faculty",
            "approvalMode": False,
            "subject": "",
            "branch": ""
        }

    mentor_id = str(
        mentor_id
    ).strip()

    mentor = db.mentors.find_one(
        {
            "mentorId": mentor_id
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
            "mentorId": mentor_id,
            "name": "Unknown Faculty",
            "approvalMode": False,
            "subject": "",
            "branch": ""
        }

    return {
        "mentorId": mentor.get(
            "mentorId"
        ),
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


def resolve_faculty(faculty_ids):

    faculty_ids = clean_id_list(
        faculty_ids
    )

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
        str(
            mentor.get(
                "mentorId"
            )
        ).strip(): mentor
        for mentor in mentors
        if mentor.get(
            "mentorId"
        ) is not None
    }

    resolved = []

    for faculty_id in faculty_ids:

        mentor = mentor_map.get(
            str(
                faculty_id
            ).strip()
        )

        if mentor:

            resolved.append({
                "mentorId":
                    mentor.get(
                        "mentorId"
                    ),

                "name":
                    mentor.get(
                        "name",
                        "Unknown Faculty"
                    ),

                "subject":
                    mentor.get(
                        "subject",
                        ""
                    ),

                "branch":
                    mentor.get(
                        "branch",
                        ""
                    ),

                "approvalMode":
                    bool(
                        mentor.get(
                            "approvalMode",
                            False
                        )
                    )
            })

        else:

            resolved.append({
                "mentorId":
                    faculty_id,

                "name":
                    "Unknown Faculty",

                "subject":
                    "",

                "branch":
                    "",

                "approvalMode":
                    False
            })

    return resolved


def get_lecture_faculty_ids(lecture):

    if not isinstance(
        lecture,
        dict
    ):
        return []

    faculty_ids = clean_id_list(
        lecture.get(
            "facultyIds",
            []
        )
    )

    if faculty_ids:
        return faculty_ids

    faculty = lecture.get(
        "faculty",
        []
    )

    if isinstance(
        faculty,
        list
    ):

        extracted = []

        for item in faculty:

            if not isinstance(
                item,
                dict
            ):
                continue

            mentor_id = (
                item.get(
                    "mentorId"
                )
                or
                item.get(
                    "facultyId"
                )
                or
                item.get(
                    "id"
                )
            )

            if mentor_id:
                extracted.append(
                    mentor_id
                )

        return clean_id_list(
            extracted
        )

    return []


# =========================================================
# LECTURE NORMALIZATION
# =========================================================

def normalize_lecture(lecture):

    if not isinstance(
        lecture,
        dict
    ):
        return lecture

    lecture["facultyIds"] = (
        get_lecture_faculty_ids(
            lecture
        )
    )

    start_time = lecture.get(
        "startTime"
    )

    end_time = lecture.get(
        "endTime"
    )

    if start_time and end_time:

        try:

            lecture["startTimeMins"] = (
                time_to_minutes(
                    start_time
                )
            )

            lecture["endTimeMins"] = (
                time_to_minutes(
                    end_time
                )
            )

        except ValueError:
            pass

    if not lecture.get(
        "status"
    ):

        lecture["status"] = (
            "approved"
        )

    return lecture


def prepare_lecture(
    lecture,
    class_name,
    day
):

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


def populate_timetable_faculties(
    timetable
):

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

        if not isinstance(
            schedule,
            list
        ):
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

            faculty_ids = (
                get_lecture_faculty_ids(
                    lecture
                )
            )

            lecture["facultyIds"] = (
                faculty_ids
            )

            lecture["faculty"] = (
                resolve_faculty(
                    faculty_ids
                )
            )

    return timetable


# =========================================================
# NORMAL CONFLICT DETECTION
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
    Used for normal timetable conflict detection.

    IMPORTANT:

    Same class is skipped here.

    This is correct for normal timetable saving because
    editing a timetable must not conflict with itself.

    MANUAL REQUEST VERIFICATION DOES NOT USE THIS FUNCTION.
    It uses find_occupied_lecture_for_mentor().
    """

    conflicts = []

    faculty_ids = clean_id_list(
        faculty_ids
    )

    if not faculty_ids:
        return conflicts

    try:

        start_mins = int(
            start_mins
        )

        end_mins = int(
            end_mins
        )

    except (
        TypeError,
        ValueError
    ):

        return conflicts

    if start_mins >= end_mins:
        return conflicts

    timetables = db.timetables.find({})

    for timetable in timetables:

        timetable_class = str(
            timetable.get(
                "className",
                ""
            )
        ).strip()

        if (
            current_class is not None
            and
            timetable_class ==
            str(
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

            if not lecture_is_active(
                lecture
            ):
                continue

            existing_faculty_ids = (
                get_lecture_faculty_ids(
                    lecture
                )
            )

            matching_faculty = [
                fid
                for fid in faculty_ids
                if fid in existing_faculty_ids
            ]

            if not matching_faculty:
                continue

            existing_start = (
                lecture.get(
                    "startTimeMins"
                )
            )

            existing_end = (
                lecture.get(
                    "endTimeMins"
                )
            )

            if (
                existing_start is None
                or
                existing_end is None
            ):

                try:

                    existing_start = (
                        time_to_minutes(
                            lecture.get(
                                "startTime"
                            )
                        )
                    )

                    existing_end = (
                        time_to_minutes(
                            lecture.get(
                                "endTime"
                            )
                        )
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    continue

            if not lectures_overlap(
                start_mins,
                end_mins,
                existing_start,
                existing_end
            ):
                continue

            if exclude_lecture:

                same_id = (
                    exclude_lecture.get(
                        "_id"
                    )
                    and
                    lecture.get(
                        "_id"
                    )
                    and
                    str(
                        exclude_lecture.get(
                            "_id"
                        )
                    )
                    ==
                    str(
                        lecture.get(
                            "_id"
                        )
                    )
                )

                same_time_and_faculty = (
                    exclude_lecture.get(
                        "startTimeMins"
                    )
                    ==
                    existing_start
                    and
                    exclude_lecture.get(
                        "endTimeMins"
                    )
                    ==
                    existing_end
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

                if (
                    same_id
                    or
                    same_time_and_faculty
                ):
                    continue

            for fid in matching_faculty:

                mentor_info = (
                    get_mentor_info(
                        fid
                    )
                )

                conflicts.append({

                    "mentorId":
                        fid,

                    "mentorName":
                        mentor_info.get(
                            "name",
                            "Unknown Faculty"
                        ),

                    "approvalMode":
                        bool(
                            mentor_info.get(
                                "approvalMode",
                                False
                            )
                        ),

                    "class":
                        timetable_class,

                    "subject":
                        lecture.get(
                            "subject",
                            ""
                        ),

                    "day":
                        day,

                    "room":
                        lecture.get(
                            "room",
                            ""
                        ),

                    "lecture":
                        lecture,

                    "start":
                        lecture.get(
                            "startTime"
                        ),

                    "end":
                        lecture.get(
                            "endTime"
                        ),

                    "startTimeMins":
                        existing_start,

                    "endTimeMins":
                        existing_end
                })

    return conflicts


# =========================================================
# EXACT OCCUPIED LECTURE FINDER
# =========================================================

def find_occupied_lecture_for_mentor(
    mentor_id,
    day,
    start_mins,
    end_mins,
    class_name=None,
    require_approval_mode=False
):
    """
    THIS IS THE IMPORTANT FIX.

    Used ONLY for manual Request Lecture /
    verify-conflict flow.

    Unlike find_conflicts():

        SAME CLASS IS NOT SKIPPED.

    It searches ALL timetable documents and finds
    an ACTIVE lecture assigned to the requested mentor.

    Match requirements:

        mentorId
        same day
        overlapping time
        active lecture

    If class_name is provided, the search can be restricted
    to that class.

    This solves:

        "This lecture is no longer occupied..."
    """

    mentor_id = str(
        mentor_id
    ).strip()

    if not mentor_id:
        return None

    try:

        start_mins = int(
            start_mins
        )

        end_mins = int(
            end_mins
        )

    except (
        TypeError,
        ValueError
    ):

        return None

    if start_mins >= end_mins:
        return None

    class_filter = None

    if class_name:
        class_filter = str(
            class_name
        ).strip()

    timetables = db.timetables.find({})

    for timetable in timetables:

        timetable_class = str(
            timetable.get(
                "className",
                ""
            )
        ).strip()

        if (
            class_filter
            and
            timetable_class != class_filter
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

            if not lecture_is_active(
                lecture
            ):
                continue

            faculty_ids = (
                get_lecture_faculty_ids(
                    lecture
                )
            )

            if mentor_id not in faculty_ids:
                continue

            existing_start = (
                lecture.get(
                    "startTimeMins"
                )
            )

            existing_end = (
                lecture.get(
                    "endTimeMins"
                )
            )

            if (
                existing_start is None
                or
                existing_end is None
            ):
                continue

            if not lectures_overlap(
                start_mins,
                end_mins,
                existing_start,
                existing_end
            ):
                continue

            mentor_info = (
                get_mentor_info(
                    mentor_id
                )
            )

            if (
                require_approval_mode
                and
                not bool(
                    mentor_info.get(
                        "approvalMode",
                        False
                    )
                )
            ):
                return {
                    "found": True,
                    "approvalMode": False,
                    "mentorId": mentor_id,
                    "mentorName":
                        mentor_info.get(
                            "name",
                            "Unknown Faculty"
                        ),
                    "class":
                        timetable_class,
                    "subject":
                        lecture.get(
                            "subject",
                            ""
                        ),
                    "day":
                        day,
                    "room":
                        lecture.get(
                            "room",
                            ""
                        ),
                    "lecture":
                        lecture,
                    "start":
                        lecture.get(
                            "startTime"
                        ),
                    "end":
                        lecture.get(
                            "endTime"
                        ),
                    "startTimeMins":
                        existing_start,
                    "endTimeMins":
                        existing_end
                }

            return {
                "found": True,

                "approvalMode":
                    bool(
                        mentor_info.get(
                            "approvalMode",
                            False
                        )
                    ),

                "mentorId":
                    mentor_id,

                "mentorName":
                    mentor_info.get(
                        "name",
                        "Unknown Faculty"
                    ),

                "class":
                    timetable_class,

                "subject":
                    lecture.get(
                        "subject",
                        ""
                    ),

                "day":
                    day,

                "room":
                    lecture.get(
                        "room",
                        ""
                    ),

                "lecture":
                    lecture,

                "start":
                    lecture.get(
                        "startTime"
                    ),

                "end":
                    lecture.get(
                        "endTime"
                    ),

                "startTimeMins":
                    existing_start,

                "endTimeMins":
                    existing_end
            }

    return None


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

    query = {

        "className":
            class_name,

        "targetMentorId":
            str(
                target_mentor_id
            ).strip(),

        "day":
            day,

        "startTime":
            start_time,

        "status":
            "pending"
    }

    if end_time:
        query["endTime"] = end_time

    existing = (
        db.lecture_requests.find_one(
            query
        )
    )

    return bool(
        existing
    )


# =========================================================
# CREATE LECTURE REQUEST
# =========================================================

def create_lecture_request(
    requester_mentor_id,
    target_conflict,
    class_name,
    day,
    start_time,
    end_time,
    new_lecture
):

    target_mentor_id = str(
        target_conflict.get(
            "mentorId",
            ""
        )
    ).strip()

    if not target_mentor_id:
        return False

    if lecture_request_exists(
        class_name,
        target_mentor_id,
        day,
        start_time,
        end_time
    ):
        return False

    mentor_info = (
        get_mentor_info(
            target_mentor_id
        )
    )

    request_document = {

        "requesterMentorId":
            str(
                requester_mentor_id or ""
            ).strip(),

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
                class_name
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
            dict(
                new_lecture
            ),

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
        request_document
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
                            "mentorId":
                                regex
                        },
                        {
                            "name":
                                regex
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
            or
            approval_mode is None
        ):

            return jsonify({
                "success": False,
                "message":
                    "mentorId and approvalMode required"
            }), 400

        result = db.mentors.update_one(
            {
                "mentorId":
                    str(
                        mentor_id
                    ).strip()
            },
            {
                "$set": {
                    "approvalMode":
                        bool(
                            approval_mode
                        )
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
            "approvalMode":
                bool(
                    approval_mode
                ),
            "message":
                "Approval mode updated"
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
                    str(
                        mentor_id
                    ).strip()
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
# MANUAL REQUEST LECTURE
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

        requester_id = data.get(
            "requesterMentorId",
            ""
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

        target_id = str(
            target_id
        ).strip()

        class_name = str(
            class_name
        ).strip()

        start_mins = (
            time_to_minutes(
                start_time
            )
        )

        end_mins = (
            time_to_minutes(
                end_time
            )
        )

        if start_mins >= end_mins:

            return jsonify({
                "success": False,
                "message":
                    "Invalid time range"
            }), 400

        # =================================================
        # IMPORTANT FIX
        # =================================================
        #
        # DO NOT use find_conflicts() here.
        #
        # find_conflicts() intentionally skips same class.
        #
        # Request Lecture must verify the actual occupied
        # lecture even if it belongs to the SAME CLASS.
        #
        # =================================================

        occupied = (
            find_occupied_lecture_for_mentor(
                mentor_id=target_id,
                day=day,
                start_mins=start_mins,
                end_mins=end_mins,
                class_name=class_name,
                require_approval_mode=True
            )
        )

        if not occupied:

            return jsonify({
                "success": False,
                "conflict": False,
                "requestCreated": False,
                "message":
                    "No active lecture assigned to this faculty was found at the selected time."
            }), 400

        if not occupied.get(
            "approvalMode",
            False
        ):

            return jsonify({
                "success": False,
                "conflict": True,
                "requestCreated": False,
                "message":
                    "The assigned faculty is occupied, but approval mode is disabled."
            }), 409

        old_lecture = occupied.get(
            "lecture",
            {}
        )

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

        # The requested lecture should normally contain
        # the requesting mentor/faculty.
        faculty_ids = clean_id_list(
            data.get(
                "facultyIds",
                []
            )
        )

        if not faculty_ids:

            requester_id_clean = str(
                requester_id or ""
            ).strip()

            if requester_id_clean:

                faculty_ids = [
                    requester_id_clean
                ]

            else:

                faculty_ids = [
                    target_id
                ]

        new_lecture["facultyIds"] = (
            faculty_ids
        )

        # =================================================
        # DUPLICATE REQUEST CHECK
        # =================================================

        already_exists = (
            lecture_request_exists(
                class_name,
                target_id,
                day,
                start_time,
                end_time
            )
        )

        if already_exists:

            return jsonify({
                "success": True,
                "conflict": True,
                "requestCreated": False,
                "alreadyExists": True,
                "targetMentorId":
                    target_id,
                "targetMentorName":
                    occupied.get(
                        "mentorName"
                    ),
                "message":
                    "A pending lecture request already exists for this faculty."
            }), 200

        created = (
            create_lecture_request(
                requester_mentor_id=requester_id,
                target_conflict=occupied,
                class_name=class_name,
                day=day,
                start_time=start_time,
                end_time=end_time,
                new_lecture=new_lecture
            )
        )

        return jsonify({

            "success":
                True,

            "conflict":
                True,

            "requestCreated":
                created,

            "targetMentorId":
                target_id,

            "targetMentorName":
                occupied.get(
                    "mentorName"
                ),

            "existingClass":
                occupied.get(
                    "class"
                ),

            "existingSubject":
                occupied.get(
                    "subject"
                ),

            "existingStart":
                occupied.get(
                    "start"
                ),

            "existingEnd":
                occupied.get(
                    "end"
                ),

            "oldLecture":
                old_lecture,

            "message":
                "Lecture request sent successfully to the assigned faculty."
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

        mentor_id = str(
            mentor_id
        ).strip()

        requests_data = list(
            db.lecture_requests.find(
                {
                    "$or": [
                        {
                            "targetMentorId":
                                mentor_id
                        },
                        {
                            "targetFaculty":
                                mentor_id
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

    try:

        data = request.get_json(silent=True) or {}

        req_id = data.get("requestId")

        mentor_id = (
            data.get("mentorId")
            or data.get("approverMentorId")
        )

        if not req_id:
            return jsonify({
                "success": False,
                "message": "requestId required"
            }), 400

        if not mentor_id:
            return jsonify({
                "success": False,
                "message": "mentorId required"
            }), 400

        mentor_id = str(mentor_id).strip()

        # -------------------------------------------------
        # Validate request ObjectId
        # -------------------------------------------------
        try:
            object_id = ObjectId(str(req_id))
        except Exception:
            return jsonify({
                "success": False,
                "message": "Invalid requestId"
            }), 400

        # -------------------------------------------------
        # Get pending request
        # -------------------------------------------------
        req = db.lecture_requests.find_one({
            "_id": object_id,
            "status": "pending"
        })

        if not req:
            return jsonify({
                "success": False,
                "message": "Request not found or already processed"
            }), 404

        # -------------------------------------------------
        # Verify approver is the target mentor
        # -------------------------------------------------
        target_mentor_id = str(
            req.get("targetMentorId", "")
        ).strip()

        if target_mentor_id and mentor_id != target_mentor_id:
            return jsonify({
                "success": False,
                "message": "This request is not assigned to this mentor."
            }), 403

        # -------------------------------------------------
        # Request data
        # -------------------------------------------------
        existing_class = str(
            req.get("existingClass", "")
        ).strip()

        new_class = str(
            req.get("className", "")
        ).strip()

        day = str(
            req.get("day", "")
        ).strip()

        old_lecture = req.get("oldLecture", {})
        new_lecture = req.get("newLecture", {})

        if not existing_class:
            return jsonify({
                "success": False,
                "message": "existingClass is missing"
            }), 409

        if not new_class:
            return jsonify({
                "success": False,
                "message": "className is missing"
            }), 409

        if not day:
            return jsonify({
                "success": False,
                "message": "day is missing"
            }), 409

        if not isinstance(old_lecture, dict):
            old_lecture = {}

        if not isinstance(new_lecture, dict):
            new_lecture = {}

        # -------------------------------------------------
        # Normalize request lectures
        # -------------------------------------------------
        normalize_lecture(old_lecture)
        normalize_lecture(new_lecture)

        # =================================================
        # FIND OLD TIMETABLE
        # =================================================
        old_tt = db.timetables.find_one({
            "className": existing_class
        })

        if not old_tt:
            return jsonify({
                "success": False,
                "message": "Old timetable no longer exists."
            }), 409

        old_schedule = (
            old_tt
            .get("weeklySchedule", {})
            .get(day, [])
        )

        if not isinstance(old_schedule, list):
            old_schedule = []

        # -------------------------------------------------
        # Find the exact old occupied lecture.
        # -------------------------------------------------
        old_lecture_index = -1

        requested_old_faculty_ids = get_lecture_faculty_ids(
            old_lecture
        )

        old_start = old_lecture.get("startTimeMins")
        old_end = old_lecture.get("endTimeMins")

        # Fallback to request's string times if mins are absent.
        if old_start is None and old_lecture.get("startTime"):
            try:
                old_start = time_to_minutes(
                    old_lecture.get("startTime")
                )
            except (ValueError, TypeError):
                old_start = None

        if old_end is None and old_lecture.get("endTime"):
            try:
                old_end = time_to_minutes(
                    old_lecture.get("endTime")
                )
            except (ValueError, TypeError):
                old_end = None

        # Request-level fallback.
        if old_start is None and req.get("startTime"):
            try:
                old_start = time_to_minutes(req.get("startTime"))
            except (ValueError, TypeError):
                pass

        if old_end is None and req.get("endTime"):
            try:
                old_end = time_to_minutes(req.get("endTime"))
            except (ValueError, TypeError):
                pass

        for index, lecture in enumerate(old_schedule):

            if not isinstance(lecture, dict):
                continue

            normalize_lecture(lecture)

            lecture_faculty_ids = get_lecture_faculty_ids(
                lecture
            )

            # Target mentor must be assigned to the occupied lecture.
            faculty_match = (
                not target_mentor_id
                or target_mentor_id in lecture_faculty_ids
            )

            # If request contains old faculty IDs, they must overlap.
            requested_faculty_match = True

            if requested_old_faculty_ids:
                requested_faculty_match = bool(
                    set(requested_old_faculty_ids)
                    & set(lecture_faculty_ids)
                )

            time_match = (
                lecture.get("startTimeMins") == old_start
                and lecture.get("endTimeMins") == old_end
            )

            if (
                faculty_match
                and requested_faculty_match
                and time_match
            ):
                old_lecture_index = index
                break

        if old_lecture_index == -1:
            return jsonify({
                "success": False,
                "message": (
                    "The occupied lecture could not be found. "
                    "Please reload the timetable."
                )
            }), 409

        actual_old_lecture = old_schedule[old_lecture_index]
        normalize_lecture(actual_old_lecture)

        # =================================================
        # VALIDATE NEW LECTURE
        # =================================================
        new_faculty_ids = get_lecture_faculty_ids(new_lecture)

        new_start = new_lecture.get("startTimeMins")
        new_end = new_lecture.get("endTimeMins")

        if new_start is None and new_lecture.get("startTime"):
            try:
                new_start = time_to_minutes(
                    new_lecture.get("startTime")
                )
            except (ValueError, TypeError):
                new_start = None

        if new_end is None and new_lecture.get("endTime"):
            try:
                new_end = time_to_minutes(
                    new_lecture.get("endTime")
                )
            except (ValueError, TypeError):
                new_end = None

        if new_start is None or new_end is None:
            return jsonify({
                "success": False,
                "message": "New lecture has invalid time information."
            }), 400

        new_start = int(new_start)
        new_end = int(new_end)

        if new_start >= new_end:
            return jsonify({
                "success": False,
                "message": "New lecture start time must be before end time."
            }), 400

        # =================================================
        # DESTINATION CONFLICT CHECK
        # =================================================
        destination_conflicts = []

        if new_faculty_ids:
            destination_conflicts = find_conflicts(
                faculty_ids=new_faculty_ids,
                day=day,
                start_mins=new_start,
                end_mins=new_end,
                current_class=new_class
            )

        filtered_conflicts = []

        for conflict in destination_conflicts:

            conflict_class = conflict.get("class")
            conflict_lecture = conflict.get("lecture", {})

            # Ignore the exact old lecture being moved.
            if (
                conflict_class == existing_class
                and conflict_lecture.get("startTimeMins")
                == actual_old_lecture.get("startTimeMins")
                and conflict_lecture.get("endTimeMins")
                == actual_old_lecture.get("endTimeMins")
                and set(get_lecture_faculty_ids(conflict_lecture))
                == set(get_lecture_faculty_ids(actual_old_lecture))
            ):
                continue

            filtered_conflicts.append(conflict)

        if filtered_conflicts:
            return jsonify({
                "success": False,
                "message": (
                    "Cannot approve because the destination timetable "
                    "has a conflict."
                ),
                "conflicts": filtered_conflicts
            }), 409

        # =================================================
        # DESTINATION TIMETABLE
        # =================================================
        destination_tt = db.timetables.find_one({
            "className": new_class
        })

        destination_schedule = []

        if destination_tt:
            destination_schedule = (
                destination_tt
                .get("weeklySchedule", {})
                .get(day, [])
            )

        if not isinstance(destination_schedule, list):
            destination_schedule = []

        # =================================================
        # DUPLICATE CHECK
        # =================================================
        for lecture in destination_schedule:

            if not isinstance(lecture, dict):
                continue

            normalize_lecture(lecture)

            # Ignore the old lecture itself when source and destination
            # are the same class.
            if (
                existing_class == new_class
                and lecture.get("startTimeMins")
                == actual_old_lecture.get("startTimeMins")
                and lecture.get("endTimeMins")
                == actual_old_lecture.get("endTimeMins")
                and set(get_lecture_faculty_ids(lecture))
                == set(get_lecture_faculty_ids(actual_old_lecture))
            ):
                continue

            same_time = (
                lecture.get("startTimeMins") == new_start
                and lecture.get("endTimeMins") == new_end
            )

            same_faculty = (
                set(get_lecture_faculty_ids(lecture))
                == set(new_faculty_ids)
            )

            if same_time and same_faculty:
                return jsonify({
                    "success": False,
                    "message": (
                        "The destination timetable already "
                        "contains this lecture."
                    )
                }), 409

        # =================================================
        # PREPARE NEW LECTURE
        # =================================================
        new_lecture["status"] = "approved"
        new_lecture["facultyIds"] = clean_id_list(new_faculty_ids)
        new_lecture["faculty"] = resolve_faculty(
            new_lecture["facultyIds"]
        )
        new_lecture["startTimeMins"] = new_start
        new_lecture["endTimeMins"] = new_end

        # =================================================
        # BUILD THE FINAL SCHEDULES IN MEMORY FIRST
        # =================================================
        updated_old_schedule = list(old_schedule)
        updated_old_schedule.pop(old_lecture_index)

        # If source and destination are the same class, update the SAME
        # timetable document in one operation. This avoids removing the
        # lecture and then trying to push it back into the same document.
        same_class_move = existing_class == new_class

        if same_class_move:

            final_same_class_schedule = updated_old_schedule + [
                new_lecture
            ]

            result = db.timetables.update_one(
                {
                    "_id": old_tt["_id"],
                    "className": existing_class
                },
                {
                    "$set": {
                        f"weeklySchedule.{day}":
                            final_same_class_schedule,
                        "updatedAt": datetime.utcnow()
                    }
                }
            )

            if result.matched_count == 0 or result.modified_count == 0:
                return jsonify({
                    "success": False,
                    "message": (
                        "Approval failed: the timetable could not "
                        "be updated."
                    )
                }), 409

        else:

            # -------------------------------------------------
            # REMOVE OLD LECTURE
            # -------------------------------------------------
            old_update_result = db.timetables.update_one(
                {
                    "_id": old_tt["_id"],
                    "className": existing_class
                },
                {
                    "$set": {
                        f"weeklySchedule.{day}":
                            updated_old_schedule,
                        "updatedAt": datetime.utcnow()
                    }
                }
            )

            if (
                old_update_result.matched_count == 0
                or old_update_result.modified_count == 0
            ):
                return jsonify({
                    "success": False,
                    "message": (
                        "Approval failed: old timetable could not "
                        "be updated. No lecture was moved."
                    )
                }), 409

            # -------------------------------------------------
            # INSERT NEW LECTURE
            # -------------------------------------------------
            if destination_tt:

                new_update_result = db.timetables.update_one(
                    {
                        "_id": destination_tt["_id"],
                        "className": new_class
                    },
                    {
                        "$push": {
                            f"weeklySchedule.{day}": new_lecture
                        },
                        "$set": {
                            "updatedAt": datetime.utcnow()
                        }
                    }
                )

                if (
                    new_update_result.matched_count == 0
                    or new_update_result.modified_count == 0
                ):
                    # Roll back the old timetable so approval cannot leave
                    # the lecture deleted from its original class.
                    db.timetables.update_one(
                        {
                            "_id": old_tt["_id"],
                            "className": existing_class
                        },
                        {
                            "$set": {
                                f"weeklySchedule.{day}": old_schedule,
                                "updatedAt": datetime.utcnow()
                            }
                        }
                    )

                    return jsonify({
                        "success": False,
                        "message": (
                            "Approval failed: destination timetable "
                            "could not be updated. The old lecture "
                            "was restored."
                        )
                    }), 409

            else:

                try:
                    db.timetables.insert_one({
                        "className": new_class,
                        "mentorID": req.get(
                            "requesterMentorId", ""
                        ),
                        "weeklySchedule": {
                            day: [new_lecture]
                        },
                        "createdAt": datetime.utcnow(),
                        "updatedAt": datetime.utcnow()
                    })
                except Exception:
                    # Roll back old timetable if destination creation fails.
                    db.timetables.update_one(
                        {
                            "_id": old_tt["_id"],
                            "className": existing_class
                        },
                        {
                            "$set": {
                                f"weeklySchedule.{day}": old_schedule,
                                "updatedAt": datetime.utcnow()
                            }
                        }
                    )
                    raise

        # =================================================
        # VERIFY FINAL TIMETABLE STATE BEFORE APPROVING REQUEST
        # =================================================
        final_old_tt = db.timetables.find_one({
            "_id": old_tt["_id"]
        })

        if not final_old_tt:
            return jsonify({
                "success": False,
                "message": "Approval failed: old timetable disappeared."
            }), 500

        final_old_schedule = (
            final_old_tt
            .get("weeklySchedule", {})
            .get(day, [])
        )

        # For different classes, old lecture must no longer be present.
        if not same_class_move:
            old_still_present = False

            for lecture in final_old_schedule:
                if not isinstance(lecture, dict):
                    continue

                normalize_lecture(lecture)

                if (
                    lecture.get("startTimeMins")
                    == actual_old_lecture.get("startTimeMins")
                    and lecture.get("endTimeMins")
                    == actual_old_lecture.get("endTimeMins")
                    and set(get_lecture_faculty_ids(lecture))
                    == set(get_lecture_faculty_ids(actual_old_lecture))
                ):
                    old_still_present = True
                    break

            if old_still_present:
                return jsonify({
                    "success": False,
                    "message": (
                        "Approval failed: old lecture is still present "
                        "in the original timetable."
                    )
                }), 500

        # For different classes, verify the new lecture exists in destination.
        final_destination_tt = db.timetables.find_one({
            "className": new_class
        })

        if not final_destination_tt:
            return jsonify({
                "success": False,
                "message": (
                    "Approval failed: destination timetable was not found "
                    "after update."
                )
            }), 500

        final_destination_schedule = (
            final_destination_tt
            .get("weeklySchedule", {})
            .get(day, [])
        )

        new_lecture_present = False

        for lecture in final_destination_schedule:
            if not isinstance(lecture, dict):
                continue

            normalize_lecture(lecture)

            if (
                lecture.get("startTimeMins") == new_start
                and lecture.get("endTimeMins") == new_end
                and set(get_lecture_faculty_ids(lecture))
                == set(new_faculty_ids)
                and lecture.get("subject", "")
                == new_lecture.get("subject", "")
            ):
                new_lecture_present = True
                break

        if not new_lecture_present:
            # Safety rollback for different-class moves.
            if not same_class_move:
                db.timetables.update_one(
                    {
                        "_id": old_tt["_id"],
                        "className": existing_class
                    },
                    {
                        "$set": {
                            f"weeklySchedule.{day}": old_schedule,
                            "updatedAt": datetime.utcnow()
                        }
                    }
                )

                # If we pushed the new lecture into an existing destination,
                # remove only the exact lecture that was just inserted.
                if destination_tt:
                    db.timetables.update_one(
                        {
                            "_id": destination_tt["_id"],
                            "className": new_class
                        },
                        {
                            "$pull": {
                                f"weeklySchedule.{day}": {
                                    "startTimeMins": new_start,
                                    "endTimeMins": new_end,
                                    "subject": new_lecture.get(
                                        "subject", ""
                                    ),
                                    "status": "approved"
                                }
                            },
                            "$set": {
                                "updatedAt": datetime.utcnow()
                            }
                        }
                    )

            return jsonify({
                "success": False,
                "message": (
                    "Approval failed: new lecture was not found in "
                    "the destination timetable."
                )
            }), 500

        # =================================================
        # MARK REQUEST APPROVED ONLY AFTER TIMETABLE UPDATE
        # =================================================
        result = db.lecture_requests.update_one(
            {
                "_id": object_id,
                "status": "pending"
            },
            {
                "$set": {
                    "status": "approved",
                    "updatedAt": datetime.utcnow(),
                    "processedAt": datetime.utcnow(),
                    "processedBy": mentor_id
                }
            }
        )

        if result.matched_count == 0 or result.modified_count == 0:
            # Timetable has already been correctly updated. Do NOT report
            # success as if request status was changed silently.
            return jsonify({
                "success": False,
                "message": (
                    "Lecture timetable was updated, but the lecture "
                    "request could not be marked as approved."
                ),
                "timetableUpdated": True,
                "requestStatusUpdated": False
            }), 500

        return jsonify({
            "success": True,
            "message": "Lecture request approved successfully.",
            "requestId": str(req_id),
            "targetMentorId": mentor_id,
            "oldLectureRemoved": True,
            "timetableUpdated": True,
            "requestStatusUpdated": True
        }), 200

    except Exception as e:

        print(
            "APPROVE LECTURE REQUEST ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# REJECT LECTURE REQUEST
# =========================================================

@timetable_bp.route(
    "/lecture-request/reject",
    methods=["PUT"]
)
def reject_lecture_request():

    try:

        data = request.get_json(silent=True) or {}

        req_id = data.get(
            "requestId"
        )

        mentor_id = (
            data.get("mentorId")
            or
            data.get("approverMentorId")
        )

        if not req_id:

            return jsonify({
                "success": False,
                "message":
                    "requestId required"
            }), 400

        if not mentor_id:

            return jsonify({
                "success": False,
                "message":
                    "mentorId required"
            }), 400

        mentor_id = str(
            mentor_id
        ).strip()

        # -------------------------------------------------
        # Validate request ID
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Find pending request
        # -------------------------------------------------

        req = db.lecture_requests.find_one({
            "_id":
                object_id,

            "status":
                "pending"
        })

        if not req:

            return jsonify({
                "success": False,
                "message":
                    "Request not found or already processed"
            }), 404

        # -------------------------------------------------
        # Basic target check only
        #
        # NO mentor DB lookup.
        # NO approvalMode check.
        # -------------------------------------------------

        target_mentor_id = str(
            req.get(
                "targetMentorId",
                ""
            )
        ).strip()

        if (
            target_mentor_id
            and
            mentor_id != target_mentor_id
        ):

            return jsonify({
                "success": False,
                "message":
                    "This request is not assigned to this mentor."
            }), 403

        # =================================================
        # DELETE REQUEST COMPLETELY
        # =================================================

        result = db.lecture_requests.delete_one({
            "_id":
                object_id,

            "status":
                "pending"
        })

        if result.deleted_count == 0:

            return jsonify({
                "success": False,
                "message":
                    "Request not found or already processed"
            }), 404

        # =================================================
        # SUCCESS
        # =================================================

        return jsonify({

            "success":
                True,

            "message":
                "Lecture request rejected and deleted successfully.",

            "requestId":
                str(req_id),

            "targetMentorId":
                mentor_id,

            "deleted":
                True

        }), 200

    except Exception as e:

        print(
            "REJECT LECTURE REQUEST ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================================================
# PROCESS ONE LECTURE FOR NORMAL SAVE
# =========================================================

def process_lecture_for_save(
    lecture,
    class_name,
    day,
    requester_mentor_id
):

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
            faculty_ids=faculty_ids,
            day=day,
            start_mins=lecture[
                "startTimeMins"
            ],
            end_mins=lecture[
                "endTimeMins"
            ],
            current_class=class_name
        )

    approval_conflicts = [
        conflict
        for conflict in conflicts
        if conflict.get(
            "approvalMode"
        ) is True
    ]

    requests_created = []

    if approval_conflicts:

        for conflict in approval_conflicts:

            created = (
                create_lecture_request(
                    requester_mentor_id,
                    conflict,
                    class_name,
                    day,
                    lecture[
                        "startTime"
                    ],
                    lecture[
                        "endTime"
                    ],
                    lecture
                )
            )

            if created:
                requests_created.append(
                    conflict
                )

        return {

            "save":
                False,

            "lecture":
                lecture,

            "conflicts":
                conflicts,

            "approvalConflicts":
                approval_conflicts,

            "requestsCreated":
                requests_created
        }

    # =====================================================
    # NO APPROVAL CONFLICT
    #
    # If no conflict OR approvalMode disabled:
    # save normally according to existing behavior.
    # =====================================================

    lecture["status"] = (
        "approved"
    )

    lecture["faculty"] = (
        resolve_faculty(
            faculty_ids
        )
    )

    return {

        "save":
            True,

        "lecture":
            lecture,

        "conflicts":
            conflicts,

        "approvalConflicts":
            [],

        "requestsCreated":
            []
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

        existing_tt = (
            db.timetables.find_one(
                {
                    "className":
                        class_name
                }
            )
        )

        if existing_tt:

            existing_weekly = (
                existing_tt.get(
                    "weeklySchedule",
                    {}
                )
            )

        else:

            existing_weekly = {}

        final_schedule = dict(
            existing_weekly
        )

        has_conflict = False

        requests_created = []

        conflict_info = []

        for day, lectures in (
            weekly_schedule.items()
        ):

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

                result = (
                    process_lecture_for_save(
                        lecture,
                        class_name,
                        day,
                        mentor_id
                    )
                )

                if result["save"]:

                    valid_day_schedule.append(
                        result[
                            "lecture"
                        ]
                    )

                else:

                    has_conflict = True

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

        timetable = (
            db.timetables.find_one(
                {
                    "className":
                        class_name
                }
            )
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

            "success":
                True,

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

        timetable = (
            db.timetables.find_one(
                {
                    "className":
                        class_name
                }
            )
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

        for lecture in schedule:

            result = (
                process_lecture_for_save(
                    lecture,
                    class_name,
                    day,
                    mentor_id
                )
            )

            if result["save"]:

                valid_schedule.append(
                    result[
                        "lecture"
                    ]
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

        result = (
            db.timetables.update_one(
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

            "success":
                True,

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

        class_name = (
            request.form.get(
                "className"
            )
        )

        uploaded_by = (
            request.form.get(
                "uploadedBy"
            )
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
            not data.get(
                "date"
            )
            or
            not data.get(
                "title"
            )
        ):

            return jsonify({
                "success": False,
                "message":
                    "date and title are required"
            }), 400

        holiday_data = {

            "date":
                data.get(
                    "date"
                ),

            "title":
                data.get(
                    "title"
                ),

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
# VERIFY CONFLICT / OCCUPANCY
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

        if (
            start_mins is None
            and
            start_time
        ):

            start_mins = (
                time_to_minutes(
                    start_time
                )
            )

        if (
            end_mins is None
            and
            end_time
        ):

            end_mins = (
                time_to_minutes(
                    end_time
                )
            )

        if (
            start_mins is None
            or
            end_mins is None
        ):

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

        except (
            TypeError,
            ValueError
        ):

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

        # =================================================
        # IMPORTANT:
        # DO NOT USE find_conflicts()
        #
        # We need exact occupied lecture verification,
        # including SAME CLASS.
        # =================================================

        occupied = (
            find_occupied_lecture_for_mentor(
                mentor_id=mentor_id,
                day=day,
                start_mins=start_mins,
                end_mins=end_mins,
                class_name=class_name,
                require_approval_mode=False
            )
        )

        if not occupied:

            return jsonify({

                "success":
                    True,

                "exists":
                    False,

                "conflict":
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
                    occupied.get(
                        "approvalMode",
                        False
                    )
                ),

            "mentorId":
                occupied.get(
                    "mentorId"
                ),

            "mentorName":
                occupied.get(
                    "mentorName"
                ),

            "existingClass":
                occupied.get(
                    "class"
                ),

            "existingSubject":
                occupied.get(
                    "subject"
                ),

            "existingStart":
                occupied.get(
                    "start"
                ),

            "existingEnd":
                occupied.get(
                    "end"
                ),

            "oldLecture":
                occupied.get(
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
    # =========================================================
# APPROVE + UPDATE TIMETABLE
#
# Flow:
#
# MH1 requests lecture from MH2
#              ↓
# MH2 approves
#              ↓
# Remove old MH2 lecture
#              ↓
# Add MH1 requested lecture
#              ↓
# Subject + Faculty + Room + Time updated
#              ↓
# Verify timetable update
#              ↓
# Mark request approved
# =========================================================

@timetable_bp.route(
    "/lecture-request/approve-update",
    methods=["PUT"]
)
def approve_lecture_request_and_update_timetable():

    try:

        # =================================================
        # READ REQUEST
        # =================================================

        data = request.get_json(
            silent=True
        ) or {}

        req_id = data.get(
            "requestId"
        )

        mentor_id = (
            data.get("mentorId")
            or
            data.get("approverMentorId")
        )

        if not req_id:

            return jsonify({
                "success": False,
                "message": "requestId required"
            }), 400

        if not mentor_id:

            return jsonify({
                "success": False,
                "message": "mentorId required"
            }), 400

        mentor_id = str(
            mentor_id
        ).strip()


        # =================================================
        # OBJECT ID
        # =================================================

        try:

            object_id = ObjectId(
                str(req_id)
            )

        except Exception:

            return jsonify({
                "success": False,
                "message": "Invalid requestId"
            }), 400


        # =================================================
        # FIND PENDING REQUEST
        # =================================================

        req = db.lecture_requests.find_one({
            "_id": object_id,
            "status": "pending"
        })

        if not req:

            return jsonify({
                "success": False,
                "message":
                    "Request not found or already processed"
            }), 404


        # =================================================
        # VERIFY APPROVING MENTOR
        # =================================================

        target_mentor_id = str(
            req.get(
                "targetMentorId",
                ""
            )
        ).strip()

        if (
            target_mentor_id
            and
            mentor_id != target_mentor_id
        ):

            return jsonify({
                "success": False,
                "message":
                    "This request is not assigned to this mentor."
            }), 403


        # =================================================
        # REQUEST DATA
        # =================================================

        old_class = req.get(
            "existingClass"
        )

        new_class = req.get(
            "className"
        )

        original_day = req.get(
            "day"
        )

        old_lecture = req.get(
            "oldLecture",
            {}
        )

        stored_new_lecture = req.get(
            "newLecture",
            {}
        )


        if not old_class:

            return jsonify({
                "success": False,
                "message":
                    "existingClass is missing"
            }), 409


        if not new_class:

            return jsonify({
                "success": False,
                "message":
                    "className is missing"
            }), 409


        if not original_day:

            return jsonify({
                "success": False,
                "message":
                    "day is missing"
            }), 409


        if not isinstance(
            old_lecture,
            dict
        ):

            old_lecture = {}


        if not isinstance(
            stored_new_lecture,
            dict
        ):

            stored_new_lecture = {}


        # =================================================
        # OPTIONAL FRONTEND EDITED LECTURE
        #
        # Frontend can send:
        #
        # approvedLecture: {
        #     subject,
        #     room,
        #     startTime,
        #     endTime,
        #     facultyIds
        # }
        #
        # If not sent, stored newLecture is used.
        # =================================================

        approved_lecture = data.get(
            "approvedLecture"
        )

        if (
            not isinstance(
                approved_lecture,
                dict
            )
            or
            not approved_lecture
        ):

            approved_lecture = dict(
                stored_new_lecture
            )

        else:

            # Start from original request
            # and override only edited values.

            merged_lecture = dict(
                stored_new_lecture
            )

            merged_lecture.update(
                approved_lecture
            )

            approved_lecture = (
                merged_lecture
            )


        # =================================================
        # DAY
        #
        # Day remains original request day unless
        # frontend explicitly sends another day.
        # =================================================

        day = (
            approved_lecture.get(
                "day"
            )
            or
            data.get(
                "day"
            )
            or
            original_day
        )


        # =================================================
        # SUBJECT
        # =================================================

        subject = str(
            approved_lecture.get(
                "subject",
                req.get(
                    "subject",
                    ""
                )
            )
            or
            ""
        ).strip()


        # =================================================
        # ROOM
        # =================================================

        room = str(
            approved_lecture.get(
                "room",
                req.get(
                    "room",
                    ""
                )
            )
            or
            ""
        ).strip()


        # =================================================
        # TIME
        # =================================================

        start_time = (
            approved_lecture.get(
                "startTime"
            )
            or
            req.get(
                "startTime"
            )
        )

        end_time = (
            approved_lecture.get(
                "endTime"
            )
            or
            req.get(
                "endTime"
            )
        )


        if not start_time:

            return jsonify({
                "success": False,
                "message":
                    "startTime is required"
            }), 400


        if not end_time:

            return jsonify({
                "success": False,
                "message":
                    "endTime is required"
            }), 400


        # =================================================
        # CONVERT TIME
        # =================================================

        new_start_mins = (
            time_to_minutes(
                start_time
            )
        )

        new_end_mins = (
            time_to_minutes(
                end_time
            )
        )


        if new_start_mins >= new_end_mins:

            return jsonify({
                "success": False,
                "message":
                    "Invalid time range"
            }), 400


        # =================================================
        # FACULTY IDS
        # =================================================

        faculty_ids = clean_id_list(
            approved_lecture.get(
                "facultyIds",
                []
            )
        )


        # If no faculty was supplied,
        # use requester mentor.

        if not faculty_ids:

            requester_id = str(
                req.get(
                    "requesterMentorId",
                    ""
                )
            ).strip()

            if requester_id:

                faculty_ids = [
                    requester_id
                ]

            else:

                return jsonify({
                    "success": False,
                    "message":
                        "Requested faculty could not be determined."
                }), 409


        # =================================================
        # BUILD FINAL LECTURE
        # =================================================

        final_lecture = dict(
            approved_lecture
        )

        final_lecture["day"] = day

        final_lecture["subject"] = subject

        final_lecture["room"] = room

        final_lecture["startTime"] = (
            str(start_time).strip()
        )

        final_lecture["endTime"] = (
            str(end_time).strip()
        )

        final_lecture["startTimeMins"] = (
            new_start_mins
        )

        final_lecture["endTimeMins"] = (
            new_end_mins
        )

        final_lecture["facultyIds"] = (
            faculty_ids
        )

        # Approved lecture is ACTIVE

        final_lecture["status"] = (
            "approved"
        )

        # Resolve faculty names from mentors collection

        final_lecture["faculty"] = (
            resolve_faculty(
                faculty_ids
            )
        )


        # =================================================
        # FIND OLD TIMETABLE
        # =================================================

        old_tt = db.timetables.find_one({
            "className": old_class
        })

        if not old_tt:

            return jsonify({
                "success": False,
                "message":
                    "Old timetable not found."
            }), 409


        old_weekly = (
            old_tt.get(
                "weeklySchedule",
                {}
            )
        )

        old_schedule = (
            old_weekly.get(
                day,
                []
            )
        )


        if not isinstance(
            old_schedule,
            list
        ):

            old_schedule = []


        # =================================================
        # FIND EXACT OLD LECTURE
        # =================================================

        old_index = -1


        old_faculty_ids = (
            get_lecture_faculty_ids(
                old_lecture
            )
        )


        old_start = (
            old_lecture.get(
                "startTimeMins"
            )
        )

        old_end = (
            old_lecture.get(
                "endTimeMins"
            )
        )


        # Fallback if minutes weren't stored

        if (
            old_start is None
            and
            old_lecture.get(
                "startTime"
            )
        ):

            old_start = (
                time_to_minutes(
                    old_lecture.get(
                        "startTime"
                    )
                )
            )


        if (
            old_end is None
            and
            old_lecture.get(
                "endTime"
            )
        ):

            old_end = (
                time_to_minutes(
                    old_lecture.get(
                        "endTime"
                    )
                )
            )


        for index, lecture in enumerate(
            old_schedule
        ):

            if not isinstance(
                lecture,
                dict
            ):

                continue


            normalize_lecture(
                lecture
            )


            lecture_faculty_ids = (
                get_lecture_faculty_ids(
                    lecture
                )
            )


            # Faculty match

            faculty_match = True

            if target_mentor_id:

                faculty_match = (
                    target_mentor_id
                    in
                    lecture_faculty_ids
                )


            # Old request faculty match

            requested_faculty_match = True

            if old_faculty_ids:

                requested_faculty_match = bool(
                    set(
                        old_faculty_ids
                    )
                    &
                    set(
                        lecture_faculty_ids
                    )
                )


            # Time match

            time_match = True

            if (
                old_start is not None
                and
                old_end is not None
            ):

                time_match = (
                    lecture.get(
                        "startTimeMins"
                    )
                    ==
                    old_start
                    and
                    lecture.get(
                        "endTimeMins"
                    )
                    ==
                    old_end
                )


            # Subject match

            subject_match = True

            old_subject = str(
                old_lecture.get(
                    "subject",
                    ""
                )
                or
                ""
            ).strip()

            current_subject = str(
                lecture.get(
                    "subject",
                    ""
                )
                or
                ""
            ).strip()


            if old_subject:

                subject_match = (
                    old_subject
                    ==
                    current_subject
                )


            if (
                faculty_match
                and
                requested_faculty_match
                and
                time_match
                and
                subject_match
            ):

                old_index = index

                break


        # =================================================
        # FALLBACK:
        # Match by old lecture _id
        # =================================================

        if old_index == -1:

            old_id = old_lecture.get(
                "_id"
            )

            if old_id:

                old_id = str(
                    old_id
                )

                for index, lecture in enumerate(
                    old_schedule
                ):

                    if not isinstance(
                        lecture,
                        dict
                    ):

                        continue

                    if str(
                        lecture.get(
                            "_id",
                            ""
                        )
                    ) == old_id:

                        old_index = index

                        break


        if old_index == -1:

            return jsonify({
                "success": False,
                "message":
                    "The original occupied lecture could not be found. Timetable was not changed."
            }), 409


        # =================================================
        # PREPARE OLD SCHEDULE
        # =================================================

        updated_old_schedule = list(
            old_schedule
        )

        removed_old_lecture = (
            updated_old_schedule.pop(
                old_index
            )
        )


        # =================================================
        # FIND DESTINATION TIMETABLE
        # =================================================

        destination_tt = db.timetables.find_one({
            "className": new_class
        })


        destination_schedule = []

        if destination_tt:

            destination_schedule = (
                destination_tt
                .get(
                    "weeklySchedule",
                    {}
                )
                .get(
                    day,
                    []
                )
            )


        if not isinstance(
            destination_schedule,
            list
        ):

            destination_schedule = []


        # =================================================
        # DESTINATION CONFLICT CHECK
        #
        # Ignore the lecture being moved when both classes
        # are the same.
        # =================================================

        for existing in destination_schedule:

            if not isinstance(
                existing,
                dict
            ):

                continue


            normalize_lecture(
                existing
            )


            # If same class, the old lecture has already
            # been logically removed from consideration.

            if (
                old_class
                ==
                new_class
                and
                existing is removed_old_lecture
            ):

                continue


            existing_start = (
                existing.get(
                    "startTimeMins"
                )
            )

            existing_end = (
                existing.get(
                    "endTimeMins"
                )
            )


            if (
                existing_start is None
                or
                existing_end is None
            ):

                try:

                    existing_start = (
                        time_to_minutes(
                            existing.get(
                                "startTime"
                            )
                        )
                    )

                    existing_end = (
                        time_to_minutes(
                            existing.get(
                                "endTime"
                            )
                        )
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    continue


            if lectures_overlap(
                new_start_mins,
                new_end_mins,
                existing_start,
                existing_end
            ):

                return jsonify({
                    "success": False,
                    "message": (
                        "The approved lecture time "
                        "conflicts with another lecture "
                        "in the destination class."
                    ),
                    "conflict": True,
                    "conflictClass": new_class,
                    "conflictDay": day,
                    "conflictStart": existing.get(
                        "startTime"
                    ),
                    "conflictEnd": existing.get(
                        "endTime"
                    ),
                    "conflictSubject": existing.get(
                        "subject",
                        ""
                    )
                }), 409


        # =================================================
        # PREPARE DESTINATION SCHEDULE
        # =================================================

        final_destination_schedule = (
            list(
                destination_schedule
            )
        )


        # If same class, remove original lecture
        # from destination schedule.

        if (
            old_class
            ==
            new_class
        ):

            same_old_index = -1

            for index, lecture in enumerate(
                final_destination_schedule
            ):

                if not isinstance(
                    lecture,
                    dict
                ):

                    continue


                if (
                    lecture.get(
                        "_id"
                    )
                    and
                    removed_old_lecture.get(
                        "_id"
                    )
                    and
                    str(
                        lecture.get(
                            "_id"
                        )
                    )
                    ==
                    str(
                        removed_old_lecture.get(
                            "_id"
                        )
                    )
                ):

                    same_old_index = index

                    break


            if same_old_index != -1:

                final_destination_schedule.pop(
                    same_old_index
                )


        # =================================================
        # ADD FINAL APPROVED LECTURE
        # =================================================

        final_destination_schedule.append(
            final_lecture
        )


        # =================================================
        # DATABASE UPDATE
        #
        # IMPORTANT:
        # Don't mark request approved until BOTH
        # timetable operations are successful.
        # =================================================

        old_update_result = None

        destination_update_result = None


        # =================================================
        # CASE 1:
        # SAME CLASS
        # =================================================

        if (
            old_class
            ==
            new_class
        ):

            result = db.timetables.update_one(
                {
                    "className":
                        old_class
                },
                {
                    "$set": {
                        f"weeklySchedule.{day}":
                            final_destination_schedule,

                        "updatedAt":
                            datetime.utcnow()
                    }
                }
            )


            if result.matched_count == 0:

                return jsonify({
                    "success": False,
                    "message":
                        "Timetable could not be updated."
                }), 500


        # =================================================
        # CASE 2:
        # DIFFERENT CLASS
        # =================================================

        else:

            # ---------------------------------------------
            # REMOVE FROM OLD CLASS
            # ---------------------------------------------

            old_update_result = (
                db.timetables.update_one(
                    {
                        "className":
                            old_class
                    },
                    {
                        "$set": {
                            f"weeklySchedule.{day}":
                                updated_old_schedule,

                            "updatedAt":
                                datetime.utcnow()
                        }
                    }
                )
            )


            if (
                old_update_result.matched_count
                == 0
            ):

                return jsonify({
                    "success": False,
                    "message":
                        "Old timetable could not be updated."
                }), 500


            # ---------------------------------------------
            # DESTINATION CLASS EXISTS
            # ---------------------------------------------

            if destination_tt:

                destination_update_result = (
                    db.timetables.update_one(
                        {
                            "className":
                                new_class
                        },
                        {
                            "$set": {
                                f"weeklySchedule.{day}":
                                    final_destination_schedule,

                                "updatedAt":
                                    datetime.utcnow()
                            }
                        }
                    )
                )


                if (
                    destination_update_result.matched_count
                    == 0
                ):

                    # -------------------------------------
                    # ROLLBACK OLD CLASS
                    # -------------------------------------

                    db.timetables.update_one(
                        {
                            "className":
                                old_class
                        },
                        {
                            "$set": {
                                f"weeklySchedule.{day}":
                                    old_schedule,

                                "updatedAt":
                                    datetime.utcnow()
                            }
                        }
                    )


                    return jsonify({
                        "success": False,
                        "message":
                            "Destination timetable could not be updated. Old timetable was restored."
                    }), 500


            # ---------------------------------------------
            # DESTINATION CLASS DOES NOT EXIST
            # ---------------------------------------------

            else:

                try:

                    db.timetables.insert_one({

                        "className":
                            new_class,

                        "mentorID":
                            req.get(
                                "requesterMentorId",
                                ""
                            ),

                        "weeklySchedule": {
                            day: [
                                final_lecture
                            ]
                        },

                        "createdAt":
                            datetime.utcnow(),

                        "updatedAt":
                            datetime.utcnow()
                    })

                except Exception as insert_error:

                    # -------------------------------------
                    # ROLLBACK OLD CLASS
                    # -------------------------------------

                    db.timetables.update_one(
                        {
                            "className":
                                old_class
                        },
                        {
                            "$set": {
                                f"weeklySchedule.{day}":
                                    old_schedule,

                                "updatedAt":
                                    datetime.utcnow()
                            }
                        }
                    )


                    return jsonify({
                        "success": False,
                        "message":
                            "Destination timetable could not be created. Old timetable was restored.",
                        "error":
                            str(insert_error)
                    }), 500


        # =================================================
        # VERIFY DATABASE TIMETABLE
        # =================================================

        verify_tt = db.timetables.find_one({
            "className":
                new_class
        })


        if not verify_tt:

            return jsonify({
                "success": False,
                "message":
                    "Timetable update verification failed."
            }), 500


        verify_schedule = (
            verify_tt
            .get(
                "weeklySchedule",
                {}
            )
            .get(
                day,
                []
            )
        )


        lecture_verified = False


        for lecture in verify_schedule:

            if not isinstance(
                lecture,
                dict
            ):

                continue


            lecture_start = (
                lecture.get(
                    "startTimeMins"
                )
            )

            lecture_end = (
                lecture.get(
                    "endTimeMins"
                )
            )


            if (
                lecture_start
                ==
                new_start_mins
                and
                lecture_end
                ==
                new_end_mins
                and
                str(
                    lecture.get(
                        "subject",
                        ""
                    )
                ).strip()
                ==
                subject
                and
                str(
                    lecture.get(
                        "room",
                        ""
                    )
                ).strip()
                ==
                room
            ):

                saved_faculty_ids = set(
                    get_lecture_faculty_ids(
                        lecture
                    )
                )

                requested_faculty_ids = set(
                    faculty_ids
                )


                if (
                    saved_faculty_ids
                    ==
                    requested_faculty_ids
                ):

                    lecture_verified = True

                    break


        if not lecture_verified:

            return jsonify({
                "success": False,
                "message":
                    "Lecture was written but database verification failed."
            }), 500


        # =================================================
        # MARK REQUEST APPROVED
        # =================================================

        approval_result = (
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
                            "approved",

                        "processedBy":
                            mentor_id,

                        "processedAt":
                            datetime.utcnow(),

                        "updatedAt":
                            datetime.utcnow(),

                        "approvedLecture":
                            final_lecture
                    }
                }
            )
        )


        if (
            approval_result.modified_count
            == 0
        ):

            return jsonify({
                "success": False,
                "message":
                    "Timetable was updated, but request status could not be changed to approved."
            }), 500


        # =================================================
        # SUCCESS
        # =================================================

        return jsonify({

            "success":
                True,

            "message":
                "Lecture approved and timetable updated successfully.",

            "requestId":
                str(req_id),

            "className":
                new_class,

            "day":
                day,

            "subject":
                subject,

            "room":
                room,

            "startTime":
                start_time,

            "endTime":
                end_time,

            "facultyIds":
                faculty_ids,

            "faculty":
                final_lecture.get(
                    "faculty",
                    []
                ),

            "timetableUpdated":
                True,

            "requestStatusUpdated":
                True

        }), 200


    except ValueError as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


    except Exception as e:

        print(
            "APPROVE + UPDATE ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "message":
                str(e)
        }), 500