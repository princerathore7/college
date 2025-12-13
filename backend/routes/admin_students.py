from flask import Blueprint, jsonify
from pymongo import MongoClient
import os
import re

admin_students_bp = Blueprint(
    "admin_students_bp",
    __name__,
    url_prefix="/api/admin/students"
)

# -------------------- Mongo Connections --------------------

# USERS DB (students / fees / fines)
users_client = MongoClient(os.getenv("MONGO_URL"))
users_db = users_client["users"]

students_collection = users_db["students"]
fees_collection = users_db["fees"]
fines_collection = users_db["fines"]

# COLLEGE DB (attendance)
college_client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
college_db = college_client["college_db"]
attendance_collection = college_db["attendance"]

# -------------------- Helpers --------------------

def extract_year(class_assigned: str):
    """
    "2nd Year IT1"  -> 2
    "1st Year - A"  -> 1
    """
    if not class_assigned:
        return "—"

    match = re.search(r'(\d)(st|nd|rd|th)\s*Year', class_assigned)
    return match.group(1) if match else "—"

def attendance_summary(enrollment):
    total = attendance_collection.count_documents(
        {"enrollment": enrollment}
    )
    present = attendance_collection.count_documents(
        {"enrollment": enrollment, "status": "P"}
    )

    percentage = round((present / total) * 100, 2) if total > 0 else 0

    return {
        "total": total,
        "present": present,
        "percentage": percentage
    }

# -------------------- API --------------------

@admin_students_bp.route("", methods=["GET"])
def get_all_students():
    try:
        students = list(students_collection.find({}, {"_id": 0}))
        final_students = []

        for s in students:
            enrollment = s.get("enrollment")

            # Fees
            fees_doc = fees_collection.find_one(
                {"enrollment": enrollment},
                {"_id": 0, "pending_fees": 1}
            )

            # Fine
            fine_doc = fines_collection.find_one(
                {"enrollment": enrollment},
                {"_id": 0, "fine": 1}
            )

            final_students.append({
                "name": s.get("name"),
                "enrollment": enrollment,
                "branch": s.get("branch"),
                "section": s.get("section", "—"),

                # ✅ FIXED YEAR
                "year": extract_year(s.get("class_assigned")),

                # ✅ REAL ATTENDANCE (from college_db)
                "attendance": attendance_summary(enrollment),

                "pendingFees": fees_doc.get("pending_fees", 0) if fees_doc else 0,
                "fine": fine_doc.get("fine", 0) if fine_doc else 0
            })

        return jsonify({
            "success": True,
            "count": len(final_students),
            "students": final_students
        }), 200

    except Exception as e:
        print("❌ Admin students error:", e)
        return jsonify({
            "success": False,
            "message": "Internal server error"
        }), 500

