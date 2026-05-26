from flask import Blueprint, jsonify
from flask_cors import CORS
from db import db
from datetime import datetime, timedelta

# ---------------- BLUEPRINT ----------------
verification_bp = Blueprint(
    "verification_bp",
    __name__,
    url_prefix="/api/verification"
)

CORS(verification_bp)

# ---------------- DATABASE ----------------
pending_collection = db["pending_verifications"]
verified_collection = db["verified_students"]

# =====================================================
# AUTO CLEANUP FUNCTION
# =====================================================

def delete_old_data():

    six_days_ago = datetime.utcnow() - timedelta(days=6)

    # Delete old pending requests
    pending_result = pending_collection.delete_many({
        "createdAt": {"$lt": six_days_ago}
    })

    # Delete old verified students
    verified_result = verified_collection.delete_many({
        "verifiedAt": {"$lt": six_days_ago}
    })

    return {
        "pendingDeleted": pending_result.deleted_count,
        "verifiedDeleted": verified_result.deleted_count
    }

# =====================================================
# MANUAL CLEANUP ROUTE
# =====================================================

@verification_bp.route("/delete-old-data", methods=["DELETE"])
def cleanup_old_data():

    try:
        result = delete_old_data()

        return jsonify({
            "success": True,
            "message": "Old data cleaned successfully",
            "deleted": result
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =====================================================
# DATABASE STATUS ROUTE
# =====================================================

@verification_bp.route("/database-status", methods=["GET"])
def database_status():

    try:
        pending_count = pending_collection.count_documents({})
        verified_count = verified_collection.count_documents({})

        return jsonify({
            "success": True,
            "database": {
                "pendingRequests": pending_count,
                "verifiedStudents": verified_count
            }
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =====================================================
# GET ALL VERIFIED STUDENTS
# =====================================================

@verification_bp.route("/verified-students", methods=["GET"])
def get_verified_students():

    try:

        students = list(
            verified_collection.find({}, {"_id": 0}).sort("verifiedAt", -1)
        )

        return jsonify({
            "success": True,
            "count": len(students),
            "students": students
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =====================================================
# DELETE ALL PENDING
# =====================================================

@verification_bp.route("/delete-all-pending", methods=["DELETE"])
def delete_all_pending():

    try:
        result = pending_collection.delete_many({})

        return jsonify({
            "success": True,
            "message": "All pending verification requests deleted",
            "deletedCount": result.deleted_count
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =====================================================
# DELETE ALL VERIFIED
# =====================================================

@verification_bp.route("/delete-all-verified", methods=["DELETE"])
def delete_all_verified():

    try:
        result = verified_collection.delete_many({})

        return jsonify({
            "success": True,
            "message": "All verified students deleted",
            "deletedCount": result.deleted_count
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500