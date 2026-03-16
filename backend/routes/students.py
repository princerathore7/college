from flask import Blueprint, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
students_bp = Blueprint("students_bp", __name__, url_prefix="/api/students")
CORS(students_bp)

# ----------------- MongoDB Setup -----------------
# ----------- MongoDB Atlas Connection (Render Environment Variables) -----------
MONGO_URL = os.getenv("MONGO_URL")

if not MONGO_URL:
    raise Exception("MONGO_URL environment variable missing!")

client = MongoClient(MONGO_URL)
classes_db = client["classes"]         # collections for each class-section
users_db = client["users"]             # user login DB
students_collection = users_db["students"]  # explicit collection reference

# Helper: convert frontend dropdown "1-A" -> collection name
def get_collection_name(branch_section):
    try:
        cls, sec = branch_section.split("-")
        return f"class_{cls}_{sec}"
    except Exception:
        raise ValueError("Invalid branch-section format. Use e.g., '1-A'")

# ----------------- STUDENTS CRUD -----------------

# GET students of a class-section
# students_bp.py
@students_bp.route("/<branch>", methods=["GET"])
def get_students(branch):
    try:
        # fetch students based on branch
        students = list(students_collection.find(
            {"branch": branch},
            {"_id": 0, "name": 1, "enrollment": 1}
        ))
        return jsonify({"success": True, "students": students}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# POST add student to class
@students_bp.route("/", methods=["POST"])
def add_student():
    try:
        data = request.get_json()
        branch = data.get("branch")
        name = data.get("name")
        enrollment = data.get("enrollment")

        if not all([branch, name, enrollment]):
            return jsonify({"success": False, "message": "Missing fields"}), 400

        coll_name = get_collection_name(branch)

        # check duplicate enrollment in class
        if classes_db[coll_name].find_one({"enrollment": enrollment}):
            return jsonify({"success": False, "message": "Student already exists in this class"}), 409

        # add student to class
        classes_db[coll_name].insert_one({"name": name, "enrollment": enrollment})

        return jsonify({"success": True, "message": "Student added"}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# DELETE student from class
@students_bp.route("/<branch>/<enrollment>", methods=["DELETE"])
def remove_student(branch, enrollment):
    try:
        coll_name = get_collection_name(branch)
        result = classes_db[coll_name].delete_one({"enrollment": enrollment})
        if result.deleted_count == 0:
            return jsonify({"success": False, "message": "Student not found"}), 404
        return jsonify({"success": True, "message": "Student removed"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ----------------- STUDENT LOGIN / SIGNUP -----------------

# Student signup
@students_bp.route("/signup", methods=["POST"])
def student_signup():
    try:
        data = request.get_json()
        name = data.get("name")
        enrollment = data.get("enrollment")
        password = data.get("password")
        branch = data.get("branch")
        email = data.get("email")
        phone = data.get("phone") 
        

        if not all([name, enrollment, password, branch]):
            return jsonify({"success": False, "message": "All fields are required"}), 400

        if students_collection.find_one({"enrollment": enrollment}):
            return jsonify({"success": False, "message": "Enrollment already exists"}), 409

        hashed_pw = generate_password_hash(password)
        students_collection.insert_one({
            "name": name,
            "enrollment": enrollment,
            "password": hashed_pw,
            "branch": branch,
            "email": email,
            "phone": phone,
            "createdAt": datetime.utcnow()

        })

        # 👇 Add also into class collection
        coll_name = get_collection_name(branch)
        classes_db[coll_name].insert_one({
            "name": name,
            "enrollment": enrollment,
            "branch": branch
        })

        return jsonify({"success": True, "message": "Signup successful"}), 201

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# Student login
@students_bp.route("/login", methods=["POST"])
def student_login():
    try:
        data = request.get_json()
        enrollment = data.get("enrollment")
        password = data.get("password")

        user = students_collection.find_one({"enrollment": enrollment})
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 401

        # ⭐ CHECK SUSPENSION
        if user.get("suspended"):
            return jsonify({
                "success": False,
                "suspended": True,
                "message": "Account suspended"
            }), 403

        if not check_password_hash(user["password"], password):
            return jsonify({"success": False, "message": "Invalid password"}), 401

        return jsonify({
            "success": True,
            "enrollment": enrollment,
            "name": user["name"]
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
# ----------------- PENDING FEES -----------------
@students_bp.route("/<enrollment>/pending-fees", methods=["GET", "POST", "OPTIONS"])
def pending_fees(enrollment):
    try:
        if request.method == "OPTIONS":
            # For CORS preflight
            return jsonify({}), 200

        fees_collection = users_db["fees"]
        student = students_collection.find_one({"enrollment": enrollment}, {"_id": 0})  # fetch student info

        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404

        if request.method == "GET":
            # Get pending fees
            record = fees_collection.find_one({"enrollment": enrollment}, {"_id": 0})
            pending = record.get("pending_fees", 0) if record else 0

            # Merge student info + pending fees
            student_info = student.copy()  # don't mutate original
            student_info["pending_fees"] = pending

            return jsonify({"success": True, "student": student_info}), 200

        if request.method == "POST":
            data = request.get_json()
            pending_fees = data.get("pending_fees", 0)
            fees_collection.update_one(
                {"enrollment": enrollment},
                {"$set": {"pending_fees": pending_fees}},
                upsert=True
            )
            return jsonify({"success": True, "message": f"Pending fees updated for {enrollment}"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
# ✅ View or update student class
@students_bp.route('/<enrollment>/class', methods=['GET', 'PUT'])
def manage_student_class(enrollment):
    student = students_collection.find_one({"enrollment": enrollment}, {"_id": 0})
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    if request.method == 'GET':
        return jsonify({"success": True, "student": student}), 200

    elif request.method == 'PUT':
        data = request.json
        new_class = data.get("class")
        new_year = data.get("year")  # year is optional now

        if not new_class:
            return jsonify({"success": False, "message": "Class is required"}), 400

        update_data = {"class": new_class}
        if new_year:
            update_data["year"] = new_year  # only set year if provided

        students_collection.update_one(
            {"enrollment": enrollment},
            {"$set": update_data}
        )

        # Build response message
        msg = f"Class updated to {new_class}"
        if new_year:
            msg = f"Class and year updated to {new_year} {new_class}"

        return jsonify({"success": True, "message": msg}), 200

def get_collection_name(branch_section):
    try:
        parts = branch_section.split("-")
        if len(parts) == 1 or not parts[1]:
            sec = "A"  # default section if missing
        else:
            sec = parts[1]
        cls = parts[0]
        return f"class_{cls}_{sec}"
    except Exception:
        raise ValueError("Invalid branch-section format. Use e.g., '1-A'")
@students_bp.route("/<enrollment>/profile", methods=["PUT"])
def update_profile(enrollment):
    data = request.json

    email = data.get("email")
    phone = data.get("phone")

    update_data = {}

    if email:
        update_data["email"] = email
    if phone:
        update_data["phone"] = phone

    if not update_data:
        return jsonify({"success": False, "message": "Nothing to update"}), 400

    students_collection.update_one(
        {"enrollment": enrollment},
        {"$set": update_data}
    )

    return jsonify({"success": True, "message": "Profile updated"})
@students_bp.route("/<enrollment>/suspend", methods=["PUT"])
def suspend_student(enrollment):
    try:
        data = request.get_json()
        suspend = data.get("suspend", True)

        student = students_collection.find_one({"enrollment": enrollment})
        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404

        students_collection.update_one(
            {"enrollment": enrollment},
            {"$set": {"suspended": suspend}}
        )

        status = "suspended" if suspend else "activated"

        return jsonify({
            "success": True,
            "message": f"Student {status} successfully"
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
@students_bp.route("/<enrollment>", methods=["DELETE"])
def delete_student(enrollment):
    try:

        student = students_collection.find_one({"enrollment": enrollment})
        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404

        branch = student.get("branch")

        # delete from users.students
        students_collection.delete_one({"enrollment": enrollment})

        # delete from class collection also
        if branch:
            coll_name = get_collection_name(branch)
            classes_db[coll_name].delete_one({"enrollment": enrollment})

        return jsonify({
            "success": True,
            "message": "Student deleted successfully"
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500