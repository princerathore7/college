from flask import Blueprint, request, jsonify
from datetime import datetime
from pymongo import MongoClient
from flask_cors import CORS
import os
from flask_cors import cross_origin

# 🔔 Import notifications helper
from routes.notifications import send_to_enrollment

# Blueprint
attendance_bp = Blueprint('attendance', __name__, url_prefix='/api/attendance')

# Enable CORS for this blueprint
CORS(attendance_bp, resources={r"/*": {"origins": "*"}})

# MongoDB Connection
client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client["college_db"]

students_collection = db["student"]
attendance_collection = db["attendance"]

# -----------------------------
# 1️⃣ Get students by Branch + Section
# -----------------------------
@attendance_bp.route('/class/<string:class_name>', methods=['GET'])
def get_students_by_class_get(class_name):
    # example URL:
    # /api/attendance/class/2nd%20Year%20IT2

    students = list(students_collection.find(
        {"class": class_name},
        {"_id": 0}
    ))

    return jsonify({
        "success": True,
        "count": len(students),
        "students": students
    }), 200


# -----------------------------
# 2️⃣ Mark Attendance (P / A)
# -----------------------------
@attendance_bp.route("/mark", methods=["POST"])
def mark_attendance():
    try:
        data = request.json
        records = data.get("records", {})
        lecture_id = data.get("lectureId")  # 🔥 REQUIRED

        if not records or not lecture_id:
            return jsonify({
                "success": False,
                "message": "Records or lectureId missing"
            }), 400

        today = datetime.now().strftime("%Y-%m-%d")

        for enrollment, status in records.items():

            if status not in ["P", "A"]:
                continue

            # 🔁 Same lecture + same student protection
            existing = attendance_collection.find_one({
                "enrollment": enrollment,
                "date": today,
                "lectureId": lecture_id
            })

            if existing:
                attendance_collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"status": status}}
                )
            else:
                student = students_collection.find_one(
                    {"enrollment": enrollment},
                    {"_id": 0}
                )

                if not student:
                    continue

                attendance_collection.insert_one({
                    "enrollment": enrollment,
                    "name": student.get("name"),
                    "year": student.get("year"),
                    "branch": student.get("branch"),
                    "section": student.get("section"),
                    "status": status,
                    "date": today,
                    "lectureId": lecture_id,   # 🔥 KEY
                    "markedAt": datetime.now()
                })

        return jsonify({
            "success": True,
            "message": "Attendance updated successfully"
        }), 200

    except Exception as e:
        print("❌ Attendance error:", e)
        return jsonify({
            "success": False,
            "message": "Server error"
        }), 500

# -----------------------------
# 3️⃣ Get attendance summary of one student
# -----------------------------
@attendance_bp.route('/student/<string:enrollment>', methods=['GET'])
def get_student_attendance(enrollment):
    total = attendance_collection.count_documents({"enrollment": enrollment})
    present = attendance_collection.count_documents({"enrollment": enrollment, "status": "P"})
    percentage = (present / total * 100) if total > 0 else 0
    return jsonify({
        "success": True,
        "attendance": {
            "total": total,
            "present": present,
            "percentage": round(percentage, 2)
        }
    }), 200

# -----------------------------
# 4️⃣ Edit attendance manually (Admin)
# -----------------------------
@attendance_bp.route('/edit', methods=['POST'])
def edit_attendance():
    data = request.json
    enrollment = data.get("enrollment")
    date = data.get("date")
    new_status = data.get("status")

    if not all([enrollment, date, new_status]):
        return jsonify({"success": False, "message": "Missing fields"}), 400

    result = attendance_collection.update_one(
        {"enrollment": enrollment, "date": date},
        {"$set": {"status": new_status}}
    )

    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Record not found"}), 404

    # 🔔 Send notification to student
    title = "📢 Attendance Updated"
    body = f"Your attendance for {date} has been updated to {new_status} by admin."
    send_to_enrollment(enrollment, title, body, url="/attendance.html")

    return jsonify({"success": True, "message": "Attendance updated and notification sent"}), 200

# -----------------------------
# 5️⃣ Edit attendance percentage (Admin)
# -----------------------------
@attendance_bp.route("/mark", methods=["POST"])
def mark_attendance_api():
    try:
        data = request.json
        records = data.get("records", {})

        if not records:
            return jsonify({
                "success": False,
                "message": "No attendance records received"
            }), 400

        for enrollment, status in records.items():

            if status not in ["P", "A"]:
                continue

            # 🔥 Build increment object
            inc_fields = {
                "totalLectures": 1
            }

            if status == "P":
                inc_fields["presentLectures"] = 1
            else:
                inc_fields["absentLectures"] = 1

            # 🔥 ATOMIC UPDATE
            students_collection.update_one(
                {"enrollment": enrollment},
                {
                    "$inc": inc_fields
                }
            )

        return jsonify({
            "success": True,
            "message": "Attendance counters updated successfully"
        }), 200

    except Exception as e:
        print("❌ Attendance error:", e)
        return jsonify({
            "success": False,
            "message": "Server error"
        }), 500

@attendance_bp.route("/class", methods=["POST", "OPTIONS"])
@cross_origin()
def get_students_by_class():
    if request.method == "OPTIONS":
        return "", 200

    data = request.json
    class_name = data.get("class")   # 🔥 IMPORTANT

    if not class_name:
        return jsonify({
            "success": False,
            "message": "Class is required (e.g. '2nd Year IT2')"
        }), 400

    students = list(students_collection.find(
        {"class": class_name},
        {"_id": 0}
    ))

    return jsonify({
        "success": True,
        "count": len(students),
        "students": students
    }), 200
@attendance_bp.route("/students", methods=["GET"])
def get_all_students_for_attendance():
    students = list(students_collection.find(
        {},
        {
            "_id": 0,
            "enrollment": 1,
            "name": 1,
            "year": 1,
            "branch": 1,
            "section": 1
        }
    ))

    return jsonify({
        "success": True,
        "count": len(students),
        "students": students
    }), 200
