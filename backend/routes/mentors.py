from flask import Blueprint, request, jsonify
from db import db
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import datetime

mentors_bp = Blueprint("mentors_bp", __name__, url_prefix="/api")

# ------------------------------------
# Helper: Convert Mongo ObjectId to str
# ------------------------------------
def to_json(data):
    if "_id" in data:
        data["_id"] = str(data["_id"])
    return data


# ============================================================
# 1️⃣  MENTOR SIGNUP  — PRODUCTION SAFE
# ============================================================
@mentors_bp.route("/signup/mentor", methods=["POST"])
def mentor_signup():
    data = request.get_json()
    print("SIGNUP DATA RECEIVED:", data)

    required = ["mentorId", "name", "email", "phone", "subject", "branch", "classAssigned", "password"]
    if not all(field in data and data[field] for field in required):
        return jsonify({"success": False, "message": "All fields are required"}), 400

    # ---------- Duplicate mentorId check ----------
    if db.mentors.find_one({"mentorId": data["mentorId"]}):
        return jsonify({"success": False, "message": "Mentor ID already exists"}), 409

    # ---------- Duplicate email check ----------
    if db.mentors.find_one({"email": data["email"]}):
        return jsonify({"success": False, "message": "Email already registered"}), 409

    # ---------- Hash password ----------
    hashed_password = generate_password_hash(data["password"])

    mentor_data = {
        "mentorId": data["mentorId"],
        "name": data["name"],
        "email": data["email"],
        "phone": data["phone"],
        "subject": data["subject"],
        "branch": data["branch"],
        "classAssigned": data["classAssigned"],
        "password": hashed_password,
        "createdAt": datetime.datetime.utcnow()
    }

    db.mentors.insert_one(mentor_data)

    return jsonify({"success": True, "message": "Mentor registered successfully"}), 201



# ============================================================
# 2️⃣  MENTOR LOGIN — PASSWORD HASH SAFE
# ============================================================
@mentors_bp.route("/login/mentor", methods=["POST"])
def mentor_login():
    data = request.json
    print("LOGIN DATA RECEIVED:", data)

    mentor = db.mentors.find_one({"mentorId": data.get("mentorId")})

    print("MENTOR FOUND:", mentor)

    if not mentor:
        return jsonify({"success": False, "message": "Mentor not found"}), 401

    if not check_password_hash(mentor["password"], data.get("password")):
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



# ============================================================
# 3️⃣  SALARY STORAGE IN MONGODB  (AUTO COLLECTION CREATE)
# ============================================================

# Collection: college_db → salary
salary_col = db.salary   # Auto-created if not exists


# -------------------------------
# GET Salary by Mentor ID
# -------------------------------
@mentors_bp.route("/salary/<mentor_id>", methods=["GET"])
def get_salary(mentor_id):
    record = salary_col.find_one({"mentorId": mentor_id})

    if not record:
        return jsonify({"success": False, "message": "No salary record found"}), 404

    record = to_json(record)

    return jsonify({"success": True, "salary": record}), 200


# -------------------------------
# ADD or UPDATE Salary
# -------------------------------
@mentors_bp.route("/salary", methods=["POST"])
def post_salary():
    data = request.get_json()
    print("SALARY DATA RECEIVED:", data)

    if not data or not data.get("mentorId"):
        return jsonify({"success": False, "message": "Mentor ID is required"}), 400

    mentor_id = data["mentorId"]

    # Auto–upsert salary data
    salary_col.update_one(
        {"mentorId": mentor_id},
        {"$set": {
            "mentorId": mentor_id,
            "baseSalary": data.get("baseSalary"),
            "bonus": data.get("bonus"),
            "month": data.get("month"),
            "year": data.get("year"),
            "updatedAt": datetime.datetime.utcnow()
        }},
        upsert=True
    )

    return jsonify({"success": True, "message": "Salary info saved successfully"}), 201
