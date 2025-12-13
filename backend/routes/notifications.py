from flask import Blueprint, request, jsonify
from pymongo import MongoClient
import firebase_admin
from firebase_admin import credentials, messaging
from datetime import datetime
import os, json

notifications_bp = Blueprint('notifications', __name__)

# -------------------- DATABASE SETUP --------------------
client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
  # replace with your DB URL
db = client['college_db']

tokens_col = db['fcm_tokens']             # Store student FCM tokens
notifications_col = db['notifications']   # Store sent notifications history/log

# -------------------- FIREBASE ADMIN SETUP --------------------
# Use environment variable for service account JSON
firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
if not firebase_json:
    raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON environment variable not set!")

cred = credentials.Certificate(json.loads(firebase_json))
firebase_admin.initialize_app(cred)

# -------------------- HELPER FUNCTION --------------------
def send_fcm_notification(title, body, tokens, data=None):
    """Send FCM notification to multiple tokens"""
    if not tokens:
        return {"success_count": 0, "failure_count": 0, "message": "No tokens available"}

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        tokens=tokens
    )

    response = messaging.send_multicast(message)
    return {"success_count": response.success_count, "failure_count": response.failure_count}


def log_notification(title, body, target_type, target, extra_data, result):
    """Store sent notification in DB"""
    notifications_col.insert_one({
        "title": title,
        "body": body,
        "target_type": target_type,
        "target": target,
        "data": extra_data,
        "success_count": result["success_count"],
        "failure_count": result["failure_count"],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


# -------------------- ROUTES --------------------

# 1️⃣ Save or update FCM token for a student
@notifications_bp.route('/api/save-token', methods=['POST'])
def save_token():
    data = request.json
    token = data.get('token')
    enrollment = data.get('enrollment')
    student_class = data.get('studentClass')

    if not token or not enrollment:
        return jsonify({"success": False, "message": "Missing token or enrollment"}), 400

    tokens_col.update_one(
        {'enrollment': enrollment},
        {'$set': {'token': token, 'studentClass': student_class}},
        upsert=True
    )
    return jsonify({"success": True, "message": "Token saved"})


# 2️⃣ Enrollment-wise notification
def send_to_enrollment(enrollment, title, body, url="/"):
    token_doc = tokens_col.find_one({"enrollment": enrollment})
    if not token_doc or not token_doc.get("token"):
        return {"success_count":0, "failure_count":1, "message":"No token for enrollment"}
    token = token_doc['token']
    result = send_fcm_notification(title, body, [token], data={"url": url})
    log_notification(title, body, "enrollment", [enrollment], {"url": url}, result)
    return result


# 3️⃣ Class-wise notification
def send_to_class(student_class, title, body, url="/"):
    tokens = [t['token'] for t in tokens_col.find({"studentClass": student_class})]
    result = send_fcm_notification(title, body, tokens, data={"url": url})
    log_notification(title, body, "class", student_class, {"url": url}, result)
    return result


# 4️⃣ Global notification
def send_global(title, body, url="/"):
    tokens = [t['token'] for t in tokens_col.find({})]
    result = send_fcm_notification(title, body, tokens, data={"url": url})
    log_notification(title, body, "global", "all", {"url": url}, result)
    return result


# -------------------- EXPOSED ROUTES --------------------

# Enrollment-wise (POST)
@notifications_bp.route('/api/notify/enrollment', methods=['POST'])
def notify_enrollment():
    data = request.json
    enrollments = data.get('enrollments', [])
    title = data.get('title')
    body = data.get('body')
    url = data.get('url', "/")
    results = []
    for e in enrollments:
        results.append(send_to_enrollment(e, title, body, url))
    return jsonify({"success": True, "results": results})


# Class-wise (POST)
@notifications_bp.route('/api/notify/class', methods=['POST'])
def notify_class():
    data = request.json
    student_class = data.get('class')
    title = data.get('title')
    body = data.get('body')
    url = data.get('url', "/")
    result = send_to_class(student_class, title, body, url)
    return jsonify({"success": True, "result": result})


# Global (POST)
@notifications_bp.route('/api/notify/global', methods=['POST'])
def notify_global_route():
    data = request.json
    title = data.get('title')
    body = data.get('body')
    url = data.get('url', "/")
    result = send_global(title, body, url)
    return jsonify({"success": True, "result": result})


# -------------------- SPECIFIC HELPERS FOR COMMON USE CASES --------------------

# Attendance update
@notifications_bp.route('/api/notify/attendance', methods=['POST'])
def notify_attendance():
    data = request.json
    enrollments = data.get('enrollments', [])
    body = data.get('body', "Your attendance has been updated")
    title = data.get('title', "Attendance Update")
    url = data.get('url', "/attendance.html")
    results = []
    for e in enrollments:
        results.append(send_to_enrollment(e, title, body, url))
    return jsonify({"success": True, "results": results})


# Marks update
@notifications_bp.route('/api/notify/marks', methods=['POST'])
def notify_marks():
    data = request.json
    enrollments = data.get('enrollments', [])
    body = data.get('body', "Your marks have been updated")
    title = data.get('title', "Marks Update")
    url = data.get('url', "/marks.html")
    results = []
    for e in enrollments:
        results.append(send_to_enrollment(e, title, body, url))
    return jsonify({"success": True, "results": results})


# Fine update
@notifications_bp.route('/api/notify/fine', methods=['POST'])
def notify_fine():
    data = request.json
    enrollments = data.get('enrollments', [])
    body = data.get('body', "A fine has been updated for you")
    title = data.get('title', "Fine Update")
    url = data.get('url', "/admin-fine.html")
    results = []
    for e in enrollments:
        results.append(send_to_enrollment(e, title, body, url))
    return jsonify({"success": True, "results": results})


# Notices / Assignments / Exams
@notifications_bp.route('/api/notify/notices', methods=['POST'])
def notify_notices():
    data = request.json
    target_class = data.get('class')  # can be None for all
    title = data.get('title')
    body = data.get('body')
    url = data.get('url', "/notices.html")
    if target_class:
        result = send_to_class(target_class, title, body, url)
    else:
        result = send_global(title, body, url)
    return jsonify({"success": True, "result": result})


@notifications_bp.route('/api/notify/assignments', methods=['POST'])
def notify_assignments():
    data = request.json
    target_class = data.get('class')
    title = data.get('title')
    body = data.get('body')
    url = data.get('url', "/assignments.html")
    if target_class:
        result = send_to_class(target_class, title, body, url)
    else:
        result = send_global(title, body, url)
    return jsonify({"success": True, "result": result})


@notifications_bp.route('/api/notify/exams', methods=['POST'])
def notify_exams():
    data = request.json
    target_class = data.get('class')
    title = data.get('title')
    body = data.get('body')
    url = data.get('url', "/exams.html")
    if target_class:
        result = send_to_class(target_class, title, body, url)
    else:
        result = send_global(title, body, url)
    return jsonify({"success": True, "result": result})


# Bus route update
@notifications_bp.route('/api/notify/bus', methods=['POST'])
def notify_bus():
    data = request.json
    title = data.get('title', "Bus Route Update")
    body = data.get('body', "New bus route PDF uploaded")
    url = data.get('url', "/bus-route.html")
    result = send_global(title, body, url)
    return jsonify({"success": True, "result": result})


# Events update (global)
@notifications_bp.route('/api/notify/events', methods=['POST'])
def notify_events():
    data = request.json
    title = data.get('title', "New Event Posted")
    body = data.get('body', "")
    url = data.get('url', "/events.html")
    result = send_global(title, body, url)
    return jsonify({"success": True, "result": result})
# --------------------------------------------------
# 🔔 COMMON HELPER (Assignments / Notices / Exams)
# --------------------------------------------------
def send_notification_to_class(class_name, title, body, url="/"):
    """
    Wrapper for class-wise notifications
    Used by assignments, notices, exams etc.
    """
    return send_to_class(
        student_class=class_name,
        title=title,
        body=body,
        url=url
    )
