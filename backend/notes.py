from flask import Blueprint, request, jsonify, redirect
from db import db
from utils import generate_id
import cloudinary
import cloudinary.uploader
from flask_cors import cross_origin
from datetime import datetime 

notes_bp = Blueprint("notes_bp", __name__, url_prefix="/api/notes")

ALLOWED = {"pdf"}

def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED


# ----------------- UPLOAD NOTE -----------------
@notes_bp.route("", methods=["POST", "OPTIONS"])
@cross_origin()
def upload_note():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    deadline = request.form.get("deadline", "")
    class_name = request.form.get("class", "").replace(" ", "").upper()
    file = request.files.get("file")

    if not title or not subject or not class_name or not file:
        return jsonify({"success": False, "message": "Missing fields"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "PDF only"}), 400

    note_id = generate_id("N")
    safe_filename = file.filename

    try:
        # ---------- IMPORTANT RAW UPLOAD ----------
        upload_result = cloudinary.uploader.upload(
            file,
            resource_type="raw",          # <--- MUST FOR PDF
            folder="notes",               # folder in cloudinary
            public_id=f"note_{note_id}",  # unique id
            overwrite=True
        )
        # ------------------------------------------
        file_url = upload_result.get("secure_url")

    except Exception as e:
        return jsonify({"success": False, "message": f"Cloudinary upload error: {str(e)}"}), 500

    rec = {
        "noteId": note_id,
        "title": title,
        "subject": subject,
        "deadline": deadline,
        "class": class_name,
        "originalFilename": safe_filename,
        "file_url": file_url,
        "uploadedAt": datetime.utcnow().isoformat()
    }

    db.notes.insert_one(rec)

    return jsonify({"success": True, "noteId": note_id, "file_url": file_url}), 201



# ----------------- GET ALL NOTES -----------------
@notes_bp.route("", methods=["GET"])
@cross_origin()
def list_all():
    docs = list(db.notes.find({}, {"_id": 0}))
    return jsonify({"success": True, "notes": docs})


# ----------------- GET NOTES BY CLASS -----------------
@notes_bp.route("/class/<className>", methods=["GET"])
@cross_origin()
def class_notes(className):
    className = className.replace(" ", "").upper()
    docs = list(db.notes.find({"class": className}, {"_id": 0}))
    return jsonify({"success": True, "notes": docs})


# ----------------- SERVE FILE (VIEW/DOWNLOAD) -----------------
@notes_bp.route("/<noteId>/file", methods=["GET"])
@cross_origin()
def serve_file(noteId):
    rec = db.notes.find_one({"noteId": noteId})

    if not rec:
        return jsonify({"success": False, "message": "Not found"}), 404

    file_url = rec.get("file_url")
    if not file_url:
        return jsonify({"success": False, "message": "File URL missing"}), 404

    # View / Download Mode
    download = request.args.get("download")

    if download:
        url = file_url + ("?fl_attachment=true" if "?" not in file_url else "&fl_attachment=true")
    else:
        url = file_url + ("?fl_attachment=false" if "?" not in file_url else "&fl_attachment=false")

    return redirect(url)


# ----------------- DIRECT PDF URL (for safe download) -----------------
@notes_bp.route("/<noteId>/direct", methods=["GET"])
@cross_origin()
def direct_url(noteId):
    rec = db.notes.find_one({"noteId": noteId}, {"_id": 0, "file_url": 1})
    if not rec:
        return jsonify({"success": False, "message": "Not found"}), 404

    return jsonify({"success": True, "url": rec["file_url"]})

# ----------------- DELETE NOTE -----------------
@notes_bp.route("/<noteId>", methods=["DELETE"])
@cross_origin()
def delete_note(noteId):
    rec = db.notes.find_one({"noteId": noteId})
    if not rec:
        return jsonify({"success": False, "message": "Not found"}), 404

    public_id = f"notes/note_{noteId}"

    try:
        cloudinary.uploader.destroy(public_id, resource_type="raw", invalidate=True)
    except Exception as e:
        return jsonify({"success": False, "message": f"Cloudinary delete error: {str(e)}"}), 500

    db.notes.delete_one({"noteId": noteId})

    return jsonify({"success": True})
