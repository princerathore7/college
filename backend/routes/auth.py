```python
from flask import Blueprint, request, jsonify
from flask_cors import CORS, cross_origin
from utils.email_service import send_reset_email, send_email
from pymongo import MongoClient
import os
from datetime import datetime
import traceback

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client["college_db"]

# Enable CORS
CORS(auth_bp)


# 🔹 Forgot password
@auth_bp.route("/forgot-password", methods=["POST", "OPTIONS"])
@cross_origin()
def forgot_password():

    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    try:

        data = request.json
        email = data.get("email")

        if not email:
            return jsonify({
                "success": False,
                "message": "Email required"
            }), 400

        # check student
        user = db.students.find_one({"email": email})

        # check mentor
        if not user:
            user = db.mentors.find_one({"email": email})

        if not user:
            return jsonify({
                "success": False,
                "message": "User not found"
            }), 404

        print("USER FOUND:", email)

        # send reset email
        token = send_reset_email(email)

        if not token:
            return jsonify({
                "success": False,
                "message": "Email sending failed"
            }), 500

        # save token
        db.password_resets.insert_one({
            "email": email,
            "token": token,
            "createdAt": datetime.utcnow()
        })

        return jsonify({
            "success": True,
            "message": "Reset email sent"
        })

    except Exception as e:

        print("FORGOT PASSWORD ERROR:")
        print(traceback.format_exc())

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500



# 🔹 Email test route
@auth_bp.route("/test-email", methods=["GET"])
def test_email():

    try:

        print("START EMAIL TEST")

        success = send_email(
            "trillionarpresent@gmail.com",
            "SMTP Test Email",
            "<h2>Email system working 🚀</h2>"
        )

        if success:
            print("EMAIL SENT SUCCESSFULLY")

            return jsonify({
                "success": True,
                "message": "Email sent successfully"
            })

        else:
            print("EMAIL FAILED")

            return jsonify({
                "success": False,
                "message": "Email sending failed"
            }), 500

    except Exception as e:

        print("EMAIL TEST ERROR:")
        print(traceback.format_exc())

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500