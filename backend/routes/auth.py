from flask import Blueprint, request, jsonify
from utils.email_service import send_reset_email, send_email
from db import db
from datetime import datetime

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# 🔹 Forgot password
@auth_bp.route("/forgot-password", methods=["POST", "OPTIONS"])
def forgot_password():

    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.json
    email = data.get("email")

    user = db.users.find_one({"email": email})

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    token = send_reset_email(email)

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
        "yourgmail@gmail.com",
        "Brevo Test Email",
        "<h2>Email system working 🚀</h2>"
    )

    return jsonify({"success": True, "message": "Email sent"})
