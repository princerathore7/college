from flask import Blueprint, request, jsonify
from datetime import datetime
from pymongo import MongoClient
from flask_cors import CORS
import os

# 🔔 Import notifications helper
from routes.notifications import send_to_enrollment

# Blueprint
attendance_bp = Blueprint('attendance', __name__, url_prefix='/api/attendance')

# MongoDB Connection
client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client["college_db"]

students_collection = db["student"]
attendance_collection = db["attendance"]

# -----------------------------
# 1️⃣ Get students by Branch + Section
# -----------------------------
@attendance_bp.route('/students/<string:branch>/<string:section>', methods=['GET'])
def get_students_by_branch_section(branch, section):
    students = list(students_collection.find(
        {"branch": branch, "section": section},
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

        today = datetime.now().strftime("%Y-%m-%d")

        for enrollment, status in records.items():
            attendance_collection.insert_one({
                "enrollment": enrollment,
                "status": status,   # "P" or "A"
                "date": today
            })

        return jsonify({"success": True}), 200

    except Exception as e:
        print("❌ Attendance error:", e)
        return jsonify({"success": False}), 500

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
@attendance_bp.route('/edit_percentage', methods=['POST'])
def edit_attendance_percentage():
    try:
        data = request.json
        enrollment = data.get("enrollment")
        total = data.get("total")
        present = data.get("present")

        if not all([enrollment is not None, total is not None, present is not None]):
            return jsonify({"success": False, "message": "Missing fields"}), 400

        # Remove old records
        attendance_collection.delete_many({"enrollment": enrollment})

        # Fetch student section
        student = students_collection.find_one({"enrollment": enrollment})
        section = student.get("section", "") if student else ""

        # Generate new attendance history
        for i in range(total):
            status = "P" if i < present else "A"
            attendance_collection.insert_one({
                "enrollment": enrollment,
                "section": section,
                "status": status,
                "date": f"2025-01-{i+1:02d}"
            })

        # 🔔 Send notification about percentage update
        title = "📢 Attendance History Updated"
        body = f"Your attendance record has been updated. Present: {present}, Total: {total}"
        send_to_enrollment(enrollment, title, body, url="/student-dashboard.html")

        return jsonify({"success": True, "message": "Attendance percentage updated and notification sent"}), 200

    except Exception as e:
        print("❌ Error in edit_attendance_percentage:", e)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500
