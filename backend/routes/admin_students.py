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

def parse_class_info(class_name: str):
    """
    "2nd Year CSE3" → year=2, branch=CSE, section=3
    """
    if not class_name:
        return {
            "year": "—",
            "branch": "—",
            "section": "—"
        }

    # year
    year_match = re.search(r'(\d)(st|nd|rd|th)\s*Year', class_name)
    year = year_match.group(1) if year_match else "—"

    # branch + section (CSE3, IT2, AIML1 etc)
    rest = class_name.split("Year")[-1].strip()

    branch = ''.join(filter(str.isalpha, rest)) or "—"
    section = ''.join(filter(str.isdigit, rest)) or "—"

    return {
        "year": year,
        "branch": branch,
        "section": section
    }


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

            class_info = parse_class_info(s.get("class"))

            fees_doc = fees_collection.find_one(
                {"enrollment": enrollment},
                {"_id": 0, "pending_fees": 1}
            )

            final_students.append({
                "name": s.get("name"),
                "enrollment": enrollment,

                # ✅ ONLY class-derived data
                "year": class_info["year"],
                "branch": class_info["branch"],
                "section": class_info["section"],

                # ✅ Attendance object
                "attendance": attendance_summary(enrollment),

                # ✅ Fees & fine
                "pendingFees": fees_doc.get("pending_fees", 0) if fees_doc else 0,
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
