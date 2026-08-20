from flask import Blueprint, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from bson import ObjectId
from datetime import datetime
import os
import re
from db import db

timetable_bp = Blueprint(
    "timetable_bp",
    __name__,
    url_prefix="/api/timetable"
)
CORS(timetable_bp)
UPLOAD_FOLDER = "uploads/timetables"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
ALLOWED_EXTENSIONS = {"pdf"}

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
    try:
        return (
            int(new_start) < int(existing_end)
            and
            int(new_end) > int(existing_start)
        )
    except (TypeError, ValueError):
        return False

def lecture_is_active(lecture):
    if not isinstance(lecture, dict):
        return False
    status = str(
        lecture.get("status", "approved")
    ).strip().lower()
    return status not in {
        "pending",
        "rejected",
        "cancelled",
        "canceled"
    }

def get_mentor_info(mentor_id):
    if not mentor_id:
        return {
            "mentorId": "",
            "name": "Unknown Faculty",
            "approvalMode": False,
            "subject": "",
            "branch": ""
        }
    mentor_id = str(mentor_id).strip()
    mentor = db.mentors.find_one(
        {"mentorId": mentor_id},
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
        "mentorId": mentor.get("mentorId"),
        "name": mentor.get("name", "Unknown Faculty"),
        "approvalMode": bool(mentor.get("approvalMode", False)),
        "subject": mentor.get("subject", ""),
        "branch": mentor.get("branch", "")
    }

def resolve_faculty(faculty_ids):
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
        mentor = mentor_map.get(str(faculty_id).strip())
        if mentor:
            resolved.append({
                "mentorId": mentor.get("mentorId"),
                "name": mentor.get("name", "Unknown Faculty"),
                "subject": mentor.get("subject", ""),
                "branch": mentor.get("branch", ""),
                "approvalMode": bool(mentor.get("approvalMode", False))
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

def get_lecture_faculty_ids(lecture):
    if not isinstance(lecture, dict):
        return []
    
    faculty_ids = clean_id_list(lecture.get("facultyIds", []))
    if faculty_ids:
        return faculty_ids
        
    faculty = lecture.get("faculty", [])
    if isinstance(faculty, list):
        extracted = []
        for item in faculty:
            if not isinstance(item, dict):
                continue
            mentor_id = (
                item.get("mentorId")
                or item.get("facultyId")
                or item.get("id")
            )
            if mentor_id:
                extracted.append(mentor_id)
        return clean_id_list(extracted)
    return []

def normalize_lecture(lecture):
    if not isinstance(lecture, dict):
        return lecture
    
    lecture["facultyIds"] = get_lecture_faculty_ids(lecture)
    start_time = lecture.get("startTime")
    end_time = lecture.get("endTime")
    
    if start_time and end_time:
        try:
            lecture["startTimeMins"] = time_to_minutes(start_time)
            lecture["endTimeMins"] = time_to_minutes(end_time)
        except ValueError:
            pass
            
    if not lecture.get("status"):
        lecture["status"] = "approved"
    return lecture

def prepare_lecture(lecture, class_name, day):
    if not isinstance(lecture, dict):
        raise ValueError(f"Invalid lecture in {day}")
        
    start_time = lecture.get("startTime")
    end_time = lecture.get("endTime")
    
    if not start_time or not end_time:
        raise ValueError(f"startTime and endTime required for {day}")
        
    start_mins = time_to_minutes(start_time)
    end_mins = time_to_minutes(end_time)
    
    if start_mins >= end_mins:
        raise ValueError(f"Invalid time range in {day}: {start_time} - {end_time}")
        
    faculty_ids = clean_id_list(lecture.get("facultyIds", []))
    lecture["facultyIds"] = faculty_ids
    lecture["startTimeMins"] = start_mins
    lecture["endTimeMins"] = end_mins
    return lecture

def populate_timetable_faculties(timetable):
    if not timetable:
        return timetable
    weekly_schedule = timetable.get("weeklySchedule", {})
    if not isinstance(weekly_schedule, dict):
        return timetable
        
    for day, schedule in weekly_schedule.items():
        if not isinstance(schedule, list):
            continue
        for lecture in schedule:
            if not isinstance(lecture, dict):
                continue
            normalize_lecture(lecture)
            faculty_ids = get_lecture_faculty_ids(lecture)
            lecture["facultyIds"] = faculty_ids
            lecture["faculty"] = resolve_faculty(faculty_ids)
    return timetable

def find_conflicts(
    faculty_ids,
    day,
    start_mins,
    end_mins,
    current_class=None,
    exclude_lecture=None
):
    conflicts = []
    faculty_ids = clean_id_list(faculty_ids)
    if not faculty_ids:
        return conflicts
        
    try:
        start_mins = int(start_mins)
        end_mins = int(end_mins)
    except (TypeError, ValueError):
        return conflicts
        
    if start_mins >= end_mins:
        return conflicts
        
    timetables = db.timetables.find({})
    for timetable in timetables:
        timetable_class = str(timetable.get("className", "")).strip()
        if current_class is not None and timetable_class == str(current_class).strip():
            continue
            
        weekly_schedule = timetable.get("weeklySchedule", {})
        if not isinstance(weekly_schedule, dict):
            continue
            
        day_schedule = weekly_schedule.get(day, [])
        if not isinstance(day_schedule, list):
            continue
            
        for lecture in day_schedule:
            if not isinstance(lecture, dict):
                continue
            lecture = normalize_lecture(lecture)
            if not lecture_is_active(lecture):
                continue
                
            existing_faculty_ids = get_lecture_faculty_ids(lecture)
            matching_faculty = [fid for fid in faculty_ids if fid in existing_faculty_ids]
            if not matching_faculty:
                continue
                
            existing_start = lecture.get("startTimeMins")
            existing_end = lecture.get("endTimeMins")
            
            if existing_start is None or existing_end is None:
                try:
                    existing_start = time_to_minutes(lecture.get("startTime"))
                    existing_end = time_to_minutes(lecture.get("endTime"))
                except (ValueError, TypeError):
                    continue
                    
            if not lectures_overlap(start_mins, end_mins, existing_start, existing_end):
                continue
                
            if exclude_lecture:
                same_id = (
                    exclude_lecture.get("_id")
                    and lecture.get("_id")
                    and str(exclude_lecture.get("_id")) == str(lecture.get("_id"))
                )
                if same_id:
                    continue
                    
            for fid in matching_faculty:
                mentor_info = get_mentor_info(fid)
                conflicts.append({
                    "mentorId": fid,
                    "mentorName": mentor_info.get("name", "Unknown Faculty"),
                    "approvalMode": bool(mentor_info.get("approvalMode", False)),
                    "class": timetable_class,
                    "subject": lecture.get("subject", ""),
                    "day": day,
                    "room": lecture.get("room", ""),
                    "lecture": lecture,
                    "start": lecture.get("startTime"),
                    "end": lecture.get("endTime"),
                    "startTimeMins": existing_start,
                    "endTimeMins": existing_end
                })
    return conflicts

def find_occupied_lecture_for_mentor(
    mentor_id,
    day,
    start_mins,
    end_mins,
    class_name=None,
    require_approval_mode=False
):
    mentor_id = str(mentor_id).strip()
    if not mentor_id:
        return None
    try:
        start_mins = int(start_mins)
        end_mins = int(end_mins)
    except (TypeError, ValueError):
        return None
        
    if start_mins >= end_mins:
        return None
        
    class_filter = str(class_name).strip() if class_name else None
    timetables = db.timetables.find({})
    
    for timetable in timetables:
        timetable_class = str(timetable.get("className", "")).strip()
        if class_filter and timetable_class != class_filter:
            continue
            
        weekly_schedule = timetable.get("weeklySchedule", {})
        if not isinstance(weekly_schedule, dict):
            continue
            
        day_schedule = weekly_schedule.get(day, [])
        if not isinstance(day_schedule, list):
            continue
            
        for lecture in day_schedule:
            if not isinstance(lecture, dict):
                continue
            lecture = normalize_lecture(lecture)
            if not lecture_is_active(lecture):
                continue
                
            faculty_ids = get_lecture_faculty_ids(lecture)
            if mentor_id not in faculty_ids:
                continue
                
            existing_start = lecture.get("startTimeMins")
            existing_end = lecture.get("endTimeMins")
            
            if existing_start is None or existing_end is None:
                continue
                
            if not lectures_overlap(start_mins, end_mins, existing_start, existing_end):
                continue
                
            mentor_info = get_mentor_info(mentor_id)
            return {
                "found": True,
                "approvalMode": bool(mentor_info.get("approvalMode", False)),
                "mentorId": mentor_id,
                "mentorName": mentor_info.get("name", "Unknown Faculty"),
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

def lecture_request_exists(
    class_name,
    target_mentor_id,
    day,
    start_time,
    end_time=None
):
    query = {
        "className": class_name,
        "targetMentorId": str(target_mentor_id).strip(),
        "day": day,
        "startTime": start_time,
        "status": "pending"
    }
    if end_time:
        query["endTime"] = end_time
    existing = db.lecture_requests.find_one(query)
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
    target_mentor_id = str(target_conflict.get("mentorId", "")).strip()
    if not target_mentor_id:
        return False
        
    if lecture_request_exists(class_name, target_mentor_id, day, start_time, end_time):
        return False
        
    mentor_info = get_mentor_info(target_mentor_id)
    request_document = {
        "requesterMentorId": str(requester_mentor_id or "").strip(),
        "targetMentorId": target_mentor_id,
        "requesterName": "",
        "targetName": mentor_info.get("name", target_conflict.get("mentorName", "Unknown Faculty")),
        "className": class_name,
        "existingClass": target_conflict.get("class", class_name),
        "day": day,
        "startTime": start_time,
        "endTime": end_time,
        "subject": new_lecture.get("subject", ""),
        "room": new_lecture.get("room", ""),
        "facultyIds": get_lecture_faculty_ids(new_lecture),
        "newLecture": dict(new_lecture),
        "oldLecture": dict(target_conflict.get("lecture", {})),
        "status": "pending",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }
    db.lecture_requests.insert_one(request_document)
    return True

@timetable_bp.route("/mentor/search", methods=["GET"])
def search_mentors():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"success": True, "mentors": []})
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
                    "branch": 1,
                    "approvalMode": 1
                }
            ).limit(15)
        )
        return jsonify({"success": True, "mentors": mentors})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/toggle-approval-mode", methods=["PUT"])
def toggle_approval_mode():
    try:
        data = request.get_json() or {}
        mentor_id = data.get("mentorId")
        approval_mode = data.get("approvalMode")
        
        if not mentor_id or approval_mode is None:
            return jsonify({"success": False, "message": "mentorId and approvalMode required"}), 400
            
        result = db.mentors.update_one(
            {"mentorId": str(mentor_id).strip()},
            {"$set": {"approvalMode": bool(approval_mode)}}
        )
        if result.matched_count == 0:
            return jsonify({"success": False, "message": "Mentor not found"}), 404
            
        return jsonify({"success": True, "approvalMode": bool(approval_mode), "message": "Approval mode updated"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/approval-mode/<mentor_id>", methods=["GET"])
def get_approval_mode(mentor_id):
    try:
        mentor = db.mentors.find_one({"mentorId": str(mentor_id).strip()})
        if not mentor:
            return jsonify({"success": False, "message": "Mentor not found"}), 404
        return jsonify({"success": True, "approvalMode": bool(mentor.get("approvalMode", False))})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/request-lecture", methods=["POST"])
def request_lecture():
    try:
        data = request.get_json() or {}
        target_id = data.get("targetMentorId")
        day = data.get("day")
        start_time = data.get("startTime")
        end_time = data.get("endTime")
        class_name = data.get("className")
        requester_id = data.get("requesterMentorId", "")
        
        if not all([target_id, day, start_time, end_time, class_name]):
            return jsonify({"success": False, "message": "targetMentorId, day, startTime, endTime and className are required"}), 400
            
        target_id = str(target_id).strip()
        class_name = str(class_name).strip()
        start_mins = time_to_minutes(start_time)
        end_mins = time_to_minutes(end_time)
        
        if start_mins >= end_mins:
            return jsonify({"success": False, "message": "Invalid time range"}), 400
            
        occupied = find_occupied_lecture_for_mentor(
            mentor_id=target_id,
            day=day,
            start_mins=start_mins,
            end_mins=end_mins,
            class_name=class_name,
            require_approval_mode=True
        )
        
        if not occupied:
            return jsonify({
                "success": False,
                "conflict": False,
                "requestCreated": False,
                "message": "No active lecture assigned to this faculty was found at the selected time."
            }), 400
            
        if not occupied.get("approvalMode", False):
            return jsonify({
                "success": False,
                "conflict": True,
                "requestCreated": False,
                "message": "The assigned faculty is occupied, but approval mode is disabled."
            }), 409
            
        old_lecture = occupied.get("lecture", {})
        new_lecture = data.get("newLecture", {})
        if not isinstance(new_lecture, dict):
            new_lecture = {}
            
        new_lecture.setdefault("startTime", start_time)
        new_lecture.setdefault("endTime", end_time)
        new_lecture.setdefault("subject", data.get("subject", ""))
        new_lecture.setdefault("room", data.get("room", ""))
        new_lecture["startTimeMins"] = start_mins
        new_lecture["endTimeMins"] = end_mins
        
        faculty_ids = clean_id_list(data.get("facultyIds", []))
        if not faculty_ids:
            requester_id_clean = str(requester_id or "").strip()
            if requester_id_clean:
                faculty_ids = [requester_id_clean]
            else:
                faculty_ids = [target_id]
        new_lecture["facultyIds"] = faculty_ids
        
        already_exists = lecture_request_exists(class_name, target_id, day, start_time, end_time)
        if already_exists:
            return jsonify({
                "success": True,
                "conflict": True,
                "requestCreated": False,
                "alreadyExists": True,
                "targetMentorId": target_id,
                "targetMentorName": occupied.get("mentorName"),
                "message": "A pending lecture request already exists for this faculty."
            }), 200
            
        created = create_lecture_request(
            requester_mentor_id=requester_id,
            target_conflict=occupied,
            class_name=class_name,
            day=day,
            start_time=start_time,
            end_time=end_time,
            new_lecture=new_lecture
        )
        
        return jsonify({
            "success": True,
            "conflict": True,
            "requestCreated": created,
            "targetMentorId": target_id,
            "targetMentorName": occupied.get("mentorName"),
            "existingClass": occupied.get("class"),
            "existingSubject": occupied.get("subject"),
            "existingStart": occupied.get("start"),
            "existingEnd": occupied.get("end"),
            "oldLecture": old_lecture,
            "message": "Lecture request sent successfully to the assigned faculty."
        }), 200
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/lecture-requests/<mentor_id>", methods=["GET"])
def get_lecture_requests(mentor_id):
    try:
        mentor_id = str(mentor_id).strip()
        requests_data = list(
            db.lecture_requests.find(
                {
                    "$or": [
                        {"targetMentorId": mentor_id},
                        {"targetFaculty": mentor_id}
                    ],
                    "status": "pending"
                }
            ).sort("createdAt", -1)
        )
        return jsonify({"success": True, "requests": serialize_many(requests_data)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/lecture-request/approve-update", methods=["PUT"])
def approve_lecture_request_and_update_timetable():
    try:
        data = request.get_json(silent=True) or {}
        req_id = data.get("requestId")
        mentor_id = data.get("mentorId") or data.get("approverMentorId")
        
        if not req_id:
            return jsonify({"success": False, "message": "requestId required"}), 400
        if not mentor_id:
            return jsonify({"success": False, "message": "mentorId required"}), 400
            
        mentor_id = str(mentor_id).strip()
        
        try:
            object_id = ObjectId(str(req_id))
        except Exception:
            return jsonify({"success": False, "message": "Invalid requestId"}), 400
            
        req = db.lecture_requests.find_one({"_id": object_id, "status": "pending"})
        if not req:
            return jsonify({"success": False, "message": "Request not found or already processed"}), 404
            
        target_mentor_id = str(req.get("targetMentorId", "")).strip()
        if target_mentor_id and mentor_id != target_mentor_id:
            return jsonify({"success": False, "message": "This request is not assigned to this mentor."}), 403
            
        old_class = req.get("existingClass")
        new_class = req.get("className")
        original_day = req.get("day")
        old_lecture = req.get("oldLecture", {})
        stored_new_lecture = req.get("newLecture", {})
        
        if not old_class or not new_class or not original_day:
            return jsonify({"success": False, "message": "Missing class or day information in request"}), 409
            
        approved_lecture = data.get("approvedLecture")
        if not isinstance(approved_lecture, dict) or not approved_lecture:
            approved_lecture = dict(stored_new_lecture)
        else:
            merged = dict(stored_new_lecture)
            merged.update(approved_lecture)
            approved_lecture = merged
            
        day = approved_lecture.get("day") or data.get("day") or original_day
        subject = str(approved_lecture.get("subject", req.get("subject", "")) or "").strip()
        room = str(approved_lecture.get("room", req.get("room", "")) or "").strip()
        start_time = approved_lecture.get("startTime") or req.get("startTime")
        end_time = approved_lecture.get("endTime") or req.get("endTime")
        
        if not start_time or not end_time:
            return jsonify({"success": False, "message": "startTime and endTime are required"}), 400
            
        new_start_mins = time_to_minutes(start_time)
        new_end_mins = time_to_minutes(end_time)
        
        if new_start_mins >= new_end_mins:
            return jsonify({"success": False, "message": "Invalid time range"}), 400
            
        faculty_ids = clean_id_list(approved_lecture.get("facultyIds", []))
        if not faculty_ids:
            requester_id = str(req.get("requesterMentorId", "")).strip()
            if requester_id:
                faculty_ids = [requester_id]
            else:
                return jsonify({"success": False, "message": "Requested faculty could not be determined."}), 409
                
        final_lecture = dict(approved_lecture)
        final_lecture["day"] = day
        final_lecture["subject"] = subject
        final_lecture["room"] = room
        final_lecture["startTime"] = str(start_time).strip()
        final_lecture["endTime"] = str(end_time).strip()
        final_lecture["startTimeMins"] = new_start_mins
        final_lecture["endTimeMins"] = new_end_mins
        final_lecture["facultyIds"] = faculty_ids
        final_lecture["status"] = "approved"
        final_lecture["faculty"] = resolve_faculty(faculty_ids)
        
        # 1. Fetch old timetable
        old_tt = db.timetables.find_one({"className": old_class})
        if not old_tt:
            return jsonify({"success": False, "message": "Old timetable not found."}), 409
            
        old_schedule = old_tt.get("weeklySchedule", {}).get(day, [])
        if not isinstance(old_schedule, list):
            old_schedule = []
            
        # Robust filtering to remove the old occupied lecture cleanly and avoid duplication
        old_start = old_lecture.get("startTimeMins")
        old_end = old_lecture.get("endTimeMins")
        if old_start is None and old_lecture.get("startTime"):
            try:
                old_start = time_to_minutes(old_lecture.get("startTime"))
            except Exception:
                pass
        if old_end is None and old_lecture.get("endTime"):
            try:
                old_end = time_to_minutes(old_lecture.get("endTime"))
            except Exception:
                pass

        updated_old_schedule = []
        for lec in old_schedule:
            if not isinstance(lec, dict):
                continue
            normalize_lecture(lec)
            
            # Check if this lecture matches the old occupied slot to be removed
            is_match = False
            if old_start is not None and old_end is not None:
                if lec.get("startTimeMins") == old_start and lec.get("endTimeMins") == old_end:
                    lec_facs = get_lecture_faculty_ids(lec)
                    if not target_mentor_id or target_mentor_id in lec_facs:
                        is_match = True
            if not is_match and old_lecture.get("_id") and str(lec.get("_id")) == str(old_lecture.get("_id")):
                is_match = True
                
            if not is_match:
                updated_old_schedule.append(lec)

        # 2. Fetch destination timetable
        destination_tt = db.timetables.find_one({"className": new_class})
        destination_schedule = []
        if destination_tt:
            destination_schedule = destination_tt.get("weeklySchedule", {}).get(day, [])
        if not isinstance(destination_schedule, list):
            destination_schedule = []
            
        # Filter destination schedule to prevent duplicate entry of the same new lecture if it already exists
        cleaned_destination_schedule = []
        for lec in destination_schedule:
            if not isinstance(lec, dict):
                continue
            normalize_lecture(lec)
            # If same time slot exists, we replace it with the new updated approved lecture
            if lec.get("startTimeMins") == new_start_mins and lec.get("endTimeMins") == new_end_mins:
                # Check faculty or subject overlap to avoid duplication
                continue
            cleaned_destination_schedule.append(lec)
            
        cleaned_destination_schedule.append(final_lecture)
        
        # 3. Save updates atomically or sequentially with rollbacks
        if old_class == new_class:
            result = db.timetables.update_one(
                {"className": old_class},
                {
                    "$set": {
                        f"weeklySchedule.{day}": cleaned_destination_schedule,
                        "updatedAt": datetime.utcnow()
                    }
                }
            )
            if result.matched_count == 0:
                return jsonify({"success": False, "message": "Timetable could not be updated."}), 500
        else:
            # Update old class schedule
            old_res = db.timetables.update_one(
                {"className": old_class},
                {
                    "$set": {
                        f"weeklySchedule.{day}": updated_old_schedule,
                        "updatedAt": datetime.utcnow()
                    }
                }
            )
            if old_res.matched_count == 0:
                return jsonify({"success": False, "message": "Old timetable could not be updated."}), 500
                
            if destination_tt:
                dest_res = db.timetables.update_one(
                    {"className": new_class},
                    {
                        "$set": {
                            f"weeklySchedule.{day}": cleaned_destination_schedule,
                            "updatedAt": datetime.utcnow()
                        }
                    }
                )
                if dest_res.matched_count == 0:
                    # Rollback old
                    db.timetables.update_one(
                        {"className": old_class},
                        {"$set": {f"weeklySchedule.{day}": old_schedule, "updatedAt": datetime.utcnow()}}
                    )
                    return jsonify({"success": False, "message": "Destination timetable could not be updated. Restored."}), 500
            else:
                try:
                    db.timetables.insert_one({
                        "className": new_class,
                        "mentorID": req.get("requesterMentorId", ""),
                        "weeklySchedule": {day: [final_lecture]},
                        "createdAt": datetime.utcnow(),
                        "updatedAt": datetime.utcnow()
                    })
                except Exception as ex:
                    db.timetables.update_one(
                        {"className": old_class},
                        {"$set": {f"weeklySchedule.{day}": old_schedule, "updatedAt": datetime.utcnow()}}
                    )
                    return jsonify({"success": False, "message": f"Destination creation failed: {str(ex)}"}), 500

        # 4. Mark request approved
        approval_result = db.lecture_requests.update_one(
            {"_id": object_id, "status": "pending"},
            {
                "$set": {
                    "status": "approved",
                    "processedBy": mentor_id,
                    "processedAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow(),
                    "approvedLecture": final_lecture
                }
            }
        )
        
        return jsonify({
            "success": True,
            "message": "Lecture approved and timetable updated successfully without duplicates.",
            "requestId": str(req_id),
            "className": new_class,
            "day": day,
            "timetableUpdated": True,
            "requestStatusUpdated": True
        }), 200
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        print("APPROVE + UPDATE ERROR:", repr(e))
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/lecture-request/reject", methods=["PUT"])
def reject_lecture_request():
    try:
        data = request.get_json(silent=True) or {}
        req_id = data.get("requestId")
        mentor_id = data.get("mentorId") or data.get("approverMentorId")
        
        if not req_id or not mentor_id:
            return jsonify({"success": False, "message": "requestId and mentorId required"}), 400
            
        mentor_id = str(mentor_id).strip()
        try:
            object_id = ObjectId(str(req_id))
        except Exception:
            return jsonify({"success": False, "message": "Invalid requestId"}), 400
            
        req = db.lecture_requests.find_one({"_id": object_id, "status": "pending"})
        if not req:
            return jsonify({"success": False, "message": "Request not found or already processed"}), 404
            
        target_mentor_id = str(req.get("targetMentorId", "")).strip()
        if target_mentor_id and mentor_id != target_mentor_id:
            return jsonify({"success": False, "message": "This request is not assigned to this mentor."}), 403
            
        result = db.lecture_requests.delete_one({"_id": object_id, "status": "pending"})
        if result.deleted_count == 0:
            return jsonify({"success": False, "message": "Request not found or already processed"}), 404
            
        return jsonify({
            "success": True,
            "message": "Lecture request rejected and deleted successfully.",
            "requestId": str(req_id),
            "targetMentorId": mentor_id,
            "deleted": True
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

def process_lecture_for_save(lecture, class_name, day, requester_mentor_id):
    lecture = prepare_lecture(lecture, class_name, day)
    faculty_ids = lecture.get("facultyIds", [])
    conflicts = []
    
    if faculty_ids:
        conflicts = find_conflicts(
            faculty_ids=faculty_ids,
            day=day,
            start_mins=lecture["startTimeMins"],
            end_mins=lecture["endTimeMins"],
            current_class=class_name
        )
        
    approval_conflicts = [c for c in conflicts if c.get("approvalMode") is True]
    requests_created = []
    
    if approval_conflicts:
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
                requests_created.append(conflict)
        return {
            "save": False,
            "lecture": lecture,
            "conflicts": conflicts,
            "approvalConflicts": approval_conflicts,
            "requestsCreated": requests_created
        }
        
    lecture["status"] = "approved"
    lecture["faculty"] = resolve_faculty(faculty_ids)
    return {
        "save": True,
        "lecture": lecture,
        "conflicts": conflicts,
        "approvalConflicts": [],
        "requestsCreated": []
    }
@timetable_bp.route("/set-weekly", methods=["POST"])
def set_weekly_timetable():
    try:
        data = request.get_json() or {}
        class_name = data.get("className")
        mentor_id = data.get("mentorID")
        weekly_schedule = data.get("weeklySchedule")
        
        if not class_name:
            return jsonify({"success": False, "message": "className is required"}), 400
        if not isinstance(weekly_schedule, dict):
            return jsonify({"success": False, "message": "weeklySchedule must be an object"}), 400
            
        existing_tt = db.timetables.find_one({"className": class_name})
        existing_weekly = existing_tt.get("weeklySchedule", {}) if existing_tt else {}
        final_schedule = dict(existing_weekly)
        
        has_conflict = False
        requests_created = []
        conflict_info = []
        
        for day, lectures in weekly_schedule.items():
            if not isinstance(lectures, list):
                return jsonify({"success": False, "message": f"Schedule for {day} must be a list"}), 400
                
            valid_day_schedule = []
            for lecture in lectures:
                result = process_lecture_for_save(lecture, class_name, day, mentor_id)
                if result["save"]:
                    valid_day_schedule.append(result["lecture"])
                else:
                    has_conflict = True
                    conflict_info.extend(result["approvalConflicts"])
                    requests_created.extend(result["requestsCreated"])
            final_schedule[day] = valid_day_schedule
            
        timetable_data = {
            "className": class_name,
            "mentorID": mentor_id,
            "weeklySchedule": final_schedule,
            "updatedAt": datetime.utcnow()
        }
        
        if existing_tt:
            db.timetables.update_one({"className": class_name}, {"$set": timetable_data})
        else:
            timetable_data["createdAt"] = datetime.utcnow()
            db.timetables.insert_one(timetable_data)
            
        return jsonify({
            "success": True,
            "conflict": has_conflict,
            "requestCreated": len(requests_created) > 0,
            "message": "Weekly timetable saved successfully."
        }), 200
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/class/<class_name>", methods=["GET"])
def get_class_timetable(class_name):
    try:
        timetable = db.timetables.find_one({"className": class_name})
        if not timetable:
            return jsonify({"success": False, "message": "Timetable not found"}), 404
        populated = populate_timetable_faculties(timetable)
        return jsonify({"success": True, "timetable": serialize_doc(populated)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/class/<class_name>/<day>", methods=["GET"])
def get_day_timetable(class_name, day):
    try:
        timetable = db.timetables.find_one({"className": class_name})
        if not timetable:
            return jsonify({"success": False, "message": "Timetable not found"}), 404
        populated = populate_timetable_faculties(timetable)
        schedule = populated.get("weeklySchedule", {}).get(day, [])
        return jsonify({"success": True, "className": class_name, "day": day, "schedule": schedule})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/update-day", methods=["PUT"])
def update_single_day():
    try:
        data = request.get_json() or {}
        class_name = data.get("className")
        day = data.get("day")
        schedule = data.get("schedule")
        mentor_id = data.get("mentorID", "")
        
        if not class_name or not day:
            return jsonify({"success": False, "message": "className and day are required"}), 400
        if not isinstance(schedule, list):
            return jsonify({"success": False, "message": "schedule must be a list"}), 400
            
        valid_schedule = []
        conflicts_found = []
        requests_created = []
        
        for lecture in schedule:
            result = process_lecture_for_save(lecture, class_name, day, mentor_id)
            if result["save"]:
                valid_schedule.append(result["lecture"])
            else:
                conflicts_found.extend(result["approvalConflicts"])
                requests_created.extend(result["requestsCreated"])
                
        result = db.timetables.update_one(
            {"className": class_name},
            {"$set": {f"weeklySchedule.{day}": valid_schedule, "updatedAt": datetime.utcnow()}}
        )
        if result.matched_count == 0:
            db.timetables.insert_one({
                "className": class_name,
                "weeklySchedule": {day: valid_schedule},
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            })
            
        return jsonify({
            "success": True,
            "conflict": len(conflicts_found) > 0,
            "message": f"{day} timetable updated successfully."
        }), 200
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/delete/<class_name>", methods=["DELETE"])
def delete_timetable(class_name):
    try:
        result = db.timetables.delete_one({"className": class_name})
        if result.deleted_count == 0:
            return jsonify({"success": False, "message": "Timetable not found"}), 404
        return jsonify({"success": True, "message": "Timetable deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/all", methods=["GET"])
def get_all_timetables():
    try:
        timetables = list(db.timetables.find({}))
        result = []
        for timetable in timetables:
            populated = populate_timetable_faculties(timetable)
            result.append(serialize_doc(populated))
        return jsonify({"success": True, "count": len(result), "timetables": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/upload-pdf", methods=["POST"])
def upload_timetable_pdf():
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400
        file = request.files["file"]
        class_name = request.form.get("className")
        uploaded_by = request.form.get("uploadedBy")
        
        if not class_name or not file.filename:
            return jsonify({"success": False, "message": "className and file required"}), 400
        if not allowed_file(file.filename):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400
            
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        final_filename = f"{class_name}_{timestamp}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, final_filename)
        file.save(file_path)
        
        db.timetable_pdfs.insert_one({
            "className": class_name,
            "uploadedBy": uploaded_by,
            "fileName": final_filename,
            "filePath": file_path,
            "uploadedAt": datetime.utcnow()
        })
        return jsonify({"success": True, "message": "PDF uploaded successfully", "fileName": final_filename})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/pdfs/<class_name>", methods=["GET"])
def get_timetable_pdfs(class_name):
    try:
        pdfs = list(db.timetable_pdfs.find({"className": class_name}).sort("uploadedAt", -1))
        return jsonify({"success": True, "pdfs": serialize_many(pdfs)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@timetable_bp.route("/holiday/add", methods=["POST"])
def add_holiday():
    try:
        data = request.get_json() or {}
        if not data.get("date") or not data.get("title"):
            return jsonify({"success": False, "message": "date and title are required"}), 400
        db.holidays.insert_one({
            "date": data.get("date"),
            "title": data.get("title"),
            "description": data.get("description", ""),
            "createdAt": datetime.utcnow()
        })
        return jsonify({"success": True, "message": "Holiday added successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@timetable_bp.route("/holidays", methods=["GET"])
def get_holidays():
    try:
        holidays = list(db.holidays.find({}).sort("date", 1))
        return jsonify({"success": True, "holidays": serialize_many(holidays)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@timetable_bp.route("/verify-conflict", methods=["POST"])
def verify_conflict():
    try:
        data = request.get_json() or {}
        class_name = data.get("existingClass")
        day = data.get("day")
        mentor_id = data.get("mentorId")
        start_mins = data.get("startTimeMins")
        end_mins = data.get("endTimeMins")
        start_time = data.get("startTime")
        end_time = data.get("endTime")
        
        if not class_name or not day or not mentor_id:
            return jsonify({"success": False, "message": "existingClass, day and mentorId are required"}), 400
            
        if start_mins is None and start_time:
            start_mins = time_to_minutes(start_time)
        if end_mins is None and end_time:
            end_mins = time_to_minutes(end_time)
            
        if start_mins is None or end_mins is None:
            return jsonify({"success": False, "message": "Valid time info required"}), 400
            
        start_mins = int(start_mins)
        end_mins = int(end_mins)
        
        occupied = find_occupied_lecture_for_mentor(
            mentor_id=mentor_id,
            day=day,
            start_mins=start_mins,
            end_mins=end_mins,
            class_name=class_name,
            require_approval_mode=False
        )
        
        if not occupied:
            return jsonify({"success": True, "exists": False, "conflict": False})
            
        return jsonify({
            "success": True,
            "exists": True,
            "conflict": True,
            "approvalMode": bool(occupied.get("approvalMode", False)),
            "mentorId": occupied.get("mentorId"),
            "mentorName": occupied.get("mentorName"),
            "existingClass": occupied.get("class"),
            "existingSubject": occupied.get("subject"),
            "existingStart": occupied.get("start"),
            "existingEnd": occupied.get("end"),
            "oldLecture": occupied.get("lecture")
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500