from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
from datetime import datetime
# from bson import ObjectId
from backend.config import db
from backend.auth.middleware import mentor_required, admin_required


attendance_pdf_bp = Blueprint("attendance_pdf", __name__)

UPLOAD_DIR = "uploads/attendance_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

collection = db.attendance_pdfs
@attendance_pdf_bp.route("/api/attendance-pdf/upload", methods=["POST"])
@mentor_required
def upload_attendance_pdf(current_user):
    year = request.form.get("year")
    branch = request.form.get("branch")
    subject = request.form.get("subject")
    week = request.form.get("week")
    file = request.files.get("pdf")

    if not all([year, branch, subject, week, file]):
        return jsonify(success=False, message="Missing fields"), 400

    filename = secure_filename(
        f"{branch}_{subject}_week{week}.pdf"
    )
    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)

    query = {
        "year": year,
        "branch": branch,
        "subject": subject,
        "week": int(week)
    }

    data = {
        **query,
        "teacherId": current_user["mentorId"],
        "teacherName": current_user["name"],
        "pdfUrl": f"/{filepath}",
        "uploadedAt": datetime.utcnow(),
        "updated": False
    }

    collection.update_one(query, {"$set": data}, upsert=True)

    return jsonify(success=True, message="Attendance PDF uploaded")
@attendance_pdf_bp.route("/api/admin/attendance-pdfs", methods=["GET"])
@admin_required
def view_attendance_pdfs():
    year = request.args.get("year")
    branch = request.args.get("branch")

    if not year or not branch:
        return jsonify(success=False, message="Missing filters"), 400

    pdfs = list(collection.find(
        {"year": year, "branch": branch},
        {"_id": 0}
    ).sort("week", 1))

    return jsonify(success=True, pdfs=pdfs)
@attendance_pdf_bp.route("/api/admin/attendance-pdf/mark-updated", methods=["POST"])
@admin_required
def mark_attendance_updated():
    key = request.json.get("key")
    if not key:
        return jsonify(success=False, message="Key required"), 400

    year, branch, subject, week = key.split("_")

    collection.update_one(
        {
            "year": year,
            "branch": branch,
            "subject": subject,
            "week": int(week)
        },
        {"$set": {"updated": True}}
    )

    return jsonify(success=True, message="Marked as updated")
