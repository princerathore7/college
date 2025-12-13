from flask import Blueprint, request, jsonify
from db import db
from utils import generate_id
from flask_cors import cross_origin

# 🔔 Notification helper
from routes.notifications import send_to_class

exams_bp = Blueprint("exams_bp", __name__, url_prefix="/api/exams")


# ---------------------------------------------------------
# ✅ GET all exams or by class
# ---------------------------------------------------------
@exams_bp.route('', methods=['GET'])
@cross_origin()
def get_exams():
    class_name = request.args.get("class")
    query = {}
    if class_name:
        query["class"] = class_name

    exams = list(db.exams.find(query, {"_id": 0}))
    return jsonify({"success": True, "exams": exams}), 200


# ---------------------------------------------------------
# ✅ GET single exam
# ---------------------------------------------------------
@exams_bp.route('/<examId>', methods=['GET'])
@cross_origin()
def get_exam(examId):
    exam = db.exams.find_one({"examId": examId}, {"_id": 0})
    if not exam:
        return jsonify({"success": False, "message": "Exam not found"}), 404

    return jsonify({"success": True, "exam": exam}), 200


# ---------------------------------------------------------
# ✅ POST new exam (CLASS-WISE NOTIFICATION)
# ---------------------------------------------------------
@exams_bp.route('', methods=['POST'])
@cross_origin()
def post_exam():
    data = request.json

    required = ["examName", "subject", "date", "room", "class"]
    for field in required:
        if field not in data or not data[field]:
            return jsonify({
                "success": False,
                "message": f"{field} is required"
            }), 400

    # Generate exam ID
    exam_id = generate_id("EX")

    exam_doc = {
        "examId": exam_id,
        "examName": data["examName"],
        "subject": data["subject"],
        "date": data["date"],
        "room": data["room"],
        "class": data["class"]
    }

    # Save to DB
    db.exams.insert_one(exam_doc)

    # 🔔 CLASS-WISE NOTIFICATION
    send_to_class(
        class_name=data["class"],
        title="📝 New Exam Scheduled",
        body=f'{data["examName"]} ({data["subject"]}) on {data["date"]}',
        url="/exams.html"
    )

    return jsonify({
        "success": True,
        "message": "Exam posted and notification sent",
        "examId": exam_id
    }), 201

# DELETE exam
@exams_bp.route('/<examId>', methods=['DELETE'])
def delete_exam(examId):
    res = db.exams.delete_one({"examId": examId})
    if res.deleted_count == 0:
        return jsonify({"success": False, "message": "Exam not found"}), 404
    return jsonify({"success": True, "message": "Exam deleted"}), 200
