from flask import Blueprint, request, jsonify
from db import db
from utils import generate_id
import re

assignments_bp = Blueprint('assignments', __name__, url_prefix='/api/assignments')
# 🔹 Normalizer function (already present)
def normalize_class_name(class_name):
    if not class_name:
        return ""
    class_name = class_name.strip().lower()
    class_name = re.sub(r'[^a-z0-9]', '', class_name)   # remove spaces, -, etc.
    class_name = class_name.replace("st", "").replace("nd", "").replace("rd", "").replace("th", "")
    return class_name.upper()  # e.g. "1st IT2" -> "1IT2"

# ✅ 1. Get all assignments (for all classes)
@assignments_bp.route('', methods=['GET'])
def get_all_assignments():
    assignments = list(db.assignments.find({}, {'_id': 0}))
    return jsonify({
        "success": True,
        "assignments": assignments
    }), 200

# ✅ 2. Get assignments by class (case-insensitive)
@assignments_bp.route('/class/<class_name>', methods=['GET'])
def get_assignments_by_class(class_name):
    normalized_class = normalize_class_name(class_name)
    # Compare normalized_class field
    assignments = list(db.assignments.find({"class_normalized": normalized_class}, {"_id": 0}))
    return jsonify({"success": True, "assignments": assignments}), 200
# ✅ 3. Post new assignment
@assignments_bp.route('', methods=['POST'])
def post_assignment():
    data = request.json
    required_fields = ["class", "title", "subject", "deadline"]
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({"success": False, "message": f"{field} is required"}), 400

    data['assignmentId'] = generate_id("A")
    data['submissions'] = []

    # 🔹 Normalize class
    data['class_normalized'] = normalize_class_name(data['class'])
    data['class'] = data['class'].strip()  # store original for display

    db.assignments.insert_one(data)
    return jsonify({
        "success": True,
        "message": "Assignment posted successfully",
        "assignmentId": data['assignmentId']
    }), 201

# ✅ 4. Delete assignment
@assignments_bp.route('/<assignmentId>', methods=['DELETE'])
def delete_assignment(assignmentId):
    result = db.assignments.delete_one({"assignmentId": assignmentId})
    if result.deleted_count == 0:
        return jsonify({"success": False, "message": "Assignment not found"}), 404
    return jsonify({"success": True, "message": "Assignment deleted"}), 200
