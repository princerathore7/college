from flask import Blueprint, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
from urllib.parse import unquote
import os
import cloudinary
import cloudinary.uploader

# --- Blueprint Setup ---
notices_bp = Blueprint("notices_bp", __name__, url_prefix="/api/notices")
CORS(notices_bp)

# --- MongoDB Setup ---
MONGO_URI = os.getenv("MONGO_COLLEGE_DB_URI")
if not MONGO_URI:
    raise Exception("MONGO_COLLEGE_DB_URI not set in environment variables")

client = MongoClient(MONGO_URI)
db = client["college_db"]
notices_collection = db["notices"]
students_collection = db["students"]

# --- Cloudinary Setup ---
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# =====================================
# 1️⃣  CREATE NOTICE (Admin only)
# =====================================
@notices_bp.route("", methods=["POST"], strict_slashes=False)
def add_notice():
    try:
        # 🔹 multipart + json dono support
        data = request.form if request.form else request.get_json()

        title = data.get("title")
        message = data.get("message")
        target = data.get("target", "all")          # student / mentor / all
        target_class = data.get("targetClass")      # 👈 NEW (optional)
        sender = data.get("sender", "Admin")

        if not title or not message:
            return jsonify({"success": False, "message": "Title and message are required"}), 400

        image_url = None

        # 🔹 Optional image upload
        if "image" in request.files:
            upload = cloudinary.uploader.upload(
                request.files["image"],
                folder="college_notices"
            )
            image_url = upload.get("secure_url")

        notice = {
            "title": title,
            "message": message,
            "target": target,
            "targetClass": target_class,    # 👈 NEW
            "imageUrl": image_url,          # 👈 NEW
            "sender": sender,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "readBy": []
        }

        notices_collection.insert_one(notice)
        return jsonify({"success": True, "message": "Notice added successfully"}), 201

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =====================================
# 2️⃣  FETCH NOTICES (Student / Mentor)
# =====================================
@notices_bp.route("", methods=["GET"], strict_slashes=False)
def get_all_notices():
    try:
        user_type = request.args.get("target", "all")
        enrollment = request.args.get("enrollment")

        student_class = None

        # 🔹 student ki class backend se nikalegi
        if enrollment:
            student = students_collection.find_one(
                {"enrollment": enrollment},
                {"_id": 0, "class": 1}
            )
            if student:
                student_class = student.get("class")

        query = {"$or": []}

        # 🔹 old target logic (unchanged)
        if user_type != "all":
            query["$or"].append({"target": user_type})

        query["$or"].append({"target": "all"})

        # 🔹 NEW class-wise filter
        if student_class:
            query["$or"].append({"targetClass": student_class})
            query["$or"].append({"targetClass": None})

        notices = list(notices_collection.find(query, {"_id": 0}))
        notices.sort(key=lambda x: x["timestamp"], reverse=True)

        # 🔹 unread flag
        if enrollment:
            for n in notices:
                n["is_read"] = enrollment in n.get("readBy", [])

        return jsonify({"success": True, "notices": notices}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =====================================
# 3️⃣  MARK NOTICE AS READ
# =====================================
@notices_bp.route("/mark-read", methods=["POST"], strict_slashes=False)
def mark_notice_as_read():
    try:
        data = request.get_json()
        title = data.get("title")
        enrollment = data.get("enrollment")

        if not title or not enrollment:
            return jsonify({"success": False, "message": "Title and enrollment required"}), 400

        result = notices_collection.update_one(
            {"title": title},
            {"$addToSet": {"readBy": enrollment}}
        )

        if result.matched_count == 0:
            return jsonify({"success": False, "message": "Notice not found"}), 404

        return jsonify({"success": True, "message": "Notice marked as read"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =====================================
# 4️⃣  DELETE NOTICE (Admin)
# =====================================
@notices_bp.route("/<path:title>", methods=["DELETE"], strict_slashes=False)
def delete_notice(title):
    try:
        title = unquote(title).strip()
        result = notices_collection.delete_one({"title": title})

        if result.deleted_count == 0:
            return jsonify({"success": False, "message": f"Notice '{title}' not found"}), 404

        return jsonify({"success": True, "message": f"Notice '{title}' deleted successfully"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =====================================
# 5️⃣  UNREAD NOTICE COUNT
# =====================================
@notices_bp.route("/unread-count", methods=["GET"], strict_slashes=False)
def unread_notice_count():
    try:
        user_type = request.args.get("target")
        enrollment = request.args.get("enrollment")

        if not user_type or not enrollment:
            return jsonify({"success": False, "message": "Missing user type or enrollment"}), 400

        student = students_collection.find_one(
            {"enrollment": enrollment},
            {"_id": 0, "class": 1}
        )
        student_class = student.get("class") if student else None

        query = {
            "$or": [
                {"target": user_type},
                {"target": "all"},
                {"targetClass": student_class}
            ],
            "readBy": {"$ne": enrollment}
        }

        count = notices_collection.count_documents(query)
        return jsonify({"success": True, "unread_count": count}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
