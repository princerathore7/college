import os
import hmac
import hashlib
import razorpay
from flask import Blueprint, request, jsonify

razorpay_bp = Blueprint("razorpay_bp", __name__)

# 🔐 Load Razorpay keys ONLY from production environment
KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
print("DEBUG Razorpay KEY_ID:", KEY_ID)
print("DEBUG Razorpay KEY_SECRET exists:", bool(KEY_SECRET))

# ❌ If keys are missing → crash early (best practice)
if not KEY_ID or not KEY_SECRET:
    raise RuntimeError("Razorpay credentials missing in environment variables")

# Razorpay client
client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))


# 🔹 CREATE ORDER (UPI / QR)
@razorpay_bp.route("/api/fines/create-order", methods=["POST"])
def create_order():
    try:
        data = request.get_json(force=True)

        enrollment = data.get("enrollment")
        amount = int(data.get("amount", 0))
        reason = data.get("reason", "College Fine")

        if not enrollment or amount <= 0:
            return jsonify({
                "success": False,
                "message": "Invalid enrollment or amount"
            }), 400

        order = client.order.create({
            "amount": amount * 100,   # convert to paisa
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
            "amount": amount * 100,   # frontend ko paisa bhejo
            "key": KEY_ID             # Razorpay public key
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# 🔹 VERIFY PAYMENT (MANDATORY SECURITY)
@razorpay_bp.route("/api/fines/verify-payment", methods=["POST"])
def verify_payment():
    try:
        data = request.get_json(force=True)

        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return jsonify({
                "success": False,
                "message": "Missing payment verification fields"
            }), 400

        body = f"{razorpay_order_id}|{razorpay_payment_id}"

        expected_signature = hmac.new(
            KEY_SECRET.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(expected_signature, razorpay_signature):
            return jsonify({"success": True})

        return jsonify({
            "success": False,
            "message": "Invalid payment signature"
        }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
