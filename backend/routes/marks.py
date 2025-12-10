from flask import Blueprint, jsonify, request
import os
import json

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

@marks_bp.route("/api/marks/<enrollment>", methods=["GET"])
def get_marks(enrollment):
    """
    Return marks for a student by enrollment.
    """
    data = load_marks()
    student = data.get(enrollment)
    if not student:
        return jsonify({"success": False, "message": "No marks found for this enrollment"}), 404
    return jsonify({"success": True, "marks": student})

@marks_bp.route("/api/marks", methods=["POST"])
def post_marks():
    """
    Add or update marks. Request JSON format:
    {
      "enrollment": "EN123",
      "name": "Student Name",
      "class": "1A",
      "mst": 78,
      "internal": 82,
      "assignments": 85,
      // optional weights (sum not required; we'll normalize)
      "weights": {"mst": 0.4, "internal":0.4, "assignments":0.2}
    }
    Response returns computed percentage.
    """
    payload = request.get_json() or {}
    enrollment = payload.get("enrollment")
    if not enrollment:
        return jsonify({"success": False, "message": "enrollment is required"}), 400

    # read numeric marks (coerce)
    def number_of(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    mst = number_of(payload.get("mst", 0))
    internal = number_of(payload.get("internal", 0))
    assignments = number_of(payload.get("assignments", 0))

    # weights (optional)
    weights = payload.get("weights") or {}
    w_mst = float(weights.get("mst", 0)) if isinstance(weights, dict) and weights.get("mst") is not None else None
    w_internal = float(weights.get("internal", 0)) if isinstance(weights, dict) and weights.get("internal") is not None else None
    w_assign = float(weights.get("assignments", 0)) if isinstance(weights, dict) and weights.get("assignments") is not None else None

    # If any weight is provided, normalize weights; else use equal weights.
    if w_mst is not None or w_internal is not None or w_assign is not None:
        # default missing to 0
        w_mst = w_mst or 0.0
        w_internal = w_internal or 0.0
        w_assign = w_assign or 0.0
        total_w = w_mst + w_internal + w_assign
        if total_w <= 0:
            # avoid division by zero -> fallback equal
            w_mst = w_internal = w_assign = 1/3
        else:
            w_mst /= total_w
            w_internal /= total_w
            w_assign /= total_w
    else:
        w_mst = w_internal = w_assign = 1/3

    # compute percentage (assuming marks are each out of 100)
    percentage = (mst * w_mst) + (internal * w_internal) + (assignments * w_assign)
    # round to 2 decimal places
    percentage = round(percentage, 2)

    # prepare record
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

    return jsonify({"success": True, "message": "Marks saved", "marks": record})
