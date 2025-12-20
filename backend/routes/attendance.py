from flask import Blueprint, request, jsonify
from datetime import datetime
from pymongo import MongoClient
from flask_cors import CORS, cross_origin
import os

# 🔔 Import notifications helper
from routes.notifications import send_to_enrollment

attendance_bp = Blueprint('attendance', __name__, url_prefix='/api/attendance')
CORS(attendance_bp, resources={r"/*": {"origins": "*"}})

# MongoDB
client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client["college_db"]

students_collection = db["student"]
attendance_collection = db["attendance"]
attendance_override_collection = db["attendance_override"]

# ------------------------------------------------
# 1️⃣ Get students by class (GET)
# ------------------------------------------------
@attendance_bp.route('/class/<string:class_name>', methods=['GET'])
def get_students_by_class_get(class_name):
    students = list(students_collection.find(
        {"class": class_name},
        {"_id": 0}
    ))
    return jsonify({"success": True, "count": len(students), "students": students}), 200


# ------------------------------------------------
# 2️⃣ Mark Attendance (P / A) — REAL ATTENDANCE
# ------------------------------------------------
@attendance_bp.route("/mark", methods=["POST"])
def mark_attendance():
    try:
        data = request.json or {}
        records = data.get("records", {})
        lecture_id = data.get("lectureId")

        if not isinstance(records, dict) or not lecture_id:
            return jsonify({"success": False, "message": "Invalid payload"}), 400

        today = datetime.utcnow().strftime("%Y-%m-%d")
        saved = 0

        for enrollment, status in records.items():
            enrollment = enrollment.strip().upper()
            if status not in ("P", "A"):
                continue

            student = students_collection.find_one({"enrollment": enrollment})
            if not student:
                continue

            attendance_collection.update_one(
                {
                    "enrollment": enrollment,
                    "date": today,
                    "lectureId": lecture_id
                },
                {
                    "$set": {
                        "status": status,
                        "year": student.get("year"),
                        "branch": student.get("branch"),
                        "section": student.get("section"),
                        "markedAt": datetime.utcnow()
                    }
                },
                upsert=True
            )
            saved += 1

        return jsonify({"success": True, "saved": saved}), 200

    except Exception as e:
        print("❌ Attendance error:", e)
        return jsonify({"success": False}), 500


# ------------------------------------------------
# 3️⃣ Get attendance summary (AUTO + MANUAL MERGED)
# ------------------------------------------------
@attendance_bp.route('/student/<string:enrollment>', methods=['GET'])
def get_student_attendance(enrollment):

    # 🔥 FIRST CHECK: manual override
    override = attendance_override_collection.find_one(
        {"enrollment": enrollment},
        {"_id": 0}
    )

    if override:
        return jsonify({
            "success": True,
            "attendance": {
                "total": override["total"],
                "present": override["present"],
                "percentage": override["percentage"],
                "source": "manual"
            }
        }), 200

    # 🔁 fallback to real attendance
    total = attendance_collection.count_documents({"enrollment": enrollment})
    present = attendance_collection.count_documents({
        "enrollment": enrollment,
        "status": "P"
    })

    percentage = round((present / total) * 100, 2) if total else 0

    return jsonify({
        "success": True,
        "attendance": {
            "total": total,
            "present": present,
            "percentage": percentage,
            "source": "auto"
        }
    }), 200


# ------------------------------------------------
# 4️⃣ Edit single date attendance (Admin)
# ------------------------------------------------
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

    send_to_enrollment(
        enrollment,
        "📢 Attendance Updated",
        f"Your attendance for {date} has been updated to {new_status}.",
        url="/attendance.html"
    )

    return jsonify({"success": True}), 200


# ------------------------------------------------
# 5️⃣ Edit attendance percentage (Admin SAFE MODE)
# ------------------------------------------------
@attendance_bp.route('/edit_percentage', methods=['POST'])
def edit_attendance_percentage():
    try:
        data = request.json
        enrollment = data.get("enrollment")
        total = int(data.get("total", 0))
        present = int(data.get("present", 0))

        if not enrollment or total <= 0 or present < 0 or present > total:
            return jsonify({"success": False, "message": "Invalid input"}), 400

        percentage = round((present / total) * 100, 2)

        attendance_override_collection.update_one(
            {"enrollment": enrollment},
            {
                "$set": {
                    "total": total,
                    "present": present,
                    "percentage": percentage,
                    "updatedAt": datetime.utcnow(),
                    "updatedBy": "admin"
                }
            },
            upsert=True
        )

        send_to_enrollment(
            enrollment,
            "📢 Attendance Percentage Updated",
            f"Your attendance has been manually updated to {percentage}%.",
            url="/student-dashboard.html"
        )

        return jsonify({"success": True, "percentage": percentage}), 200

    except Exception as e:
        print("❌ edit_percentage error:", e)
        return jsonify({"success": False}), 500


# ------------------------------------------------
# 6️⃣ Get students by class (POST)
# ------------------------------------------------
@attendance_bp.route("/class", methods=["POST", "OPTIONS"])
@cross_origin()
def get_students_by_class():
    if request.method == "OPTIONS":
        return "", 200

    class_name = request.json.get("class")
    if not class_name:
        return jsonify({"success": False, "message": "Class required"}), 400

    students = list(students_collection.find(
        {"class": class_name},
        {"_id": 0}
    ))

    return jsonify({"success": True, "count": len(students), "students": students}), 200


# ------------------------------------------------
# 7️⃣ Get all students (attendance panel)
# ------------------------------------------------
@attendance_bp.route("/students", methods=["GET"])
def get_all_students_for_attendance():
    students = list(students_collection.find(
        {},
        {"_id": 0, "enrollment": 1, "name": 1, "year": 1, "branch": 1, "section": 1}
    ))
    return jsonify({"success": True, "count": len(students), "students": students}), 200
# ----------------------------------------
# 3️⃣ Attendance Summary — VIEW PAGE
# ----------------------------------------
@attendance_bp.route("/summary/<enrollment>", methods=["GET"])
def attendance_summary(enrollment):
    enrollment = enrollment.strip().upper()

    records = list(attendance_collection.find(
        {"enrollment": enrollment},
        {"status": 1}
    ))

    if not records:
        return jsonify({"success": True, "summary": {
            "total": 0, "present": 0, "absent": 0, "percentage": 0
        }})

    total = len(records)
    present = sum(1 for r in records if r["status"] == "P")
    absent = total - present
    percentage = round((present / total) * 100, 2)

    return jsonify({
        "success": True,
        "summary": {
            "total": total,
            "present": present,
            "absent": absent,
            "percentage": percentage
        }
    })
