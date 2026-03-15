import os
import smtplib
from email.mime.text import MIMEText
import secrets
from flask_cors import CORS
SMTP_SERVER = os.getenv("MAIL_SERVER")
SMTP_PORT = int(os.getenv("MAIL_PORT", 587))
SMTP_USERNAME = os.getenv("MAIL_USERNAME")
SMTP_PASSWORD = os.getenv("MAIL_PASSWORD")
SENDER_EMAIL = os.getenv("MAIL_DEFAULT_SENDER")

def send_email(to_email, subject, body):

    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USERNAME, SMTP_PASSWORD)
    server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
    server.quit()
def send_reset_email(user_email):

    token = secrets.token_urlsafe(32)

    reset_link = f"https://college-hwbb.onrender.com/reset-password.html?token={token}"

    body = f"""
    <h2>Password Reset</h2>
    <p>Click the link below to reset your password:</p>

    <a href="{reset_link}">{reset_link}</a>

    <p>This link will expire in 10 minutes.</p>
    """

    send_email(user_email, "Reset Your Password", body)

    return token
