from flask import Blueprint, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from bson import ObjectId
from datetime import datetime
import os
import re

from db import db

# ---------------- Blueprint ----------------
timetable_bp = Blueprint(
    "timetable_bp",
    __name__,
    url_prefix="/api/timetable"
)

CORS(timetable_bp)

# ---------------- Upload Config ----------------
UPLOAD_FOLDER = "uploads/timetables"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {"pdf"}


# =========================================================
# Helper Functions
# =========================================================

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def serialize_doc(doc):
    if not doc:
        return None

    if "_id" in doc:
        doc["_id"] = str(doc["_id"])

    return doc


def serialize_many(items):
    return [serialize_doc(item) for item in items]


def clean_id_list(ids):
    if not ids:
        return []

    cleaned = []

    for item in ids:
        if item is None:
            continue

        value = str(item).strip()

        if value and value not in cleaned:
            cleaned.append(value)

    return cleaned


def time_to_minutes(time_str):
    """
    Converts a time string like '08:00 AM' to total minutes from midnight.
    """
    try:
        dt = datetime.strptime(time_str.strip(), "%I:%M %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        raise ValueError(
            f"Invalid time format: {time_str}. Expected format: 'hh:mm AM/PM'"
        )


def resolve_faculty(faculty_ids):
    """
    Fetch mentor details for a list of mentor IDs.
    """
    faculty_ids = clean_id_list(faculty_ids)

    if not faculty_ids:
        return []

    mentors = list(
        db.mentors.find(
            {"mentorId": {"$in": faculty_ids}},
            {
                "_id": 0,
                "mentorId": 1,
                "name": 1,
                "subject": 1,
                "branch": 1
            }
        )
    )

    mentor_map = {
        mentor.get("mentorId"): mentor
        for mentor in mentors
    }

    resolved = []

    for faculty_id in faculty_ids:
        mentor = mentor_map.get(faculty_id)

        if mentor:
            resolved.append({
                "mentorId": mentor.get("mentorId"),
                "name": mentor.get("name"),
                "subject": mentor.get("subject"),
                "branch": mentor.get("branch")
            })
        else:
            resolved.append({
                "mentorId": faculty_id,
                "name": "Unknown Faculty",
                "subject": ""
            })

    return resolved


def populate_timetable_faculties(timetable):
    """
    Adds faculty details inside every lecture using facultyIds.
    """
    if not timetable or "weeklySchedule" not in timetable:
        return timetable

    for day, schedule in timetable.get("weeklySchedule", {}).items():
        if not isinstance(schedule, list):
            continue

        for lec in schedule:
            faculty_ids = clean_id_list(lec.get("facultyIds", []))

            if not faculty_ids and isinstance(lec.get("faculty"), list):
                faculty_ids = clean_id_list([
                    f.get("mentorId")
                    for f in lec.get("faculty", [])
                    if isinstance(f, dict)
                ])

            lec["facultyIds"] = faculty_ids
            lec["faculty"] = resolve_faculty(faculty_ids)

    return timetable


def find_conflicts(faculty_ids, day, start_mins, end_mins, current_class):
    """
    Checks if any faculty is already scheduled in an overlapping time
    on the given day for a different class, returning comprehensive details.
    """
    conflicts = []
    faculty_ids = clean_id_list(faculty_ids)

    for fid in faculty_ids:
        mentor = db.mentors.find_one({"mentorId": fid})
        approval_mode = False
        mentor_name = "Unknown Faculty"
        
        if mentor:
            approval_mode = mentor.get("approvalMode", False)
            mentor_name = mentor.get("name", "Unknown Faculty")

        query = {
            "className": {"$ne": current_class},
            f"weeklySchedule.{day}": {
                "$elemMatch": {
                    "facultyIds": fid,
                    "startTimeMins": {"$lt": end_mins},
                    "endTimeMins": {"$gt": start_mins},
                    "status": "approved"
                }
            }
        }

        conflict_doc = db.timetables.find_one(query)

        if conflict_doc:
            for lec in conflict_doc.get("weeklySchedule", {}).get(day, []):
                if (
                    fid in clean_id_list(lec.get("facultyIds", [])) and
                    lec.get("status") == "approved" and
                    lec.get("startTimeMins", 0) < end_mins and
                    lec.get("endTimeMins", 0) > start_mins
                ):
                    conflicts.append({
                        "mentorId": fid,
                        "mentorName": mentor_name,
                        "approvalMode": approval_mode,
                        "class": conflict_doc.get("className"),
                        "subject": lec.get("subject", ""),
                        "day": day,
                        "room": lec.get("room", ""),
                        "lecture": lec,
                        "start": lec.get("startTime"),
                        "end": lec.get("endTime")
                    })

    return conflicts


# =========================================================
# MENTOR SEARCH API
# =========================================================

@timetable_bp.route("/mentor/search", methods=["GET"])
def search_mentors():
    """
    Search mentors by mentorId or name.
    Returns same structure as /api/mentor/search.
    """
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({
            "success": True,
            "mentors": []
        })

    try:
        regex = re.compile(re.escape(query), re.IGNORECASE)

        mentors = list(
            db.mentors.find(
                {
                    "$or": [
                        {"mentorId": regex},
                        {"name": regex}
                    ]
                },
                {
                    "_id": 0,
                    "mentorId": 1,
                    "name": 1,
                    "subject": 1,
                    "branch": 1
                }
            ).limit(15)
        )

        return jsonify({
            "success": True,
            "mentors": mentors
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# APPROVAL MODE APIs
# =========================================================

@timetable_bp.route("/toggle-approval-mode", methods=["PUT"])
def toggle_approval_mode():
    try:
        data = request.get_json() or {}
        mentor_id = data.get("mentorId")
        approval_mode = data.get("approvalMode")

        if not mentor_id or approval_mode is None:
            return jsonify({"success": False, "message": "mentorId and approvalMode required"}), 400

        db.mentors.update_one(
            {"mentorId": mentor_id},
            {"$set": {"approvalMode": bool(approval_mode)}}
        )

        return jsonify({"success": True, "message": "Approval mode updated"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@timetable_bp.route("/approval-mode/<mentor_id>", methods=["GET"])
def get_approval_mode(mentor_id):
    try:
        mentor = db.mentors.find_one({"mentorId": mentor_id})
        if not mentor:
            return jsonify({"success": False, "message": "Mentor not found"}), 404
            
        return jsonify({
            "success": True,
            "approvalMode": mentor.get("approvalMode", False)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# LECTURE REQUESTS APIs
# =========================================================

@timetable_bp.route("/request-lecture", methods=["POST"])
def request_lecture():
    try:
        data = request.get_json() or {}
        
        target_id = data.get("targetMentorId")
        day = data.get("day")
        start_time = data.get("startTime")
        class_name = data.get("className")
        
        existing = db.lecture_requests.find_one({
            "className": class_name,
            "targetMentorId": target_id,
            "day": day,
            "startTime": start_time,
            "status": "pending"
        })
        
        if existing:
            return jsonify({"success": True, "message": "Request already exists", "requestCreated": False})
            
        req_doc = {
            "requesterMentorId": data.get("requesterMentorId", ""),
            "targetMentorId": target_id,
            "requesterName": data.get("requesterName", ""),
            "targetName": data.get("targetName", ""),
            "className": class_name,
            "existingClass": data.get("existingClass", ""),
            "day": day,
            "startTime": start_time,
            "endTime": data.get("endTime", ""),
            "subject": data.get("subject", ""),
            "room": data.get("room", ""),
            "facultyIds": data.get("facultyIds", []),
            "newLecture": data.get("newLecture", {}),
            "oldLecture": data.get("oldLecture", {}),
            "status": "pending",
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        db.lecture_requests.insert_one(req_doc)
        
        return jsonify({"success": True, "message": "Lecture request created", "requestCreated": True})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@timetable_bp.route("/lecture-requests/<mentor_id>", methods=["GET"])
def get_lecture_requests(mentor_id):
    try:
        requests_data = list(db.lecture_requests.find({
            "$or": [
                {"targetMentorId": mentor_id},
                {"targetFaculty": mentor_id}
            ],
            "status": "pending"
        }))

        return jsonify({
            "success": True,
            "requests": serialize_many(requests_data)
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@timetable_bp.route("/lecture-request/approve", methods=["PUT"])
def approve_lecture_request():
    try:
        data = request.get_json() or {}
        req_id = data.get("requestId")

        if not req_id:
            return jsonify({"success": False, "message": "requestId required"}), 400

        req = db.lecture_requests.find_one({"_id": ObjectId(req_id), "status": "pending"})
        
        if not req:
            return jsonify({
                "success": False,
                "message": "Request not found or already processed"
            }), 404

        # 1. Find timetable
        existing_class = req.get("existingClass")
        day = req.get("day")
        old_lecture = req.get("oldLecture", {})
        
        if existing_class and day and old_lecture:
            # 3. Remove old lecture
            db.timetables.update_one(
                {"className": existing_class},
                {
                    "$pull": {
                        f"weeklySchedule.{day}": {
                            "startTimeMins": old_lecture.get("startTimeMins"),
                            "endTimeMins": old_lecture.get("endTimeMins")
                        }
                    },
                    "$set": {"updatedAt": datetime.utcnow()}
                }
            )

        new_class = req.get("className")
        new_lecture = req.get("newLecture", {})
        new_lecture["status"] = "approved"

        if new_class and day and new_lecture:
            existing_tt = db.timetables.find_one({"className": new_class})
            
            # 4. Insert new lecture
            if existing_tt:
                db.timetables.update_one(
                    {"className": new_class},
                    {
                        "$push": {f"weeklySchedule.{day}": new_lecture},
                        "$set": {"updatedAt": datetime.utcnow()}
                    }
                )
            else:
                db.timetables.insert_one({
                    "className": new_class,
                    "weeklySchedule": {day: [new_lecture]},
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                })

        # 5. Mark request approved
        # 6. Store updatedAt
        db.lecture_requests.update_one(
            {"_id": ObjectId(req_id)},
            {"$set": {"status": "approved", "updatedAt": datetime.utcnow()}}
        )

        return jsonify({
            "success": True,
            "message": "Lecture request approved"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@timetable_bp.route("/lecture-request/reject", methods=["PUT"])
def reject_lecture_request():
    try:
        data = request.get_json() or {}
        req_id = data.get("requestId")

        if not req_id:
            return jsonify({"success": False, "message": "requestId required"}), 400

        result = db.lecture_requests.update_one(
            {"_id": ObjectId(req_id)},
            {"$set": {"status": "rejected", "updatedAt": datetime.utcnow()}}
        )

        if result.modified_count == 0:
            return jsonify({
                "success": False,
                "message": "Request not found or already processed"
            }), 404

        return jsonify({
            "success": True,
            "message": "Lecture request rejected"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 1. CREATE / UPDATE COMPLETE WEEKLY TIMETABLE
# =========================================================

@timetable_bp.route("/set-weekly", methods=["POST"])
def set_weekly_timetable():
    try:
        data = request.get_json() or {}

        class_name = data.get("className")
        mentor_id = data.get("mentorID")
        weekly_schedule = data.get("weeklySchedule")

        if not class_name or not weekly_schedule:
            return jsonify({
                "success": False,
                "message": "className and weeklySchedule are required"
            }), 400

        has_conflict = False
        conflict_return_info = {}
        valid_schedule = {}

        for day, lectures in weekly_schedule.items():
            valid_schedule[day] = []

            if not isinstance(lectures, list):
                continue

            for lec in lectures:
                start_time = lec.get("startTime")
                end_time = lec.get("endTime")

                if start_time and end_time:
                    try:
                        lec["startTimeMins"] = time_to_minutes(start_time)
                        lec["endTimeMins"] = time_to_minutes(end_time)
                    except ValueError as ve:
                        return jsonify({"success": False, "message": str(ve)}), 400
                else:
                    return jsonify({
                        "success": False,
                        "message": f"startTime and endTime required for {day}"
                    }), 400

                if lec["startTimeMins"] >= lec["endTimeMins"]:
                    return jsonify({
                        "success": False,
                        "message": f"Invalid time range in {day}"
                    }), 400

                faculty_ids = clean_id_list(lec.get("facultyIds", []))
                lec["facultyIds"] = faculty_ids

                conflicts = []

                if faculty_ids:
                    conflicts = find_conflicts(
                        faculty_ids,
                        day,
                        lec["startTimeMins"],
                        lec["endTimeMins"],
                        class_name
                    )

                actual_conflicts = [c for c in conflicts if c.get("approvalMode") == True]

                if actual_conflicts:
                    has_conflict = True

                    for conflict in actual_conflicts:
                        existing_req = db.lecture_requests.find_one({
                            "className": class_name,
                            "targetMentorId": conflict["mentorId"],
                            "day": day,
                            "startTime": lec.get("startTime"),
                            "status": "pending"
                        })
                        
                        if not existing_req:
                            db.lecture_requests.insert_one({
                                "requesterMentorId": mentor_id,
                                "targetMentorId": conflict["mentorId"],
                                "requesterName": "",
                                "targetName": conflict["mentorName"],
                                "className": class_name,
                                "existingClass": conflict["class"],
                                "day": day,
                                "startTime": lec.get("startTime"),
                                "endTime": lec.get("endTime"),
                                "subject": lec.get("subject", ""),
                                "room": lec.get("room", ""),
                                "facultyIds": lec.get("facultyIds", []),
                                "newLecture": lec,
                                "oldLecture": conflict["lecture"],
                                "status": "pending",
                                "createdAt": datetime.utcnow(),
                                "updatedAt": datetime.utcnow()
                            })
                        
                        if not conflict_return_info:
                            conflict_return_info = {
                                "conflictFacultyName": conflict["mentorName"],
                                "conflictFacultyId": conflict["mentorId"],
                                "existingClass": conflict["class"],
                                "existingSubject": conflict["subject"],
                                "existingStart": conflict["start"],
                                "existingEnd": conflict["end"]
                            }
                else:
                    lec["status"] = "approved"
                    lec["faculty"] = resolve_faculty(faculty_ids)
                    valid_schedule[day].append(lec)

        timetable_data = {
            "className": class_name,
            "mentorID": mentor_id,
            "weeklySchedule": valid_schedule,
            "updatedAt": datetime.utcnow()
        }

        existing = db.timetables.find_one({"className": class_name})

        if existing:
            db.timetables.update_one(
                {"className": class_name},
                {"$set": timetable_data}
            )
        else:
            timetable_data["createdAt"] = datetime.utcnow()
            db.timetables.insert_one(timetable_data)

        if has_conflict and conflict_return_info:
            return jsonify({
                "success": True,
                "conflict": True,
                "requestCreated": True,
                "conflictFacultyName": conflict_return_info["conflictFacultyName"],
                "conflictFacultyId": conflict_return_info["conflictFacultyId"],
                "existingClass": conflict_return_info["existingClass"],
                "existingSubject": conflict_return_info["existingSubject"],
                "existingStart": conflict_return_info["existingStart"],
                "existingEnd": conflict_return_info["existingEnd"],
                "message": "Timetable saved partially. Conflicts were routed to lecture_requests."
            })

        return jsonify({
            "success": True,
            "message": "Weekly timetable saved successfully"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 2. GET COMPLETE TIMETABLE CLASS-WISE
# =========================================================

@timetable_bp.route("/class/<class_name>", methods=["GET"])
def get_class_timetable(class_name):
    try:
        timetable = db.timetables.find_one({"className": class_name})

        if not timetable:
            return jsonify({
                "success": False,
                "message": "Timetable not found"
            }), 404

        populated_timetable = populate_timetable_faculties(timetable)

        return jsonify({
            "success": True,
            "timetable": serialize_doc(populated_timetable)
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 3. GET SPECIFIC DAY TIMETABLE
# =========================================================

@timetable_bp.route("/class/<class_name>/<day>", methods=["GET"])
def get_day_timetable(class_name, day):
    try:
        timetable = db.timetables.find_one({"className": class_name})

        if not timetable:
            return jsonify({
                "success": False,
                "message": "Timetable not found"
            }), 404

        populated_timetable = populate_timetable_faculties(timetable)
        day_schedule = populated_timetable.get("weeklySchedule", {}).get(day, [])

        return jsonify({
            "success": True,
            "className": class_name,
            "day": day,
            "schedule": day_schedule
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 4. UPDATE SINGLE DAY ONLY
# =========================================================

@timetable_bp.route("/update-day", methods=["PUT"])
def update_single_day():
    try:
        data = request.get_json() or {}

        class_name = data.get("className")
        day = data.get("day")
        schedule = data.get("schedule")
        mentor_id = data.get("mentorID", "")

        if not class_name or not day or schedule is None:
            return jsonify({
                "success": False,
                "message": "className, day, and schedule required"
            }), 400

        has_conflict = False
        valid_schedule = []
        conflict_return_info = {}

        for lec in schedule:
            start_time = lec.get("startTime")
            end_time = lec.get("endTime")

            if start_time and end_time:
                try:
                    lec["startTimeMins"] = time_to_minutes(start_time)
                    lec["endTimeMins"] = time_to_minutes(end_time)
                except ValueError as ve:
                    return jsonify({"success": False, "message": str(ve)}), 400
            else:
                return jsonify({
                    "success": False,
                    "message": f"startTime and endTime required for {day}"
                }), 400

            if lec["startTimeMins"] >= lec["endTimeMins"]:
                return jsonify({
                    "success": False,
                    "message": f"Invalid time range in {day}"
                }), 400

            faculty_ids = clean_id_list(lec.get("facultyIds", []))
            lec["facultyIds"] = faculty_ids

            conflicts = []

            if faculty_ids:
                conflicts = find_conflicts(
                    faculty_ids,
                    day,
                    lec["startTimeMins"],
                    lec["endTimeMins"],
                    class_name
                )

            actual_conflicts = [c for c in conflicts if c.get("approvalMode") == True]

            if actual_conflicts:
                has_conflict = True

                for conflict in actual_conflicts:
                    existing_req = db.lecture_requests.find_one({
                        "className": class_name,
                        "targetMentorId": conflict["mentorId"],
                        "day": day,
                        "startTime": lec.get("startTime"),
                        "status": "pending"
                    })
                    
                    if not existing_req:
                        db.lecture_requests.insert_one({
                            "requesterMentorId": mentor_id,
                            "targetMentorId": conflict["mentorId"],
                            "requesterName": "",
                            "targetName": conflict["mentorName"],
                            "className": class_name,
                            "existingClass": conflict["class"],
                            "day": day,
                            "startTime": lec.get("startTime"),
                            "endTime": lec.get("endTime"),
                            "subject": lec.get("subject", ""),
                            "room": lec.get("room", ""),
                            "facultyIds": lec.get("facultyIds", []),
                            "newLecture": lec,
                            "oldLecture": conflict["lecture"],
                            "status": "pending",
                            "createdAt": datetime.utcnow(),
                            "updatedAt": datetime.utcnow()
                        })
                    
                    if not conflict_return_info:
                        conflict_return_info = {
                            "conflictFacultyName": conflict["mentorName"],
                            "conflictFacultyId": conflict["mentorId"],
                            "existingClass": conflict["class"],
                            "existingSubject": conflict["subject"],
                            "existingStart": conflict["start"],
                            "existingEnd": conflict["end"]
                        }
            else:
                lec["status"] = "approved"
                lec["faculty"] = resolve_faculty(faculty_ids)
                valid_schedule.append(lec)

        update_field = f"weeklySchedule.{day}"

        result = db.timetables.update_one(
            {"className": class_name},
            {
                "$set": {
                    update_field: valid_schedule,
                    "updatedAt": datetime.utcnow()
                }
            }
        )

        if result.matched_count == 0:
            db.timetables.insert_one({
                "className": class_name,
                "weeklySchedule": {
                    day: valid_schedule
                },
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            })

        if has_conflict and conflict_return_info:
            return jsonify({
                "success": True,
                "conflict": True,
                "requestCreated": True,
                "conflictFacultyName": conflict_return_info["conflictFacultyName"],
                "conflictFacultyId": conflict_return_info["conflictFacultyId"],
                "existingClass": conflict_return_info["existingClass"],
                "existingSubject": conflict_return_info["existingSubject"],
                "existingStart": conflict_return_info["existingStart"],
                "existingEnd": conflict_return_info["existingEnd"],
                "message": f"{day} timetable updated partially due to conflicts."
            })

        return jsonify({
            "success": True,
            "message": f"{day} timetable updated successfully"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 5. DELETE TIMETABLE
# =========================================================

@timetable_bp.route("/delete/<class_name>", methods=["DELETE"])
def delete_timetable(class_name):
    try:
        result = db.timetables.delete_one({"className": class_name})

        if result.deleted_count == 0:
            return jsonify({
                "success": False,
                "message": "Timetable not found"
            }), 404

        return jsonify({
            "success": True,
            "message": "Timetable deleted successfully"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 6. GET ALL CLASSES TIMETABLES
# =========================================================

@timetable_bp.route("/all", methods=["GET"])
def get_all_timetables():
    try:
        timetables = list(db.timetables.find())
        result = []

        for item in timetables:
            populated = populate_timetable_faculties(item)
            result.append(serialize_doc(populated))

        return jsonify({
            "success": True,
            "count": len(result),
            "timetables": result
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 7. UPLOAD TIMETABLE PDF
# =========================================================

@timetable_bp.route("/upload-pdf", methods=["POST"])
def upload_timetable_pdf():
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file = request.files["file"]
        class_name = request.form.get("className")
        uploaded_by = request.form.get("uploadedBy")

        if not class_name:
            return jsonify({"success": False, "message": "className is required"}), 400

        if file.filename == "":
            return jsonify({"success": False, "message": "No selected file"}), 400

        if not allowed_file(file.filename):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        final_filename = f"{class_name}_{timestamp}_{filename}"

        file_path = os.path.join(UPLOAD_FOLDER, final_filename)
        file.save(file_path)

        pdf_data = {
            "className": class_name,
            "uploadedBy": uploaded_by,
            "fileName": final_filename,
            "filePath": file_path,
            "uploadedAt": datetime.utcnow()
        }

        db.timetable_pdfs.insert_one(pdf_data)

        return jsonify({
            "success": True,
            "message": "PDF uploaded successfully",
            "fileName": final_filename,
            "filePath": file_path
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 8. GET TIMETABLE PDFs
# =========================================================

@timetable_bp.route("/pdfs/<class_name>", methods=["GET"])
def get_timetable_pdfs(class_name):
    try:
        pdfs = list(db.timetable_pdfs.find({"className": class_name}))

        return jsonify({
            "success": True,
            "pdfs": serialize_many(pdfs)
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 9. ADD HOLIDAY
# =========================================================

@timetable_bp.route("/holiday/add", methods=["POST"])
def add_holiday():
    try:
        data = request.get_json() or {}

        if not data.get("date") or not data.get("title"):
            return jsonify({
                "success": False,
                "message": "date and title are required"
            }), 400

        holiday_data = {
            "date": data.get("date"),
            "title": data.get("title"),
            "description": data.get("description", ""),
            "createdAt": datetime.utcnow()
        }

        db.holidays.insert_one(holiday_data)

        return jsonify({
            "success": True,
            "message": "Holiday added successfully"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 10. GET HOLIDAYS
# =========================================================

@timetable_bp.route("/holidays", methods=["GET"])
def get_holidays():
    try:
        holidays = list(db.holidays.find())

        return jsonify({
            "success": True,
            "holidays": serialize_many(holidays)
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500