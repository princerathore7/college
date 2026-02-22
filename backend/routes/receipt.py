from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from db import db
from datetime import datetime
from bson.objectid import ObjectId
from utils.serializer import serialize_list

receipt_bp = Blueprint("receipt_bp", __name__, url_prefix="/api/receipts")


# ---------------------------------------------------------
# Helper — serialize single receipt
# ---------------------------------------------------------
def serialize(receipt):

    return {
        "_id": str(receipt.get("_id")),
        "enrollment": receipt.get("enrollment"),
        "payment_id": receipt.get("payment_id"),
        "order_id": receipt.get("order_id"),
        "amount_paid": receipt.get("amount_paid"),
        "reason": receipt.get("reason"),
        "payment_method": receipt.get("payment_method"),
        "status": receipt.get("status"),
        "createdAt": receipt.get("createdAt").isoformat() if receipt.get("createdAt") else None
    }


# ---------------------------------------------------------
# 1️⃣ CREATE RECEIPT
# Called from razorpay_bp after payment success
# ---------------------------------------------------------
def create_receipt(data):

    try:

        receipt = {
            "enrollment": data.get("enrollment"),
            "payment_id": data.get("payment_id"),
            "order_id": data.get("order_id"),
            "amount_paid": data.get("amount_paid"),
            "reason": data.get("reason", "College Fine"),
            "payment_method": data.get("method", "UPI"),
            "status": "Paid",
            "createdAt": datetime.utcnow()
        }

        result = db.receipts.insert_one(receipt)

        return str(result.inserted_id)

    except Exception as e:
        print("CREATE RECEIPT ERROR:", str(e))
        return None


# ---------------------------------------------------------
# 2️⃣ GET RECEIPT BY PAYMENT ID
# Used after successful payment redirect
# ---------------------------------------------------------
@receipt_bp.route("/payment/<payment_id>", methods=["GET"])
@cross_origin()
def get_receipt_by_payment(payment_id):

    try:

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

    except Exception as e:

        print("GET RECEIPT ERROR:", str(e))

        return jsonify({
            "success": False,
            "message": "Server error"
        }), 500


# ---------------------------------------------------------
# 3️⃣ GET ALL RECEIPTS OF STUDENT
# Used for payment history page
# ---------------------------------------------------------
@receipt_bp.route("/finestudent/<enrollment>", methods=["GET"])
@cross_origin()
def get_student_receipts(enrollment):

    try:

        receipts = list(
            db.receipts
            .find({"enrollment": enrollment})
            .sort("createdAt", -1)
        )

        return jsonify({
            "success": True,
            "receipts": serialize_list(receipts)
        }), 200

    except Exception as e:

        print("GET STUDENT RECEIPTS ERROR:", str(e))

        return jsonify({
            "success": False,
            "message": "Server error"
        }), 500


# ---------------------------------------------------------
# 4️⃣ GET ALL RECEIPTS (ADMIN)
# ---------------------------------------------------------
@receipt_bp.route("/all", methods=["GET"])
@cross_origin()
def get_all_receipts():

    try:

        receipts = list(
            db.receipts
            .find()
            .sort("createdAt", -1)
        )

        return jsonify({
            "success": True,
            "receipts": serialize_list(receipts)
        }), 200

    except Exception as e:

        print("GET ALL RECEIPTS ERROR:", str(e))

        return jsonify({
            "success": False,
            "message": "Server error"
        }), 500


# ---------------------------------------------------------
# 5️⃣ GET SINGLE RECEIPT BY ID
# ---------------------------------------------------------
@receipt_bp.route("/<receipt_id>", methods=["GET"])
@cross_origin()
def get_receipt(receipt_id):

    try:

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

    except Exception as e:

        print("GET RECEIPT BY ID ERROR:", str(e))

        return jsonify({
            "success": False,
            "message": "Invalid receipt ID"
        }), 400