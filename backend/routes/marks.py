from flask import Blueprint, jsonify, request
import os
import json

# 🔔 Notification helper
from routes.notifications import send_to_enrollment as send_notification_to_enrollment

marks_bp = Blueprint("marks_bp", __name__)

DATA_FILE = os.path.join("data", "marks.json")

def load_marks():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_marks(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# -----------------------------
# GET marks by enrollment
# -----------------------------
@marks_bp.route("/api/marks/<enrollment>", methods=["GET"])
def get_marks(enrollment):
    data = load_marks()
    student = data.get(enrollment)
    if not student:
        return jsonify({"success": False, "message": "No marks found for this enrollment"}), 404
    return jsonify({"success": True, "marks": student})

# -----------------------------
# POST/UPDATE marks
# -----------------------------
@marks_bp.route("/api/marks", methods=["POST"])
def post_marks():
    payload = request.get_json() or {}
    enrollment = payload.get("enrollment")
    if not enrollment:
        return jsonify({"success": False, "message": "enrollment is required"}), 400

    def number_of(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    mst = number_of(payload.get("mst", 0))
    internal = number_of(payload.get("internal", 0))
    assignments = number_of(payload.get("assignments", 0))

    weights = payload.get("weights") or {}
    w_mst = float(weights.get("mst", 0)) if isinstance(weights, dict) and weights.get("mst") is not None else None
    w_internal = float(weights.get("internal", 0)) if isinstance(weights, dict) and weights.get("internal") is not None else None
    w_assign = float(weights.get("assignments", 0)) if isinstance(weights, dict) and weights.get("assignments") is not None else None

    if w_mst is not None or w_internal is not None or w_assign is not None:
        w_mst = w_mst or 0.0
        w_internal = w_internal or 0.0
        w_assign = w_assign or 0.0
        total_w = w_mst + w_internal + w_assign
        if total_w <= 0:
            w_mst = w_internal = w_assign = 1/3
        else:
            w_mst /= total_w
            w_internal /= total_w
            w_assign /= total_w
    else:
        w_mst = w_internal = w_assign = 1/3

    percentage = round((mst * w_mst) + (internal * w_internal) + (assignments * w_assign), 2)

    record = {
        "enrollment": enrollment,
        "name": payload.get("name", ""),
        "class": payload.get("class", ""),
        "mst": mst,
        "internal": internal,
        "assignments": assignments,
        "weights": {"mst": round(w_mst,4), "internal": round(w_internal,4), "assignments": round(w_assign,4)},
        "percentage": percentage,
        "notes": payload.get("notes", "")
    }

    data = load_marks()
    data[enrollment] = record
    save_marks(data)

    # 🔔 SEND notification to student
    try:
        title = "📊 Marks Updated"
        body = f"Hello {record['name']}, your MST/Internal/Assignment marks have been updated. Total: {percentage}%"
        url = "/marks.html"
        send_notification_to_enrollment(enrollment, title=title, body=body, url=url)
    except Exception as e:
        print("Notification error:", e)

    return jsonify({"success": True, "message": "Marks saved & notification sent", "marks": record})
