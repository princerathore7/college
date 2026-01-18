import os
import hmac
import hashlib
import razorpay
from flask import Blueprint, request, jsonify
from dotenv import load_dotenv

load_dotenv()

razorpay_bp = Blueprint("razorpay_bp", __name__)

KEY_ID = os.getenv("RAZORPAY_KEY_ID")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))

# 🔹 CREATE ORDER (UPI / QR – SAME API)
@razorpay_bp.route("/api/fines/create-order", methods=["POST"])
def create_order():
    try:
        data = request.get_json()

        amount = int(data.get("amount", 0))
        enrollment = data.get("enrollment")
        reason = data.get("reason", "College Fine")

        if amount <= 0 or not enrollment:
            return jsonify({
                "success": False,
                "message": "Invalid amount or enrollment"
            }), 400

        order = client.order.create({
            "amount": amount * 100,   # paisa
            "currency": "INR",
            "payment_capture": 1,
            "notes": {
                "enrollment": enrollment,
                "reason": reason
            }
        })

        return jsonify({
            "success": True,
            "order_id": order["id"],
            "amount": amount,
            "key": KEY_ID   # frontend ko yahin se milegi
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# 🔹 VERIFY PAYMENT (SECURITY – MUST)
@razorpay_bp.route("/verify-payment", methods=["POST"])
def verify_payment():
    try:
        data = request.get_json()

        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")

        body = razorpay_order_id + "|" + razorpay_payment_id

        expected_signature = hmac.new(
            KEY_SECRET.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        if expected_signature == razorpay_signature:
            # ✅ Payment verified
            return jsonify({"success": True})

        else:
            return jsonify({"success": False, "message": "Invalid signature"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500
