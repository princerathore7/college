
from flask import Blueprint, request, jsonify
from db import db
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import datetime
import os

mentors_bp = Blueprint("mentors_bp", __name__, url_prefix="/api")


# ============================================================
# FIXED MENTOR DESIGNATIONS
# ============================================================

MENTOR_DESIGNATIONS = [
    "Principal",
    "Director",
    "Dean",
    "HOD (Head of Department)",

    "Professor",
    "Associate Professor",
    "Assistant Professor",
    "Senior Assistant Professor",
    "Lecturer",
    "Visiting Faculty",
    "Adjunct Faculty",
    "Professor of Practice",

    "Lab Instructor",
    "Lab Assistant",
    "Teaching Assistant"
]


# ============================================================
# HELPER: Convert Mongo ObjectId to string
# ============================================================

def to_json(data):
    if "_id" in data:
        data["_id"] = str(data["_id"])
    return data


# ============================================================
# 1. GET AVAILABLE MENTOR DESIGNATIONS
# ============================================================

@mentors_bp.route("/mentor/designations", methods=["GET"])
def get_mentor_designations():

    return jsonify({
        "success": True,
        "designations": MENTOR_DESIGNATIONS
    }), 200


# ============================================================
# 2. MENTOR SIGNUP
# ============================================================

@mentors_bp.route("/signup/mentor", methods=["POST"])
def mentor_signup():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "Invalid request data"
        }), 400

    print("SIGNUP DATA RECEIVED:", data)

    required = [
        "mentorId",
        "name",
        "email",
        "phone",
        "subject",
        "branch",
        "classAssigned",
        "password"
    ]

    if not all(field in data and data[field] for field in required):

        return jsonify({
            "success": False,
            "message": "All fields are required"
        }), 400

    # Designation validation (optional for backward compatibility)

    designation = data.get("designation", "").strip()

    if designation and designation not in MENTOR_DESIGNATIONS:

        return jsonify({
            "success": False,
            "message": "Invalid mentor designation",
            "availableDesignations": MENTOR_DESIGNATIONS
        }), 400

    # Duplicate mentorId check

    if db.mentors.find_one({"mentorId": data["mentorId"]}):

        return jsonify({
            "success": False,
            "message": "Mentor ID already exists"
        }), 409

    # Duplicate email check

    if db.mentors.find_one({"email": data["email"]}):

        return jsonify({
            "success": False,
            "message": "Email already registered"
        }), 409

    # Password hashing

    hashed_password = generate_password_hash(data["password"])

    mentor_data = {

        "mentorId": data["mentorId"],
        "name": data["name"],
        "email": data["email"],
        "phone": data["phone"],
        "subject": data["subject"],
        "branch": data["branch"],
        "classAssigned": data["classAssigned"],

        "designation": designation,

        "password": hashed_password,

        "status": "active",

        "createdAt": datetime.datetime.utcnow()
    }

    db.mentors.insert_one(mentor_data)

    return jsonify({
        "success": True,
        "message": "Mentor registered successfully"
    }), 201


# ============================================================
# 3. MENTOR LOGIN
# ============================================================

@mentors_bp.route("/login/mentor", methods=["POST"])
def mentor_login():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "Invalid request data"
        }), 400

    print("LOGIN DATA RECEIVED:", data)

    mentor = db.mentors.find_one({
        "mentorId": data.get("mentorId")
    })

    print("MENTOR FOUND:", mentor)

    if not mentor:

        return jsonify({
            "success": False,
            "message": "Mentor not found"
        }), 401

    # Password check

    if not check_password_hash(
        mentor["password"],
        data.get("password", "")
    ):

        return jsonify({
            "success": False,
            "message": "Incorrect password"
        }), 401

    # Suspended account check

    if mentor.get("status") == "suspended":

        return jsonify({
            "success": False,
            "message": "Your account is suspended. Contact admin."
        }), 403

    track_login("mentor")

    # Login success

    return jsonify({

        "success": True,

        "message": "Login successful",

        "mentor": {

            "mentorId": mentor["mentorId"],

            "name": mentor["name"],

            "classAssigned": mentor.get("classAssigned"),

            "designation": mentor.get("designation", "")

        }

    }), 200


# ============================================================
# 4. SALARY STORAGE IN MONGODB
# ============================================================

salary_col = db.salary


# -------------------------------
# GET Salary by Mentor ID
# -------------------------------

@mentors_bp.route("/salary/<mentor_id>", methods=["GET"])
def get_salary(mentor_id):

    record = salary_col.find_one({
        "mentorId": mentor_id
    })

    if not record:

        return jsonify({
            "success": False,
            "message": "No salary record found"
        }), 404

    record = to_json(record)

    return jsonify({
        "success": True,
        "salary": record
    }), 200


# -------------------------------
# ADD / UPDATE Salary
# -------------------------------

@mentors_bp.route("/salary", methods=["POST"])
def post_salary():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "Invalid request data"
        }), 400

    print("SALARY DATA RECEIVED:", data)

    if not data.get("mentorId"):

        return jsonify({
            "success": False,
            "message": "Mentor ID is required"
        }), 400

    designation = data.get("designation")

    if designation and designation not in MENTOR_DESIGNATIONS:

        return jsonify({
            "success": False,
            "message": "Invalid designation",
            "availableDesignations": MENTOR_DESIGNATIONS
        }), 400

    mentor_id = data["mentorId"]

    salary_col.update_one(

        {"mentorId": mentor_id},

        {
            "$set": {

                "mentorId": mentor_id,

                "name": data.get("name"),

                "designation": designation,

                "month": data.get("month"),

                "amount": data.get("amount"),

                "status": data.get("status"),

                "updatedAt": datetime.datetime.utcnow()

            }
        },

        upsert=True
    )

    return jsonify({
        "success": True,
        "message": "Salary info saved successfully"
    }), 201


# ============================================================
# 5. UPDATE MENTOR STATUS
# ============================================================

@mentors_bp.route("/mentor/status", methods=["PUT"])
def update_mentor_status():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "Invalid request data"
        }), 400

    mentor_id = data.get("mentorId")

    new_status = data.get("status")

    if not mentor_id or new_status not in ["active", "suspended"]:

        return jsonify({
            "success": False,
            "message": "mentorId and valid status required"
        }), 400

    result = db.mentors.update_one(

        {"mentorId": mentor_id},

        {
            "$set": {

                "status": new_status,

                "updatedAt": datetime.datetime.utcnow()

            }
        }
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

# ============================================================
# UPDATE COMPLETE MENTOR INFORMATION
# ============================================================

@mentors_bp.route("/mentor/update", methods=["PUT"])
def edit_mentor_info():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "Invalid request data"
        }), 400

    mentor_id = data.get("mentorId")

    if not mentor_id:
        return jsonify({
            "success": False,
            "message": "Mentor ID is required"
        }), 400

    # Check mentor exists

    mentor = db.mentors.find_one({
        "mentorId": mentor_id
    })

    if not mentor:
        return jsonify({
            "success": False,
            "message": "Mentor not found"
        }), 404

    # Editable fields

    editable_fields = [
        "name",
        "email",
        "phone",
        "subject",
        "branch",
        "classAssigned",
        "designation"
    ]

    update_data = {}

    for field in editable_fields:

        if field in data:

            value = data[field]

            if not isinstance(value, str) or not value.strip():

                return jsonify({
                    "success": False,
                    "message": f"{field} cannot be empty"
                }), 400

            update_data[field] = value.strip()

    if not update_data:

        return jsonify({
            "success": False,
            "message": "No information provided for update"
        }), 400

    # Validate designation

    if "designation" in update_data:

        if update_data["designation"] not in MENTOR_DESIGNATIONS:

            return jsonify({
                "success": False,
                "message": "Invalid designation"
            }), 400

    # Check duplicate email

    if "email" in update_data:

        existing_email = db.mentors.find_one({

            "email": update_data["email"],

            "mentorId": {"$ne": mentor_id}

        })

        if existing_email:

            return jsonify({
                "success": False,
                "message": "Email already registered with another mentor"
            }), 409

    # Update MongoDB

    update_data["updatedAt"] = datetime.datetime.utcnow()

    db.mentors.update_one(

        {"mentorId": mentor_id},

        {
            "$set": update_data
        }

    )

    return jsonify({

        "success": True,

        "message": "Mentor information updated successfully"

    }), 200
# ============================================================
# 6. DELETE MENTOR
# ============================================================

@mentors_bp.route("/mentor/<mentor_id>", methods=["DELETE"])
def delete_mentor(mentor_id):

    result = db.mentors.delete_one({
        "mentorId": mentor_id
    })

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
# 7. GET ALL MENTORS (AUTHORITY PANEL)
# ============================================================

@mentors_bp.route("/mentors", methods=["GET"])
def get_all_mentors():

    mentors = list(

        db.mentors.find(

            {},

            {
                "_id": 0,

                "mentorId": 1,

                "name": 1,

                "email": 1,

                "phone": 1,

                "subject": 1,

                "branch": 1,

                "classAssigned": 1,

                "designation": 1,

                "status": 1,

                "createdAt": 1
            }
        )
    )

    return jsonify({

        "success": True,

        "mentors": mentors

    }), 200


# ============================================================
# 8. AUTHORITY PASSWORD VERIFICATION
# ============================================================

@mentors_bp.route("/authority/verify-password", methods=["POST"])
def verify_authority_password():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False
        }), 400

    if data.get("password") == os.getenv("AUTHORITY_PASSWORD"):

        return jsonify({
            "success": True
        }), 200

    return jsonify({
        "success": False
    }), 401


# ============================================================
# 9. LOGIN TRACKING
# ============================================================

def track_login(user_type):

    try:

        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        db.login_stats.update_one(

            {"date": today},

            {
                "$inc": {

                    "total_logins": 1,

                    f"{user_type}_logins": 1

                }
            },

            upsert=True
        )

    except Exception as e:

        print("Login tracking error:", e)


# ============================================================
# 10. MENTOR SEARCH
# ============================================================

@mentors_bp.route("/mentor/search", methods=["GET"])
def search_mentor():

    query = request.args.get("q", "").strip()

    mentors = list(

        db.mentors.find(

            {
                "$or": [

                    {
                        "mentorId": {
                            "$regex": query,
                            "$options": "i"
                        }
                    },

                    {
                        "name": {
                            "$regex": query,
                            "$options": "i"
                        }
                    }

                ]
            },

            {
                "_id": 0,

                "mentorId": 1,

                "name": 1,

                "subject": 1,

                "branch": 1,

                "designation": 1
            }

        ).limit(15)
    )

    return jsonify({

        "success": True,

        "mentors": mentors

    }), 200
