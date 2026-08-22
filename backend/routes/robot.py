from flask import Blueprint, jsonify, request
from flask_cors import CORS
from bson import ObjectId
import copy
from db import db

robot_bp = Blueprint("robot_bp", __name__, url_prefix="/api/robot")
CORS(robot_bp)


def serialize(doc):
    if isinstance(doc, dict):
        doc = copy.deepcopy(doc)
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
    return doc


def faculty_ids(lecture):
    ids = lecture.get("facultyIds", []) if isinstance(lecture, dict) else []
    if isinstance(ids, str):
        ids = [ids]
    out=[]
    for x in ids or []:
        if isinstance(x, dict):
            x=x.get("mentorId") or x.get("facultyId") or x.get("id")
        if x is not None and str(x).strip(): out.append(str(x).strip())
    return list(dict.fromkeys(out))


@robot_bp.route("/requests", methods=["GET"])
def all_requests():
    mentor_id=request.args.get("mentorId")
    q={"status":"pending"}
    if mentor_id: q["targetMentorId"]=str(mentor_id)
    rows=list(db.lecture_requests.find(q).sort("createdAt",-1))
    return jsonify({"success":True,"count":len(rows),"requests":[serialize(x) for x in rows]})


@robot_bp.route("/requests/<request_id>", methods=["GET"])
def single_request(request_id):
    if not ObjectId.is_valid(request_id):
        return jsonify({"success":False,"message":"Invalid requestId"}),400
    row=db.lecture_requests.find_one({"_id":ObjectId(request_id)})
    if not row: return jsonify({"success":False,"message":"Request not found"}),404
    return jsonify({"success":True,"request":serialize(row)})


@robot_bp.route("/request-status/<request_id>", methods=["GET"])
def request_status(request_id):
    if not ObjectId.is_valid(request_id):
        return jsonify({"success":False,"message":"Invalid requestId"}),400
    row=db.lecture_requests.find_one({"_id":ObjectId(request_id)})
    if not row: return jsonify({"success":False,"message":"Request not found"}),404
    return jsonify({"success":True,"request":serialize(row)})


@robot_bp.route("/schedule/<path:class_name>", methods=["GET"])
def student_schedule(class_name):
    tt=db.timetables.find_one({"className":class_name})
    if not tt:
        return jsonify({"success":False,"message":"Timetable not found"}),404

    weekly=copy.deepcopy(tt.get("weeklySchedule",{}))
    for day, lectures in weekly.items():
        for lec in lectures:
            resolved=[]
            for fid in faculty_ids(lec):
                m=db.mentors.find_one({"mentorId":fid},{"_id":0,"mentorId":1,"name":1,"subject":1})
                if m: resolved.append(m)
            lec["faculty"]=resolved

    return jsonify({"success":True,"source":"robot","className":class_name,"weeklySchedule":weekly})
