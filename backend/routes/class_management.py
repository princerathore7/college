# routes/class_management.py
# routes/class_management.py
from flask import Blueprint, request, jsonify
from flask_cors import CORS, cross_origin
from db import db

class_mgmt_bp = Blueprint('class_mgmt', __name__, url_prefix='/api/class')

# Enable CORS for this entire blueprint
CORS(class_mgmt_bp)

# ✅ Get student info by enrollment number
@class_mgmt_bp.route('/get/<enrollment>', methods=['GET'])
def get_student(enrollment):
    student = db.students.find_one({"enrollment": enrollment}, {"_id": 0})
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404
    return jsonify({"success": True, "student": student}), 200


# ✅ Update student's class
@class_mgmt_bp.route('/update', methods=['PUT'])
def update_class():
    data = request.json
    enrollment = data.get("enrollment")
    new_class = data.get("class")

    if not enrollment or not new_class:
        return jsonify({"success": False, "message": "Enrollment and new class are required"}), 400

    result = db.students.update_one({"enrollment": enrollment}, {"$set": {"class": new_class}})

    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Student not found"}), 404

    return jsonify({"success": True, "message": f"Class updated to {new_class}"}), 200
