import requests
import os

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

def send_verification_email(to_email, student_name, otp):

    url = "https://api.resend.com/emails"

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "from": "Acropolis <onboarding@resend.dev>",
        "to": [to_email],
        "subject": "Acropolis Verification Code",
        "html": f"""
        <h2>Welcome to Acropolis Institute</h2>

        <p>Dear {student_name},</p>

        <p>Your verification code is:</p>

        <h1>{otp}</h1>

        <p>Please use this OTP to verify your account.</p>

        <br>

        <p>Powered By S&P Developments</p>
        """
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload
    )

    return response.json()