from flask import Blueprint, request, jsonify
from flask_cors import CORS, cross_origin
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import os
import cloudinary
import cloudinary.uploader

# --------------------------------
# Blueprint setup
# --------------------------------
missing_bp = Blueprint("missing_bp", __name__, url_prefix="/api/missing")
CORS(missing_bp)

# --------------------------------
# MongoDB (SAFE: function-based)
# --------------------------------
MONGO_URI = os.getenv("MONGO_COLLEGE_DB_URI")
if not MONGO_URI:
    raise Exception("MONGO_COLLEGE_DB_URI not set")

def get_collection():
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000
    )
    db = client["college_db"]
    return db["missing_items"]

# --------------------------------
# Cloudinary setup
# --------------------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# =================================
# 1️⃣ STUDENT: SUBMIT MISSING ITEM
# =================================
@missing_bp.route("/submit", methods=["POST", "OPTIONS"])
@cross_origin()
def submit_missing():

    if request.method == "OPTIONS":
        return jsonify({"success": True}), 200

    try:
        missing_col = get_collection()

        photo = request.files.get("photo")
        if not photo:
            return jsonify({"success": False, "message": "Photo required"}), 400

        upload = cloudinary.uploader.upload(
            photo,
            folder="college_missing_items"
        )

        item = {
            "photo": upload["secure_url"],
            "category": request.form.get("category"),
            "description": request.form.get("description"),
            "enrollment": request.form.get("enrollment"),
            "name": request.form.get("name"),
            "class": request.form.get("class"),
            "status": "pending",
            "created_at": datetime.utcnow()
        }

        if not all([item["category"], item["description"], item["enrollment"], item["name"], item["class"]]):
            return jsonify({"success": False, "message": "All fields required"}), 400

        missing_col.insert_one(item)

        return jsonify({
            "success": True,
            "message": "Missing item submitted, waiting for mentor approval"
        }), 201

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =================================
# 2️⃣ STUDENT: MY SUBMITTED ITEMS
# =================================
@missing_bp.route("/my/<enrollment>", methods=["GET"])
def my_complaints(enrollment):
    try:
        missing_col = get_collection()

        items = list(missing_col.find(
            {"enrollment": enrollment},
            {"photo": 1, "category": 1, "description": 1, "status": 1, "created_at": 1}
        ))

        for i in items:
            i["_id"] = str(i["_id"])

        return jsonify({"success": True, "data": items}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =================================
# 3️⃣ PUBLIC: APPROVED MISSING LIST
# =================================
@missing_bp.route("/public", methods=["GET"])
def public_missing():
    try:
        missing_col = get_collection()

        category = request.args.get("category")
        search = request.args.get("search")

        query = {"status": "approved"}

        if category:
            query["category"] = category

        if search:
            query["description"] = {"$regex": search, "$options": "i"}

        items = list(missing_col.find(query))

        for i in items:
            i["_id"] = str(i["_id"])

        return jsonify({"success": True, "data": items}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =================================
# 4️⃣ MENTOR: VIEW PENDING ITEMS
# =================================
@missing_bp.route("/pending", methods=["GET"])
def pending_items():
    try:
        missing_col = get_collection()

        items = list(missing_col.find({"status": "pending"}))

        for i in items:
            i["_id"] = str(i["_id"])

        return jsonify({"success": True, "data": items}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =================================
# 5️⃣ MENTOR: APPROVE ITEM
# =================================
@missing_bp.route("/approve/<id>", methods=["PUT"])
def approve_item(id):
    try:
        missing_col = get_collection()

        missing_col.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"status": "approved"}}
        )

        return jsonify({"success": True, "message": "Item approved"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =================================
# 6️⃣ MENTOR: DISAPPROVE ITEM
# =================================
@missing_bp.route("/disapprove/<id>", methods=["PUT"])
def disapprove_item(id):
    try:
        missing_col = get_collection()

        missing_col.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"status": "disapproved"}}
        )

        return jsonify({"success": True, "message": "Item disapproved"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =================================
# 7️⃣ MENTOR: DELETE ITEM
# =================================
@missing_bp.route("/delete/<id>", methods=["DELETE"])
def delete_item(id):
    try:
        missing_col = get_collection()

        missing_col.delete_one({"_id": ObjectId(id)})

        return jsonify({"success": True, "message": "Item deleted permanently"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
# =================================
# 8️⃣ ADMIN: VIEW ALL ITEMS
# =================================
@missing_bp.route("/all", methods=["GET"])
def all_items():
    try:
        missing_col = get_collection()

        items = list(missing_col.find().sort("created_at", -1))

        for i in items:
            i["_id"] = str(i["_id"])

        return jsonify({"success": True, "data": items}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
