from flask import Blueprint, request, jsonify
from db import db
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import datetime
import os
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
        "status": "active",
        "createdAt": datetime.datetime.utcnow()
    }

    db.mentors.insert_one(mentor_data)

    return jsonify({"success": True, "message": "Mentor registered successfully"}), 201



@mentors_bp.route("/login/mentor", methods=["POST"])
def mentor_login():
    data = request.json
    print("LOGIN DATA RECEIVED:", data)

    mentor = db.mentors.find_one({"mentorId": data.get("mentorId")})
    print("MENTOR FOUND:", mentor)

    if not mentor:
        return jsonify({"success": False, "message": "Mentor not found"}), 401

    # Password check
    if not check_password_hash(mentor["password"], data.get("password")):
        return jsonify({"success": False, "message": "Incorrect password"}), 401

    # 🚫 Suspend check (PASSWORD ke baad karna best practice hai)
    if mentor.get("status") == "suspended":
        return jsonify({
            "success": False,
            "message": "Your account is suspended. Contact admin."
        }), 403

    # ✅ Login success
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
# 3️⃣  SALARY STORAGE IN MONGODB — MATCHES FRONTEND EXACTLY
# ============================================================

salary_col = db.salary  # Auto-created

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
# ADD / UPDATE Salary
# -------------------------------
@mentors_bp.route("/salary", methods=["POST"])
def post_salary():
    data = request.get_json()
    print("SALARY DATA RECEIVED:", data)

    if not data.get("mentorId"):
        return jsonify({"success": False, "message": "Mentor ID is required"}), 400

    mentor_id = data["mentorId"]

    salary_col.update_one(
        {"mentorId": mentor_id},
        {"$set": {
            "mentorId": mentor_id,
            "name": data.get("name"),
            "designation": data.get("designation"),
            "month": data.get("month"),
            "amount": data.get("amount"),
            "status": data.get("status"),
            "updatedAt": datetime.datetime.utcnow()
        }},
        upsert=True
    )

    return jsonify({"success": True, "message": "Salary info saved successfully"}), 201
@mentors_bp.route("/mentor/status", methods=["PUT"])
def update_mentor_status():
    data = request.get_json()

    mentor_id = data.get("mentorId")
    new_status = data.get("status")  # "active" or "suspended"

    if not mentor_id or new_status not in ["active", "suspended"]:
        return jsonify({
            "success": False,
            "message": "mentorId and valid status required"
        }), 400

    result = db.mentors.update_one(
        {"mentorId": mentor_id},
        {"$set": {
            "status": new_status,
            "updatedAt": datetime.datetime.utcnow()
        }}
    )

    if result.matched_count == 0:
        return jsonify({
            "success": False,
            "message": "Mentor not found"
        }), 404

    return jsonify({
        "success": True,
        "message": f"Mentor {new_status} successfully"
    }), 200
@mentors_bp.route("/mentor/<mentor_id>", methods=["DELETE"])
def delete_mentor(mentor_id):

    result = db.mentors.delete_one({"mentorId": mentor_id})

    if result.deleted_count == 0:
        return jsonify({
            "success": False,
            "message": "Mentor not found"
        }), 404

    return jsonify({
        "success": True,
        "message": "Mentor deleted successfully"
    }), 200
# ============================================================
# 6️⃣  GET ALL MENTORS (Authority Panel)
# ============================================================
@mentors_bp.route("/mentors", methods=["GET"])
def get_all_mentors():

    mentors = list(db.mentors.find({}, {
        "_id": 0,
        "mentorId": 1,
        "name": 1,
        "email": 1,
        "phone": 1,
        "subject": 1,
        "branch": 1,
        "classAssigned": 1,
        "status": 1,
        "createdAt": 1
    }))

    return jsonify({
        "success": True,
        "mentors": mentors
    }), 200

@mentors_bp.route("/authority/verify-password", methods=["POST"])
def verify_authority_password():

    data=request.json

    if data.get("password")==os.getenv("AUTHORITY_PASSWORD"):
        return jsonify({"success":True})

    return jsonify({"success":False}),401