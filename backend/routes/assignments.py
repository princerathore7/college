from flask import Blueprint, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import re
from datetime import datetime
from utils import generate_id
from routes.notifications import send_notification_to_class

assignments_bp = Blueprint(
    "assignments_bp",
    __name__,
    url_prefix="/api/assignments"
)
CORS(assignments_bp)

# -----------------------------
# MongoDB Setup
# -----------------------------
MONGO_URI = os.getenv("MONGO_COLLEGE_DB_URI", "mongodb://localhost:27017/")
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
    class_name = re.sub(r"[^A-Z0-9]", "", class_name)
    return class_name

# -----------------------------
# Convert admin class → student format
# -----------------------------
def to_student_class_format(raw_class):
    """
    Converts: 2CSE2 → 2nd Year CSE2
    """
    if not raw_class:
        return ""

    raw_class = raw_class.strip().upper()

    year = raw_class[0]
    rest = raw_class[1:]

    branch = "".join(filter(str.isalpha, rest))
    section = "".join(filter(str.isdigit, rest))

    year_map = {
        "1": "1st Year",
        "2": "2nd Year",
        "3": "3rd Year",
        "4": "4th Year"
    }

    return f"{year_map.get(year, year)} {branch}{section}"

# -----------------------------
# GET all ACTIVE assignments
# -----------------------------
@assignments_bp.route("", methods=["GET"])
def get_all_assignments():
    assignments = list(
        assignments_collection.find(
            {"active": True},
            {"_id": 0}
        )
    )
    return jsonify({
        "success": True,
        "assignments": assignments
    }), 200

# -----------------------------
# GET ACTIVE assignments by class
# -----------------------------
@assignments_bp.route("/class/<class_name>", methods=["GET"])
def get_assignments_by_class(class_name):
    assignments = list(
        assignments_collection.find(
            {
                "class": {"$regex": class_name, "$options": "i"},
                "active": True
            },
            {"_id": 0}
        )
    )
    return jsonify({
        "success": True,
        "assignments": assignments
    }), 200

# -----------------------------
# POST new assignment
# -----------------------------
@assignments_bp.route("", methods=["POST"])
def post_assignment():
    data = request.get_json(force=True)

    required_fields = ["class", "title", "subject", "deadline"]
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({
                "success": False,
                "message": f"{field} is required"
            }), 400

    try:
        assignment_id = generate_id("A")

        # ✅ CONVERT CLASS FORMAT HERE
        student_class = to_student_class_format(data["class"])

        assignment = {
            "assignmentId": assignment_id,
            "class": student_class,
            "class_normalized": normalize_class_name(student_class),
            "title": data["title"].strip(),
            "subject": data["subject"].strip(),
            "deadline": data["deadline"],
            "createdAt": datetime.utcnow(),
            "submissions": [],
            "active": True
        }

        assignments_collection.insert_one(assignment)

        # 🔔 SEND CLASS-WISE NOTIFICATION
        send_notification_to_class(
            class_name=assignment["class_normalized"],
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
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# -----------------------------
# DELETE assignment (soft delete)
# -----------------------------
@assignments_bp.route("/<assignmentId>", methods=["DELETE"])
def delete_assignment(assignmentId):
    res = assignments_collection.update_one(
        {"assignmentId": assignmentId},
        {"$set": {"active": False}}
    )

    if res.matched_count == 0:
        return jsonify({
            "success": False,
            "message": "Assignment not found"
        }), 404

    return jsonify({
        "success": True,
        "message": "Assignment deleted & reminders stopped"
    }), 200
