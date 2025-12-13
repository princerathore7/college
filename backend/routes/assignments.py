from flask import Blueprint, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import re
from datetime import datetime
from utils import generate_id

# 🔔 Notification helpers
from routes.notifications import send_notification_to_class

assignments_bp = Blueprint("assignments_bp", __name__, url_prefix="/api/assignments")
CORS(assignments_bp)

# -----------------------------
# MongoDB Setup
# -----------------------------
MONGO_URI = os.getenv("MONGO_COLLEGE_DB_URI") or "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client["college_db"]
assignments_collection = db["assignments"]

# -----------------------------
# Normalize class format
# -----------------------------
def normalize_class_name(class_name):
    if not class_name:
        return ""
    class_name = class_name.strip().upper()
    class_name = re.sub(r'[^A-Z0-9]', '', class_name)
    return class_name

# -----------------------------
# GET all assignments
# -----------------------------
@assignments_bp.route("", methods=["GET"])
def get_all_assignments():
    assignments = list(assignments_collection.find({}, {"_id": 0}))
    return jsonify({"success": True, "assignments": assignments}), 200

# -----------------------------
# GET assignments by class
# -----------------------------
@assignments_bp.route("/class/<class_name>", methods=["GET"])
def get_assignments_by_class(class_name):
    normalized_class = normalize_class_name(class_name)
    assignments = list(assignments_collection.find(
        {"class_normalized": normalized_class}, {"_id": 0}
    ))
    return jsonify({"success": True, "assignments": assignments}), 200

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
        assignment_id = generate_id("A")

        assignment = {
            "assignmentId": assignment_id,
            "class": data["class"].strip(),
            "class_normalized": normalize_class_name(data["class"]),
            "title": data["title"].strip(),
            "subject": data["subject"].strip(),
            "deadline": data["deadline"],
            "createdAt": datetime.utcnow(),
            "submissions": [],
            "active": True  # 🔑 for repeat notification logic
        }

        assignments_collection.insert_one(assignment)

        # 🔔 CLASS-WISE NOTIFICATION (NEW ASSIGNMENT)
        send_notification_to_class(
            class_name=assignment["class"],
            title="📚 New Assignment Posted",
            body=f"{assignment['subject']}: {assignment['title']}",
            url="/assignments.html"
        )

        return jsonify({
            "success": True,
            "message": "Assignment posted & notification sent",
            "assignmentId": assignment_id
        }), 201

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# -----------------------------
# DELETE assignment (stop reminders)
# -----------------------------
@assignments_bp.route("/<assignmentId>", methods=["DELETE"])
def delete_assignment(assignmentId):
    res = assignments_collection.update_one(
        {"assignmentId": assignmentId},
        {"$set": {"active": False}}
    )

    if res.matched_count == 0:
        return jsonify({"success": False, "message": "Assignment not found"}), 404

    return jsonify({"success": True, "message": "Assignment deleted & reminders stopped"}), 200
