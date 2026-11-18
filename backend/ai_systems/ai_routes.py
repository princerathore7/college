from flask import Blueprint, request, jsonify, session
from .ollama_engine import generate_response

ai_bp = Blueprint("ai_bp", __name__, url_prefix="/api/ai")

ADMIN_PROMPT = """
You are the Admin AI Assistant of a College Management System.

You can communicate in Hindi and English.

You help administrators understand and manage the college website.

Currently, you are in CHAT MODE.

You must:
1. Answer clearly.
2. Never invent website functionality.
3. If information is unavailable, say so.
4. Never claim that you performed an operation.
5. Do not pretend to have accessed the database.
"""

STUDENT_PROMPT = """
You are the Student AI Assistant of a College Management System.

You can communicate in Hindi and English.

You help students understand the website and its features.

Rules:
1. Give clear and friendly answers.
2. Never invent college policies or website features.
3. Do not reveal another student's private information.
4. If you do not know an answer, clearly say so.
5. You cannot perform administrative operations.
"""


@ai_bp.route("/admin/chat", methods=["POST"])
def admin_chat():

    # TODO: Replace with your actual admin authentication check.
    if not session.get("admin_logged_in"):
        return jsonify({
            "success": False,
            "error": "Unauthorized"
        }), 401

    data = request.get_json(silent=True) or {}

    message = str(data.get("message", "")).strip()
    history = data.get("history", [])

    if not message:
        return jsonify({
            "success": False,
            "error": "Message is required"
        }), 400

    messages = [{"role": "system", "content": ADMIN_PROMPT}]

    for item in history[-10:]:
        if item.get("role") in ("user", "assistant"):
            messages.append({
                "role": item["role"],
                "content": str(item.get("content", ""))[:4000]
            })

    messages.append({
        "role": "user",
        "content": message[:4000]
    })

    result = generate_response(messages)

    if not result["success"]:
        return jsonify(result), 503

    return jsonify(result)


@ai_bp.route("/student/chat", methods=["POST"])
def student_chat():

    # TODO: Replace with your actual student authentication check.
    if not session.get("student_id"):
        return jsonify({
            "success": False,
            "error": "Unauthorized"
        }), 401

    data = request.get_json(silent=True) or {}

    message = str(data.get("message", "")).strip()
    history = data.get("history", [])

    if not message:
        return jsonify({
            "success": False,
            "error": "Message is required"
        }), 400

    messages = [{"role": "system", "content": STUDENT_PROMPT}]

    for item in history[-10:]:
        if item.get("role") in ("user", "assistant"):
            messages.append({
                "role": item["role"],
                "content": str(item.get("content", ""))[:4000]
            })

    messages.append({
        "role": "user",
        "content": message[:4000]
    })

    result = generate_response(messages)

    if not result["success"]:
        return jsonify(result), 503

    return jsonify(result)