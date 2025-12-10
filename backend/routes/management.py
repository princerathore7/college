from flask import Blueprint, request, jsonify
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["college_db"]
students_collection = db["students"]

management_bp = Blueprint("management_bp", __name__)

# ----------------------------------------
# FETCH STUDENTS BY BRANCH (IT, IT1, IT2)
@management_bp.route("/api/students/<branch>", methods=["GET"])
def get_students_by_branch(branch):
    students = list(db.students.find({"branch": branch}))   # ✔ CORRECT

    for s in students:
        s["_id"] = str(s["_id"])

    return jsonify({"success": True, "students": students})

# ----------------------------------------
# ADD SINGLE STUDENT
# ----------------------------------------
@management_bp.route("/api/students/add", methods=["POST"])
def add_single_student():
    try:
        data = request.json
        branch = data.get("branch")
        enrollment = data.get("enrollment")

        if not branch or not enrollment:
            return jsonify({"success": False, "message": "Missing branch or enrollment"}), 400

        if students_collection.find_one({"branch": branch, "enrollment": enrollment}):
            return jsonify({"success": False, "message": "Student already exists"}), 400

        students_collection.insert_one({
            "branch": branch,
            "enrollment": enrollment,
            "name": ""     # default empty
        })

        return jsonify({"success": True, "message": "Student added successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ----------------------------------------
# ADD BULK
# ----------------------------------------
@management_bp.route("/api/students/bulk", methods=["POST"])
def add_bulk_students():
    try:
        data = request.json
        branch = data.get("branch")
        start = data.get("start")
        end = data.get("end")

        if not branch or not start or not end:
            return jsonify({"success": False, "message": "Missing fields"}), 400

        prefix = start[:-3]
        s = int(start[-3:])
        e = int(end[-3:])

        added = 0
        for i in range(s, e + 1):
            enr = f"{prefix}{i:03d}"
            if not students_collection.find_one({"branch": branch, "enrollment": enr}):
                students_collection.insert_one({
                    "branch": branch,
                    "enrollment": enr,
                    "name": ""
                })
                added += 1

        return jsonify({"success": True, "message": f"{added} students added"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
