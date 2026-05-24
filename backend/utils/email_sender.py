import smtplib
import os

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ---------------- EMAIL CONFIG ----------------

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


# ---------------- SEND VERIFICATION EMAIL ----------------

def send_verification_email(

    student_name,
    receiver_email,
    verification_code

):

    try:

        # ---------------- EMAIL SUBJECT ----------------

        subject = "Acropolis Digital Verification Code"

        # ---------------- PROFESSIONAL HTML EMAIL ----------------

        html_body = f"""

        <html>

        <head>

        <style>

        body {{
            background:#f4f6fa;
            font-family:Arial,sans-serif;
            padding:20px;
        }}

        .container {{
            max-width:650px;
            margin:auto;
            background:white;
            border-radius:12px;
            overflow:hidden;
            box-shadow:0 0 15px rgba(0,0,0,0.1);
        }}

        .header {{
            background:#003366;
            color:white;
            text-align:center;
            padding:30px;
        }}

        .header h1 {{
            margin:0;
            font-size:32px;
            letter-spacing:1px;
        }}

        .content {{
            padding:35px;
            color:#333;
            line-height:1.7;
        }}

        .code-box {{
            margin-top:30px;
            margin-bottom:30px;
            background:#003366;
            color:white;
            text-align:center;
            padding:25px;
            border-radius:10px;
        }}

        .code-box h2 {{
            margin:0;
            margin-bottom:15px;
            font-size:24px;
        }}

        .code {{
            font-size:48px;
            letter-spacing:8px;
            font-weight:bold;
        }}

        .footer {{
            background:#f1f1f1;
            padding:20px;
            text-align:center;
            color:#666;
            font-size:14px;
        }}

        </style>

        </head>

        <body>

            <div class="container">

                <div class="header">

                    <h1>
                        ACROPOLIS DIGITAL CAMPUS
                    </h1>

                    <p>
                        Powered By S&P Developments
                    </p>

                </div>

                <div class="content">

                    <h2>
                        Welcome {student_name}
                    </h2>

                    <p>

                        Welcome to the digital journey of
                        Acropolis Institute of Technology
                        & Research.

                    </p>

                    <p>

                        Your verification request has been
                        successfully approved by our
                        verification team.

                    </p>

                    <div class="code-box">

                        <h2>
                            YOUR VERIFICATION CODE
                        </h2>

                        <div class="code">
                            {verification_code}
                        </div>

                    </div>

                    <p>

                        This verification code is uniquely
                        generated for your registered
                        email address and mobile number.

                    </p>

                    <p>

                        Please use this code to activate
                        your student account.

                    </p>

                    <br>

                    <p>

                        Regards,<br>
                        Acropolis Verification Team

                    </p>

                </div>

                <div class="footer">

                    © 2026 Acropolis Institute Digital Campus

                </div>

            </div>

        </body>

        </html>

        """

        # ---------------- EMAIL OBJECT ----------------

        msg = MIMEMultipart()

        msg["From"] = EMAIL_ADDRESS
        msg["To"] = receiver_email
        msg["Subject"] = subject

        msg.attach(
            MIMEText(html_body, "html")
        )

        # ---------------- SMTP SERVER ----------------

        server = smtplib.SMTP(
            "smtp.gmail.com",
            587
        )

        server.starttls()

        server.login(
            EMAIL_ADDRESS,
            EMAIL_PASSWORD
        )

        server.send_message(msg)

        server.quit()

        return {

            "success": True,
            "message": "Verification email sent successfully"

        }

    except Exception as e:

        return {

            "success": False,
            "message": str(e)

        }


# ---------------- TESTING ----------------

if __name__ == "__main__":

    response = send_verification_email(

        student_name="Vikas Rajput",

        receiver_email="example@gmail.com",

        verification_code="AXP741"

    )

    print(response)