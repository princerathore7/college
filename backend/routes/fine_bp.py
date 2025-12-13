from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from db import db
from datetime import datetime
from bson.objectid import ObjectId

# 🔔 Notification helper
from routes.notifications import send_notification_to_enrollment

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
@cross_origin()
def add_bulk_fines():
    data = request.json
    fines = data.get("fines", [])

    if not fines or not isinstance(fines, list):
        return jsonify({"success": False, "message": "Invalid fines format"}), 400

    for f in fines:
        enrollment = f.get("enrollment")
        fine_amount = int(f.get("fine", 0))
        reason = f.get("reason", "Fine added")

        record = {
            "enrollment": enrollment,
            "class": f.get("class"),
            "fine": fine_amount,
            "reason": reason,
            "status": "Pending",
            "createdAt": datetime.now(),
            "updatedAt": datetime.now()
        }

        db.fine.insert_one(record)

        # 🔔 SEND NOTIFICATION (ENROLLMENT WISE)
        send_notification_to_enrollment(
            enrollment=enrollment,
            title="💰 New Fine Added",
            body=f"A fine of ₹{fine_amount} has been added. Reason: {reason}",
            url="/fine.html"
        )

    return jsonify({
        "success": True,
        "message": "Fines added successfully and notifications sent!"
    }), 201


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
@cross_origin()
def update_fine(fine_id):
    data = request.json

    fine_amount = int(data.get("fine"))
    reason = data.get("reason", "Fine updated")

    # 🔍 Get existing fine (for enrollment)
    fine_record = db.fine.find_one({"_id": ObjectId(fine_id)})
    if not fine_record:
        return jsonify({"success": False, "message": "Fine not found"}), 404

    enrollment = fine_record.get("enrollment")

    update_fields = {
        "fine": fine_amount,
        "reason": reason,
        "updatedAt": datetime.now()
    }

    db.fine.update_one(
        {"_id": ObjectId(fine_id)},
        {"$set": update_fields}
    )

    # 🔔 SEND NOTIFICATION TO THAT STUDENT ONLY
    send_notification_to_enrollment(
        enrollment=enrollment,
        title="💰 Fine Updated",
        body=f"Your fine has been updated to ₹{fine_amount}. Reason: {reason}",
        url="/fine.html"
    )

    return jsonify({
        "success": True,
        "message": "Fine updated and notification sent"
    }), 200

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
@fine_bp.route("/payment-success", methods=["POST"])
@cross_origin()
def payment_success():
    data = request.json
    enrollment = data.get("enrollment")

    db.fine.update_many(
        {"enrollment": enrollment},
        {"$set": {"status": "Paid", "updatedAt": datetime.now()}}
    )

    return jsonify({"success": True, "message": "Payment verified"}), 200
