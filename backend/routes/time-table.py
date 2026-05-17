from flask import Blueprint, request, jsonify, current_app
from flask_cors import CORS
from werkzeug.utils import secure_filename
from bson import ObjectId
from datetime import datetime
import os

# ---------------- Blueprint ----------------
timetable_bp = Blueprint(
    "timetable_bp",
    __name__,
    url_prefix="/api/timetable"
)

CORS(timetable_bp)

# ---------------- MongoDB ----------------
# app.py me:
# from db import db
# app.register_blueprint(timetable_bp)

from db import db

# ---------------- Upload Config ----------------
UPLOAD_FOLDER = "uploads/timetables"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {"pdf"}


# =========================================================
# Helper Functions
# =========================================================

def allowed_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def serialize_doc(doc):
    doc["_id"] = str(doc["_id"])
    return doc


# =========================================================
# 1. CREATE / UPDATE COMPLETE WEEKLY TIMETABLE
# =========================================================

@timetable_bp.route("/set-weekly", methods=["POST"])
def set_weekly_timetable():

    """
    Expected JSON:

    {
      "className": "IT-1-A",
      "mentorID": "MENTOR123",

      "weeklySchedule": {

        "Monday": [
          {
            "startTime": "08:00 AM",
            "endTime": "09:45 AM",
            "type": "subject",
            "subject": "Mathematics",
            "faculty": "Sharma Sir",
            "room": "A-101"
          },

          {
            "startTime": "09:45 AM",
            "endTime": "10:00 AM",
            "type": "break",
            "title": "Short Break"
          }
        ],

        "Tuesday": [],

        "Wednesday": [],

        "Thursday": [],

        "Friday": [],

        "Saturday": []

      }
    }
    """

    try:

        data = request.json

        class_name = data.get("className")
        mentor_id = data.get("mentorID")
        weekly_schedule = data.get("weeklySchedule")

        if not class_name:
            return jsonify({
                "success": False,
                "message": "className is required"
            }), 400

        if not weekly_schedule:
            return jsonify({
                "success": False,
                "message": "weeklySchedule is required"
            }), 400

        existing = db.timetables.find_one({
            "className": class_name
        })

        timetable_data = {
            "className": class_name,
            "mentorID": mentor_id,
            "weeklySchedule": weekly_schedule,
            "updatedAt": datetime.utcnow()
        }

        if existing:

            db.timetables.update_one(
                {"className": class_name},
                {"$set": timetable_data}
            )

            return jsonify({
                "success": True,
                "message": "Weekly timetable updated successfully"
            })

        else:

            timetable_data["createdAt"] = datetime.utcnow()

            db.timetables.insert_one(timetable_data)

            return jsonify({
                "success": True,
                "message": "Weekly timetable created successfully"
            })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 2. GET COMPLETE TIMETABLE CLASS-WISE
# =========================================================

@timetable_bp.route("/class/<class_name>", methods=["GET"])
def get_class_timetable(class_name):

    try:

        timetable = db.timetables.find_one({
            "className": class_name
        })

        if not timetable:
            return jsonify({
                "success": False,
                "message": "Timetable not found"
            }), 404

        return jsonify({
            "success": True,
            "timetable": serialize_doc(timetable)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 3. GET SPECIFIC DAY TIMETABLE
# =========================================================

@timetable_bp.route("/class/<class_name>/<day>", methods=["GET"])
def get_day_timetable(class_name, day):

    try:

        timetable = db.timetables.find_one({
            "className": class_name
        })

        if not timetable:
            return jsonify({
                "success": False,
                "message": "Timetable not found"
            }), 404

        weekly_schedule = timetable.get("weeklySchedule", {})

        day_schedule = weekly_schedule.get(day, [])

        return jsonify({
            "success": True,
            "className": class_name,
            "day": day,
            "schedule": day_schedule
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 4. UPDATE SINGLE DAY ONLY
# =========================================================

@timetable_bp.route("/update-day", methods=["PUT"])
def update_single_day():

    """
    {
      "className": "IT-1-A",
      "day": "Monday",

      "schedule": [
        {
          "startTime": "08:00 AM",
          "endTime": "09:45 AM",
          "type": "subject",
          "subject": "Physics",
          "faculty": "Raj Sir",
          "room": "A-201"
        }
      ]
    }
    """

    try:

        data = request.json

        class_name = data.get("className")
        day = data.get("day")
        schedule = data.get("schedule")

        if not class_name or not day:
            return jsonify({
                "success": False,
                "message": "className and day required"
            }), 400

        update_field = f"weeklySchedule.{day}"

        db.timetables.update_one(
            {"className": class_name},
            {
                "$set": {
                    update_field: schedule,
                    "updatedAt": datetime.utcnow()
                }
            }
        )

        return jsonify({
            "success": True,
            "message": f"{day} timetable updated successfully"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 5. DELETE TIMETABLE
# =========================================================

@timetable_bp.route("/delete/<class_name>", methods=["DELETE"])
def delete_timetable(class_name):

    try:

        result = db.timetables.delete_one({
            "className": class_name
        })

        if result.deleted_count == 0:
            return jsonify({
                "success": False,
                "message": "Timetable not found"
            }), 404

        return jsonify({
            "success": True,
            "message": "Timetable deleted successfully"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 6. GET ALL CLASSES TIMETABLES
# =========================================================

@timetable_bp.route("/all", methods=["GET"])
def get_all_timetables():

    try:

        timetables = list(db.timetables.find())

        result = []

        for item in timetables:
            result.append(serialize_doc(item))

        return jsonify({
            "success": True,
            "count": len(result),
            "timetables": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 7. UPLOAD TIMETABLE PDF
# =========================================================

@timetable_bp.route("/upload-pdf", methods=["POST"])
def upload_timetable_pdf():

    """
    FormData:

    file
    className
    uploadedBy
    """

    try:

        if "file" not in request.files:
            return jsonify({
                "success": False,
                "message": "No file uploaded"
            }), 400

        file = request.files["file"]

        class_name = request.form.get("className")
        uploaded_by = request.form.get("uploadedBy")

        if file.filename == "":
            return jsonify({
                "success": False,
                "message": "No selected file"
            }), 400

        if not allowed_file(file.filename):
            return jsonify({
                "success": False,
                "message": "Only PDF files allowed"
            }), 400

        filename = secure_filename(file.filename)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        final_filename = f"{class_name}_{timestamp}_{filename}"

        file_path = os.path.join(
            UPLOAD_FOLDER,
            final_filename
        )

        file.save(file_path)

        pdf_data = {
            "className": class_name,
            "uploadedBy": uploaded_by,
            "fileName": final_filename,
            "filePath": file_path,
            "uploadedAt": datetime.utcnow()
        }

        db.timetable_pdfs.insert_one(pdf_data)

        return jsonify({
            "success": True,
            "message": "PDF uploaded successfully",
            "fileName": final_filename,
            "filePath": file_path
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 8. GET TIMETABLE PDFs
# =========================================================

@timetable_bp.route("/pdfs/<class_name>", methods=["GET"])
def get_timetable_pdfs(class_name):

    try:

        pdfs = list(db.timetable_pdfs.find({
            "className": class_name
        }))

        result = []

        for pdf in pdfs:
            result.append(serialize_doc(pdf))

        return jsonify({
            "success": True,
            "pdfs": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 9. ADD HOLIDAY
# =========================================================

@timetable_bp.route("/holiday/add", methods=["POST"])
def add_holiday():

    """
    {
      "date": "2026-05-20",
      "title": "Festival Holiday",
      "description": "College Closed"
    }
    """

    try:

        data = request.json

        holiday_data = {
            "date": data.get("date"),
            "title": data.get("title"),
            "description": data.get("description"),
            "createdAt": datetime.utcnow()
        }

        db.holidays.insert_one(holiday_data)

        return jsonify({
            "success": True,
            "message": "Holiday added successfully"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# 10. GET HOLIDAYS
# =========================================================

@timetable_bp.route("/holidays", methods=["GET"])
def get_holidays():

    try:

        holidays = list(db.holidays.find())

        result = []

        for holiday in holidays:
            result.append(serialize_doc(holiday))

        return jsonify({
            "success": True,
            "holidays": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500