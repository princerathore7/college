from flask import Blueprint, request, jsonify, session
from .ollama_engine import generate_response

ai_bp = Blueprint("ai_bp", __name__, url_prefix="/api/ai")


MENTOR_PROMPT = """
You are the College Management System AI Assistant for mentors.

You can communicate in Hindi and English.

You help mentors understand their college website and its features.

Rules:
1. Answer clearly and helpfully.
2. Never invent website functionality.
3. If information is unavailable, say so.
4. Never claim that you performed an operation.
5. Do not pretend to have accessed the database.
6. Never reveal another mentor's private information.
7. You are currently in CHAT MODE.
"""


STUDENT_PROMPT = """
You are the Student AI Assistant of a College Management System.

You can communicate in Hindi and English.

Rules:
1. Give clear and friendly answers.
2. Never invent college policies or website features.
3. Do not reveal another student's private information.
4. If you do not know an answer, clearly say so.
5. You cannot perform administrative operations.
"""


def process_ai_message(prompt, data):

    message = str(data.get("message", "")).strip()
    history = data.get("history", [])

    if not message:
        return jsonify({
            "success": False,
            "error": "Message is required"
        }), 400

    if not isinstance(history, list):
        history = []

    messages = [
        {
            "role": "system",
            "content": prompt
        }
    ]

    for item in history[-10:]:

        if not isinstance(item, dict):
            continue

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

    if not result.get("success"):
        return jsonify(result), 503

    return jsonify(result), 200


# ============================================================
# MENTOR AI CHAT
# ============================================================

@ai_bp.route("/admin/chat", methods=["POST"])
@ai_bp.route("/mentor/chat", methods=["POST"])
def mentor_chat():

    try:
        data = request.get_json(silent=True) or {}

        mentor_id = data.get("mentor_id")

        if not mentor_id:
            return jsonify({
                "success": False,
                "error": "Mentor ID not found"
            }), 401

        return process_ai_message(MENTOR_PROMPT, data)

    except Exception as e:

        print("MENTOR AI ERROR:", repr(e))

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
# ============================================================
# STUDENT AI CHAT
# ============================================================

@ai_bp.route("/student/chat", methods=["POST"])
def student_chat():

    student_id = session.get("student_id")

    if not student_id:
        return jsonify({
            "success": False,
            "error": "Student login required"
        }), 401

    data = request.get_json(silent=True) or {}

    return process_ai_message(STUDENT_PROMPT, data)
