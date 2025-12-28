from flask import Blueprint, request, jsonify
from pymongo import MongoClient
import firebase_admin
from firebase_admin import credentials, messaging
from datetime import datetime
import os, json
from pywebpush import webpush
notifications_bp = Blueprint('notifications', __name__)

# -------------------- DATABASE SETUP --------------------
client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client['college_db']

tokens_col = db['fcm_tokens']             # Store student FCM tokens
notifications_col = db['notifications']   # Store sent notifications history/log

# -------------------- FIREBASE ADMIN SETUP --------------------
# Initialize Firebase only once
firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if firebase_json:
    try:
        cred_dict = json.loads(firebase_json)
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully")
    except Exception as e:
        print("❌ Firebase init failed:", e)
else:
    print("⚠️ Firebase disabled: FIREBASE_SERVICE_ACCOUNT_JSON not set")

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
        "timestamp": datetime.utcnow() 
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
    log_notification(title, body, "enrollment", enrollment, {"url": url}, result)
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

    if not enrollments:
        return jsonify({"success": False, "message": "No enrollments provided"}), 400

    results = []
    for e in enrollments:
        try:
            res = send_to_enrollment(e, title, body, url)
            results.append({"enrollment": e, "status": "success", "result": res})
        except Exception as ex:
            results.append({"enrollment": e, "status": "failed", "error": str(ex)})

    return jsonify({"success": True, "results": results}), 200


# Fine update
@notifications_bp.route('/api/notify/fine', methods=['POST'])
def notify_fine(enrollment, title, body, url):
    # 🔎 enrollment se student ka device token nikaalo
    sub = db.notifications.find_one({"enrollment": enrollment})
    if not sub:
        return

    send_web_push(
        subscription=sub["subscription"],
        title=title,
        body=body,
        url=url
    )


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
    class_name = data.get('class')  # optional, send to specific class
    title = data.get('title')
    body = data.get('body')
    url = data.get('url', "/assignments.html")

    if not title or not body:
        return jsonify({"success": False, "message": "Title and body are required"}), 400

    if class_name:
        result = send_to_class(class_name, title, body, url)
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
def send_web_notification(subscription, message, private_key):
    webpush(
        subscription_info=subscription,
        data=message,
        vapid_private_key=private_key,
        vapid_claims={"sub": "mailto:your-email@example.com"}
    )
@notifications_bp.route('/api/subscribe', methods=['POST'])
def subscribe():
    data = request.json
    enrollment = data.get('enrollment')  # frontend se enrollment pass karna zaruri
    if not enrollment:
        return jsonify({"success": False, "message": "Enrollment missing"}), 400

    # subscription object
    subscription = data.get('subscription') or data  # data me pura subscription object aa sakta hai

    try:
        tokens_col.update_one(
            {'enrollment': enrollment},
            {'$set': {'token': subscription}},
            upsert=True
        )
        return jsonify({"success": True, "message": "Subscription saved"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    # 📥 Fetch notifications for a student
@notifications_bp.route('/api/notifications', methods=['GET'])
def get_notifications():
    enrollment = request.args.get('enrollment')
    student_class = request.args.get('class')

    if not enrollment:
        return jsonify({"success": False, "message": "Enrollment required"}), 400

    query = {
        "$or": [
            {"target_type": "global"},
            {"target_type": "class", "target": student_class},
            {"target_type": "enrollment", "target": enrollment}
        ]
    }

    notifications = list(
        notifications_col.find(query)
        .sort("timestamp", -1)
        .limit(100)
    )

    for n in notifications:
        n["_id"] = str(n["_id"])
        n["timestamp"] = n["timestamp"].strftime("%Y-%m-%d %H:%M")

    return jsonify({"success": True, "notifications": notifications})
