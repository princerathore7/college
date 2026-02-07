from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import cloudinary
import cloudinary.uploader
from db import db
import pdfplumber
import re
# 🔔 Notification helper
from routes.notifications import notify_bus

bus_bp = Blueprint("bus_bp", __name__, url_prefix="/api/bus")
def find_buses_for_stop(text, stop_name):
    lines = text.split("\n")
    buses = set()

    for line in lines:
        if stop_name.lower() in line.lower():
            # Look upward for Bus No lines
            for l in lines:
                match = re.search(r"Bus No.-\s*(G\d+)", l)
                if match:
                    buses.add(match.group(1))

    return list(buses)
def extract_pdf_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text
db.bus_routes.insert_one({
    "destination": "Aopolis institutes",
    "stop": "Maksi",
    "buses": ["G64", "G58", "G52"]
})
@bus_bp.route("/search", methods=["GET"])
def search_bus():
    stop = request.args.get("stop")

    rec = db.bus_routes.find_one(
        {"stop": {"$regex": f"^{stop}$", "$options": "i"}},
        {"_id": 0}
    )

    if not rec:
        return jsonify({"success": False, "message": "No bus found"}), 404

    return jsonify({
        "success": True,
        "stop": stop,
        "destination": "Aopolis institutes",
        "buses": rec["buses"]
    })


# ----------------- UPLOAD BUS PDF -----------------
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

    if not pdf.filename.lower().endswith(".pdf"):
        return jsonify({"success": False, "message": "File must be PDF"}), 400

    try:
        upload_result = cloudinary.uploader.upload(
            pdf,
            folder="bus",
            public_id="bus_routes",
            resource_type="raw",
            overwrite=True
        )

        pdf_url = upload_result.get("secure_url")

        # Save inside database
        db.bus.update_one({}, {"$set": {"pdf_url": pdf_url}}, upsert=True)

        # 🔔 GLOBAL NOTIFICATION (ALL USERS)
        notify_bus(
            title="🚌 Bus Route Updated",
            body="New bus route PDF has been uploaded. Check routes now.",
            url="/bus-route.html"
        )

        return jsonify({
            "success": True,
            "message": "Bus PDF uploaded & notification sent",
            "pdf_url": pdf_url
        }), 201

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ----------------- VIEW PDF (JSON URL) -----------------
@bus_bp.route("/view", methods=["GET"])
@cross_origin()
def view_bus_pdf():
    rec = db.bus.find_one({}, {"_id": 0, "pdf_url": 1})
    if not rec or not rec.get("pdf_url"):
        return jsonify({"success": False, "message": "No Bus PDF found"}), 404

    return jsonify({"success": True, "pdf_url": rec["pdf_url"]}), 200


# ----------------- DIRECT DOWNLOAD (REAL FIXED) -----------------
@bus_bp.route("/direct", methods=["GET"])
@cross_origin()
def bus_direct():

    rec = db.bus.find_one({}, {"_id": 0, "pdf_url": 1})
    if not rec or not rec.get("pdf_url"):
        return jsonify({"success": False, "message": "No Bus PDF found"}), 404

    base_url = rec["pdf_url"]

    # 🔥 RAW Cloudinary PDF requires this flag for download:
    download_url = base_url + "?fl_attachment=true"

    return jsonify({"success": True, "url": download_url}), 200
