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

users_client = MongoClient(os.getenv("MONGO_URL"))
users_db = users_client["users"]

students_collection = users_db["students"]
fees_collection = users_db["fees"]
fines_collection = users_db["fines"]

college_client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
college_db = college_client["college_db"]
attendance_collection = college_db["attendance"]

# -------------------- Helpers --------------------

def extract_year(class_name: str):
    """
    "1st Year IT" -> 1
    "2nd Year CSE" -> 2
    """
    if not class_name:
        return "—"

    m = re.search(r'(\d)(st|nd|rd|th)\s*Year', class_name)
    return m.group(1) if m else "—"


def attendance_summary(enrollment):
    total = attendance_collection.count_documents(
        {"enrollment": enrollment}
    )
    present = attendance_collection.count_documents(
        {"enrollment": enrollment, "status": "P"}
    )

    percentage = round((present / total) * 100, 2) if total else 0

    return {
        "total": total,
        "present": present,
        "percentage": percentage
    }


def total_fine(enrollment):
    fines = fines_collection.find(
        {"enrollment": enrollment},
        {"fine": 1}
    )
    return sum(f.get("fine", 0) for f in fines)


# -------------------- API --------------------

@admin_students_bp.route("", methods=["GET"])
def get_all_students():
    try:
        students = list(students_collection.find({}, {"_id": 0}))
        final_students = []

        for s in students:
            enrollment = s.get("enrollment")

            # ✅ Pending Fees (DON'T TOUCH)
            fees_doc = fees_collection.find_one(
                {"enrollment": enrollment},
                {"_id": 0, "pending_fees": 1}
            )

            final_students.append({
                "name": s.get("name"),
                "enrollment": enrollment,

                # ✅ Branch fix
                "branch": s.get("branch"),

                # ❌ Section hata diya (as per your rule)
                "section": "—",

                # ✅ Proper year from class
                "year": extract_year(s.get("class")),

                # ✅ FULL attendance object
                "attendance": attendance_summary(enrollment),

                # ✅ Fees unchanged
                "pendingFees": fees_doc.get("pending_fees", 0) if fees_doc else 0,

                # ✅ TOTAL fine (FIXED)
                "fine": total_fine(enrollment)
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
