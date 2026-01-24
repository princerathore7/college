from flask import Blueprint, request, jsonify
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# =========================
# DB COLLECTIONS (models.py se import)
# =========================
from models.models import bus_pilots, bus_locations

# =========================
# BLUEPRINT (RENAMED)
# =========================
bus_track_bp = Blueprint("bus_track_bp", __name__)

# ======================================================
# ADMIN: CREATE BUS PILOT ID
# ======================================================
@bus_track_bp.route("/api/admin/bus/create", methods=["POST"])
def create_bus():
    data = request.json or {}
    busId = data.get("busId")
    password = data.get("password")

    if not busId or not password:
        return jsonify({"error": "busId and password required"}), 400

    if bus_pilots.find_one({"busId": busId}):
        return jsonify({"error": "Bus already exists"}), 400

    bus_pilots.insert_one({
        "busId": busId,
        "password": generate_password_hash(password),
        "active": True,
        "createdAt": datetime.utcnow()
    })

    return jsonify({"status": "bus_created"})


# ======================================================
# ADMIN: DELETE BUS PILOT ID
# ======================================================
@bus_track_bp.route("/api/admin/bus/delete/<busId>", methods=["DELETE"])
def delete_bus(busId):
    bus_pilots.delete_one({"busId": busId})
    bus_locations.delete_one({"busId": busId})
    return jsonify({"status": "bus_deleted"})


# ======================================================
# BUS DRIVER LOGIN
# ======================================================
@bus_track_bp.route("/api/bus/login", methods=["POST"])
def bus_login():
    data = request.json or {}
    busId = data.get("busId")
    password = data.get("password")

    bus = bus_pilots.find_one({"busId": busId, "active": True})
    if not bus:
        return jsonify({"error": "Invalid bus ID"}), 401

    if not check_password_hash(bus["password"], password):
        return jsonify({"error": "Wrong password"}), 401

    return jsonify({
        "status": "login_success",
        "busId": busId
    })


# ======================================================
# BUS DRIVER: LOCATION UPDATE (ON)
# ======================================================
@bus_track_bp.route("/api/bus/update-location", methods=["POST"])
def update_location():
    data = request.json or {}
    busId = data.get("busId")

    bus = bus_pilots.find_one({"busId": busId, "active": True})
    if not bus:
        return jsonify({"error": "Bus not active"}), 403

    bus_locations.update_one(
        {"busId": busId},
        {"$set": {
            "lat": data.get("lat"),
            "lng": data.get("lng"),
            "lastUpdated": datetime.utcnow()
        }},
        upsert=True
    )

    return jsonify({"status": "location_updated"})


# ======================================================
# BUS DRIVER: LOCATION OFF
# ======================================================
@bus_track_bp.route("/api/bus/stop-location/<busId>", methods=["POST"])
def stop_location(busId):
    bus_locations.delete_one({"busId": busId})
    return jsonify({"status": "tracking_stopped"})


# ======================================================
# STUDENT: GET ALL ACTIVE BUSES
# ======================================================
@bus_track_bp.route("/api/bus/list", methods=["GET"])
def list_buses():
    buses = list(bus_pilots.find(
        {"active": True},
        {"_id": 0, "busId": 1}
    ))
    return jsonify(buses)


# ======================================================
# STUDENT: GET BUS LIVE LOCATION
# ======================================================
@bus_track_bp.route("/api/bus/location/<busId>", methods=["GET"])
def get_bus_location(busId):
    loc = bus_locations.find_one({"busId": busId}, {"_id": 0})
    if not loc:
        return jsonify({"error": "Location not available"}), 404

    return jsonify(loc)
