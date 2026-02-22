from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from db import db
from datetime import datetime
from bson.objectid import ObjectId

receipt_bp = Blueprint("receipt_bp", __name__, url_prefix="/api/receipts")


# ---------------------------------------------------------
# Helper — serialize Mongo Object
# ---------------------------------------------------------
def serialize(receipt):
    receipt["_id"] = str(receipt["_id"])
    return receipt


# ---------------------------------------------------------
# 1️⃣ CREATE RECEIPT (called internally after payment success)
# ---------------------------------------------------------
def create_receipt(data):
    """
    This function will be called from razorpay webhook
    """

    receipt = {
        "enrollment": data.get("enrollment"),
        "payment_id": data.get("payment_id"),
        "order_id": data.get("order_id"),
        "amount_paid": data.get("amount_paid"),
        "reason": data.get("reason", "College Fine"),
        "payment_method": data.get("method", "UPI"),
        "status": "Paid",
        "createdAt": datetime.now()
    }

    result = db.receipts.insert_one(receipt)

    return str(result.inserted_id)


# ---------------------------------------------------------
# 2️⃣ GET RECEIPT BY PAYMENT ID
# Used after successful payment redirect
# ---------------------------------------------------------
@receipt_bp.route("/payment/<payment_id>", methods=["GET"])
@cross_origin()
def get_receipt_by_payment(payment_id):

    receipt = db.receipts.find_one({
        "payment_id": payment_id
    })

    if not receipt:
        return jsonify({
            "success": False,
            "message": "Receipt not found"
        }), 404

    return jsonify({
        "success": True,
        "receipt": serialize(receipt)
    }), 200


# ---------------------------------------------------------
# 3️⃣ GET ALL RECEIPTS OF STUDENT
# Used for payment history page
# ---------------------------------------------------------
# @receipt_bp.route("/student/<enrollment>", methods=["GET"])
# @cross_origin()
# def get_student_receipts(enrollment):

#     receipts = list(db.receipts.find({
#         "enrollment": enrollment
#     }).sort("createdAt", -1))

#     receipts = [serialize(r) for r in receipts]

#     return jsonify({
#         "success": True,
#         "receipts": receipts
#     }), 200


# ---------------------------------------------------------
# 4️⃣ GET ALL RECEIPTS (ADMIN)
# ---------------------------------------------------------
@receipt_bp.route("/all", methods=["GET"])
@cross_origin()
def get_all_receipts():

    receipts = list(db.receipts.find().sort("createdAt", -1))

    receipts = [serialize(r) for r in receipts]

    return jsonify({
        "success": True,
        "receipts": receipts
    }), 200


# ---------------------------------------------------------
# 5️⃣ GET SINGLE RECEIPT BY ID
# ---------------------------------------------------------
@receipt_bp.route("/<receipt_id>", methods=["GET"])
@cross_origin()
def get_receipt(receipt_id):

    receipt = db.receipts.find_one({
        "_id": ObjectId(receipt_id)
    })

    if not receipt:
        return jsonify({
            "success": False,
            "message": "Receipt not found"
        }), 404

    return jsonify({
        "success": True,
        "receipt": serialize(receipt)
    }), 200
@receipt_bp.route("/finestudent/<enrollment>", methods=["GET"])
@cross_origin()
def get_student_receipts(enrollment):

    receipts = list(db.receipts.find({
        "enrollment": enrollment
    }).sort("createdAt", -1))

    return jsonify({
        "success": True,
        "receipts": serialize_list(receipts)
    }), 200