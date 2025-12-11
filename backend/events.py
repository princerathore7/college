# events.py
from flask import Blueprint, request, jsonify
from db import db  # assuming pymongo client
from utils import generate_id
from flask_cors import cross_origin, CORS

events_bp = Blueprint("events_bp", __name__, url_prefix="/api/events")
CORS(events_bp, resources={r"/*": {"origins": "*"}})

# ✅ GET all events
@events_bp.route('', methods=['GET'])
@cross_origin()
def get_all_events():
    events = list(db.events.find({}, {"_id": 0}))
    return jsonify({"success": True, "events": events}), 200

# ✅ GET single event by ID
@events_bp.route('/<eventId>', methods=['GET'])
@cross_origin()
def get_event(eventId):
    event = db.events.find_one({"eventId": eventId}, {"_id": 0})
    if not event:
        return jsonify({"success": False, "message": "Event not found"}), 404
    return jsonify({"success": True, "event": event}), 200

# ✅ POST new event (JSON body with image URL)
@events_bp.route('', methods=['POST', 'OPTIONS'])
@cross_origin(headers=["Content-Type"])
def post_event():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    # Use silent=True to avoid crash if body is not JSON
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "Invalid or missing JSON body"}), 400

    # Validate required fields
    required = ["title", "description", "image"]
    for field in required:
        if field not in data or not data[field].strip():
            return jsonify({"success": False, "message": f"{field} is required"}), 400

    # Generate unique event ID
    data['eventId'] = generate_id("E")

    # Insert into MongoDB safely
    try:
        db.events.insert_one({
            "eventId": data["eventId"],
            "title": data["title"].strip(),
            "description": data["description"].strip(),
            "date": data.get("date", "").strip(),
            "image": data["image"].strip()
        })
    except Exception as e:
        print("DB Insert Error:", e)
        return jsonify({"success": False, "message": "Database error occurred"}), 500

    return jsonify({
        "success": True,
        "message": "Event posted",
        "eventId": data['eventId']
    }), 201

# ✅ DELETE an event
@events_bp.route('/<eventId>', methods=['DELETE'])
@cross_origin()
def delete_event(eventId):
    event = db.events.find_one({"eventId": eventId})
    if not event:
        return jsonify({"success": False, "message": "Event not found"}), 404

    # Optional: Delete from Cloudinary if needed

    try:
        db.events.delete_one({"eventId": eventId})
    except Exception as e:
        print("DB Delete Error:", e)
        return jsonify({"success": False, "message": "Database error occurred"}), 500

    return jsonify({"success": True, "message": "Event deleted"}), 200
