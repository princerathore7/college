# __init__.py
import os
from flask import Flask, jsonify
from flask_cors import CORS
from mongoengine import connect
from pymongo import MongoClient
import cloudinary
from dotenv import load_dotenv

# -------------------------
# LOAD ENV VARIABLES
# -------------------------
load_dotenv()  # loads .env automatically

# -------------------------
# IMPORT BLUEPRINTS
# -------------------------
from notes import notes_bp
from routes.class_management import class_mgmt_bp
from routes.students import students_bp
from routes.mentors import mentors_bp
from routes.attendance import attendance_bp
from routes.assignments import assignments_bp
from routes.classes import classes_bp
from routes.exams import exams_bp
from routes.marks import marks_bp
from routes.notices_bp import notices_bp
from events import events_bp
from timetables import timetables_bp
from routes.bus_bp import bus_bp
from routes.management import management_bp
# -------------------------
# FLASK APP SETUP
# -------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# 🔥 GLOBAL CORS — WORKS FOR ALL BLUEPRINTS AUTOMATICALLY
CORS(app, resources={r"/*": {
    "origins": [
        "https://acropoliss.netlify.app",
        "https://college-hwbb.onrender.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    "supports_credentials": True,
}})

# -------------------------
# MONGODB CONNECTION
# -------------------------
# MongoEngine (college database)
connect(
    db="college",
    alias="db1",
    host=os.getenv("MONGO_COLLEGE_URI")
)

# MongoEngine (college_db database)
connect(
    db="college_db",
    alias="db2",
    host=os.getenv("MONGO_COLLEGE_DB_URI")
)

# PyMongo (college_db)
client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client["college_db"]
students_collection = db["students"]

# Cloudinary config
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# -------------------------
# REGISTER BLUEPRINTS
# -------------------------
app.register_blueprint(notes_bp)
app.register_blueprint(class_mgmt_bp)
app.register_blueprint(students_bp)
app.register_blueprint(mentors_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(assignments_bp)
app.register_blueprint(classes_bp)
app.register_blueprint(exams_bp)
app.register_blueprint(marks_bp)
app.register_blueprint(notices_bp)
app.register_blueprint(events_bp)
app.register_blueprint(timetables_bp)
app.register_blueprint(bus_bp)
app.register_blueprint(management_bp)
# -------------------------
# DEFAULT ROUTE
# -------------------------
@app.route('/')
def home():
    return jsonify({"message": "College Dashboard API running"}), 200

# -------------------------
# GLOBAL ERROR HANDLERS
# -------------------------
@app.errorhandler(404)
def not_found_error(e):
    return jsonify({"success": False, "message": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"success": False, "message": "Internal server error"}), 500

# -------------------------
# MAIN ENTRY POINT
# -------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
