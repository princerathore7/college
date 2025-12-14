from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from mongoengine import connect
from pymongo import MongoClient, WriteConcern
import os
import cloudinary
import cloudinary.uploader
import firebase_init
from threading import Thread
firebase_init.init_firebase()
# Import blueprints
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
from models.uniform_request import create_uniform_request, get_all_requests, update_status
from routes.bus_bp import bus_bp
from routes.management import management_bp
from routes.fine_bp import fine_bp
from routes.admin_students import admin_students_bp
from routes.notifications import notifications_bp
# ---------------------------------------------
# FLASK APP SETUP
# ---------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/*": {
    "origins": [
        "https://acropoliss.netlify.app",
        "https://college-hwbb.onrender.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    "supports_credentials": True
}})

# ---------------------------------------------
# MONGODB CONNECTION
# ---------------------------------------------
connect(db="college", alias="db1", host=os.getenv("MONGO_COLLEGE_URI"))
connect(db="college_db", alias="db2", host=os.getenv("MONGO_COLLEGE_DB_URI"))

client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client.get_database("college_db", write_concern=WriteConcern(w=1))  # safe write
students_collection = db["students"]

# Ensure indexes for faster queries (no majority issue)
students_collection.create_index("enrollment", background=True)
students_collection.create_index("branch", background=True)
students_collection.create_index("class_assigned", background=True)
db.classes.create_index("classname", background=True)
db.attendance.create_index([("branch", 1), ("date", 1)], background=True)

# ---------------------------------------------
# CLOUDINARY CONFIG
# ---------------------------------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")

# ---------------------------------------------
# REGISTER BLUEPRINTS
# ---------------------------------------------
for bp in [
    notices_bp, students_bp, mentors_bp, attendance_bp,
    assignments_bp, classes_bp, class_mgmt_bp,
    events_bp, exams_bp, timetables_bp, marks_bp,
    bus_bp, management_bp, notes_bp, fine_bp,
    admin_students_bp, notifications_bp
]:
    app.register_blueprint(bp)

# ---------------------------------------------
# BASIC ROUTES
# ---------------------------------------------
@app.route('/')
def home():
    return {"message": "College Dashboard API running"}, 200

@app.route("/mentor-signup")
def mentor_signup_page():
    return render_template("mentor-signup.html")

@app.route("/mentor-login")
def mentor_login_page():
    return render_template("mentor-login.html")

@app.route("/admin-dashboard")
def admin_dashboard():
    return render_template("admin-class-man.html")

# ---------------------------------------------
# TIMETABLE UPLOAD / DELETE / FETCH (background upload)
# ---------------------------------------------
def async_upload(pdf, filename):
    cloudinary.uploader.upload(pdf, public_id=filename, resource_type="raw", folder="timetables")

@app.route('/upload_timetable', methods=['POST'])
def upload_timetable():
    class_name = request.form['class_name']
    pdf = request.files['pdf']
    if pdf and pdf.filename.endswith('.pdf'):
        filename = f"{class_name}_timetable"
        Thread(target=async_upload, args=(pdf, filename)).start()
        return jsonify({'success': True, 'message': 'Timetable upload started!'}), 202
    return jsonify({'success': False, 'message': 'Invalid file type'}), 400

@app.route('/delete_timetable/<class_name>', methods=['DELETE'])
def delete_timetable(class_name):
    public_id = f"timetables/{class_name}_timetable"
    try:
        result = cloudinary.uploader.destroy(public_id, resource_type="raw")
        if result.get("result") == "ok":
            return jsonify({'success': True, 'message': 'Deleted successfully'})
        return jsonify({'success': False, 'message': 'File not found'})
    except Exception:
        return jsonify({'success': False, 'message': 'Error deleting file'})

@app.route("/api/timetables/classes", methods=["GET"])
def get_timetable_classes():
    try:
        result = cloudinary.api.resources(type="upload", prefix="timetables/", resource_type="raw", max_results=500)
        classes = [f["public_id"].replace("timetables/", "").replace("_timetable", "") for f in result.get("resources", [])]
        return jsonify({"success": True, "classes": classes})
    except Exception:
        return jsonify({"success": False, "classes": []})

@app.route("/api/timetables", methods=["GET"])
def get_timetable_by_class():
    class_name = request.args.get("class")
    if not class_name:
        return jsonify({"success": False, "message": "Class name missing"}), 400
    public_id = f"timetables/{class_name}_timetable"
    try:
        file_data = cloudinary.api.resource(public_id, resource_type="raw")
        return jsonify({"success": True, "timetables": [{"class": class_name, "file_url": file_data.get("secure_url")}]}), 200
    except Exception:
        return jsonify({"success": False, "message": "No timetable found"}), 404

# ---------------------------------------------
# UNIFORM REQUEST ROUTES
# ---------------------------------------------
@app.route("/api/uniform/request", methods=["POST"])
def create_request():
    data = request.json
    if not data or not data.get("item") or not data.get("student_name"):
        return jsonify({"success": False, "msg": "Missing required fields"}), 400
    try:
        req_result = create_uniform_request(data)
        inserted_id = str(req_result.inserted_id) if hasattr(req_result, "inserted_id") else "N/A"
        return jsonify({"success": True, "msg": "✅ Request submitted successfully!", "id": inserted_id}), 201
    except Exception as e:
        print("❌ Error creating uniform request:", e)
        return jsonify({"success": False, "msg": "Server error while saving request"}), 500

@app.route("/api/uniform/requests", methods=["GET"])
def fetch_requests():
    try:
        all_requests = get_all_requests()
        for r in all_requests:
            if "_id" in r:
                r["_id"] = str(r["_id"])
        return jsonify({"success": True, "requests": all_requests}), 200
    except Exception as e:
        print("❌ Error fetching requests:", e)
        return jsonify({"success": False, "msg": "Error fetching requests"}), 500

@app.route("/api/uniform/update-status/<req_id>", methods=["PUT"])
def modify_status(req_id):
    try:
        new_status = request.json.get("status")
        if not new_status:
            return jsonify({"success": False, "msg": "Missing status value"}), 400
        update_status(req_id, new_status)
        return jsonify({"success": True, "msg": f"✅ Status updated to '{new_status}' successfully!"}), 200
    except Exception as e:
        print("❌ Error updating status:", e)
        return jsonify({"success": False, "msg": "Error updating status"}), 500

# ---------------------------------------------
# STUDENT & CLASS ROUTES
# ---------------------------------------------
@app.route('/api/classes/<string:branch>/<string:class_name>/students', methods=['GET'])
def get_students_by_branch_class(branch, class_name):
    students = list(students_collection.find(
        {"branch": {"$regex": f"^{branch}$", "$options": "i"},
         "class_assigned": {"$regex": f"{class_name}", "$options": "i"}},
        {"_id": 0, "name": 1, "enrollment": 1, "branch": 1, "class_assigned": 1}
    ))
    return jsonify({"success": True, "students": students}), 200

@app.route('/api/students/<enrollment>/class', methods=['PUT'])
def update_student_class(enrollment):
    data = request.json
    new_class = data.get("class")
    if not new_class:
        return jsonify({"success": False, "message": "Missing class"}), 400
    result = students_collection.update_one({"enrollment": enrollment}, {"$set": {"class_assigned": new_class}})
    return jsonify({"success": result.modified_count > 0, "message": "Class updated successfully" if result.modified_count > 0 else "No changes made or enrollment not found"}), 200 if result.modified_count > 0 else 404

@app.route('/api/students/<enrollment>/branch', methods=['PUT'])
def update_student_branch(enrollment):
    data = request.json
    new_branch = data.get("branch")
    if not new_branch:
        return jsonify({"success": False, "message": "Missing branch"}), 400
    result = students_collection.update_one({"enrollment": enrollment}, {"$set": {"branch": new_branch}})
    return jsonify({"success": result.modified_count > 0, "message": "Branch updated successfully" if result.modified_count > 0 else "No changes made or enrollment not found"}), 200 if result.modified_count > 0 else 404

@app.route("/api/classes/create", methods=["POST"])
def create_class():
    try:
        data = request.json
        classname = data.get("classname")
        start = data.get("start")
        end = data.get("end")
        if not classname or not start or not end:
            return jsonify({"success": False, "message": "Missing fields"}), 400

        db.classes.insert_one({"classname": classname, "from": start, "to": end})

        prefix = start[:-3]
        start_num = int(start[-3:])
        end_num = int(end[-3:])
        students_bulk = [{"classname": classname, "enrollment": f"{prefix}{i:03d}"} for i in range(start_num, end_num+1)]
        if students_bulk:
            db.students.insert_many(students_bulk)

        return jsonify({"success": True, "message": "Class & Students Created"}), 201
    except Exception as e:
        print("Error:", e)
        return jsonify({"success": False, "message": "Server Error"}), 500

@app.route("/api/classes", methods=["GET"])
def get_classes():
    try:
        all_classes = list(db.classes.find({}))
        class_names = []
        for c in all_classes:
            if "classname" in c:
                class_names.append(c["classname"])
            elif "class_name" in c:
                class_names.append(c["class_name"])
            elif "classes" in c and isinstance(c["classes"], list):
                for cls in c["classes"]:
                    if "class_name" in cls:
                        class_names.append(cls["class_name"])
        return jsonify({"success": True, "classes": class_names})
    except Exception as e:
        print("Error fetching classes:", e)
        return jsonify({"success": False, "classes": [], "error": str(e)})

@app.route("/api/attendance/submit", methods=["POST"])
def submit_attendance():
    data = request.json
    db.attendance.insert_one({
        "branch": data.get("branch"), 
        "date": data["date"],
        "attendance": data["attendance"]
    })
    return jsonify({"success": True, "message": "Attendance Saved"})

@app.route('/api/students/<string:classname>', methods=['GET'])
def get_students_by_classname(classname):
    try:
        students = list(students_collection.find(
            {"classname": {"$regex": f"^{classname}$", "$options": "i"}},
            {"_id": 0, "enrollment": 1}
        ))
        return jsonify({"success": True, "students": students}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
@app.route("/send-notification", methods=["POST"])
def send_notification():
    data = request.json
    subscription = data["subscription"]
    message = data["message"]
    send_web_notification(subscription, message, VAPID_PRIVATE_KEY)
    return {"success": True}

# ---------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
