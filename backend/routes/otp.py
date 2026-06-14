# from twilio.rest import Client

# client = Client(account_sid, auth_token)

# verification = client.verify \
#     .v2 \
#     .services("VAbd04c0eb835458fa9cdf00ecd0a0910e") \
#     .verifications \
#     .create(
#         to="+917024205530",
#         channel="sms"
#     )

# print(verification.status)
# check = client.verify \
#     .v2 \
#     .services("VAbd04c0eb835458fa9cdf00ecd0a0910e") \
#     .verification_checks \
#     .create(
#         to="+917024205530",
#         code="123456"
#     )

# print(check.status)
from flask import Blueprint, request, jsonify
from twilio.rest import Client
import os
from flask_cors import cross_origin
otp_bp = Blueprint("otp_bp", __name__)

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")

client = Client(account_sid, auth_token)

SERVICE_SID = "VAbd04c0eb835458fa9cdf00ecd0a0910e"


@otp_bp.route("/send-phone-otp", methods=["POST"])
@cross_origin(origins="https://acropoliss.netlify.app")
def send_phone_otp():

    data = request.json

    phone = data.get("phone")

    try:

        verification = client.verify \
            .v2 \
            .services(SERVICE_SID) \
            .verifications \
            .create(
                to=phone,
                channel="sms"
            )

        return jsonify({
            "success": True,
            "status": verification.status
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        })


@otp_bp.route("/verify-phone-otp", methods=["POST"])
@cross_origin(origins="https://acropoliss.netlify.app")
def verify_phone_otp():

    data = request.json

    phone = data.get("phone")
    otp = data.get("otp")

    try:

        check = client.verify \
            .v2 \
            .services(SERVICE_SID) \
            .verification_checks \
            .create(
                to=phone,
                code=otp
            )

        if check.status == "approved":

            return jsonify({
                "success": True
            })

        else:

            return jsonify({
                "success": False
            })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        })