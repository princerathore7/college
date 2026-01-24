from flask import Blueprint, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import os

missing_bp = Blueprint("missing_bp", __name__, url_prefix="/api/missing")

# MongoDB connection
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["college_portal"]

missing_col = db["missing_items"]

# -----------------------------
# STUDENT: SUBMIT MISSING ITEM
# -----------------------------
@missing_bp.route("/submit", methods=["POST"])
def submit_missing():
    data = request.get_json()

    required = ["photo", "category", "description", "enrollment", "name", "class"]
    if not all(k in data for k in required):
        return jsonify({"success": False, "message": "Missing fields"}), 400

    item = {
        "photo": data["photo"],  # base64 or image URL
        "category": data["category"],
        "description": data["description"],
        "enrollment": data["enrollment"],
        "name": data["name"],
        "class": data["class"],
        "status": "pending",   # pending | approved | disapproved
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
