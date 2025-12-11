from flask import Blueprint, request, jsonify
from pymongo import MongoClient

classes_bp = Blueprint("classes_bp", __name__, url_prefix="/api/classes")

# Enable CORS for this entire blueprint
CORS(classes_bp)
# MongoDB connection
client = MongoClient("mongodb://localhost:27017/")
db = client["college"]  # Database name

# Branches, Years, Sections
BRANCHES = ["CSE", "IT", "ECE", "AIML", "AIDS", "ME", "EX", "CIVIL"]
YEARS = ["1", "2", "3", "4", "5"]  # 1st to 5th year
SECTIONS = ["A", "B", "C"]

# ----------------- GET all created class-sections -----------------
@classes_bp.route("/", methods=["GET"])
def get_all_class_sections():
    try:
        class_sections = []
        for branch in BRANCHES:
            for year in YEARS:
                for sec in SECTIONS:
                    coll_name = f"{branch}{year}_{sec}"
                    if coll_name in db.list_collection_names():
                        class_sections.append({"name": f"{branch}{year}-{sec}"})
        return jsonify({"success": True, "classes": class_sections}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ----------------- POST create a new class-section -----------------
@classes_bp.route("/", methods=["POST"])
def create_class_section():
    try:
        data = request.get_json()
        branch = data.get("branch")   # ex: "CSE"
        year = data.get("year")       # ex: "1"
        section = data.get("section") # ex: "A"

        if not branch or not year or not section:
            return jsonify({"success": False, "message": "Branch, year, and section required"}), 400

        coll_name = f"{branch}{year}_{section}"
        if coll_name in db.list_collection_names():
            return jsonify({"success": False, "message": "Class-section already exists"}), 409

        db[coll_name].insert_one({"_init": True})  # create collection with dummy doc
        return jsonify({"success": True, "message": f"Class-section {branch}{year}-{section} created"}), 201

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
