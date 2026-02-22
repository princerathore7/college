from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from db import db
from datetime import datetime
from bson.objectid import ObjectId

receipt_bp = Blueprint("receipt_bp", __name__, url_prefix="/api/receipts")


# ---------------------------------------------------------
# SERIALIZE SINGLE RECEIPT
# ---------------------------------------------------------
def serialize(receipt):

    return {
        "_id": str(receipt.get("_id")),
        "enrollment": receipt.get("enrollment"),
        "payment_id": receipt.get("payment_id"),
        "order_id": receipt.get("order_id"),
        "amount_paid": receipt.get("amount_paid"),
        "reason": receipt.get("reason"),
        "class": receipt.get("class"),
        "payment_method": receipt.get("payment_method"),
        "status": receipt.get("status"),
        "createdAt": receipt.get("createdAt").isoformat() if receipt.get("createdAt") else None
    }


# ---------------------------------------------------------
# SERIALIZE LIST
# ---------------------------------------------------------
def serialize_list(receipts):
    return [serialize(r) for r in receipts]


# ---------------------------------------------------------
# GET LATEST FINE REASON FROM DB
# ---------------------------------------------------------
def get_reason_from_fine(enrollment):

    fine = db.fine.find_one(
        {"enrollment": enrollment},
        sort=[("createdAt", -1)]
    )

    if fine:
        return fine.get("reason", "College Fine")

    return "College Fine"


# ---------------------------------------------------------
# 🤖 CLEAR ALL FINES OF STUDENT
# ---------------------------------------------------------
def clear_student_fines(enrollment):

    try:

        if not enrollment:
            print("❌ Enrollment missing in clear_student_fines")
            return False


        result = db.fine.update_many(

            {
                "enrollment": enrollment,
                "status": {"$in": ["Unpaid", "Partial"]}
            },

            {
                "$set": {
                    "fine": 0,
                    "status": "Paid",
                    "updatedAt": datetime.utcnow()
                }
            }

        )


        print(f"✅ Cleared fines for {enrollment}, Modified: {result.modified_count}")

        return True


    except Exception as e:

        print("❌ clear_student_fines ERROR:", str(e))
        return False


# ---------------------------------------------------------
# CREATE RECEIPT  ⭐ MAIN FUNCTION
# ---------------------------------------------------------
def create_receipt(data):

    try:

        enrollment = data.get("enrollment")

        if not enrollment:
            print("❌ Missing enrollment in receipt")
            return None


        # Priority: webhook → db → default
        reason = data.get("reason")

        if not reason:
            reason = get_reason_from_fine(enrollment)


        receipt = {

            "enrollment": enrollment,

            "payment_id": data.get("payment_id"),

            "order_id": data.get("order_id"),

            "amount_paid": int(data.get("amount_paid", 0)),

            "reason": reason,

            "class": data.get("class"),

            "payment_method": data.get("method", "UPI"),

            "status": "Paid",

            "createdAt": datetime.utcnow()

        }


        # INSERT RECEIPT
        result = db.receipts.insert_one(receipt)

        print(f"✅ Receipt created for {enrollment}")


        # 🤖 AUTO CLEAR FINES
        clear_student_fines(enrollment)


        print(f"✅ Fine cleared for {enrollment}")


        return str(result.inserted_id)


    except Exception as e:

        print("❌ CREATE RECEIPT ERROR:", str(e))
        return None


# ---------------------------------------------------------
# GET RECEIPT BY PAYMENT ID
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
# GET STUDENT RECEIPTS
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
# GET ALL RECEIPTS
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
# GET SINGLE RECEIPT
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

        print("GET RECEIPT ERROR:", str(e))

        return jsonify({
            "success": False,
            "message": "Invalid receipt ID"
        }), 400