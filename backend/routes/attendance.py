from flask import Blueprint, request, jsonify
from datetime import datetime
from pymongo import MongoClient
from flask_cors import CORS

# Blueprint
attendance_bp = Blueprint('attendance', __name__, url_prefix='/api/attendance')

# Enable CORS for this blueprint
CORS(attendance_bp)

# MongoDB Connection
client = MongoClient("mongodb://localhost:27017/")
db = client["college_db"]

students_collection = db["student"]
attendance_collection = db["attendance"]



# =====================================================
# 1️⃣ Get students by Branch + Section
# URL: GET /api/attendance/students/<branch>/<section>
# Example: /api/attendance/students/IT/IT2
# =====================================================
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

@attendance_bp.route('/students_by_class/<string:year>/<string:branch>/<string:section>', methods=['GET'])
def get_students_by_class(year, branch, section):
    """
    Fetch students filtered by year, branch, and section.
    """
    try:
        # Find students
        students = list(students_collection.find(
            {"year": year, "branch": branch, "section": section},
            {"_id": 0}  # Exclude MongoDB _id
        ))

        if not students:
            return jsonify({
                "success": True,
                "count": 0,
                "students": []
            }), 200

        return jsonify({
            "success": True,
            "count": len(students),
            "students": students
        }), 200

    except Exception as e:
        print("Error fetching students:", e)
        return jsonify({"success": False, "message": "Internal server error"}), 500
# =====================================================
# 2️⃣ Mark Attendance (P / A)
# URL: POST /api/attendance/mark
# Body: { "enrollment": "", "section": "", "status": "P" }
# =====================================================
@attendance_bp.route('/mark', methods=['POST'])
def mark_attendance():

    data = request.json
    required = ["enrollment", "section", "status"]

    if not all(key in data for key in required):
        return jsonify({"success": False, "message": "Missing fields"}), 400

    record = {
        "enrollment": data["enrollment"],
        "section": data["section"],
        "status": data["status"],     # P or A
        "date": datetime.now().strftime("%Y-%m-%d")
    }

    attendance_collection.insert_one(record)

    return jsonify({
        "success": True,
        "message": "Attendance marked successfully"
    }), 201


# =====================================================
# 3️⃣ Get attendance summary of one student
# URL: GET /api/attendance/student/<enrollment>
# =====================================================
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


# =====================================================
# 4️⃣ Edit attendance manually (Admin)
# URL: POST /api/attendance/edit
# =====================================================
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

    return jsonify({"success": True, "message": "Attendance updated"}), 200


# =====================================================
# 5️⃣ Edit attendance percentage (Admin)
# Rebuild attendance history based on present/absent count
# =====================================================
@attendance_bp.route('/edit_percentage', methods=['POST'])
def edit_attendance_percentage():

    data = request.json
    enrollment = data.get("enrollment")
    total = data.get("total")
    present = data.get("present")

    if not all([enrollment, total is not None, present is not None]):
        return jsonify({"success": False, "message": "Missing fields"}), 400

    # Remove old records
    attendance_collection.delete_many({"enrollment": enrollment})

    # Fetch student section
    student = students_collection.find_one({"enrollment": enrollment})
    section = student.get("section", "") if student else ""

    # Generate new attendance histor
    for i in range(total):
        status = "P" if i < present else "A"

        attendance_collection.insert_one({
            "enrollment": enrollment,
            "section": section,
            "status": status,
            "date": f"2025-01-{i+1:02d}"
        })

    return jsonify({"success": True, "message": "Attendance percentage updated"}), 200
