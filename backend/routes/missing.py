from flask import Blueprint, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import os
from flask_cors import cross_origin
import cloudinary.uploader
missing_bp = Blueprint("missing_bp", __name__, url_prefix="/api/missing")

# MongoDB connection
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["college_portal"]

missing_col = db["missing_items"]

# -----------------------------
# STUDENT: SUBMIT MISSING ITEM
# -----------------------------
@missing_bp.route("/submit", methods=["POST", "OPTIONS"])
@cross_origin()
def submit_missing():

    # ✅ Handle preflight safely
    if request.method == "OPTIONS":
        return jsonify({"success": True}), 200

    photo = request.files.get("photo")
    if not photo:
        return jsonify({"success": False, "message": "Photo required"}), 400

    upload = cloudinary.uploader.upload(photo)

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

    missing_col.insert_one(item)

    return jsonify({
        "success": True,
        "message": "Missing item submitted, waiting for mentor approval"
    })



# --------------------------------
# STUDENT: MY SUBMITTED COMPLAINTS
# --------------------------------
@missing_bp.route("/my/<enrollment>", methods=["GET"])
def my_complaints(enrollment):
    items = list(missing_col.find(
        {"enrollment": enrollment},
        {"photo": 1, "category": 1, "description": 1, "status": 1, "created_at": 1}
    ))

    for i in items:
        i["_id"] = str(i["_id"])

    return jsonify({"success": True, "data": items})


# -----------------------------
# PUBLIC: APPROVED MISSING LIST
# -----------------------------
@missing_bp.route("/public", methods=["GET"])
def public_missing():
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

    return jsonify({"success": True, "data": items})


# -----------------------------
# MENTOR: VIEW PENDING ITEMS
# -----------------------------
@missing_bp.route("/pending", methods=["GET"])
def pending_items():
    items = list(missing_col.find({"status": "pending"}))

    for i in items:
        i["_id"] = str(i["_id"])

    return jsonify({"success": True, "data": items})


# -----------------------------
# MENTOR: APPROVE ITEM
# -----------------------------
@missing_bp.route("/approve/<id>", methods=["PUT"])
def approve_item(id):
    missing_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "approved"}}
    )
    return jsonify({"success": True, "message": "Item approved"})


# -----------------------------
# MENTOR: DISAPPROVE ITEM
# -----------------------------
@missing_bp.route("/disapprove/<id>", methods=["PUT"])
def disapprove_item(id):
    missing_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "disapproved"}}
    )
    return jsonify({"success": True, "message": "Item disapproved"})


# -----------------------------
# MENTOR: DELETE ITEM (PERMANENT)
# -----------------------------
@missing_bp.route("/delete/<id>", methods=["DELETE"])
def delete_item(id):
    missing_col.delete_one({"_id": ObjectId(id)})
    return jsonify({"success": True, "message": "Item deleted permanently"})
