from flask import Blueprint, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash
from datetime import datetime
import random
import string
import os
from utils.email import send_verification_email
from db import db

# ---------------- IMPORT AUTO EMAIL FUNCTION ----------------

from utils.email import send_verification_email

# ---------------- BLUEPRINT ----------------

signup_bp = Blueprint(
    "signup_bp",
    __name__,
    url_prefix="/api/signup"
)

CORS(signup_bp)

# ---------------- DATABASE ----------------

pending_collection = db["pending_verifications"]

done_collection = db["done_verifications"]

verified_collection = db["verified_students"]

# ---------------- AUTO DELETE AFTER 6 DAYS ----------------

pending_collection.create_index(
    "createdAt",
    expireAfterSeconds=518400
)

# ---------------- CODE GENERATOR ----------------

def generate_verification_code():

    letters = ''.join(
        random.choices(string.ascii_uppercase, k=3)
    )

    numbers = ''.join(
        random.choices(string.digits, k=3)
    )

    return letters + numbers

# ---------------- SIGNUP REQUEST ROUTE ----------------

@signup_bp.route("/request", methods=["POST"])
def signup_request():

    try:

        data = request.form

        student_name = data.get("studentName")
        enrollment = data.get("enrollment")
        password = data.get("password")

        email = data.get("email")
        phone = data.get("phone")

        branch = data.get("branch")
        semester = data.get("semester")
        year = data.get("year")

        # ---------------- VALIDATION ----------------

        if not all([

            student_name,
            enrollment,
            password,
            email,
            phone,
            branch,
            semester,
            year

        ]):

            return jsonify({

                "success": False,
                "message": "All fields are required"

            }), 400

        # ---------------- CHECK VERIFIED ----------------

        existing_verified = verified_collection.find_one({

            "$or": [

                {"email": email},
                {"phone": phone},
                {"enrollment": enrollment}

            ]

        })

        if existing_verified:

            return jsonify({

                "success": False,
                "message": "Student already verified"

            }), 409

        # ---------------- CHECK PENDING ----------------

        existing_pending = pending_collection.find_one({

            "$or": [

                {"email": email},
                {"phone": phone},
                {"enrollment": enrollment}

            ]

        })

        if existing_pending:

            return jsonify({

                "success": False,
                "message": "Verification already pending"

            }), 409

        # ---------------- GENERATE VERIFICATION CODE ----------------

        verification_code = generate_verification_code()

        # ---------------- HASH PASSWORD ----------------

        hashed_password = generate_password_hash(password)

        # ---------------- PHOTO UPLOAD ----------------

        photo = request.files.get("photo")

        photo_filename = ""

        if photo:

            upload_folder = "uploads"

            if not os.path.exists(upload_folder):

                os.makedirs(upload_folder)

            photo_filename = f"{enrollment}_{photo.filename}"

            photo_path = os.path.join(
                upload_folder,
                photo_filename
            )

            photo.save(photo_path)

        # ---------------- SAVE DATA ----------------

        pending_data = {

            "studentName": student_name,
            "enrollment": enrollment,

            "password": hashed_password,

            "email": email,
            "phone": phone,

            "branch": branch,
            "semester": semester,
            "year": year,

            "photo": photo_filename,

            "verificationCode": verification_code,

            "emailSent": False,
            "smsSent": False,

            "status": "pending",

            "createdAt": datetime.utcnow()

        }

        pending_collection.insert_one(pending_data)

        # ---------------- AUTO EMAIL SEND ----------------

        email_response = send_verification_email(

            student_name=student_name,

            student_email=email,

            verification_code=verification_code,

            enrollment=enrollment,

            branch=branch,

            semester=semester,

            year=year,

            phone=phone

        )

        # ---------------- UPDATE EMAIL STATUS ----------------

        if email_response["success"]:

            pending_collection.update_one(

                {"email": email},

                {
                    "$set": {
                        "emailSent": True
                    }
                }

            )

        # ---------------- RESPONSE ----------------

        return jsonify({

            "success": True,

            "message": "Signup request submitted successfully",

            "emailStatus": email_response,

            "waitMessage":
            "Verification code has been sent to your registered email."

        }), 201

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500