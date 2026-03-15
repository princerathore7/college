from flask import Blueprint, request, jsonify
from flask_cors import CORS
from flask_cors import cross_origin
from utils.email_service import send_reset_email, send_email
from pymongo import MongoClient
import os
from datetime import datetime

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client["college_db"]
# ✅ Enable CORS
CORS(auth_bp)

# 🔹 Forgot password
@auth_bp.route("/forgot-password", methods=["POST"])
@cross_origin()
def forgot_password():
 
    if request.method == "OPTIONS":
     return jsonify({"status":"ok"}),200
    data = request.json
    email = data.get("email")

    # 🔎 Check in students collection
    user = db.students.find_one({"email": email})

    if not user:
        # 🔎 Check in mentors collection
        user = db.mentors.find_one({"email": email})

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    # send reset email
    token = send_reset_email(email)

    # save token in DB
    db.password_resets.insert_one({
        "email": email,
        "token": token,
        "createdAt": datetime.utcnow()
    })

    return jsonify({
        "success": True,
        "message": "Reset email sent"
    })


# 🔹 Email test route
@auth_bp.route("/test-email")
def test_email():

    send_email(
        "trillionarpresent@gmail.com",
        "Brevo Test Email",
        "<h2>Email system working 🚀</h2>"
    )

    return jsonify({"success": True, "message": "Email sent"})