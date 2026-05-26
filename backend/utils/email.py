import os
import requests

# ---------------- RESEND API KEY ----------------

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# ---------------- SEND VERIFICATION EMAIL ----------------

def send_verification_email(

    student_name,
    student_email,
    verification_code,
    enrollment,
    branch,
    semester,
    year,
    phone

):

    try:

        # ---------------- EMAIL HTML ----------------

        html_content = f"""

        <div style="background:#edf3fb;padding:40px;font-family:Arial,sans-serif;">

            <div style="
                max-width:700px;
                margin:auto;
                background:white;
                border-radius:20px;
                overflow:hidden;
                box-shadow:0 10px 30px rgba(0,0,0,0.1);
            ">

                <div style="
                    background:linear-gradient(135deg,#001f4d,#003366,#004080);
                    color:white;
                    padding:40px;
                    text-align:center;
                ">

                    <h1 style="
                        margin:0;
                        font-size:34px;
                        letter-spacing:1px;
                    ">
                        ACROPOLIS DIGITAL CAMPUS
                    </h1>

                    <p style="
                        margin-top:12px;
                        font-size:15px;
                        color:#dbeafe;
                    ">
                        Powered By S&P Developments
                    </p>

                </div>

                <div style="padding:40px;">

                    <h2 style="
                        color:#002855;
                        margin-bottom:18px;
                    ">
                        Welcome {student_name}
                    </h2>

                    <p style="
                        color:#475569;
                        line-height:1.8;
                        font-size:15px;
                    ">

                        Your digital student verification request
                        has been successfully received.

                    </p>

                    <div style="
                        background:#f8fbff;
                        border:1px solid #dbe7f5;
                        padding:25px;
                        border-radius:18px;
                        margin-top:25px;
                        margin-bottom:25px;
                    ">

                        <h3 style="
                            margin-top:0;
                            color:#003366;
                        ">
                            Student Information
                        </h3>

                        <p><b>Name:</b> {student_name}</p>

                        <p><b>Enrollment:</b> {enrollment}</p>

                        <p><b>Branch:</b> {branch}</p>

                        <p><b>Semester:</b> {semester}</p>

                        <p><b>Year:</b> {year}</p>

                        <p><b>Phone:</b> {phone}</p>

                        <p><b>Email:</b> {student_email}</p>

                    </div>

                    <div style="
                        background:#003366;
                        color:white;
                        text-align:center;
                        padding:30px;
                        border-radius:18px;
                        margin-top:30px;
                        margin-bottom:30px;
                    ">

                        <h2 style="
                            margin-top:0;
                            margin-bottom:15px;
                        ">
                            YOUR VERIFICATION CODE
                        </h2>

                        <div style="
                            font-size:48px;
                            font-weight:700;
                            letter-spacing:10px;
                        ">
                            {verification_code}
                        </div>

                    </div>

                    <p style="
                        color:#475569;
                        line-height:1.8;
                        font-size:15px;
                    ">

                        Please use this verification code to
                        activate your student account securely.

                    </p>

                    <br>

                    <p style="
                        color:#334155;
                        line-height:1.8;
                    ">

                        Regards,<br>

                        Acropolis Verification Team<br>

                        S&P Developments

                    </p>

                </div>

                <div style="
                    background:#f1f5f9;
                    padding:20px;
                    text-align:center;
                    color:#64748b;
                    font-size:13px;
                ">

                    © 2026 Acropolis Digital Campus

                </div>

            </div>

        </div>

        """

        # ---------------- RESEND API REQUEST ----------------

        headers = {

            "Authorization": f"Bearer {RESEND_API_KEY}",

            "Content-Type": "application/json"

        }

        payload = {

            "from": "Acropolis Digital Campus <onboarding@resend.dev>",

            "to": [student_email],

            "subject": "Your Acropolis Verification Code",

            "html": html_content

        }

        response = requests.post(

            "https://api.resend.com/emails",

            headers=headers,

            json=payload

        )

        # ---------------- SUCCESS ----------------

        if response.status_code in [200, 201]:

            return {

                "success": True,

                "message": "Verification email sent successfully",

                "response": response.json()

            }

        # ---------------- FAILED ----------------

        else:

            return {

                "success": False,

                "message": "Email sending failed",

                "response": response.text

            }

    except Exception as e:

        return {

            "success": False,

            "message": str(e)

        }


# ---------------- TESTING ----------------

if __name__ == "__main__":

    result = send_verification_email(

        student_name="Vikas Rajput",

        student_email="test@example.com",

        verification_code="AXP741",

        enrollment="0827IT221001",

        branch="Information Technology",

        semester="4",

        year="2nd Year",

        phone="9876543210"

    )

    print(result)