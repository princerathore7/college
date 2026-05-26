from flask import Blueprint, request, jsonify
from flask_cors import CORS
from datetime import datetime
from db import db

# ---------------- BLUEPRINT ----------------

verification_bp = Blueprint(
    "verification_bp",
    __name__,
    url_prefix="/api/verify"
)

CORS(verification_bp)

# ---------------- MONGODB COLLECTIONS ----------------

pending_collection = db["pending_verifications"]

done_collection = db["done_verifications"]

verified_collection = db["verified_students"]

students_collection = db["students"]

# ---------------- VERIFY CODE ROUTE ----------------

@verification_bp.route("/code", methods=["POST"])
def verify_code():

    try:

        data = request.json

        email = data.get("email")
        phone = data.get("phone")
        verification_code = data.get("verificationCode")

        # ---------------- VALIDATION ----------------

        if not all([email, phone, verification_code]):

            return jsonify({
                "success": False,
                "message": "Email, phone and verification code are required"
            }), 400

        # ---------------- FIND PENDING USER ----------------

        pending_user = pending_collection.find_one({

            "email": email,
            "phone": phone,
            "verificationCode": verification_code

        })

        # ---------------- INVALID CODE ----------------

        if not pending_user:

            return jsonify({
                "success": False,
                "message": "Invalid verification code"
            }), 401

        # ---------------- CHECK ALREADY VERIFIED ----------------

        existing_student = students_collection.find_one({

            "enrollment": pending_user.get("enrollment")

        })

        if existing_student:

            return jsonify({
                "success": False,
                "message": "Student already verified"
            }), 409

        # ---------------- CREATE VERIFIED USER DATA ----------------

        verified_user_data = {

            "studentName": pending_user.get("studentName"),

            "enrollment": pending_user.get("enrollment"),

            "password": pending_user.get("password"),

            "email": pending_user.get("email"),

            "phone": pending_user.get("phone"),

            "branch": pending_user.get("branch"),

            "semester": pending_user.get("semester"),

            "year": pending_user.get("year"),

            "photo": pending_user.get("photo"),

            "verifiedAt": datetime.utcnow(),

            "status": "verified"

        }

        # ---------------- INSERT INTO VERIFIED COLLECTION ----------------

        verified_collection.insert_one(verified_user_data)

        # ---------------- INSERT INTO MAIN STUDENTS COLLECTION ----------------

        student_login_data = {

            "name": pending_user.get("studentName"),

            "enrollment": pending_user.get("enrollment"),

            "password": pending_user.get("password"),

            "email": pending_user.get("email"),

            "phone": pending_user.get("phone"),

            "branch": pending_user.get("branch"),

            "semester": pending_user.get("semester"),

            "year": pending_user.get("year"),

            "photo": pending_user.get("photo"),

            "createdAt": datetime.utcnow(),

            "status": "active"

        }

        students_collection.insert_one(student_login_data)

        # ---------------- DELETE FROM PENDING ----------------

        pending_collection.delete_one({
            "_id": pending_user["_id"]
        })

        # ---------------- RESPONSE ----------------

        return jsonify({

            "success": True,

            "message": "Student account verified successfully",

            "student": {

                "name": verified_user_data["studentName"],

                "enrollment": verified_user_data["enrollment"],

                "email": verified_user_data["email"],

                "branch": verified_user_data["branch"],

                "semester": verified_user_data["semester"],

                "year": verified_user_data["year"]

            }

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ---------------- CHECK VERIFICATION STATUS ----------------

@verification_bp.route("/status", methods=["POST"])
def check_status():

    try:

        data = request.json

        email = data.get("email")

        if not email:

            return jsonify({
                "success": False,
                "message": "Email is required"
            }), 400

        # ---------------- CHECK VERIFIED ----------------

        verified_user = verified_collection.find_one({
            "email": email
        })

        if verified_user:

            return jsonify({

                "success": True,
                "status": "verified",
                "message": "Account verified successfully"

            }), 200

        # ---------------- CHECK PENDING ----------------

        pending_user = pending_collection.find_one({
            "email": email
        })

        if pending_user:

            return jsonify({

                "success": True,
                "status": "pending",
                "message": "Verification pending"

            }), 200

        # ---------------- NOT FOUND ----------------

        return jsonify({

            "success": False,
            "status": "not_found",
            "message": "No account found"

        }), 404

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500