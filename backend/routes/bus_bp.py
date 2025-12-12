from flask import Blueprint, request, jsonify
from flask_cors import CORS, cross_origin
import cloudinary
import cloudinary.uploader

bus_bp = Blueprint("bus_bp", __name__, url_prefix="/api/bus")


# Cloudinary setup should be configured in your app's config
# cloudinary.config(
#     cloud_name='YOUR_CLOUD_NAME',
#     api_key='YOUR_API_KEY',
#     api_secret='YOUR_API_SECRET'
# )

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
        # Upload PDF to Cloudinary (resource_type="raw" for non-image files)
        upload_result = cloudinary.uploader.upload(
            pdf,
            folder="bus",
            public_id="bus_routes.pdf",
            resource_type="raw",
            overwrite=True
        )
        pdf_url = upload_result.get("secure_url")
        return jsonify({"success": True, "message": "Bus PDF uploaded successfully", "pdf_url": pdf_url}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ----------------- View PDF -----------------
@bus_bp.route("/view", methods=["GET"])
@cross_origin()
def view_bus_pdf():
    try:
        # In real use, you can store the PDF URL in a DB and fetch here
        # For simplicity, returning the Cloudinary public URL
        pdf_url = "https://res.cloudinary.com/deqqkiovg/raw/upload/bus/bus_routes.pdf"
        return jsonify({"success": True, "pdf_url": pdf_url}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
# /api/bus/direct
@bus_bp.route("/direct", methods=["GET"])
@cross_origin()
def bus_direct():
    rec = db.bus.find_one({}, {"_id":0,"pdf_url":1})
    if not rec or not rec.get("pdf_url"):
        return jsonify({"success":False,"message":"No Bus PDF found"}),404
    return jsonify({"success":True,"url":rec["pdf_url"]})
