from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import cloudinary
import cloudinary.uploader
from db import db

bus_bp = Blueprint("bus_bp", __name__, url_prefix="/api/bus")


# ----------------- Upload PDF -----------------
@bus_bp.route("/upload", methods=["POST", "OPTIONS"])
@cross_origin()
def upload_bus_pdf():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    if "pdf" not in request.files:
        return jsonify({"success": False, "message": "No file part"}), 400

    pdf = request.files["pdf"]

    if pdf.filename == "":
        return jsonify({"success": False, "message": "No selected file"}), 400

    if not pdf.filename.endswith(".pdf"):
        return jsonify({"success": False, "message": "File must be PDF"}), 400

    try:
        # Upload to Cloudinary as RAW (non-image)
        upload_result = cloudinary.uploader.upload(
            pdf,
            folder="bus",
            public_id="bus_routes",     # remove .pdf extension
            resource_type="raw",
            overwrite=True
        )

        pdf_url = upload_result.get("secure_url")

        # SAVE PDF URL TO DATABASE
        db.bus.update_one({}, {"$set": {"pdf_url": pdf_url}}, upsert=True)

        return jsonify({
            "success": True,
            "message": "Bus PDF uploaded successfully",
            "pdf_url": pdf_url
        }), 201

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ----------------- Direct Download (Used by App) -----------------
@bus_bp.route("/direct", methods=["GET"])
@cross_origin()
def bus_direct():
    rec = db.bus.find_one({}, {"_id": 0, "pdf_url": 1})

    if not rec or not rec.get("pdf_url"):
        return jsonify({"success": False, "message": "No Bus PDF found"}), 404

    # Force download mode
    url = rec["pdf_url"] + "?fl=attachment"

    return jsonify({"success": True, "url": url}), 200


# ----------------- Simple View PDF (Optional) -----------------
@bus_bp.route("/view", methods=["GET"])
@cross_origin()
def view_bus_pdf():
    try:
        rec = db.bus.find_one({}, {"_id": 0, "pdf_url": 1})
        if not rec:
            return jsonify({"success": False, "message": "No Bus PDF found"}), 404
        
        return jsonify({"success": True, "pdf_url": rec["pdf_url"]}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
