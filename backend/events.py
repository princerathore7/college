# events.py
from flask import Blueprint, request, jsonify
from db import db  # assuming pymongo client
from utils import generate_id
from flask_cors import cross_origin

events_bp = Blueprint("events_bp", __name__, url_prefix="/api/events")

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
@cross_origin()
def post_event():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json()

    required = ["title", "description", "image"]  # Cloudinary URL
    for field in required:
        if field not in data or not data[field]:
            return jsonify({"success": False, "message": f"{field} is required"}), 400

    data['eventId'] = generate_id("E")

    db.events.insert_one({
        "eventId": data["eventId"],
        "title": data["title"],
        "description": data["description"],
        "date": data.get("date", ""),
        "image": data["image"]  # Cloudinary URL
    })

    return jsonify({
        "success": True,
        "message": "Event posted",
        "eventId": data['eventId']
    }), 201

# DELETE an event
@events_bp.route('/<eventId>', methods=['DELETE'])
@cross_origin()
def delete_event(eventId):
    event = db.events.find_one({"eventId": eventId})
    if not event:
        return jsonify({"success": False, "message": "Event not found"}), 404

    # Optional: Delete from Cloudinary if stored
    # Only if you saved public_id or using a pattern
    # Example: public_id = f"events/event_{eventId}"

    result = db.events.delete_one({"eventId": eventId})
    return jsonify({"success": True, "message": "Event deleted"}), 200
