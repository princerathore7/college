from flask import Blueprint, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta
import os

# ---------------- BLUEPRINT ----------------

cleanup_bp = Blueprint(
    "cleanup_bp",
    __name__,
    url_prefix="/api/cleanup"
)

CORS(cleanup_bp)

# ---------------- MONGODB ----------------

MONGO_URL = os.getenv("MONGO_URL")

client = MongoClient(MONGO_URL)

db = client["acropolis_db"]

pending_collection = db["pending_verifications"]

done_collection = db["done_verifications"]

verified_collection = db["verified_students"]

# ---------------- AUTO CLEANUP FUNCTION ----------------

def delete_old_data():

    six_days_ago = datetime.utcnow() - timedelta(days=6)

    # ---------------- DELETE OLD PENDING ----------------

    pending_result = pending_collection.delete_many({
        "createdAt": {
            "$lt": six_days_ago
        }
    })

    # ---------------- DELETE OLD DONE ----------------

    done_result = done_collection.delete_many({
        "doneAt": {
            "$lt": six_days_ago
        }
    })

    return {

        "pendingDeleted": pending_result.deleted_count,
        "doneDeleted": done_result.deleted_count

    }

# ---------------- MANUAL CLEANUP ROUTE ----------------

@cleanup_bp.route("/delete-old-data", methods=["DELETE"])
def cleanup_old_data():

    try:

        result = delete_old_data()

        return jsonify({

            "success": True,

            "message": "Old verification data cleaned successfully",

            "deleted": result

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ---------------- DATABASE STATUS ROUTE ----------------

@cleanup_bp.route("/database-status", methods=["GET"])
def database_status():

    try:

        pending_count = pending_collection.count_documents({})

        done_count = done_collection.count_documents({})

        verified_count = verified_collection.count_documents({})

        return jsonify({

            "success": True,

            "database": {

                "pendingRequests": pending_count,

                "doneRequests": done_count,

                "verifiedStudents": verified_count

            }

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ---------------- FORCE DELETE ALL PENDING ----------------

@cleanup_bp.route("/delete-all-pending", methods=["DELETE"])
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


# ---------------- FORCE DELETE ALL DONE ----------------

@cleanup_bp.route("/delete-all-done", methods=["DELETE"])
def delete_all_done():

    try:

        result = done_collection.delete_many({})

        return jsonify({

            "success": True,

            "message": "All done verification records deleted",

            "deletedCount": result.deleted_count

        }), 200

    except Exception as e:

        return jsonify({

            "success": False,
            "message": str(e)

        }), 500