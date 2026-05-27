from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import jwt
import os
from db import db
from bson import ObjectId

# =====================================================
# BLUEPRINT
# =====================================================

sme_bp = Blueprint(
    "sme_bp",
    __name__,
    url_prefix="/api/sme"
)

# =====================================================
# CONFIG
# =====================================================

SECRET_KEY = os.getenv(
    "JWT_SECRET",
    "supersecretkey"
)

# =====================================================
# COLLECTIONS
# =====================================================

sme_users = db["sme_users"]
sme_devices = db["sme_devices"]
sme_stats = db["sme_stats"]

# =====================================================
# TOKEN VERIFY FUNCTION
# =====================================================

def verify_sme_token(token):

    try:

        decoded = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"]
        )

        device = sme_devices.find_one({
            "sme_id": decoded["sme_id"],
            "device_id": decoded["device_id"],
            "status": "approved"
        })

        if not device:
            return None

        return decoded

    except Exception:
        return None

# =====================================================
# 1. CREATE SME ACCOUNT
# =====================================================

@sme_bp.route("/create", methods=["POST"])
def create_sme():

    try:

        data = request.json

        email = data.get("email")
        password = data.get("password")
        name = data.get("name", "SME Member")
        daily_target = data.get("daily_target", 50)

        # ---------------- VALIDATION ----------------

        if not email or not password:

            return jsonify({
                "error": "Email and password required"
            }), 400

        # ---------------- CHECK EXISTING ----------------

        existing = sme_users.find_one({
            "email": email
        })

        if existing:

            return jsonify({
                "error": "SME already exists"
            }), 409

        # ---------------- HASH PASSWORD ----------------

        hashed_password = generate_password_hash(password)

        # ---------------- INSERT SME ----------------

        result = sme_users.insert_one({

            "name": name,

            "email": email,

            "password": hashed_password,

            "daily_target": daily_target,

            "created_at": datetime.utcnow()

        })

        sme_id = str(result.inserted_id)

        # ---------------- CREATE INITIAL STATS ----------------

        sme_stats.insert_one({

            "sme_id": sme_id,

            "email": email,

            "total_email_verifications": 0,

            "total_sms_verifications": 0,

            "total_done_verifications": 0,

            "today_verifications": 0,

            "daily_target": daily_target,

            "last_reset_date": datetime.utcnow().strftime("%Y-%m-%d"),

            "updated_at": datetime.utcnow()

        })

        return jsonify({

            "success": True,

            "message": "SME created successfully",

            "sme_id": sme_id

        }), 201

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =====================================================
# 2. SME LOGIN
# =====================================================

@sme_bp.route("/login", methods=["POST"])
def sme_login():

    try:

        data = request.json

        email = data.get("email")
        password = data.get("password")
        device_id = data.get("device_id")

        # ---------------- VALIDATION ----------------

        if not email or not password or not device_id:

            return jsonify({
                "error": "Missing fields"
            }), 400

        # ---------------- FIND SME ----------------

        sme = sme_users.find_one({
            "email": email
        })

        if not sme:

            return jsonify({
                "error": "Invalid credentials"
            }), 401

        # ---------------- CHECK PASSWORD ----------------

        if not check_password_hash(
            sme["password"],
            password
        ):

            return jsonify({
                "error": "Invalid credentials"
            }), 401

        # =====================================================
        # DEVICE CHECK
        # =====================================================

        device = sme_devices.find_one({

            "sme_id": str(sme["_id"]),

            "device_id": device_id

        })

        # ---------------- NEW DEVICE ----------------

        if not device:

            sme_devices.insert_one({

                "sme_id": str(sme["_id"]),

                "email": email,

                "device_id": device_id,

                "status": "pending",

                "created_at": datetime.utcnow()

            })

            return jsonify({

                "message": "Device not approved yet",

                "status": "pending_device"

            }), 403

        # ---------------- DEVICE REJECTED ----------------

        if device["status"] == "rejected":

            return jsonify({
                "message": "Device rejected by admin"
            }), 403

        # ---------------- DEVICE NOT APPROVED ----------------

        if device["status"] != "approved":

            return jsonify({
                "message": "Device not authorized"
            }), 403

        # =====================================================
        # RESET DAILY STATS
        # =====================================================

        stats = sme_stats.find_one({
            "sme_id": str(sme["_id"])
        })

        today = datetime.utcnow().strftime("%Y-%m-%d")

        if stats:

            if stats.get("last_reset_date") != today:

                sme_stats.update_one(

                    {
                        "sme_id": str(sme["_id"])
                    },

                    {
                        "$set": {

                            "today_verifications": 0,

                            "last_reset_date": today

                        }
                    }

                )

        # =====================================================
        # JWT TOKEN
        # =====================================================

        token = jwt.encode({

            "sme_id": str(sme["_id"]),

            "email": email,

            "name": sme.get("name", "SME"),

            "device_id": device_id,

            "exp": datetime.utcnow() + timedelta(hours=12)

        },
        SECRET_KEY,
        algorithm="HS256")

        return jsonify({

            "success": True,

            "message": "Login successful",

            "token": token,

            "sme": {

                "sme_id": str(sme["_id"]),

                "email": email,

                "name": sme.get("name", "SME"),

                "daily_target": sme.get("daily_target", 50)

            }

        }), 200

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

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

            {
                "sme_id": sme_id,
                "device_id": device_id
            },

            {
                "$set": {
                    "status": "approved"
                }
            }

        )

        if result.matched_count == 0:

            return jsonify({
                "error": "Device not found"
            }), 404

        return jsonify({

            "success": True,

            "message": "Device approved successfully"

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =====================================================
# 4. REJECT DEVICE
# =====================================================

@sme_bp.route("/reject-device", methods=["POST"])
def reject_device():

    try:

        data = request.json

        sme_id = data.get("sme_id")
        device_id = data.get("device_id")

        result = sme_devices.update_one(

            {
                "sme_id": sme_id,
                "device_id": device_id
            },

            {
                "$set": {
                    "status": "rejected"
                }
            }

        )

        if result.matched_count == 0:

            return jsonify({
                "error": "Device not found"
            }), 404

        return jsonify({

            "success": True,

            "message": "Device rejected successfully"

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =====================================================
# 5. GET ALL DEVICES
# =====================================================

@sme_bp.route("/all-devices", methods=["GET"])
def all_devices():

    try:

        devices = list(

            sme_devices.find(
                {},
                {"_id": 0}
            ).sort("created_at", -1)

        )

        return jsonify({

            "success": True,

            "devices": devices

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =====================================================
# 6. SME DASHBOARD
# =====================================================

@sme_bp.route("/dashboard", methods=["GET"])
def dashboard():

    try:

        token = request.headers.get("Authorization")

        if not token:

            return jsonify({
                "error": "Token missing"
            }), 401

        user = verify_sme_token(token)

        if not user:

            return jsonify({
                "error": "Unauthorized device"
            }), 403

        # ---------------- GET STATS ----------------

        stats = sme_stats.find_one({
            "sme_id": user["sme_id"]
        })

        sme = sme_users.find_one({
            "_id": ObjectId(user["sme_id"])
        })

        if not stats:

            stats = {}

        return jsonify({

            "success": True,

            "message": "Welcome SME Dashboard",

            "sme": {

                "sme_id": user["sme_id"],

                "name": sme.get("name", "SME"),

                "email": user["email"]

            },

            "stats": {

                "totalEmailVerifications":
                stats.get("total_email_verifications", 0),

                "totalSMSVerifications":
                stats.get("total_sms_verifications", 0),

                "totalDoneVerifications":
                stats.get("total_done_verifications", 0),

                "todayVerifications":
                stats.get("today_verifications", 0),

                "dailyTarget":
                stats.get("daily_target", 50)

            }

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =====================================================
# 7. UPDATE SME VERIFICATION COUNTS
# =====================================================

@sme_bp.route("/update-stats", methods=["POST"])
def update_stats():

    try:

        token = request.headers.get("Authorization")

        if not token:

            return jsonify({
                "error": "Token missing"
            }), 401

        user = verify_sme_token(token)

        if not user:

            return jsonify({
                "error": "Unauthorized"
            }), 403

        data = request.json

        verification_type = data.get("type")

        update_query = {

            "$inc": {

                "today_verifications": 1,

                "total_done_verifications": 1

            },

            "$set": {

                "updated_at": datetime.utcnow()

            }

        }

        # ---------------- EMAIL ----------------

        if verification_type == "email":

            update_query["$inc"]["total_email_verifications"] = 1

        # ---------------- SMS ----------------

        elif verification_type == "sms":

            update_query["$inc"]["total_sms_verifications"] = 1

        sme_stats.update_one(

            {
                "sme_id": user["sme_id"]
            },

            update_query

        )

        return jsonify({

            "success": True,

            "message": "Stats updated successfully"

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =====================================================
# 8. DELETE SME ACCOUNT
# =====================================================

@sme_bp.route("/delete/<sme_id>", methods=["DELETE"])
def delete_sme(sme_id):

    try:

        sme_users.delete_one({
            "_id": ObjectId(sme_id)
        })

        sme_devices.delete_many({
            "sme_id": sme_id
        })

        sme_stats.delete_many({
            "sme_id": sme_id
        })

        return jsonify({

            "success": True,

            "message": "SME account deleted successfully"

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500