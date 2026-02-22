import os
import hmac
import hashlib
import razorpay
from flask import Blueprint, request, jsonify
from routes.receipt import create_receipt
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

        enrollment = str(data.get("enrollment", "")).strip()
        amount = int(data.get("amount", 0))
        reason = str(data.get("reason", "College Fine")).strip()
        class_name = str(data.get("class", "")).strip()

        # Validation
        if not enrollment or amount <= 0:
            return jsonify({
                "success": False,
                "message": "Invalid enrollment or amount"
            }), 400


        # ---------------------------------------------------------
        # CREATE RAZORPAY ORDER
        # ---------------------------------------------------------
        order = client.order.create({
            "amount": amount * 100,   # convert to paisa
            "currency": "INR",
            "payment_capture": 1,

            # ⭐ IMPORTANT — SEND EXTRA DATA HERE
            "notes": {
                "enrollment": enrollment,
                "reason": reason,
                "class": class_name
            }
        })


        return jsonify({
            "success": True,
            "order_id": order["id"],
            "amount": amount * 100,
            "key": KEY_ID,
            "enrollment": enrollment,
            "reason": reason,
            "class": class_name
        })


    except Exception as e:
        print("❌ Create order error:", e)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
# 🔹 VERIFY PAYMENT (MANDATORY SECURITY)
@razorpay_bp.route("/api/fines/verify-payment", methods=["POST"])
@cross_origin()
def verify_payment():

    try:

        data = request.get_json(force=True)

        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):

            return jsonify({
                "success": False,
                "message": "Missing fields"
            }), 400


        # ---------------------------------------------------------
        # VERIFY SIGNATURE
        # ---------------------------------------------------------
        body = f"{razorpay_order_id}|{razorpay_payment_id}"

        expected_signature = hmac.new(
            KEY_SECRET.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()


        if not hmac.compare_digest(expected_signature, razorpay_signature):

            return jsonify({
                "success": False,
                "message": "Invalid signature"
            }), 400


        # ---------------------------------------------------------
        # FETCH ORDER DETAILS FROM RAZORPAY
        # ---------------------------------------------------------
        order = client.order.fetch(razorpay_order_id)

        enrollment = order["notes"].get("enrollment")

        reason = order["notes"].get("reason", "College Fine")

        student_class = order["notes"].get("class", "")

        amount_paid = order["amount"] // 100


        # ---------------------------------------------------------
        # CREATE RECEIPT
        # ---------------------------------------------------------
        create_receipt({

            "enrollment": enrollment,

            "payment_id": razorpay_payment_id,

            "order_id": razorpay_order_id,

            "amount_paid": amount_paid,

            "reason": reason,

            "class": student_class,

            "method": "UPI"

        })


        print(f"✅ Payment verified and receipt created for {enrollment}")


        return jsonify({
            "success": True,
            "message": "Payment verified successfully"
        })


    except Exception as e:

        print("VERIFY ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500