# import requests
# import os

# RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# def send_verification_email(to_email, student_name, otp):

#     url = "https://api.resend.com/emails"

#     headers = {
#         "Authorization": f"Bearer {RESEND_API_KEY}",
#         "Content-Type": "application/json"
#     }

#     payload = {
#         "from": "Acropolis <onboarding@resend.dev>",
#         "to": [to_email],
#         "subject": "Acropolis Verification Code",
#         "html": f"""
#         <h2>Welcome to Acropolis Institute</h2>

#         <p>Dear {student_name},</p>

#         <p>Your verification code is:</p>

#         <h1>{otp}</h1>

#         <p>Please use this OTP to verify your account.</p>

#         <br>

#         <p>Powered By S&P Developments</p>
#         """
#     }

#     response = requests.post(
#         url,
#         headers=headers,
#         json=payload
#     )

#     return response.json()

from flask import Blueprint, request, jsonify
import requests
import os
from flask_cors import cross_origin
email_bp = Blueprint("email_bp", __name__)

RESEND_API_KEY = os.getenv("EMAIL_API")

@email_bp.route("/send-email", methods=["POST"])
@cross_origin(origins="https://acropoliss.netlify.app")
def send_email():

    data = request.json

    recipient = data.get("email")
    subject = data.get("subject")
    html = data.get("html")

    try:

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from": "Acropolis Campus <onboarding@resend.dev>",
                "to": [recipient],
                "subject": subject,
                "html": html
            }
        )

        return jsonify({
            "success": response.status_code in [200, 201],
            "response": response.json()
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500