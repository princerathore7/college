from flask import Blueprint, request, jsonify
from db import db
from utils import generate_id
from flask_cors import cross_origin, CORS

# 🔔 Notification helper
from routes.notifications import send_global_notification

events_bp = Blueprint("events_bp", __name__, url_prefix="/api/events")
CORS(events_bp, resources={r"/*": {"origins": "*"}})


# ---------------------------------------------------------
# ✅ GET all events
# ---------------------------------------------------------
@events_bp.route('', methods=['GET'])
@cross_origin()
def get_all_events():
    events = list(db.events.find({}, {"_id": 0}))
    return jsonify({"success": True, "events": events}), 200


# ---------------------------------------------------------
# ✅ GET single event by ID
# ---------------------------------------------------------
@events_bp.route('/<eventId>', methods=['GET'])
@cross_origin()
def get_event(eventId):
    event = db.events.find_one({"eventId": eventId}, {"_id": 0})
    if not event:
        return jsonify({"success": False, "message": "Event not found"}), 404
    return jsonify({"success": True, "event": event}), 200


# ---------------------------------------------------------
# ✅ POST new event (GLOBAL NOTIFICATION)
# ---------------------------------------------------------
@events_bp.route('', methods=['POST', 'OPTIONS'])
@cross_origin(headers=["Content-Type"])
def post_event():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "Invalid or missing JSON body"}), 400

    # Required fields
    required = ["title", "description", "image"]
    for field in required:
        if field not in data or not data[field].strip():
            return jsonify({"success": False, "message": f"{field} is required"}), 400

    # Generate unique event ID
    event_id = generate_id("E")

    event_doc = {
        "eventId": event_id,
        "title": data["title"].strip(),
        "description": data["description"].strip(),
        "date": data.get("date", "").strip(),
        "image": data["image"].strip(),
        "createdAt": datetime.now()
    }

    try:
        db.events.insert_one(event_doc)
    except Exception as e:
        print("DB Insert Error:", e)
        return jsonify({"success": False, "message": "Database error occurred"}), 500

    # 🔔 GLOBAL NOTIFICATION (ALL USERS)
    send_global_notification(
        title="📢 New Event Announced",
        body=data["title"].strip(),
        url="/events.html"
    )

    return jsonify({
        "success": True,
        "message": "Event posted and notification sent to all users",
        "eventId": event_id
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
