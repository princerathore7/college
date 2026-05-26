from flask import Blueprint, jsonify
from db import db
from datetime import datetime

verified_students_bp = Blueprint(
    "verified_students_bp",
    __name__,
    url_prefix="/api/verified-students"
)

verified_collection = db["verified_students"]

# ---------------- GET ALL VERIFIED STUDENTS ----------------

@verified_students_bp.route("/", methods=["GET"])
def get_verified_students():

    try:
        students = list(
            verified_collection.find({}, {"_id": 0}).sort("verifiedAt", -1)
        )

        return jsonify({
            "success": True,
            "count": len(students),
            "students": students
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500