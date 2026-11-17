# hierarchy.py

from flask import Blueprint, jsonify, request
from pymongo import MongoClient
from bson import ObjectId
import os
import re

hierarchy_bp = Blueprint(
    "hierarchy",
    __name__,
    url_prefix="/api/authority/hierarchy"
)

# ==========================================
# DATABASE CONFIGURATION
# ==========================================

# Existing MongoDB connection reuse karna preferred hai.
# init_hierarchy() mein existing database pass karna hai.

db = None
mentors_collection = None


def init_hierarchy(database):

    global db, mentors_collection

    db = database

    # Apne existing mentor collection ka naam use karein.
    mentors_collection = db["mentors"]


# ==========================================
# DESIGNATION LEVELS
# ==========================================

DESIGNATION_LEVELS = {

    "board of trustees": 1,
    "chairman": 1,
    "vice chairman": 1,
    "trustee": 1,
    "trustee member": 1,

    "director": 2,
    "executive director": 2,
    "principal": 2,

    "dean": 3,
    "associate dean": 3,
    "academic dean": 3,

    "hod": 4,
    "head of department": 4,
    "associate hod": 4,

    "coordinator": 5,
    "academic coordinator": 5,
    "department coordinator": 5,
    "class coordinator": 5,
    "lab coordinator": 5,

    "professor": 6,
    "associate professor": 6,
    "assistant professor": 6,
    "lecturer": 6,
    "teaching assistant": 6,
    "faculty": 6
}


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def normalize(value):

    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip().lower()
    )


def get_level(designation):

    designation = normalize(designation)

    if designation in DESIGNATION_LEVELS:
        return DESIGNATION_LEVELS[designation]

    # Unknown designations ko automatically
    # faculty category mein force nahi karenge.
    return 99


def serialize_mentor(mentor):

    mentor = dict(mentor)

    mentor["_id"] = str(mentor.get("_id", ""))

    return mentor


def is_active(mentor):

    status = normalize(mentor.get("status", "active"))

    return status not in ["inactive", "suspended", "deleted"]


def get_mentor_id(mentor):

    return str(mentor.get("mentorId", "")).strip()


def get_department(mentor):

    return (
        mentor.get("department")
        or mentor.get("branch")
        or "General Administration"
    )


def get_reports_to(mentor):

    return str(
        mentor.get("reportsTo")
        or mentor.get("reports_to")
        or ""
    ).strip()


# ==========================================
# BUILD ORGANIZATIONAL TREE
# ==========================================

def build_hierarchy(mentors):

    active_mentors = [
        m for m in mentors if is_active(m)
    ]

    nodes = {}

    for mentor in active_mentors:

        mentor_id = get_mentor_id(mentor)

        if not mentor_id:
            continue

        designation = mentor.get("designation", "Not Assigned")

        nodes[mentor_id] = {

            "mentorId": mentor_id,

            "name": mentor.get("name", "Unknown"),

            "designation": designation,

            "department": get_department(mentor),

            "branch": mentor.get("branch", ""),

            "subject": mentor.get("subject", ""),

            "email": mentor.get("email", ""),

            "phone": mentor.get("phone", ""),

            "status": mentor.get("status", "active"),

            "hierarchyLevel": get_level(designation),

            "reportsTo": get_reports_to(mentor),

            "assignmentType": (
                "MANUAL"
                if get_reports_to(mentor)
                else "AUTO"
            ),

            "children": []

        }

    # --------------------------------------
    # MANUAL REPORTING RELATIONSHIPS FIRST
    # --------------------------------------

    roots = []

    attached = set()

    for mentor_id, node in nodes.items():

        parent_id = node["reportsTo"]

        if parent_id and parent_id in nodes and parent_id != mentor_id:

            nodes[parent_id]["children"].append(node)

            attached.add(mentor_id)

    # --------------------------------------
    # AUTOMATIC FALLBACK GROUPING
    # --------------------------------------

    # Jo members manually assigned nahi hain,
    # unko designation aur department ke basis
    # par suitable parent ke under group karenge.

    for mentor_id, node in nodes.items():

        if mentor_id in attached:
            continue

        current_level = node["hierarchyLevel"]

        if current_level == 1:
            roots.append(node)
            continue

        department = normalize(node["department"])

        possible_parents = []

        for parent_id, parent in nodes.items():

            if parent_id == mentor_id:
                continue

            if parent["hierarchyLevel"] >= current_level:
                continue

            parent_department = normalize(parent["department"])

            # Department-level matching
            if current_level >= 4:

                if department != parent_department:
                    continue

            possible_parents.append(parent)

        if possible_parents:

            # Nearest higher organizational level
            possible_parents.sort(
                key=lambda p: (
                    current_level - p["hierarchyLevel"],
                    p["mentorId"]
                )
            )

            parent = possible_parents[0]

            parent["children"].append(node)

        else:

            roots.append(node)

    # --------------------------------------
    # SORT TREE
    # --------------------------------------

    def sort_tree(items):

        items.sort(
            key=lambda x: (
                x["hierarchyLevel"],
                x["name"].lower()
            )
        )

        for item in items:
            sort_tree(item["children"])

    sort_tree(roots)

    return roots


# ==========================================
# API 1: COMPLETE HIERARCHY
# ==========================================

@hierarchy_bp.route("", methods=["GET"])
def get_complete_hierarchy():

    try:

        if mentors_collection is None:
            return jsonify({
                "success": False,
                "message": "Database not initialized"
            }), 500

        mentors = list(
            mentors_collection.find({})
        )

        tree = build_hierarchy(mentors)

        return jsonify({

            "success": True,

            "totalPeople": len(mentors),

            "activePeople": sum(
                1 for m in mentors if is_active(m)
            ),

            "hierarchy": tree

        }), 200

    except Exception as e:

        print("HIERARCHY ERROR:", str(e))

        return jsonify({

            "success": False,

            "message": "Unable to generate hierarchy"

        }), 500


# ==========================================
# API 2: ALL PEOPLE
# ==========================================

@hierarchy_bp.route("/people", methods=["GET"])
def get_all_people():

    try:

        if mentors_collection is None:
            return jsonify({
                "success": False,
                "message": "Database not initialized"
            }), 500

        mentors = list(
            mentors_collection.find({})
        )

        people = []

        for mentor in mentors:

            person = serialize_mentor(mentor)

            person["hierarchyLevel"] = get_level(
                person.get("designation", "")
            )

            person["department"] = get_department(person)

            person["reportsTo"] = get_reports_to(person)

            people.append(person)

        people.sort(
            key=lambda x: (
                x["hierarchyLevel"],
                normalize(x.get("name"))
            )
        )

        return jsonify({

            "success": True,

            "total": len(people),

            "people": people

        }), 200

    except Exception as e:

        print("PEOPLE FETCH ERROR:", str(e))

        return jsonify({

            "success": False,

            "message": "Unable to fetch people"

        }), 500


# ==========================================
# API 3: UNASSIGNED PEOPLE
# ==========================================

@hierarchy_bp.route("/unassigned", methods=["GET"])
def get_unassigned_people():

    try:

        if mentors_collection is None:
            return jsonify({
                "success": False,
                "message": "Database not initialized"
            }), 500

        mentors = list(
            mentors_collection.find({})
        )

        unassigned = []

        for mentor in mentors:

            if not is_active(mentor):
                continue

            if not get_reports_to(mentor):

                person = serialize_mentor(mentor)

                person["hierarchyLevel"] = get_level(
                    person.get("designation", "")
                )

                person["department"] = get_department(person)

                unassigned.append(person)

        return jsonify({

            "success": True,

            "total": len(unassigned),

            "people": unassigned

        }), 200

    except Exception as e:

        print("UNASSIGNED FETCH ERROR:", str(e))

        return jsonify({

            "success": False,

            "message": "Unable to fetch unassigned people"

        }), 500