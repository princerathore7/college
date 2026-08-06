from flask import Blueprint, request, jsonify, current_app
from flask_cors import CORS
from werkzeug.utils import secure_filename
from bson import ObjectId
from datetime import datetime
import os
import re

# ---------------- Blueprint ----------------
timetable_bp = Blueprint(
    "timetable_bp",
    __name__,
    url_prefix="/api/timetable"
)

CORS(timetable_bp)

# ---------------- MongoDB ----------------
from db import db

# ---------------- Upload Config ----------------
UPLOAD_FOLDER = "uploads/timetables"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {"pdf"}


# =========================================================
# Helper Functions
# =========================================================

def allowed_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def serialize_doc(doc):
    if not doc:
        return None
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

def time_to_minutes(time_str):
    """Converts a time string like '08:00 AM' to total minutes from midnight."""
    try:
        dt = datetime.strptime(time_str.strip(), "%I:%M %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        raise ValueError(f"Invalid time format: {time_str}. Expected format: 'hh:mm AM/PM'")

def resolve_faculty(faculty_ids):
    """Fetches mentor details for a list of mentor IDs."""
    if not faculty_ids:
        return []
    
    mentors = list(db.mentors.find({"mentorId": {"$in": faculty_ids}}))
    resolved = []
    for mentor in mentors:
        resolved.append({
            "mentorId": mentor.get("mentorId"),
            "name": mentor.get("name"),
            "subject": mentor.get("subject")
        })
    return resolved

def populate_timetable_faculties(timetable):
    """Replaces facultyIds with resolved faculty objects in a timetable document."""
    if not timetable or "weeklySchedule" not in timetable:
        return timetable

    # Gather all unique faculty IDs
    unique_faculty_ids = set()
    for day, schedule in timetable.get("weeklySchedule", {}).items():
        for lec in schedule:
            if "facultyIds" in lec and isinstance(lec["facultyIds"], list):
                for fid in lec["facultyIds"]:
                    unique_faculty_ids.add(fid)

    # Fetch all needed faculties at once
    resolved_faculties_map = { 
        f["mentorId"]: f for f in resolve_faculty(list(unique_faculty_ids)) 
    }

    # Populate the timetable
    for day, schedule in timetable.get("weeklySchedule", {}).items():
        for lec in schedule:
            if "facultyIds" in lec and isinstance(lec["facultyIds"], list):
                lec["faculty"] = []
                for fid in lec["facultyIds"]:
                    if fid in resolved_faculties_map:
                        lec["faculty"].append(resolved_faculties_map[fid])
                # Optionally remove facultyIds from response to strictly follow format
                # del lec["facultyIds"]

    return timetable

def find_conflicts(faculty_ids, day, start_mins, end_mins, current_class):
    """
    Checks if any of the faculty_ids are already scheduled in an overlapping time 
    on the given day for a DIFFERENT class.
    Overlap condition: newStart < oldEnd AND newEnd > oldStart
    """
    conflicts = []
    for fid in faculty_ids:
        # Check if this faculty is busy in another class
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
            # Extract specific lecture details causing the conflict
            for lec in conflict_doc.get("weeklySchedule", {}).get(day, []):
                if (
                    fid in lec.get("facultyIds", []) and
                    lec.get("status") == "approved" and
                    lec.get("startTimeMins", 0) < end_mins and
                    lec.get("endTimeMins", 0) > start_mins
                ):
                    conflicts.append({
                        "targetFaculty": fid,
                        "existingClass": conflict_doc["className"],
                        "existingSubject": lec.get("subject", ""),
                        "existingStart": lec.get("startTime"),
                        "existingEnd": lec.get("endTime")
                    })
    return conflicts


# =========================================================
# MENTOR SEARCH API
# =========================================================

@timetable_bp.route("/mentor/search", methods=["GET"])
def search_mentors():
    """Search mentors by mentorId or name using regex."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    try:
        regex = re.compile(query, re.IGNORECASE)
        mentors = list(db.mentors.find({
            "$or": [
                {"mentorId": regex},
                {"name": regex}
            ]
        }).limit(15))

        result = []
        for mentor in mentors:
            result.append({
                "mentorId": mentor.get("mentorId"),
                "name": mentor.get("name"),
                "subject": mentor.get("subject")
            })

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# LECTURE REQUESTS APIs
# =========================================================

@timetable_bp.route("/lecture-requests/<mentor_id>", methods=["GET"])
def get_lecture_requests(mentor_id):
    try:
        requests = list(db.lecture_requests.find({
            "targetFaculty": mentor_id,
            "status": "pending"
        }))
        return jsonify({
            "success": True,
            "requests": [serialize_doc(r) for r in requests]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/lecture-request/approve", methods=["PUT"])
def approve_lecture_request():
    try:
        req_id = request.json.get("requestId")
        if not req_id:
            return jsonify({"success": False, "message": "requestId required"}), 400
        
        result = db.lecture_requests.update_one(
            {"_id": ObjectId(req_id)},
            {"$set": {"status": "approved", "updatedAt": datetime.utcnow()}}
        )
        if result.modified_count == 0:
            return jsonify({"success": False, "message": "Request not found or already processed"}), 404
            
        return jsonify({"success": True, "message": "Lecture request approved"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/lecture-request/reject", methods=["PUT"])
def reject_lecture_request():
    try:
        req_id = request.json.get("requestId")
        if not req_id:
            return jsonify({"success": False, "message": "requestId required"}), 400
        
        result = db.lecture_requests.update_one(
            {"_id": ObjectId(req_id)},
            {"$set": {"status": "rejected", "updatedAt": datetime.utcnow()}}
        )
        if result.modified_count == 0:
            return jsonify({"success": False, "message": "Request not found or already processed"}), 404
            
        return jsonify({"success": True, "message": "Lecture request rejected"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 1. CREATE / UPDATE COMPLETE WEEKLY TIMETABLE
# =========================================================

@timetable_bp.route("/set-weekly", methods=["POST"])
def set_weekly_timetable():
    try:
        data = request.json
        class_name = data.get("className")
        mentor_id = data.get("mentorID")
        weekly_schedule = data.get("weeklySchedule")

        if not class_name or not weekly_schedule:
            return jsonify({"success": False, "message": "className and weeklySchedule are required"}), 400

        has_conflict = False
        valid_schedule = {}

        for day, lectures in weekly_schedule.items():
            valid_schedule[day] = []
            
            for lec in lectures:
                # Add validation and minute calculations
                if "startTime" in lec and "endTime" in lec:
                    try:
                        lec["startTimeMins"] = time_to_minutes(lec["startTime"])
                        lec["endTimeMins"] = time_to_minutes(lec["endTime"])
                    except ValueError as ve:
                        return jsonify({"success": False, "message": str(ve)}), 400
                        
                faculty_ids = lec.get("facultyIds", [])
                
                # Verify faculties actually exist
                if faculty_ids:
                    existing_faculties = db.mentors.count_documents({"mentorId": {"$in": faculty_ids}})
                    if existing_faculties != len(faculty_ids):
                        return jsonify({"success": False, "message": f"One or more faculty IDs are invalid in {day}"}), 400

                # Detect Conflicts for subjects with assigned faculty
                conflicts = []
                if faculty_ids and "startTimeMins" in lec:
                    conflicts = find_conflicts(
                        faculty_ids, 
                        day, 
                        lec["startTimeMins"], 
                        lec["endTimeMins"], 
                        class_name
                    )

                if conflicts:
                    has_conflict = True
                    for conflict in conflicts:
                        db.lecture_requests.insert_one({
                            "className": class_name,
                            "targetFaculty": conflict["targetFaculty"],
                            "existingClass": conflict["existingClass"],
                            "day": day,
                            "startTime": lec["startTime"],
                            "endTime": lec["endTime"],
                            "subject": lec.get("subject", ""),
                            "status": "pending",
                            "createdAt": datetime.utcnow()
                        })
                else:
                    lec["status"] = "approved"
                    valid_schedule[day].append(lec)

        # Upsert valid timetable
        timetable_data = {
            "className": class_name,
            "mentorID": mentor_id,
            "weeklySchedule": valid_schedule,
            "updatedAt": datetime.utcnow()
        }

        existing = db.timetables.find_one({"className": class_name})
        if existing:
            db.timetables.update_one({"className": class_name}, {"$set": timetable_data})
        else:
            timetable_data["createdAt"] = datetime.utcnow()
            db.timetables.insert_one(timetable_data)

        if has_conflict:
            return jsonify({
                "success": True,
                "conflict": True,
                "requestCreated": True,
                "message": "Timetable saved partially. Conflicts were routed to lecture_requests."
            })
            
        return jsonify({"success": True, "message": "Weekly timetable saved successfully"})

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
            return jsonify({"success": False, "message": "Timetable not found"}), 404

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
            return jsonify({"success": False, "message": "Timetable not found"}), 404

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
        data = request.json
        class_name = data.get("className")
        day = data.get("day")
        schedule = data.get("schedule")

        if not class_name or not day or schedule is None:
            return jsonify({"success": False, "message": "className, day, and schedule required"}), 400

        has_conflict = False
        valid_schedule = []

        for lec in schedule:
            if "startTime" in lec and "endTime" in lec:
                try:
                    lec["startTimeMins"] = time_to_minutes(lec["startTime"])
                    lec["endTimeMins"] = time_to_minutes(lec["endTime"])
                except ValueError as ve:
                    return jsonify({"success": False, "message": str(ve)}), 400
                    
            faculty_ids = lec.get("facultyIds", [])
            conflicts = []
            
            if faculty_ids and "startTimeMins" in lec:
                conflicts = find_conflicts(
                    faculty_ids, 
                    day, 
                    lec["startTimeMins"], 
                    lec["endTimeMins"], 
                    class_name
                )

            if conflicts:
                has_conflict = True
                for conflict in conflicts:
                    db.lecture_requests.insert_one({
                        "className": class_name,
                        "targetFaculty": conflict["targetFaculty"],
                        "existingClass": conflict["existingClass"],
                        "day": day,
                        "startTime": lec["startTime"],
                        "endTime": lec["endTime"],
                        "subject": lec.get("subject", ""),
                        "status": "pending",
                        "createdAt": datetime.utcnow()
                    })
            else:
                lec["status"] = "approved"
                valid_schedule.append(lec)

        update_field = f"weeklySchedule.{day}"
        db.timetables.update_one(
            {"className": class_name},
            {
                "$set": {
                    update_field: valid_schedule,
                    "updatedAt": datetime.utcnow()
                }
            }
        )

        if has_conflict:
            return jsonify({
                "success": True,
                "conflict": True,
                "requestCreated": True,
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
            return jsonify({"success": False, "message": "Timetable not found"}), 404

        return jsonify({"success": True, "message": "Timetable deleted successfully"})

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
        result = [serialize_doc(pdf) for pdf in pdfs]

        return jsonify({
            "success": True,
            "pdfs": result
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================================================
# 9. ADD HOLIDAY
# =========================================================

@timetable_bp.route("/holiday/add", methods=["POST"])
def add_holiday():
    try:
        data = request.json
        
        if not data.get("date") or not data.get("title"):
            return jsonify({"success": False, "message": "date and title are required"}), 400

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
        result = [serialize_doc(holiday) for holiday in holidays]

        return jsonify({
            "success": True,
            "holidays": result
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500