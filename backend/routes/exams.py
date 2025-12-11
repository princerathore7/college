# exams.py
from flask import Blueprint, request, jsonify
from db import db  # assume pymongo client
from utils import generate_id

exams_bp = Blueprint("exams_bp", __name__, url_prefix="/api/exams")

# Enable CORS for this blueprint
CORS(exams_bp)

# GET all exams or by class
@exams_bp.route('', methods=['GET'])
def get_exams():
    class_name = request.args.get("class")
    query = {}
    if class_name:
        query["class"] = class_name
    exams = list(db.exams.find(query, {"_id":0}))
    return jsonify({"success": True, "exams": exams}), 200

# GET single exam
@exams_bp.route('/<examId>', methods=['GET'])
def get_exam(examId):
    exam = db.exams.find_one({"examId": examId}, {"_id":0})
    if not exam:
        return jsonify({"success": False, "message": "Exam not found"}), 404
    return jsonify({"success": True, "exam": exam}), 200

# POST new exam
@exams_bp.route('', methods=['POST'])
def post_exam():
    data = request.json
    required = ["examName","subject","date","room","class"]
    for field in required:
        if field not in data or not data[field]:
            return jsonify({"success": False, "message": f"{field} is required"}), 400
    data["examId"] = generate_id("EX")
    db.exams.insert_one(data)
    return jsonify({"success": True, "message":"Exam posted", "examId": data["examId"]}), 201

# DELETE exam
@exams_bp.route('/<examId>', methods=['DELETE'])
def delete_exam(examId):
    res = db.exams.delete_one({"examId": examId})
    if res.deleted_count == 0:
        return jsonify({"success": False, "message": "Exam not found"}), 404
    return jsonify({"success": True, "message": "Exam deleted"}), 200
