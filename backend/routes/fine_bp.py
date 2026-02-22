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
from routes.receipt import create_receipt
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
# 🔹 RAZORPAY WEBHOOK — HANDLE PAYMENT SUCCESS
# ---------------------------------------------------------
from routes.receipt import create_receipt   # ADD THIS IMPORT AT TOP

@fine_bp.route("/razorpay-webhook", methods=["POST"])
def razorpay_webhook():
    try:
        # 🔐 Get raw payload and signature
        payload = request.data
        signature = request.headers.get("X-Razorpay-Signature")

        webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")

        if not webhook_secret:
            print("❌ Webhook secret missing")
            return "Webhook secret not configured", 500

        # 🔐 Verify webhook signature
        expected_signature = hmac.new(
            webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            print("❌ Invalid Razorpay signature")
            return "Invalid signature", 400

        # 🔹 Parse event
        event = json.loads(payload)

        # 🔹 Only handle successful captured payments
        if event.get("event") == "payment.captured":

            payment = event["payload"]["payment"]["entity"]

            enrollment = payment["notes"].get("enrollment")
            reason = payment["notes"].get("reason", "College Fine")

            amount_paid = payment["amount"] // 100   # convert paisa → rupees

            razorpay_payment_id = payment["id"]
            razorpay_order_id = payment["order_id"]
            payment_method = payment.get("method", "UPI")

            print(f"✅ Payment captured for {enrollment}, Amount: ₹{amount_paid}")

            # ---------------------------------------------------------
            # 1️⃣ SAVE TRANSACTION
            # ---------------------------------------------------------
            db.payment_transactions.insert_one({
                "enrollment": enrollment,
                "amount_paid": amount_paid,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_order_id": razorpay_order_id,
                "status": "success",
                "createdAt": datetime.now()
            })

            # ---------------------------------------------------------
            # 2️⃣ CLEAR FINES AUTOMATICALLY
            # ---------------------------------------------------------
            fines = list(db.fine.find({
                "enrollment": enrollment,
                "status": {"$in": ["Unpaid", "Partial"]}
            }))

            remaining_payment = amount_paid

            for f in fines:

                if remaining_payment <= 0:
                    break

                fine_amount = int(f.get("fine", 0))

                if remaining_payment >= fine_amount:

                    # FULL CLEAR
                    db.fine.update_one(
                        {"_id": f["_id"]},
                        {"$set": {
                            "fine": 0,
                            "status": "Paid",
                            "updatedAt": datetime.now()
                        }}
                    )

                    remaining_payment -= fine_amount

                else:

                    # PARTIAL CLEAR
                    db.fine.update_one(
                        {"_id": f["_id"]},
                        {"$set": {
                            "fine": fine_amount - remaining_payment,
                            "status": "Partial",
                            "updatedAt": datetime.now()
                        }}
                    )

                    remaining_payment = 0


            # ---------------------------------------------------------
            # 3️⃣ CREATE RECEIPT  ⭐ IMPORTANT
            # ---------------------------------------------------------
            create_receipt({
                "enrollment": enrollment,
                "payment_id": razorpay_payment_id,
                "order_id": razorpay_order_id,
                "amount_paid": amount_paid,
                "reason": reason,
                "method": payment_method
            })

            print("🧾 Receipt created successfully")


        return "OK", 200


    except Exception as e:
        print("❌ Razorpay webhook error:", e)
        return "Server Error", 500
    # ---------------------------------------------------------
# 🔹 AUTO CLEAR ALL FINES FOR A STUDENT
# ---------------------------------------------------------
@fine_bp.route("/clear-fines/<enrollment>", methods=["POST"])
def clear_fines(enrollment):
    try:
        # Fetch all unpaid/partial fines
        fines = list(db.fine.find({
            "enrollment": enrollment,
            "status": {"$in": ["Unpaid", "Partial"]}
        }))

        if not fines:
            return jsonify({"success": True, "message": "No fines to clear"}), 200

        # Update all fines to zero
        for f in fines:
            db.fine.update_one(
                {"_id": f["_id"]},
                {"$set": {"fine": 0, "status": "Paid", "updatedAt": datetime.now()}}
            )

        return jsonify({"success": True, "message": f"All fines for {enrollment} cleared successfully"}), 200

    except Exception as e:
        print("❌ Clear fines error:", e)
        return jsonify({"success": False, "message": "Server error"}), 500