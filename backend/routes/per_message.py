from flask import Blueprint, request, jsonify, send_from_directory
from flask_cors import cross_origin
from werkzeug.utils import secure_filename
from datetime import datetime
from bson import ObjectId
import os
from db import db

# =========================
# ✅ BLUEPRINT
# =========================
per_message_bp = Blueprint(
    "per_message",
    __name__,
    url_prefix="/api"  # /api ke under sab routes
)

# =========================
# CONFIG
# =========================
UPLOAD_FOLDER = "uploads/messages"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
messages_col = db.personal_messages

# =========================
# ADMIN: SEND PERSONAL MESSAGE
# =========================
@per_message_bp.route("/admin/personal-message/send", methods=["POST", "OPTIONS"])
@cross_origin()
def send_personal_message():
    # ✅ CORS preflight
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        title = request.form.get("title")
        description = request.form.get("description")
        enrollments = request.form.get("enrollments")

        if not title or not description or not enrollments:
            return jsonify({"success": False, "message": "Required fields missing"}), 400

        enrollment_list = [e.strip() for e in enrollments.split(",") if e.strip()]

        attachments = []
        files = request.files.getlist("attachments")

        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                attachments.append({"filename": filename, "path": filepath})

        read_status = {enr: False for enr in enrollment_list}

        messages_col.insert_one({
            "title": title,
            "description": description,
            "enrollments": enrollment_list,
            "attachments": attachments,
            "created_by": "admin",
            "created_at": datetime.utcnow(),
            "is_read": read_status
        })

        return jsonify({"success": True, "message": "Personal message sent successfully"}), 201

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500

# =========================
# STUDENT: FETCH MY MESSAGES
# =========================
@per_message_bp.route("/student/personal-messages/<enrollment>", methods=["GET"])
def get_student_messages(enrollment):
    messages = messages_col.find({"enrollments": enrollment}).sort("created_at", -1)

    result = []
    for msg in messages:
        result.append({
            "id": str(msg["_id"]),
            "title": msg["title"],
            "description": msg["description"],
            "attachments": msg.get("attachments", []),
            "created_at": msg["created_at"],
            "is_read": msg["is_read"].get(enrollment, False)
        })

    return jsonify(result)

# =========================
# STUDENT: MARK AS READ
# =========================
@per_message_bp.route("/student/personal-message/read/<message_id>", methods=["POST"])
def mark_message_read(message_id):
    enrollment = request.json.get("enrollment")

    if not enrollment:
        return jsonify({"error": "Enrollment required"}), 400

    messages_col.update_one(
        {"_id": ObjectId(message_id)},
        {"$set": {f"is_read.{enrollment}": True}}
    )

    return jsonify({"message": "Marked as read"})

# =========================
# DOWNLOAD ATTACHMENT
# =========================
@per_message_bp.route("/personal-message/attachment/<filename>")
def download_attachment(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

# =========================
# ADMIN: GET ALL SENT MESSAGES
# =========================
@per_message_bp.route("/admin/personal-messages", methods=["GET"])
def admin_all_messages():
    messages = messages_col.find().sort("created_at", -1)

    result = []
    for msg in messages:
        result.append({
            "id": str(msg["_id"]),
            "title": msg["title"],
            "enrollments": msg["enrollments"],
            "attachments_count": len(msg.get("attachments", [])),
            "created_at": msg["created_at"]
        })

    return jsonify(result)
# =========================
# ADMIN: GET ALL PERSONAL MESSAGES
# =========================
@per_message_bp.route("/admin/personal-messages/all", methods=["GET"])
def admin_get_all_messages():
    try:
        messages = messages_col.find().sort("created_at", -1)
        result = []
        for msg in messages:
            result.append({
                "id": str(msg["_id"]),
                "title": msg["title"],
                "description": msg["description"],
                "enrollments": msg["enrollments"],
                "attachments": msg.get("attachments", []),
                "created_at": msg["created_at"]
            })
        return jsonify({"success": True, "messages": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =========================
# ADMIN: DELETE PERSONAL MESSAGE
# =========================
@per_message_bp.route("/admin/personal-message/<message_id>", methods=["DELETE"])
def admin_delete_message(message_id):
    try:
        msg = messages_col.find_one({"_id": ObjectId(message_id)})
        if not msg:
            return jsonify({"success": False, "message": "Message not found"}), 404

        # Delete attachments from disk
        for f in msg.get("attachments", []):
            try:
                if os.path.exists(f["path"]):
                    os.remove(f["path"])
            except:
                pass  # ignore errors

        messages_col.delete_one({"_id": ObjectId(message_id)})
        return jsonify({"success": True, "message": "Message deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
