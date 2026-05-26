from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import jwt
import os
from db import db
# ---------------- BLUEPRINT ----------------
sme_bp = Blueprint("sme_bp", __name__, url_prefix="/api/sme")

# ---------------- CONFIG ----------------
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")

# ---------------- DB (Mongo assumed) ----------------
# db = MongoClient()["your_db_name"]

# =====================================================
# 1. CREATE SME ACCOUNT (email + password only)
# =====================================================

@sme_bp.route("/create", methods=["POST"])
def create_sme():
    data = request.json

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    existing = db.sme_users.find_one({"email": email})
    if existing:
        return jsonify({"error": "SME already exists"}), 409

    hashed_password = generate_password_hash(password)

    sme_id = db.sme_users.insert_one({
        "email": email,
        "password": hashed_password,
        "created_at": datetime.utcnow()
    }).inserted_id

    return jsonify({
        "message": "SME created successfully",
        "sme_id": str(sme_id)
    })


# =====================================================
# 2. SME LOGIN + DEVICE REGISTRATION
# =====================================================

@sme_bp.route("/login", methods=["POST"])
def sme_login():
    data = request.json

    email = data.get("email")
    password = data.get("password")
    device_id = data.get("device_id")

    if not email or not password or not device_id:
        return jsonify({"error": "Missing fields"}), 400

    sme = db.sme_users.find_one({"email": email})

    if not sme:
        return jsonify({"error": "Invalid credentials"}), 401

    if not check_password_hash(sme["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    # ---------------- DEVICE CHECK ----------------
    device = db.sme_devices.find_one({
        "sme_id": str(sme["_id"]),
        "device_id": device_id
    })

    if not device:
        db.sme_devices.insert_one({
            "sme_id": str(sme["_id"]),
            "device_id": device_id,
            "status": "pending",
            "created_at": datetime.utcnow()
        })

        return jsonify({
            "message": "Device not approved yet",
            "status": "pending_device"
        }), 403

    if device["status"] != "approved":
        return jsonify({
            "message": "Device not authorized"
        }), 403

    # ---------------- JWT TOKEN ----------------
    token = jwt.encode({
        "sme_id": str(sme["_id"]),
        "email": email,
        "device_id": device_id,
        "exp": datetime.utcnow() + timedelta(hours=12)
    }, SECRET_KEY, algorithm="HS256")

    return jsonify({
        "message": "Login successful",
        "token": token
    })


# =====================================================
# 3. APPROVE DEVICE (ADMIN ONLY ROUTE)
# =====================================================

@sme_bp.route("/approve-device", methods=["POST"])
def approve_device():
    data = request.json

    sme_id = data.get("sme_id")
    device_id = data.get("device_id")

    result = db.sme_devices.update_one(
        {"sme_id": sme_id, "device_id": device_id},
        {"$set": {"status": "approved"}}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Device not found"}), 404

    return jsonify({"message": "Device approved successfully"})


# =====================================================
# 4. SME AUTH CHECK (FOR PROTECTED ROUTES)
# =====================================================

def verify_sme_token(token):
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

        sme_id = decoded["sme_id"]
        device_id = decoded["device_id"]

        device = db.sme_devices.find_one({
            "sme_id": sme_id,
            "device_id": device_id,
            "status": "approved"
        })

        if not device:
            return None

        return decoded

    except:
        return None


# Example protected route
@sme_bp.route("/dashboard", methods=["GET"])
def dashboard():
    token = request.headers.get("Authorization")

    if not token:
        return jsonify({"error": "Token missing"}), 401

    user = verify_sme_token(token)

    if not user:
        return jsonify({"error": "Unauthorized device"}), 403

    return jsonify({
        "message": "Welcome SME Dashboard",
        "sme_id": user["sme_id"]
    })


# =====================================================
# 5. DELETE SME ACCOUNT
# =====================================================

@sme_bp.route("/delete/<sme_id>", methods=["DELETE"])
def delete_sme(sme_id):

    db.sme_users.delete_one({"_id": sme_id})
    db.sme_devices.delete_many({"sme_id": sme_id})

    return jsonify({
        "message": "SME account deleted successfully"
    })