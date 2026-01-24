from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from db import db
from datetime import datetime
from bson.objectid import ObjectId
import razorpay
import os
import hmac
import hashlib
import json

# 🔔 Notification helper
from routes.notifications import notify_fine

fine_bp = Blueprint("fine_bp", __name__, url_prefix="/api/fines")

# ---------------------------------------------------------
# 🛠 Helper — Convert MongoDB Record to JSON Safe Dict
# ---------------------------------------------------------
def serialize(fine):
    fine["_id"] = str(fine["_id"])
    return fine


# ---------------------------------------------------------
# 1️⃣ ADMIN — BULK ADD FINES
# ---------------------------------------------------------
@fine_bp.route("/bulk-add", methods=["POST"])
def add_bulk_fines():
    try:
        data = request.get_json(force=True)
        fines = data.get("fines", [])

        if not fines:
            return jsonify({"success": False, "message": "No fines provided"}), 400

        for f in fines:
            record = {
                "enrollment": f.get("enrollment"),
                "class": f.get("class"),
                "fine": int(f.get("fine", 0)),
                "reason": f.get("reason", ""),
                "status": "Unpaid",
                "createdAt": datetime.now(),
                "updatedAt": datetime.now()
            }

            db.fine.insert_one(record)

        return jsonify({
            "success": True,
            "message": "Fines added successfully"
        }), 200

    except Exception as e:
        print("❌ bulk-add error:", e)
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------
# 2️⃣ SEARCH FINES OF ONE STUDENT (ADMIN / TEACHER)
# ---------------------------------------------------------
@fine_bp.route("/<enrollment>", methods=["GET"])
@cross_origin()
def get_student_fines(enrollment):
    records = list(db.fine.find({"enrollment": enrollment}))
    records = [serialize(r) for r in records]

    return jsonify(records), 200


# ---------------------------------------------------------
# 3️⃣ TEACHER — UPDATE SINGLE FINE USING ID
# ---------------------------------------------------------
@fine_bp.route("/update/<fine_id>", methods=["PUT"])
def update_fine(fine_id):
    try:
        data = request.get_json(force=True)

        fine_amount = int(data.get("fine", 0))
        reason = data.get("reason", "Fine updated")

        fine_record = db.fine.find_one({"_id": ObjectId(fine_id)})
        if not fine_record:
            return jsonify({"success": False, "message": "Fine not found"}), 404

        enrollment = fine_record["enrollment"]

        db.fine.update_one(
            {"_id": ObjectId(fine_id)},
            {"$set": {
                "fine": fine_amount,
                "reason": reason,
                "updatedAt": datetime.now()
            }}
        )

        return jsonify({
            "success": True,
            "message": "Fine updated successfully"
        }), 200

    except Exception as e:
        print("❌ Update fine error:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

# ---------------------------------------------------------
# 4️⃣ DELETE FINE BY ID
# ---------------------------------------------------------
@fine_bp.route("/delete/<fine_id>", methods=["DELETE"])
@cross_origin()
def delete_fine(fine_id):
    db.fine.delete_one({"_id": ObjectId(fine_id)})
    return jsonify({"success": True, "message": "Fine deleted"}), 200


# ---------------------------------------------------------
# 5️⃣ STUDENT DASHBOARD — FETCH OWN FINES
# ---------------------------------------------------------
@fine_bp.route("/student-dashboard/<enrollment>", methods=["GET"])
@cross_origin()
def student_dashboard(enrollment):
    rec = list(db.fine.find({"enrollment": enrollment}))
    rec = [serialize(r) for r in rec]

    return jsonify({"success": True, "fines": rec}), 200


# ---------------------------------------------------------
# 6️⃣ STUDENT PUBLIC PAGE — CHECK FINES BY ENTERING ENR
# ---------------------------------------------------------
@fine_bp.route("/public-check/<enrollment>", methods=["GET"])
@cross_origin()
def public_check(enrollment):
    rec = list(db.fine.find({"enrollment": enrollment}))
    rec = [serialize(r) for r in rec]

    return jsonify({"success": True, "fines": rec}), 200


# ---------------------------------------------------------
# 7️⃣ ADMIN / TEACHER — ALL FINES LIST
# ---------------------------------------------------------
@fine_bp.route("/all", methods=["GET"])
@cross_origin()
def all_fines():
    all_rec = list(db.fine.find())
    all_rec = [serialize(r) for r in all_rec]

    return jsonify({"success": True, "fines": all_rec}), 200


# ---------------------------------------------------------
# 8️⃣ FUTURE — PAYMENT GATEWAY WEBHOOK
# ---------------------------------------------------------
# @fine_bp.route("/payment-success", methods=["POST"])
# @cross_origin()
# def payment_success():
#     data = request.json
#     enrollment = data.get("enrollment")

#     db.fine.update_many(
#         {"enrollment": enrollment},
#         {"$set": {"status": "Paid", "updatedAt": datetime.now()}}
#     )

#     return jsonify({"success": True, "message": "Payment verified"}), 200
@fine_bp.route("/create-order", methods=["POST"])
@cross_origin()
def create_order():
    data = request.json
    enrollment = data.get("enrollment")
    amount = int(data.get("amount"))  # rupees

    if amount <= 0:
        return jsonify({"success": False, "message": "Invalid amount"}), 400

    # Razorpay client (credentials later env me dalna)
    client = razorpay.Client(auth=(
        os.getenv("RAZORPAY_KEY_ID"),
        os.getenv("RAZORPAY_KEY_SECRET")
    ))

    order = client.order.create({
        "amount": amount * 100,
        "currency": "INR",
        "payment_capture": 1
    })

    return jsonify({
        "success": True,
        "order_id": order["id"],
        "amount": amount,
        "currency": "INR"
    }), 200
@fine_bp.route("/razorpay-webhook", methods=["POST"])
def razorpay_webhook():
    payload = request.data
    signature = request.headers.get("X-Razorpay-Signature")

    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")

    expected_signature = hmac.new(
        webhook_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        return "Invalid signature", 400

    event = json.loads(payload)

    if event["event"] == "payment.captured":
        payment = event["payload"]["payment"]["entity"]

        enrollment = payment["notes"].get("enrollment")
        amount_paid = payment["amount"] // 100

        # 🔹 Insert transaction
        db.payment_transactions.insert_one({
            "enrollment": enrollment,
            "amount_paid": amount_paid,
            "razorpay_payment_id": payment["id"],
            "razorpay_order_id": payment["order_id"],
            "status": "success",
            "createdAt": datetime.now()
        })

        # 🔹 Recalculate fine
        fine = db.fine.find_one({"enrollment": enrollment})

        total = fine["fine"]
        paid = sum(t["amount_paid"] for t in db.payment_transactions.find({"enrollment": enrollment}))
        pending = total - paid

        status = "Paid" if pending <= 0 else "Partial"

        db.fine.update_many(
            {"enrollment": enrollment},
            {"$set": {
                "status": status,
                "updatedAt": datetime.now()
            }}
        )

    return "OK", 200