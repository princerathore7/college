# timetables.py
import os
from flask import Blueprint, request, jsonify, send_from_directory, current_app
from werkzeug.utils import secure_filename
from db import db                     # your pymongo db object
from utils import generate_id         # you already use this pattern

timetables_bp = Blueprint("timetables_bp", __name__, url_prefix="/api/timetables")

# Config
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "timetables")
ALLOWED_EXTENSIONS = {"pdf"}
os.makedirs(UPLOAD_DIR, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# POST /api/timetables  -> upload a pdf with form-data: class, file
@timetables_bp.route('', methods=['POST'])
def upload_timetable():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file part"}), 400

    file = request.files['file']
    class_name = request.form.get('class', '').strip().replace(" ", "").upper()  # normalize

    if not class_name:
        return jsonify({"success": False, "message": "Class is required"}), 400
    if file.filename == '':
        return jsonify({"success": False, "message": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Only PDF files are allowed"}), 400

    filename = secure_filename(file.filename)
    timetable_id = generate_id("T")
    stored_filename = f"{timetable_id}__{filename}"
    save_path = os.path.join(UPLOAD_DIR, stored_filename)

    try:
        file.save(save_path)
        # use normalized class_name here
        record = {
            "timetableId": timetable_id,
            "class": class_name,   # <- fix applied
            "originalFilename": filename,
            "storedFilename": stored_filename,
            "uploadedAt": __import__("datetime").datetime.utcnow().isoformat()
        }
        db.timetables.insert_one(record)
        return jsonify({"success": True, "message": "Timetable uploaded", "timetableId": timetable_id}), 201

    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        return jsonify({"success": False, "message": str(e)}), 500

# GET /api/timetables?class=1A -> list timetables, optional class filter
@timetables_bp.route('', methods=['GET'])
def list_timetables():
    class_q = request.args.get("class")
    query = {}
    try:
        if class_q:
            # ✅ normalize input like "1-a", "1 - A", " 1A ", etc.
            normalized = class_q.replace(" ", "").replace("-", "").upper()
            # use regex to allow flexible match (case-insensitive)
            query["class"] = {"$regex": f"^{normalized}$", "$options": "i"}

        docs = list(db.timetables.find(query, {"_id": 0}))
        return jsonify({"success": True, "timetables": docs}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# GET /api/timetables/<timetableId>/file -> serves the PDF file
@timetables_bp.route('/<timetableId>/file', methods=['GET'])
def serve_timetable_file(timetableId):
    rec = db.timetables.find_one({"timetableId": timetableId})
    if not rec:
        return jsonify({"success": False, "message": "Not found"}), 404
    stored = rec.get("storedFilename")
    if not stored:
        return jsonify({"success": False, "message": "File missing"}), 404
    try:
        return send_from_directory(UPLOAD_DIR, stored, as_attachment=False)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# DELETE /api/timetables/<timetableId> -> delete record + file
@timetables_bp.route('/<timetableId>', methods=['DELETE'])
def delete_timetable(timetableId):
    rec = db.timetables.find_one({"timetableId": timetableId})
    if not rec:
        return jsonify({"success": False, "message": "Timetable not found"}), 404
    stored = rec.get("storedFilename")
    try:
        db.timetables.delete_one({"timetableId": timetableId})
        if stored:
            fp = os.path.join(UPLOAD_DIR, stored)
            if os.path.exists(fp):
                os.remove(fp)
        return jsonify({"success": True, "message": "Timetable deleted"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
