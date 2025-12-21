from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
from utils import generate_id
import cloudinary
import cloudinary.uploader
from db import db
from auth.middleware import mentor_required, admin_required
from bson import ObjectId


attendance_pdf_bp = Blueprint("attendance_pdf_bp", __name__)

ALLOWED = {"pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED

# =========================
# MENTOR → UPLOAD PDF
# =========================
@attendance_pdf_bp.route("/api/attendance-pdf/upload", methods=["POST"])
def upload_attendance_pdf():
    try:
        year    = request.form.get("year")
        branch  = request.form.get("branch")
        subject = request.form.get("subject")
        week    = request.form.get("week")
        file    = request.files.get("pdf")

        if not all([year, branch, subject, week, file]):
            return jsonify({"success": False, "message": "Missing fields"}), 400

        if not allowed_file(file.filename):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        # Generate unique filename
        filename = f"{year}_{branch}_{subject}_week{week}_{generate_id()}.pdf"

        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file,
            resource_type="raw",  # for PDFs
            public_id=f"attendance_pdfs/{filename}",
            overwrite=True
        )

        pdf_url = upload_result.get("secure_url")
        public_id = upload_result.get("public_id")

        if not pdf_url:
            return jsonify({"success": False, "message": "Upload failed"}), 500

        # Save info in MongoDB
        query = {"year": year, "branch": branch, "subject": subject, "week": int(week)}
        data = {
            **query,
            "pdfUrl": pdf_url,
            "filename": filename,
            "cloudinary_id": public_id,
            "uploadedAt": datetime.utcnow(),
            "updated": False
        }

        db.attendance_pdfs.update_one(query, {"$set": data}, upsert=True)

        return jsonify({"success": True, "message": "Attendance PDF uploaded", "pdfUrl": pdf_url})

    except Exception as e:
        print("Error uploading PDF:", e)
        return jsonify({"success": False, "message": str(e)}), 500

# =========================
# ADMIN → VIEW PDFs
# =========================
@attendance_pdf_bp.route("/api/attendance-pdfs", methods=["GET"])
def view_attendance_pdfs():
    year = request.args.get("year")
    branch = request.args.get("branch")

    if not year or not branch:
        return jsonify(success=False, message="Missing filters"), 400

    pdfs = list(db.attendance_pdfs.find({"year": year, "branch": branch}))

    serialized = []
    for pdf in pdfs:
        serialized.append({
            "_id": str(pdf["_id"]),
            "year": pdf["year"],
            "branch": pdf["branch"],
            "subject": pdf["subject"],
            "week": pdf["week"],
            "pdfUrl": pdf["pdfUrl"],
            "updated": pdf.get("updated", False),
        })

    return jsonify(success=True, pdfs=serialized)

# =========================
# ADMIN → MARK UPDATED
# =========================
@attendance_pdf_bp.route("/api/admin/attendance-pdf/mark-updated", methods=["POST"])
def mark_attendance_updated():
    try:
        key = request.json.get("key")
        if not key:
            return jsonify(success=False, message="Key required"), 400

        year, branch, subject, week = key.split("_")

        db.attendance_pdfs.update_one(
            {"year": year, "branch": branch, "subject": subject, "week": int(week)},
            {"$set": {"updated": True}}
        )

        return jsonify(success=True, message="Marked as updated")
    except Exception as e:
        print("Error marking updated:", e)
        return jsonify(success=False, message=str(e)), 500

# =========================
# DELETE PDF
# =========================
@attendance_pdf_bp.route("/api/attendance-pdf/delete/<pdf_id>", methods=["DELETE"])
def delete_attendance_pdf(pdf_id):
    try:
        if not ObjectId.is_valid(pdf_id):
            return jsonify({"success": False, "message": "Invalid PDF ID"}), 400

        pdf = db.attendance_pdfs.find_one({"_id": ObjectId(pdf_id)})
        if not pdf:
            return jsonify({"success": False, "message": "PDF not found"}), 404

        # Delete PDF from Cloudinary
        cloud_id = pdf.get("cloudinary_id")
        if cloud_id:
            cloudinary.uploader.destroy(cloud_id, resource_type="raw")

        # Delete record from MongoDB
        db.attendance_pdfs.delete_one({"_id": ObjectId(pdf_id)})

        return jsonify({"success": True, "message": "PDF deleted successfully"})

    except Exception as e:
        print("Error deleting PDF:", e)
        return jsonify({"success": False, "message": str(e)}), 500
# =========================
# Update PDF
# =========================
@attendance_pdf_bp.route("/api/attendance-pdf/update/<pdf_id>", methods=["POST"])
def update_attendance_pdf(pdf_id):
    try:
        if not ObjectId.is_valid(pdf_id):
            return jsonify({"success": False, "message": "Invalid PDF ID"}), 400

        file = request.files.get("pdf")
        if not file:
            return jsonify({"success": False, "message": "No PDF file provided"}), 400

        # Fetch old record
        pdf = db.attendance_pdfs.find_one({"_id": ObjectId(pdf_id)})
        if not pdf:
            return jsonify({"success": False, "message": "PDF not found"}), 404

        # Delete old file from Cloudinary
        cloud_id = pdf.get("cloudinary_id")
        if cloud_id:
            cloudinary.uploader.destroy(cloud_id, resource_type="raw")

        # Upload new file
        filename = f"{pdf['year']}_{pdf['branch']}_{pdf['subject']}_week{pdf['week']}_{generate_id()}.pdf"
        upload_result = cloudinary.uploader.upload(
            file,
            resource_type="raw",
            public_id=f"attendance_pdfs/{filename}",
            overwrite=True
        )
        pdf_url = upload_result.get("secure_url")
        public_id = upload_result.get("public_id")

        # Update MongoDB record & reset updated status
        db.attendance_pdfs.update_one(
            {"_id": ObjectId(pdf_id)},
            {"$set": {
                "pdfUrl": pdf_url,
                "filename": filename,
                "cloudinary_id": public_id,
                "updated": False,
                "uploadedAt": datetime.utcnow()
            }}
        )

        return jsonify({"success": True, "message": "PDF updated", "pdfUrl": pdf_url})

    except Exception as e:
        print("Error updating PDF:", e)
        return jsonify({"success": False, "message": str(e)}), 500
