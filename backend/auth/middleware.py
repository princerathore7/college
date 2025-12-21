from functools import wraps
from flask import request, jsonify
import jwt
import os

JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey")


def mentor_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return jsonify(success=False, message="Token missing"), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            if data.get("role") != "mentor":
                return jsonify(success=False, message="Mentor access required"), 403
        except Exception:
            return jsonify(success=False, message="Invalid token"), 401

        return f(data, *args, **kwargs)

    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return jsonify(success=False, message="Token missing"), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            if data.get("role") != "admin":
                return jsonify(success=False, message="Admin access required"), 403
        except Exception:
            return jsonify(success=False, message="Invalid token"), 401

        return f(*args, **kwargs)

    return wrapper
