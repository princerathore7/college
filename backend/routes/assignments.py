# backend/routes/assignments_bp.py
from flask import Blueprint, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import re
from utils import generate_id  # make sure this exists

assignments_bp = Blueprint("assignments_bp", __name__, url_prefix="/api/assignments")
CORS(assignments_bp)

# -----------------------------
# MongoDB Setup
# -----------------------------
# Use environment variable for deployment
MONGO_URI = os.getenv("MONGO_COLLEGE_DB_URI") or "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client["college_db"]
assignments_collection = db["assignments"]

# -----------------------------
# Normalize class format (IT-2 → IT2)
# -----------------------------
def normalize_class_name(class_name):
    if not class_name:
        return ""
    class_name = class_name.strip().upper()
    class_name = re.sub(r"[^A-Z0-9]", "", class_name)
    return class_name

# -----------------------------
# GET all assignments
# -----------------------------
@assignments_bp.route("", methods=["GET"])
def get_all_assignments():
    try:
        assignments = list(assignments_collection.find({}, {"_id": 0}))
        return jsonify({"success": True, "assignments": assignments}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------------
# GET assignments by class
# -----------------------------
@assignments_bp.route("/class/<class_name>", methods=["GET"])
def get_assignments_by_class(class_name):
    normalized_class = normalize_class_name(class_name)
    try:
        assignments = list(assignments_collection.find(
            {"class_normalized": normalized_class}, {"_id": 0}
        ))
        return jsonify({"success": True, "assignments": assignments}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------------
# POST new assignment
# -----------------------------
@assignments_bp.route("", methods=["POST"])
def post_assignment():
    data = request.get_json()
    required_fields = ["class", "title", "subject", "deadline"]
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({"success": False, "message": f"{field} is required"}), 400

    try:
        # Generate assignment ID
        data["assignmentId"] = generate_id("A")
        data["submissions"] = []

        # Normalize class
        data["class_normalized"] = normalize_class_name(data["class"])
        data["class"] = data["class"].strip()  # store original for display

        assignments_collection.insert_one(data)
        return jsonify({
            "success": True,
            "message": "Assignment posted successfully",
            "assignmentId": data["assignmentId"]
        }), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------------
# DELETE assignment
# -----------------------------
@assignments_bp.route("/<assignmentId>", methods=["DELETE"])
def delete_assignment(assignmentId):
    try:
        result = assignments_collection.delete_one({"assignmentId": assignmentId})
        if result.deleted_count == 0:
            return jsonify({"success": False, "message": "Assignment not found"}), 404
        return jsonify({"success": True, "message": "Assignment deleted"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
