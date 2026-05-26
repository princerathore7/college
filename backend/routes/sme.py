from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import jwt
import os
from db import db
from bson import ObjectId

# ---------------- BLUEPRINT ----------------
sme_bp = Blueprint("sme_bp", __name__, url_prefix="/api/sme")

# ---------------- CONFIG ----------------
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")

# ---------------- COLLECTIONS (SAFE) ----------------
sme_users = db["sme_users"]
sme_devices = db["sme_devices"]

# =====================================================
# 1. CREATE SME ACCOUNT
# =====================================================

@sme_bp.route("/create", methods=["POST"])
def create_sme():
    try:
        data = request.json

        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        existing = sme_users.find_one({"email": email})
        if existing:
            return jsonify({"error": "SME already exists"}), 409

        hashed_password = generate_password_hash(password)

        result = sme_users.insert_one({
            "email": email,
            "password": hashed_password,
            "created_at": datetime.utcnow()
        })

        return jsonify({
            "message": "SME created successfully",
            "sme_id": str(result.inserted_id)
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================
# 2. SME LOGIN + DEVICE REGISTRATION
# =====================================================

@sme_bp.route("/login", methods=["POST"])
def sme_login():
    try:
        data = request.json

        email = data.get("email")
        password = data.get("password")
        device_id = data.get("device_id")

        if not email or not password or not device_id:
            return jsonify({"error": "Missing fields"}), 400

        sme = sme_users.find_one({"email": email})

        if not sme:
            return jsonify({"error": "Invalid credentials"}), 401

        if not check_password_hash(sme["password"], password):
            return jsonify({"error": "Invalid credentials"}), 401

        # ---------------- DEVICE CHECK ----------------
        device = sme_devices.find_one({
            "sme_id": str(sme["_id"]),
            "device_id": device_id
        })

        if not device:
            sme_devices.insert_one({
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
            return jsonify({"message": "Device not authorized"}), 403

        # ---------------- JWT ----------------
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

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================
# 3. APPROVE DEVICE
# =====================================================

@sme_bp.route("/approve-device", methods=["POST"])
def approve_device():
    try:
        data = request.json

        sme_id = data.get("sme_id")
        device_id = data.get("device_id")

        result = sme_devices.update_one(
            {"sme_id": sme_id, "device_id": device_id},
            {"$set": {"status": "approved"}}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Device not found"}), 404

        return jsonify({"message": "Device approved successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================
# 4. VERIFY TOKEN
# =====================================================

def verify_sme_token(token):
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

        device = sme_devices.find_one({
            "sme_id": decoded["sme_id"],
            "device_id": decoded["device_id"],
            "status": "approved"
        })

        if not device:
            return None

        return decoded

    except:
        return None


# =====================================================
# 5. SME DASHBOARD (PROTECTED)
# =====================================================

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
# 6. DELETE SME ACCOUNT
# =====================================================

@sme_bp.route("/delete/<sme_id>", methods=["DELETE"])
def delete_sme(sme_id):
    try:
        sme_users.delete_one({"_id": ObjectId(sme_id)})
        sme_devices.delete_many({"sme_id": sme_id})

        return jsonify({
            "message": "SME account deleted successfully"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500