from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime
import cloudinary.uploader

from db import db
import json

from auth.middleware import admin_required # teacher_required hata diya

forms_bp = Blueprint("forms_bp", __name__,url_prefix="/api")

# ==============================
# COLLECTIONS
# ==============================
forms_col = db.forms              # form master
submissions_col = db.form_submissions


# ==============================
# CREATE FORM (NO AUTH)
# ==============================
@forms_bp.route("/forms", methods=["POST"])
def create_form():
    data = request.form

    title = data.get("title")
    description = data.get("description", "")
    fields_str = data.get("fields", "[]")

    try:
        fields = json.loads(fields_str)
    except Exception:
        return jsonify({"error": "Invalid fields format"}), 400

    if not title or not fields:
        return jsonify({"error": "Title and fields required"}), 400

    pdf_urls = []
    for pdf in request.files.getlist("pdfs"):
        upload = cloudinary.uploader.upload(
            pdf,
            resource_type="raw",
            folder="forms/pdfs"
        )
        pdf_urls.append(upload["secure_url"])

    form_doc = {
        "title": title,
        "description": description,
        "fields": fields,
        "pdfs": pdf_urls,
        "created_at": datetime.utcnow(),
        "active": True
    }

    result = forms_col.insert_one(form_doc)

    return jsonify({
        "message": "Form created successfully",
        "form_id": str(result.inserted_id)
    }), 201


# ==============================
# GET ALL ACTIVE FORMS (STUDENT)
# ==============================
@forms_bp.route("/forms", methods=["GET"])
def get_forms():
    forms = []
    for f in forms_col.find({"active": True}).sort("created_at", -1):
        forms.append({
            "id": str(f["_id"]),
            "title": f["title"],
            "description": f.get("description", ""),
            "fields_count": len(f["fields"])
        })

    return jsonify(forms), 200


# ==============================
# GET SINGLE FORM (STUDENT)
# ==============================
@forms_bp.route("/forms/<form_id>", methods=["GET"])
def get_single_form(form_id):
    form = forms_col.find_one({"_id": ObjectId(form_id), "active": True})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    return jsonify({
        "id": str(form["_id"]),
        "title": form["title"],
        "description": form.get("description", ""),
        "fields": form["fields"],
        "pdfs": form.get("pdfs", [])
    }), 200


# ==============================
# SUBMIT FORM (STUDENT)
# ==============================
@forms_bp.route("/forms/<form_id>/submit", methods=["POST"])

def submit_form(form_id):
    form = forms_col.find_one({"_id": ObjectId(form_id)})
    if not form:
        return jsonify({"error": "Invalid form"}), 404

    responses = {}

    for field in form["fields"]:
        label = field["label"]
        field_type = field["type"]

        if field_type == "file":
            file = request.files.get(label)
            if file:
                upload = cloudinary.uploader.upload(
                    file,
                    resource_type="raw",
                    folder="forms/submissions"
                )
                responses[label] = upload["secure_url"]
        else:
            responses[label] = request.form.get(label)

    submission = {
        "form_id": ObjectId(form_id),
        "form_title": form["title"],
        "enrollment": request.user["enrollment"],
        "student_name": request.user["name"],
        "responses": responses,
        "submitted_at": datetime.utcnow()
    }

    submissions_col.insert_one(submission)

    return jsonify({"message": "Form submitted successfully"}), 201


# ==============================
# GET FORMS WITH SUBMISSION COUNT (ADMIN / TEACHER)
# ==============================
@forms_bp.route("/admin/forms", methods=["GET"])
@admin_required
def get_forms_admin():
    forms = []
    for f in forms_col.find():
        count = submissions_col.count_documents({"form_id": f["_id"]})
        forms.append({
            "id": str(f["_id"]),
            "name": f["title"],
            "submissions": count
        })

    return jsonify(forms), 200


# ==============================
# GET SUBMISSIONS OF A FORM
# ==============================
@forms_bp.route("/admin/forms/<form_id>/submissions", methods=["GET"])
@admin_required
def get_form_submissions(form_id):
    submissions = []
    for s in submissions_col.find({"form_id": ObjectId(form_id)}).sort("submitted_at", -1):
        submissions.append({
            "id": str(s["_id"]),
            "enrollment": s["enrollment"],
            "name": s["student_name"],
            "submitted_at": s["submitted_at"]
        })

    return jsonify(submissions), 200


# ==============================
# VIEW SINGLE SUBMISSION
# ==============================
@forms_bp.route("/admin/submissions/<submission_id>", methods=["GET"])
@admin_required
def view_submission(submission_id):
    s = submissions_col.find_one({"_id": ObjectId(submission_id)})
    if not s:
        return jsonify({"error": "Submission not found"}), 404

    return jsonify({
        "form_name": s["form_title"],
        "enrollment": s["enrollment"],
        "student_name": s["student_name"],
        "submitted_at": s["submitted_at"],
        "responses": s["responses"]
    }), 200
# ==============================
# GET SUBMISSIONS OF A SINGLE FORM (ADMIN / TEACHER)
# ==============================
@forms_bp.route("/admin/forms/<form_id>/submissions", methods=["GET"])
@admin_required
def get_form_submissions_by_id(form_id):
    try:
        form = forms_col.find_one({"_id": ObjectId(form_id)})
        if not form:
            return jsonify({"error": "Form not found"}), 404

        submissions = []

        for s in submissions_col.find(
            {"form_id": ObjectId(form_id)}
        ).sort("submitted_at", -1):

            submissions.append({
                "id": str(s["_id"]),
                "enrollment": s["enrollment"],
                "student_name": s["student_name"],
                "submitted_at": s["submitted_at"],
                "form_title": s["form_title"]
            })

        return jsonify({
            "form_id": form_id,
            "form_title": form["title"],
            "total_submissions": len(submissions),
            "submissions": submissions
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ==============================
# APPROVE / DISAPPROVE SUBMISSION (ADMIN)
# ==============================
@forms_bp.route("/admin/submissions/<submission_id>/status", methods=["POST"])
@admin_required
def update_submission_status(submission_id):
    """
    Expected JSON:
    {
        "status": "approved" / "disapproved",
        "reason": "Optional, required if disapproved"
    }
    """
    data = request.json
    status = data.get("status")
    reason = data.get("reason", "")

    if status not in ["approved", "disapproved"]:
        return jsonify({"error": "Invalid status"}), 400

    if status == "disapproved" and not reason:
        return jsonify({"error": "Reason required for disapproval"}), 400

    result = submissions_col.update_one(
        {"_id": ObjectId(submission_id)},
        {"$set": {
            "status": status,
            "reason": reason,
            "status_updated_at": datetime.utcnow()
        }}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Submission not found"}), 404

    return jsonify({"message": f"Submission marked as {status}"}), 200

# ==============================
# GET MY SUBMITTED FORMS (STUDENT)
# ==============================
@forms_bp.route("/student/my-submissions", methods=["GET"])
def get_my_submissions():
    enrollment = request.user["enrollment"]

    submissions = []
    for s in submissions_col.find({"enrollment": enrollment}).sort("submitted_at", -1):
        submissions.append({
            "submission_id": str(s["_id"]),
            "form_title": s["form_title"],
            "submitted_at": s["submitted_at"],
            "status": s.get("status", "pending"),
            "reason": s.get("reason", "")
        })

    return jsonify(submissions), 200