from flask import Blueprint, request, jsonify
from datetime import datetime
from pymongo.errors import DuplicateKeyError
from pymongo import ASCENDING
from bson import ObjectId
from db import db
import copy
import re


# ============================================================
# BLUEPRINT
# ============================================================

compensation_bp = Blueprint(
    "compensation_bp",
    __name__,
    url_prefix="/api/compensation"
)


# ============================================================
# DATABASE COLLECTIONS
# ============================================================

mentors_col = db.mentors

profiles_col = db.salary_profiles

slips_col = db.salary_slips

templates_col = db.salary_templates


# ============================================================
# INDEXES
# ============================================================

try:

    profiles_col.create_index(
        [("mentorId", ASCENDING)],
        unique=True,
        name="unique_salary_profile_mentor"
    )

    slips_col.create_index(
        [
            ("mentorId", ASCENDING),
            ("month", ASCENDING)
        ],
        unique=True,
        name="unique_mentor_month_salary"
    )

    slips_col.create_index(
        [("createdAt", ASCENDING)]
    )

    templates_col.create_index(
        [("templateName", ASCENDING)],
        unique=True,
        name="unique_salary_template_name"
    )

except Exception as e:

    print("COMPENSATION INDEX WARNING:", str(e))


# ============================================================
# HELPERS
# ============================================================

def now():

    return datetime.utcnow()


def clean_id(value):

    return str(value or "").strip()


def clean_month(value):

    value = str(value or "").strip()

    if not re.fullmatch(r"\d{4}-\d{2}", value):

        raise ValueError(
            "Month must be in YYYY-MM format"
        )

    month_number = int(value.split("-")[1])

    if month_number < 1 or month_number > 12:

        raise ValueError("Invalid month")

    return value


def serialize(value):

    if isinstance(value, ObjectId):

        return str(value)

    if isinstance(value, datetime):

        return value.isoformat()

    if isinstance(value, dict):

        return {
            key: serialize(val)
            for key, val in value.items()
        }

    if isinstance(value, list):

        return [
            serialize(item)
            for item in value
        ]

    return value


def success(message, data=None, status=200):

    response = {
        "success": True,
        "message": message
    }

    if data:

        response.update(data)

    return jsonify(serialize(response)), status


def failure(message, status=400):

    return jsonify({
        "success": False,
        "message": message
    }), status


def get_mentor(mentor_id):

    mentor_id = clean_id(mentor_id)

    if not mentor_id:

        return None

    return mentors_col.find_one({
        "mentorId": mentor_id
    })


def get_employee_data(mentor):

    if not mentor:

        return {}

    return {

        "mentorId": mentor.get("mentorId"),

        "name": mentor.get("name", ""),

        "email": mentor.get("email", ""),

        "phone": mentor.get("phone", ""),

        "designation": mentor.get("designation", ""),

        "subject": mentor.get("subject", ""),

        "branch": mentor.get("branch", ""),

        "classAssigned": mentor.get("classAssigned", "")

    }


def calculate_totals(earnings, deductions):

    gross = sum(
        float(item.get("amount", 0) or 0)
        for item in earnings
    )

    total_deductions = sum(
        float(item.get("amount", 0) or 0)
        for item in deductions
    )

    return {

        "grossEarnings": round(gross, 2),

        "totalDeductions": round(
            total_deductions, 2
        ),

        "netTransfer": round(
            gross - total_deductions, 2
        )

    }


def normalize_components(items):

    if not isinstance(items, list):

        raise ValueError(
            "Earnings and deductions must be lists"
        )

    result = []

    for item in items:

        if not isinstance(item, dict):

            raise ValueError(
                "Invalid salary component"
            )

        name = str(
            item.get("name", "")
        ).strip()

        if not name:

            raise ValueError(
                "Salary component name is required"
            )

        amount = float(
            item.get("amount", 0) or 0
        )

        if amount < 0:

            raise ValueError(
                "Salary amount cannot be negative"
            )

        result.append({

            "name": name,

            "amount": round(amount, 2),

            "masterAmount": round(
                float(
                    item.get("masterAmount", amount) or 0
                ), 2
            ),

            "ytd": round(
                float(item.get("ytd", 0) or 0), 2
            )

        })

    return result


def validate_attendance(attendance):

    if not isinstance(attendance, dict):

        raise ValueError(
            "Attendance must be an object"
        )

    result = {}

    for key, value in attendance.items():

        try:

            number = float(value or 0)

        except (TypeError, ValueError):

            raise ValueError(
                f"Invalid attendance value: {key}"
            )

        if number < 0:

            raise ValueError(
                "Attendance values cannot be negative"
            )

        result[str(key)] = number

    return result


def validate_salary_data(data):

    earnings = normalize_components(
        data.get("earnings", [])
    )

    deductions = normalize_components(
        data.get("deductions", [])
    )

    attendance = validate_attendance(
        data.get("attendance", {})
    )

    totals = calculate_totals(
        earnings,
        deductions
    )

    return {

        "earnings": earnings,

        "deductions": deductions,

        "attendance": attendance,

        **totals

    }


# ============================================================
# 1. VALIDATE MENTOR
# ============================================================

@compensation_bp.route(
    "/mentor/<mentor_id>",
    methods=["GET"]
)
def get_mentor_details(mentor_id):

    try:

        mentor = get_mentor(mentor_id)

        if not mentor:

            return failure(
                "Invalid Mentor ID. Employee not found.",
                404
            )

        profile = profiles_col.find_one(
            {"mentorId": clean_id(mentor_id)},
            {"_id": 0}
        )

        employee = get_employee_data(mentor)

        if profile:

            employee.update(profile)

        return success(
            "Mentor found successfully.",
            {
                "employee": employee,
                "profileExists": bool(profile)
            }
        )

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 2. GET COMPENSATION PROFILE
# ============================================================

@compensation_bp.route(
    "/profile/<mentor_id>",
    methods=["GET"]
)
def get_compensation_profile(mentor_id):

    try:

        mentor = get_mentor(mentor_id)

        if not mentor:

            return failure(
                "Invalid Mentor ID",
                404
            )

        profile = profiles_col.find_one({
            "mentorId": clean_id(mentor_id)
        })

        if not profile:

            return success(
                "No compensation profile found.",
                {
                    "profile": {},
                    "employee": get_employee_data(mentor)
                }
            )

        profile.pop("_id", None)

        return success(
            "Compensation profile fetched.",
            {
                "profile": profile,
                "employee": get_employee_data(mentor)
            }
        )

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 3. CREATE / UPDATE COMPENSATION PROFILE
# ============================================================

@compensation_bp.route(
    "/profile/<mentor_id>",
    methods=["POST", "PUT"]
)
def save_compensation_profile(mentor_id):

    try:

        mentor_id = clean_id(mentor_id)

        mentor = get_mentor(mentor_id)

        if not mentor:

            return failure(
                "Invalid Mentor ID. Profile cannot be created.",
                404
            )

        data = request.get_json(silent=True) or {}

        allowed_fields = [

            "employeeCode",

            "pan",

            "uan",

            "pfNumber",

            "esiNumber",

            "dateOfJoining",

            "department",

            "location",

            "bankName",

            "accountNumber",

            "ifscCode",

            "accountHolderName",

            "employmentType",

            "grade",

            "costCenter",

            "basicSalary",

            "hra",

            "otherAllowance",

            "monthlyCTC",

            "annualCTC",

            "taxRegime",

            "professionalTax",

            "pfApplicable",

            "esiApplicable",

            "salaryMode",

            "designation",

            "notes"

        ]

        profile_data = {}

        for field in allowed_fields:

            if field in data:

                profile_data[field] = data[field]

        profile_data["mentorId"] = mentor_id

        profile_data["employeeName"] = mentor.get(
            "name", ""
        )

        profile_data["updatedAt"] = now()

        existing = profiles_col.find_one({
            "mentorId": mentor_id
        })

        if existing:

            profiles_col.update_one(
                {"mentorId": mentor_id},
                {
                    "$set": profile_data
                }
            )

            message = "Compensation profile updated."

        else:

            profile_data["createdAt"] = now()

            profiles_col.insert_one(
                profile_data
            )

            message = "Compensation profile created."

        profile = profiles_col.find_one(
            {"mentorId": mentor_id},
            {"_id": 0}
        )

        return success(
            message,
            {"profile": profile}
        )

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 4. ISSUE INDIVIDUAL SALARY SLIP
# ============================================================

@compensation_bp.route(
    "/slip",
    methods=["POST"]
)
def create_salary_slip():

    try:

        data = request.get_json(silent=True) or {}

        mentor_id = clean_id(
            data.get("mentorId")
        )

        if not mentor_id:

            return failure(
                "Mentor ID is required."
            )

        mentor = get_mentor(mentor_id)

        if not mentor:

            return failure(
                "Invalid Mentor ID. Salary slip cannot be issued.",
                404
            )

        month = clean_month(
            data.get("month")
        )

        # Duplicate protection

        existing = slips_col.find_one({

            "mentorId": mentor_id,

            "month": month

        })

        if existing:

            return failure(
                "Salary slip already exists for this mentor and month. Use Edit Salary Slip instead.",
                409
            )

        salary_data = validate_salary_data(data)

        profile = profiles_col.find_one(
            {"mentorId": mentor_id},
            {"_id": 0}
        ) or {}

        employee = get_employee_data(mentor)

        employee.update(profile)

        slip = {

            "mentorId": mentor_id,

            "month": month,

            "employee": employee,

            "attendance": salary_data["attendance"],

            "earnings": salary_data["earnings"],

            "deductions": salary_data["deductions"],

            "grossEarnings": salary_data["grossEarnings"],

            "totalDeductions": salary_data["totalDeductions"],

            "netTransfer": salary_data["netTransfer"],

            "status": data.get(
                "status",
                "issued"
            ),

            "paymentDate": data.get(
                "paymentDate"
            ),

            "paymentMode": data.get(
                "paymentMode",
                "Bank Transfer"
            ),

            "remarks": data.get(
                "remarks",
                ""
            ),

            "createdAt": now(),

            "updatedAt": now()

        }

        result = slips_col.insert_one(slip)

        slip["_id"] = result.inserted_id

        return success(
            "Salary slip issued successfully.",
            {"slip": slip},
            201
        )

    except DuplicateKeyError:

        return failure(
            "Salary slip already exists for this month.",
            409
        )

    except ValueError as e:

        return failure(str(e), 400)

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 5. GET EXISTING SALARY SLIP
# ============================================================

@compensation_bp.route(
    "/slip/<mentor_id>/<month>",
    methods=["GET"]
)
def get_salary_slip(mentor_id, month):

    try:

        mentor_id = clean_id(mentor_id)

        month = clean_month(month)

        mentor = get_mentor(mentor_id)

        if not mentor:

            return failure(
                "Invalid Mentor ID.",
                404
            )

        slip = slips_col.find_one({

            "mentorId": mentor_id,

            "month": month

        })

        if not slip:

            return failure(
                "No salary slip found for this month.",
                404
            )

        return success(
            "Salary slip fetched successfully.",
            {"slip": slip}
        )

    except ValueError as e:

        return failure(str(e), 400)

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 6. EDIT EXISTING SALARY SLIP
# ============================================================

@compensation_bp.route(
    "/slip/<mentor_id>/<month>",
    methods=["PUT"]
)
def update_salary_slip(mentor_id, month):

    try:

        mentor_id = clean_id(mentor_id)

        month = clean_month(month)

        mentor = get_mentor(mentor_id)

        if not mentor:

            return failure(
                "Invalid Mentor ID.",
                404
            )

        existing = slips_col.find_one({

            "mentorId": mentor_id,

            "month": month

        })

        if not existing:

            return failure(
                "Salary slip does not exist. Create it first using the issue salary option.",
                404
            )

        data = request.get_json(silent=True) or {}

        # Prevent changing slip identity through request body.

        if (
            data.get("mentorId")
            and clean_id(data.get("mentorId")) != mentor_id
        ):

            return failure(
                "Mentor ID cannot be changed."
            )

        if (
            data.get("month")
            and clean_month(data.get("month")) != month
        ):

            return failure(
                "Salary month cannot be changed."
            )

        salary_data = validate_salary_data(data)

        update_fields = {

            "attendance": salary_data["attendance"],

            "earnings": salary_data["earnings"],

            "deductions": salary_data["deductions"],

            "grossEarnings": salary_data["grossEarnings"],

            "totalDeductions": salary_data["totalDeductions"],

            "netTransfer": salary_data["netTransfer"],

            "updatedAt": now()

        }

        optional_fields = [

            "status",

            "paymentDate",

            "paymentMode",

            "remarks"

        ]

        for field in optional_fields:

            if field in data:

                update_fields[field] = data[field]

        slips_col.update_one(

            {
                "mentorId": mentor_id,
                "month": month
            },

            {
                "$set": update_fields
            }

        )

        updated_slip = slips_col.find_one({

            "mentorId": mentor_id,

            "month": month

        })

        return success(
            "Existing salary slip updated successfully.",
            {"slip": updated_slip}
        )

    except ValueError as e:

        return failure(str(e), 400)

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 7. BULK SALARY DISTRIBUTION
# ============================================================

@compensation_bp.route(
    "/bulk",
    methods=["POST"]
)
def bulk_salary_distribution():

    try:

        data = request.get_json(silent=True) or {}

        mentor_ids = data.get("mentorIds", [])

        month = clean_month(
            data.get("month")
        )

        if not isinstance(mentor_ids, list) or not mentor_ids:

            return failure(
                "At least one Mentor ID is required."
            )

        results = {

            "created": [],

            "failed": []

        }

        for raw_id in mentor_ids:

            mentor_id = clean_id(raw_id)

            try:

                mentor = get_mentor(mentor_id)

                if not mentor:

                    raise ValueError(
                        "Invalid Mentor ID"
                    )

                existing = slips_col.find_one({

                    "mentorId": mentor_id,

                    "month": month

                })

                if existing:

                    raise ValueError(
                        "Salary slip already exists"
                    )

                profile = profiles_col.find_one(
                    {"mentorId": mentor_id},
                    {"_id": 0}
                ) or {}

                employee = get_employee_data(mentor)

                employee.update(profile)

                salary_data = validate_salary_data(data)

                slip = {

                    "mentorId": mentor_id,

                    "month": month,

                    "employee": employee,

                    **salary_data,

                    "status": data.get(
                        "status",
                        "issued"
                    ),

                    "paymentDate": data.get(
                        "paymentDate"
                    ),

                    "paymentMode": data.get(
                        "paymentMode",
                        "Bank Transfer"
                    ),

                    "remarks": data.get(
                        "remarks",
                        ""
                    ),

                    "createdAt": now(),

                    "updatedAt": now()

                }

                result = slips_col.insert_one(slip)

                results["created"].append({

                    "mentorId": mentor_id,

                    "slipId": str(result.inserted_id)

                })

            except DuplicateKeyError:

                results["failed"].append({

                    "mentorId": mentor_id,

                    "reason": "Salary slip already exists"

                })

            except Exception as e:

                results["failed"].append({

                    "mentorId": mentor_id,

                    "reason": str(e)

                })

        return success(
            "Bulk salary distribution completed.",
            {"results": results}
        )

    except ValueError as e:

        return failure(str(e), 400)

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 8. BULK FIXED SALARY DISTRIBUTION
# ============================================================

@compensation_bp.route(
    "/bulk-fixed",
    methods=["POST"]
)
def bulk_fixed_salary_distribution():

    try:

        data = request.get_json(silent=True) or {}

        mentor_ids = data.get("mentorIds", [])

        month = clean_month(
            data.get("month")
        )

        if not isinstance(mentor_ids, list) or not mentor_ids:

            return failure(
                "Mentor IDs are required."
            )

        template_id = data.get("templateId")

        template = None

        if template_id:

            try:

                template = templates_col.find_one({
                    "_id": ObjectId(template_id)
                })

            except Exception:

                return failure(
                    "Invalid salary template ID."
                )

        if not template:

            template = {

                "earnings": data.get("earnings", []),

                "deductions": data.get("deductions", []),

                "attendance": data.get("attendance", {})

            }

        results = {

            "created": [],

            "failed": []

        }

        for raw_id in mentor_ids:

            mentor_id = clean_id(raw_id)

            try:

                mentor = get_mentor(mentor_id)

                if not mentor:

                    raise ValueError(
                        "Invalid Mentor ID"
                    )

                existing = slips_col.find_one({

                    "mentorId": mentor_id,

                    "month": month

                })

                if existing:

                    raise ValueError(
                        "Salary slip already exists"
                    )

                profile = profiles_col.find_one(
                    {"mentorId": mentor_id},
                    {"_id": 0}
                ) or {}

                employee = get_employee_data(mentor)

                employee.update(profile)

                salary_data = validate_salary_data({

                    "earnings": copy.deepcopy(
                        template.get("earnings", [])
                    ),

                    "deductions": copy.deepcopy(
                        template.get("deductions", [])
                    ),

                    "attendance": copy.deepcopy(
                        data.get(
                            "attendance",
                            template.get("attendance", {})
                        )
                    )

                })

                slip = {

                    "mentorId": mentor_id,

                    "month": month,

                    "employee": employee,

                    **salary_data,

                    "status": data.get(
                        "status",
                        "issued"
                    ),

                    "paymentDate": data.get(
                        "paymentDate"
                    ),

                    "paymentMode": data.get(
                        "paymentMode",
                        "Bank Transfer"
                    ),

                    "remarks": data.get(
                        "remarks",
                        "Fixed salary distribution"
                    ),

                    "createdAt": now(),

                    "updatedAt": now()

                }

                result = slips_col.insert_one(slip)

                results["created"].append({

                    "mentorId": mentor_id,

                    "slipId": str(result.inserted_id)

                })

            except DuplicateKeyError:

                results["failed"].append({

                    "mentorId": mentor_id,

                    "reason": "Salary slip already exists"

                })

            except Exception as e:

                results["failed"].append({

                    "mentorId": mentor_id,

                    "reason": str(e)

                })

        return success(
            "Fixed salary distribution completed.",
            {"results": results}
        )

    except ValueError as e:

        return failure(str(e), 400)

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 9. MONTHLY SALARY HISTORY
# ============================================================

@compensation_bp.route(
    "/history/<mentor_id>",
    methods=["GET"]
)
def salary_history(mentor_id):

    try:

        mentor_id = clean_id(mentor_id)

        mentor = get_mentor(mentor_id)

        if not mentor:

            return failure(
                "Invalid Mentor ID.",
                404
            )

        history = list(

            slips_col.find({

                "mentorId": mentor_id

            }).sort(

                "month",
                -1

            )

        )

        return success(
            "Salary history fetched.",
            {
                "history": history,
                "totalSlips": len(history)
            }
        )

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 10. ALL EMPLOYEE SALARY RECORDS
# ============================================================

@compensation_bp.route(
    "/all",
    methods=["GET"]
)
def all_salary_records():

    try:

        month = request.args.get("month")

        query = {}

        if month:

            month = clean_month(month)

            query["month"] = month

        records = list(

            slips_col.find(
                query
            ).sort(
                "createdAt",
                -1
            )

        )

        return success(
            "Salary records fetched.",
            {
                "records": records,
                "count": len(records)
            }
        )

    except ValueError as e:

        return failure(str(e), 400)

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 11. DELETE SALARY SLIP
# ============================================================

@compensation_bp.route(
    "/slip/<mentor_id>/<month>",
    methods=["DELETE"]
)
def delete_salary_slip(mentor_id, month):

    try:

        mentor_id = clean_id(mentor_id)

        month = clean_month(month)

        result = slips_col.delete_one({

            "mentorId": mentor_id,

            "month": month

        })

        if result.deleted_count == 0:

            return failure(
                "Salary slip not found.",
                404
            )

        return success(
            "Salary slip deleted successfully."
        )

    except ValueError as e:

        return failure(str(e), 400)

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 12. SALARY TEMPLATES
# ============================================================

@compensation_bp.route(
    "/templates",
    methods=["GET", "POST"]
)
def salary_templates():

    try:

        if request.method == "GET":

            templates = list(
                templates_col.find().sort(
                    "createdAt",
                    -1
                )
            )

            return success(
                "Salary templates fetched.",
                {"templates": templates}
            )

        data = request.get_json(silent=True) or {}

        template_name = str(
            data.get("templateName", "")
        ).strip()

        if not template_name:

            return failure(
                "Template name is required."
            )

        template = {

            "templateName": template_name,

            "description": data.get(
                "description",
                ""
            ),

            "earnings": normalize_components(
                data.get("earnings", [])
            ),

            "deductions": normalize_components(
                data.get("deductions", [])
            ),

            "attendance": validate_attendance(
                data.get("attendance", {})
            ),

            "updatedAt": now()

        }

        existing = templates_col.find_one({
            "templateName": template_name
        })

        if existing:

            templates_col.update_one(

                {"_id": existing["_id"]},

                {"$set": template}

            )

            template["_id"] = existing["_id"]

            message = "Salary template updated."

        else:

            template["createdAt"] = now()

            result = templates_col.insert_one(
                template
            )

            template["_id"] = result.inserted_id

            message = "Salary template created."

        return success(
            message,
            {"template": template}
        )

    except DuplicateKeyError:

        return failure(
            "Template already exists.",
            409
        )

    except ValueError as e:

        return failure(str(e), 400)

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 13. DELETE SALARY TEMPLATE
# ============================================================

@compensation_bp.route(
    "/templates/<template_id>",
    methods=["DELETE"]
)
def delete_salary_template(template_id):

    try:

        try:

            object_id = ObjectId(template_id)

        except Exception:

            return failure(
                "Invalid template ID."
            )

        result = templates_col.delete_one({
            "_id": object_id
        })

        if result.deleted_count == 0:

            return failure(
                "Template not found.",
                404
            )

        return success(
            "Salary template deleted."
        )

    except Exception as e:

        return failure(str(e), 500)


# ============================================================
# 14. DELETE MENTOR COMPENSATION DATA
# ============================================================

def delete_mentor_compensation(mentor_id):

    """
    Call this helper when a mentor is deleted.

    Deletes:
    - Compensation profile
    - All monthly salary slips
    """

    mentor_id = clean_id(mentor_id)

    if not mentor_id:

        return False

    profiles_col.delete_many({

        "mentorId": mentor_id

    })

    slips_col.delete_many({

        "mentorId": mentor_id

    })

    return True


# ============================================================
# 15. DELETE COMPENSATION PROFILE
# ============================================================

@compensation_bp.route(
    "/profile/<mentor_id>",
    methods=["DELETE"]
)
def delete_compensation_profile(mentor_id):

    try:

        mentor_id = clean_id(mentor_id)

        result = profiles_col.delete_one({

            "mentorId": mentor_id

        })

        if result.deleted_count == 0:

            return failure(
                "Compensation profile not found.",
                404
            )

        return success(
            "Compensation profile deleted. Salary slips are preserved."
        )

    except Exception as e:

        return failure(str(e), 500)