from flask import Blueprint, request, jsonify
from flask_cors import CORS

from bson import ObjectId
from datetime import datetime
import os
import smtplib
from db import db
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------------- BLUEPRINT ----------------

admin_verification_bp = Blueprint(
    "admin_verification_bp",
    __name__,
    url_prefix="/api/admin"
)

CORS(admin_verification_bp)


# ---------------- DATABASE ----------------

pending_collection = db["pending_verifications"]

done_collection = db["done_verifications"]

verified_collection = db["verified_students"]

# ---------------- EMAIL CONFIG ----------------

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# ---------------- GET ALL PENDING REQUESTS ----------------

@admin_verification_bp.route("/pending", methods=["GET"])
def get_pending_requests():

    try:

        pending_students = list(

            pending_collection.find(
                {"status": "pending"},
                {"password": 0}
            )

        )

        # Convert ObjectId to string

        for student in pending_students:
            student["_id"] = str(student["_id"])

        return jsonify({

            "success": True,
            "count": len(pending_students),
            "students": pending_students

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ---------------- SEND EMAIL ----------------

@admin_verification_bp.route("/send-email", methods=["POST"])
def send_email():

    try:

        data = request.json

        student_id = data.get("studentId")

        if not student_id:

            return jsonify({
                "success": False,
                "message": "Student ID required"
            }), 400

        # ---------------- FIND STUDENT ----------------

        student = pending_collection.find_one({
            "_id": ObjectId(student_id)
        })

        if not student:

            return jsonify({
                "success": False,
                "message": "Student not found"
            }), 404

        # ---------------- EMAIL DATA ----------------

        receiver_email = student["email"]

        verification_code = student["verificationCode"]

        student_name = student["studentName"]

        # ---------------- EMAIL CONTENT ----------------

        subject = "Acropolis Verification Code"

        html_body = f"""

        <html>

        <body style="font-family:Arial;background:#f4f6fa;padding:20px;">

            <div style="
                max-width:600px;
                margin:auto;
                background:white;
                padding:30px;
                border-radius:10px;
                border-top:6px solid #003366;
            ">

                <h1 style="color:#003366;">
                    Welcome To Acropolis Digital Campus
                </h1>

                <p>
                    Dear {student_name},
                </p>

                <p>
                    Welcome to the digital journey of
                    Acropolis Institute of Technology & Research
                    powered by S&P Developments.
                </p>

                <div style="
                    margin-top:30px;
                    margin-bottom:30px;
                    background:#003366;
                    color:white;
                    text-align:center;
                    padding:20px;
                    border-radius:8px;
                ">

                    <h2>YOUR VERIFICATION CODE</h2>

                    <h1 style="
                        letter-spacing:5px;
                        font-size:42px;
                    ">
                        {verification_code}
                    </h1>

                </div>

                <p>
                    This code is uniquely generated for your
                    registered email and mobile number.
                </p>

                <p>
                    Please use this code to activate your
                    student account.
                </p>

                <br>

                <p>
                    Regards,<br>
                    Acropolis Verification Team
                </p>

            </div>

        </body>

        </html>

        """

        # ---------------- EMAIL SETUP ----------------

        msg = MIMEMultipart()

        msg["From"] = EMAIL_ADDRESS
        msg["To"] = receiver_email
        msg["Subject"] = subject

        msg.attach(MIMEText(html_body, "html"))

        # ---------------- SEND EMAIL ----------------

        server = smtplib.SMTP("smtp.gmail.com", 587)

        server.starttls()

        server.login(
            EMAIL_ADDRESS,
            EMAIL_PASSWORD
        )

        server.send_message(msg)

        server.quit()

        # ---------------- UPDATE STATUS ----------------

        pending_collection.update_one(

            {"_id": ObjectId(student_id)},

            {
                "$set": {
                    "emailSent": True,
                    "emailSentAt": datetime.utcnow()
                }
            }

        )

        return jsonify({

            "success": True,
            "message": "Email sent successfully"

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ---------------- SEND SMS ----------------

@admin_verification_bp.route("/send-sms", methods=["POST"])
def send_sms():

    try:

        data = request.json

        student_id = data.get("studentId")

        if not student_id:

            return jsonify({
                "success": False,
                "message": "Student ID required"
            }), 400

        # ---------------- FIND STUDENT ----------------

        student = pending_collection.find_one({
            "_id": ObjectId(student_id)
        })

        if not student:

            return jsonify({
                "success": False,
                "message": "Student not found"
            }), 404

        # ---------------- SMS TEXT ----------------

        sms_text = f"""

Acropolis Verification Code

Code: {student['verificationCode']}

Use this code to activate your account.

Powered by S&P Developments.

        """

        # ---------------- HERE YOUR SMS API WILL COME ----------------

        # Example:
        # requests.post("SMS_API_URL", data={})

        # ---------------- UPDATE DATABASE ----------------

        pending_collection.update_one(

            {"_id": ObjectId(student_id)},

            {
                "$set": {
                    "smsSent": True,
                    "smsSentAt": datetime.utcnow()
                }
            }

        )

        return jsonify({

            "success": True,
            "message": "SMS marked as sent",
            "smsPreview": sms_text

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ---------------- MARK AS DONE ----------------

@admin_verification_bp.route("/mark-done", methods=["POST"])
def mark_done():

    try:

        data = request.json

        student_id = data.get("studentId")

        if not student_id:

            return jsonify({
                "success": False,
                "message": "Student ID required"
            }), 400

        # ---------------- FIND STUDENT ----------------

        student = pending_collection.find_one({
            "_id": ObjectId(student_id)
        })

        if not student:

            return jsonify({
                "success": False,
                "message": "Student not found"
            }), 404

        # ---------------- ADD DONE TIME ----------------

        student["doneAt"] = datetime.utcnow()

        # ---------------- INSERT INTO DONE COLLECTION ----------------

        done_collection.insert_one(student)

        # ---------------- DELETE FROM PENDING ----------------

        pending_collection.delete_one({
            "_id": ObjectId(student_id)
        })

        return jsonify({

            "success": True,
            "message": "Student moved to done list"

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ---------------- GET DONE LIST ----------------

@admin_verification_bp.route("/done-list", methods=["GET"])
def get_done_list():

    try:

        done_students = list(

            done_collection.find({}, {"password": 0})

        )

        # Convert ObjectId to string

        for student in done_students:
            student["_id"] = str(student["_id"])

        return jsonify({

            "success": True,
            "count": len(done_students),
            "students": done_students

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500