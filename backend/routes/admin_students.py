from flask import Blueprint, jsonify
from pymongo import MongoClient
import os

admin_students_bp = Blueprint(
    "admin_students_bp",
    __name__,
    url_prefix="/api/admin/students"
)

# -------------------- MongoDB --------------------
MONGO_URL = os.getenv("MONGO_URL")
if not MONGO_URL:
    raise Exception("MONGO_URL environment variable missing")

client = MongoClient(MONGO_URL)

users_db = client["users"]

students_collection = users_db["students"]
fees_collection = users_db["fees"]
attendance_collection = users_db["attendance"]
fines_collection = users_db["fines"]

# -------------------- GET ALL STUDENTS (ADMIN) --------------------
@admin_students_bp.route("", methods=["GET"])
def get_all_students():
    try:
        students = list(students_collection.find({}, {"_id": 0}))
        final_students = []

        for s in students:
            enrollment = s.get("enrollment")

            # ---------------- Pending Fees ----------------
            fees_doc = fees_collection.find_one(
                {"enrollment": enrollment},
                {"_id": 0, "pending_fees": 1}
            )

            # ---------------- Fine ----------------
            fine_doc = fines_collection.find_one(
                {"enrollment": enrollment},
                {"_id": 0, "fine": 1}
            )

            # ---------------- Attendance ----------------
            attendance_doc = attendance_collection.find_one(
                {"enrollment": enrollment},
                {"_id": 0, "total": 1, "present": 1}
            )

            total = attendance_doc.get("total", 0) if attendance_doc else 0
            present = attendance_doc.get("present", 0) if attendance_doc else 0

            attendance_percentage = (
                round((present / total) * 100, 2) if total > 0 else 0
            )

            final_students.append({
                "name": s.get("name"),
                "enrollment": enrollment,
                "branch": s.get("branch"),
                "section": s.get("section", "—"),
                "year": s.get("year", "—"),

                # ✅ Attendance (clean & frontend-friendly)
                "attendance": {
                    "total": total,
                    "present": present,
                    "percentage": attendance_percentage
                },

                "pendingFees": fees_doc.get("pending_fees", 0) if fees_doc else 0,
                "fine": fine_doc.get("fine", 0) if fine_doc else 0
            })

        return jsonify({
            "success": True,
            "count": len(final_students),
            "students": final_students
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
