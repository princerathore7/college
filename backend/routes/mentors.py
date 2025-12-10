from flask import Blueprint, request, jsonify
from db import db
import os, json

# ✅ Single, unified blueprint
mentors_bp = Blueprint("mentors_bp", __name__, url_prefix="/api")

# -------------------------------
# 1️⃣ Mentor Login Route
# -------------------------------
@mentors_bp.route("/login/mentor", methods=["POST"])
def mentor_login():
    data = request.json
    print("LOGIN DATA RECEIVED:", data)

    mentor = db.mentors.find_one({"mentorId": data.get("mentorId")})
    print("MENTOR FOUND:", mentor)

    if not mentor:
        return jsonify({"success": False, "message": "Mentor not found"}), 401

    if mentor["password"] != data.get("password"):
        return jsonify({"success": False, "message": "Incorrect password"}), 401

    return jsonify({
        "success": True,
        "message": "Login successful",
        "mentor": {
            "mentorId": mentor["mentorId"],
            "name": mentor["name"],
            "classAssigned": mentor.get("classAssigned")
        }
    }), 200

# -------------------------------
# 2️⃣ Salary Data Management
# -------------------------------
DATA_FILE = os.path.join("data", "salaries.json")

def load_salaries():
    """Load salaries from JSON file."""
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_salaries(data):
    """Save salaries to JSON file."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

@mentors_bp.route("/salary/<mentor_id>", methods=["GET"])
def get_salary(mentor_id):
    """Fetch salary details for a given Mentor ID."""
    data = load_salaries()
    if mentor_id in data:
        return jsonify({"success": True, "salary": data[mentor_id]})
    return jsonify({"success": False, "message": "No record found for this Mentor ID"})

@mentors_bp.route("/salary", methods=["POST"])
def post_salary():
    """Add or update salary information."""
    salary = request.get_json()
    if not salary.get("mentorId"):
        return jsonify({"success": False, "message": "Mentor ID is required"}), 400

    data = load_salaries()
    data[salary["mentorId"]] = salary
    save_salaries(data)
    return jsonify({"success": True, "message": "Salary info saved successfully"})
