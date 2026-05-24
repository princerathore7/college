import requests
import os


# ---------------- SMS API CONFIG ----------------

SMS_API_KEY = os.getenv("SMS_API_KEY")

SMS_SENDER_ID = os.getenv("SMS_SENDER_ID")

SMS_TEMPLATE_ID = os.getenv("SMS_TEMPLATE_ID")

SMS_BASE_URL = os.getenv("SMS_BASE_URL")


# ---------------- SEND VERIFICATION SMS ----------------

def send_verification_sms(

    student_name,
    mobile_number,
    verification_code

):

    try:

        # ---------------- SMS TEXT ----------------

        sms_message = f"""

Welcome To Acropolis Digital Campus

Hello {student_name},

Your verification code is:

{verification_code}

Use this code to activate your student account.

Powered By S&P Developments.

        """

        # ---------------- SMS API REQUEST ----------------

        payload = {

            "apikey": SMS_API_KEY,

            "sender": SMS_SENDER_ID,

            "number": mobile_number,

            "message": sms_message,

            "templateid": SMS_TEMPLATE_ID

        }

        # ---------------- SEND SMS ----------------

        response = requests.post(

            SMS_BASE_URL,

            data=payload

        )

        # ---------------- RESPONSE CHECK ----------------

        if response.status_code == 200:

            return {

                "success": True,

                "message": "SMS sent successfully",

                "response": response.text

            }

        else:

            return {

                "success": False,

                "message": "SMS sending failed",

                "response": response.text

            }

    except Exception as e:

        return {

            "success": False,

            "message": str(e)

        }


# ---------------- MANUAL SMS PREVIEW ----------------

def generate_sms_preview(

    student_name,
    verification_code

):

    sms_preview = f"""

ACROPOLIS DIGITAL CAMPUS

Hello {student_name},

YOUR VERIFICATION CODE

{verification_code}

Use this code to activate your student account.

Powered By S&P Developments.

    """

    return sms_preview


# ---------------- TESTING ----------------

if __name__ == "__main__":

    response = send_verification_sms(

        student_name="Vikas Rajput",

        mobile_number="9999999999",

        verification_code="AXP741"

    )

    print(response)
    