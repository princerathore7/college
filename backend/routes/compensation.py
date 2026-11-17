from flask import Blueprint, request, jsonify, g, make_response
from db import db
from datetime import datetime
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from functools import wraps
from decimal import Decimal, InvalidOperation
import os
import re
import json


compensation_bp = Blueprint(
    "compensation_bp",
    __name__,
    url_prefix="/api/compensation"
)


# ============================================================
# MONGODB COLLECTIONS
# ============================================================

mentors_col = db.mentors
salary_profiles_col = db.salary_profiles
salary_slips_col = db.salary_slips
salary_templates_col = db.salary_templates


# ============================================================
# COMPANY INFORMATION
# ============================================================

COMPANY = {
    "name": "TaskUs India Private Limited",
    "registeredOffice": (
        "18th & 19th floor, Tower-9, Gigaplex IT Park, MIDC, "
        "Plot No 1 I.T.5, Airoli Knowledge Park Road, "
        "TTC Industrial Area, Airoli, Navi Mumbai, "
        "Maharashtra – 400708, India"
    )
}


# ============================================================
# SALARY SLIP FIELD DEFINITIONS
# ============================================================

ATTENDANCE_FIELDS = [
    "stdDays",
    "workDays",
    "lopDays",
    "previousLopDays",
    "ndHours",
    "utHours",
    "otHours",
    "nationalHolidayPayHours",
    "supplementaryPayHours",
    "publicHolidayPayHours",
    "newJoinerArrearDays",
    "plEncashmentDays",
    "previousOvertimePayHours",
    "previousSupplementaryPayHours",
    "previousUtAndTardinessDeduction",
    "previousPublicHolidayPayHours",
    "previousUtAndTardinessReversalHours",
    "previousNationalHolidayPayHours",
    "managementLevel",
    "lateDeductionHours",
    "previousLateDeductionPayHours",
    "lopReversalDays"
]


EARNING_FIELDS = [
    "BASIC PAY",
    "BASIC PAY ARREAR",
    "HOUSE RENT ALLOWANCE",
    "HOUSE RENT ALLOWANCE ARREAR",
    "BONUS",
    "BONUS ARREAR",
    "OVERTIME PAY",
    "PUBLIC HOLIDAY PAY",
    "SUPPLEMENTARY PAY",
    "UNDERTIME DEDUCTION",
    "LATE DEDUCTIONS",
    "DRIVER_CAR_LEASE_REIMBURSEMENT",
    "DRIVER SALARY REIMBURSEMENT",
    "FUEL_CAR_LEASE_REIMBURSEMENT",
    "LTA REIMBURSEMENT"
]


DEDUCTION_FIELDS = [
    "PROVIDENT FUND",
    "ASSET RECOVERY",
    "EMPLOYEE STATE INSURANCE",
    "LABOUR WELFARE FUND",
    "EMPLOYER NPS DEDUCTION",
    "TELEPHONE REIMBURSEMENT DEDUCTION",
    "GYM RECOVERY",
    "DRIVER_CAR_LEASE_REIMBURSEMENT",
    "DRIVER SALARY REIMBURSEMENT",
    "FUEL_CAR_LEASE_REIMBURSEMENT",
    "LTA REIMBURSEMENT",
    "MEDICLAIM DEDUCTION"
]


PROFILE_FIELDS = [
    "pan",
    "uan",
    "pfNumber",
    "esiNumber",
    "dateOfJoining",
    "bankName",
    "accountNumber",
    "ifsc",
    "department",
    "location",
    "employeeCode"
]


# ============================================================
# BASIC HELPERS
# ============================================================

def now():
    return datetime.utcnow()


def clean_document(data):
    if not data:
        return data

    if isinstance(data, list):
        return [clean_document(item) for item in data]

    if isinstance(data, dict):
        result = {}

        for key, value in data.items():
            if key == "_id":
                result[key] = str(value)
            else:
                result[key] = clean_document(value)

        return result

    return data


def error(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def get_json():
    return request.get_json(silent=True) or {}


def valid_month(month):
    return bool(
        isinstance(month, str)
        and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month)
    )


def money(value):
    try:
        result = Decimal(str(value or 0))

        if not result.is_finite():
            raise ValueError("Invalid amount")

        return float(result)

    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid monetary value")


def amount_in_words(amount):
    # Basic Indian currency wording helper.
    # For production, use a tested number-to-words library.
    amount = round(float(amount or 0), 2)

    return f"INR {amount:,.2f} Only"


# ============================================================
# AUTHORIZATION
# ============================================================

def admin_required(func):
    """
    Admin requests must provide:
    X-Admin-Token: value stored in SALARY_ADMIN_TOKEN env variable.

    Do not expose this token in frontend JavaScript.
    Admin actions should be performed through a protected backend.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):

        expected = os.getenv("SALARY_ADMIN_TOKEN")
        supplied = request.headers.get("X-Admin-Token")

        if not expected:
            return error(
                "SALARY_ADMIN_TOKEN is not configured",
                503
            )

        if not supplied or supplied != expected:
            return error("Admin authorization required", 401)

        return func(*args, **kwargs)

    return wrapper


def mentor_required(func):
    """
    Requires existing authentication middleware to populate g.user.

    Expected identity:
    g.user = {
        "mentorId": "...",
        "role": "mentor"
    }

    Never trust mentorId from localStorage or request body.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):

        user = getattr(g, "user", None)

        if not user:
            return error("Login required", 401)

        if user.get("role") != "mentor":
            return error("Mentor access required", 403)

        return func(*args, **kwargs)

    return wrapper


def mentor_can_access(mentor_id):
    user = getattr(g, "user", None)

    return bool(
        user and user.get("mentorId") == mentor_id
    )


# ============================================================
# MENTOR PROFILE LOOKUP
# ============================================================

def get_mentor(mentor_id):

    mentor = mentors_col.find_one({
        "mentorId": mentor_id
    })

    return mentor


def get_employee_profile(mentor_id):

    mentor = get_mentor(mentor_id)

    if not mentor:
        return None

    profile = salary_profiles_col.find_one({
        "mentorId": mentor_id
    }) or {}

    return {
        "mentorId": mentor_id,
        "employeeCode": profile.get(
            "employeeCode",
            mentor.get("mentorId")
        ),
        "name": mentor.get("name", ""),
        "designation": mentor.get("designation", ""),
        "email": mentor.get("email", ""),
        "phone": mentor.get("phone", ""),
        "subject": mentor.get("subject", ""),
        "branch": mentor.get("branch", ""),
        "classAssigned": mentor.get("classAssigned", ""),
        "pan": profile.get("pan", ""),
        "uan": profile.get("uan", ""),
        "pfNumber": profile.get("pfNumber", ""),
        "esiNumber": profile.get("esiNumber", ""),
        "dateOfJoining": profile.get("dateOfJoining", ""),
        "bankName": profile.get("bankName", ""),
        "accountNumber": profile.get("accountNumber", ""),
        "ifsc": profile.get("ifsc", ""),
        "department": profile.get(
            "department",
            mentor.get("branch", "")
        ),
        "location": profile.get("location", "")
    }


# ============================================================
# 1. GET MENTOR INFORMATION BY MENTOR ID
# ============================================================

@compensation_bp.route(
    "/mentor/<mentor_id>",
    methods=["GET"]
)
@admin_required
def compensation_mentor_lookup(mentor_id):

    profile = get_employee_profile(mentor_id)

    if not profile:
        return error("Mentor not found", 404)

    return jsonify({
        "success": True,
        "employee": profile
    })


# ============================================================
# 2. SAVE / UPDATE EMPLOYEE PAYROLL PROFILE
# ============================================================

@compensation_bp.route(
    "/profile/<mentor_id>",
    methods=["GET", "POST"]
)
@admin_required
def salary_profile(mentor_id):

    mentor = get_mentor(mentor_id)

    if not mentor:
        return error("Mentor not found", 404)

    if request.method == "GET":

        profile = get_employee_profile(mentor_id)

        return jsonify({
            "success": True,
            "profile": profile
        })

    data = get_json()

    update_data = {}

    for field in PROFILE_FIELDS:
        if field in data:
            update_data[field] = str(
                data[field] or ""
            ).strip()

    if "pan" in update_data:
        pan = update_data["pan"].upper()

        if pan and not re.fullmatch(
            r"[A-Z]{5}[0-9]{4}[A-Z]",
            pan
        ):
            return error("Invalid PAN format")

        update_data["pan"] = pan

    if not update_data:
        return error("No profile fields provided")

    update_data["mentorId"] = mentor_id
    update_data["updatedAt"] = now()

    salary_profiles_col.update_one(
        {"mentorId": mentor_id},
        {"$set": update_data},
        upsert=True
    )

    return jsonify({
        "success": True,
        "message": "Payroll profile saved successfully",
        "profile": get_employee_profile(mentor_id)
    })


# ============================================================
# 3. SALARY CALCULATION
# ============================================================

def calculate_salary(data):

    earnings = data.get("earnings", [])
    deductions = data.get("deductions", [])

    if not isinstance(earnings, list):
        raise ValueError("Earnings must be a list")

    if not isinstance(deductions, list):
        raise ValueError("Deductions must be a list")

    clean_earnings = []
    clean_deductions = []

    gross_earnings = 0
    gross_deductions = 0

    for row in earnings:

        if not isinstance(row, dict):
            raise ValueError("Invalid earning row")

        name = str(row.get("name", "")).strip()

        if not name:
            raise ValueError("Earning name is required")

        master_amount = money(row.get("masterAmount", 0))
        amount = money(row.get("amount", 0))
        ytd = money(row.get("ytd", 0))

        clean_earnings.append({
            "name": name,
            "masterAmount": master_amount,
            "amount": amount,
            "ytd": ytd
        })

        gross_earnings += amount

    for row in deductions:

        if not isinstance(row, dict):
            raise ValueError("Invalid deduction row")

        name = str(row.get("name", "")).strip()

        if not name:
            raise ValueError("Deduction name is required")

        amount = money(row.get("amount", 0))
        ytd = money(row.get("ytd", 0))

        clean_deductions.append({
            "name": name,
            "amount": amount,
            "ytd": ytd
        })

        gross_deductions += amount

    net_transfer = gross_earnings - gross_deductions

    return {
        "earnings": clean_earnings,
        "deductions": clean_deductions,
        "grossEarnings": round(gross_earnings, 2),
        "grossDeductions": round(gross_deductions, 2),
        "netTransfer": round(net_transfer, 2),
        "amountInWords": amount_in_words(net_transfer)
    }


# ============================================================
# 4. BUILD COMPLETE SALARY SLIP
# ============================================================

def build_salary_slip(mentor_id, month, data):

    if not valid_month(month):
        raise ValueError("Month must be YYYY-MM")

    employee = get_employee_profile(mentor_id)

    if not employee:
        raise ValueError(
            f"Mentor {mentor_id} does not exist"
        )

    calculated = calculate_salary(data)

    attendance = data.get("attendance", {})

    if not isinstance(attendance, dict):
        raise ValueError("Attendance must be an object")

    clean_attendance = {}

    for field in ATTENDANCE_FIELDS:
        clean_attendance[field] = attendance.get(field, 0)

    slip = {
        "company": COMPANY,

        "mentorId": mentor_id,

        "month": month,
        "year": int(month[:4]),

        "employee": employee,

        "attendance": clean_attendance,

        "earnings": calculated["earnings"],
        "deductions": calculated["deductions"],

        "grossEarnings": calculated["grossEarnings"],
        "grossDeductions": calculated["grossDeductions"],

        "netTransfer": calculated["netTransfer"],

        "amountInWords": calculated["amountInWords"],

        "status": data.get("status", "generated"),

        "createdAt": now(),
        "updatedAt": now()
    }

    return slip


# ============================================================
# 5. CREATE INDIVIDUAL MONTHLY SALARY SLIP
# ============================================================

@compensation_bp.route(
    "/slip",
    methods=["POST"]
)
@admin_required
def create_salary_slip():

    data = get_json()

    mentor_id = data.get("mentorId")
    month = data.get("month")

    if not mentor_id or not month:
        return error("mentorId and month are required")

    try:
        slip = build_salary_slip(
            mentor_id,
            month,
            data
        )

        slip["createdBy"] = "admin"

        salary_slips_col.insert_one(slip)

        return jsonify({
            "success": True,
            "message": "Salary slip created successfully",
            "slip": clean_document(slip)
        }), 201

    except DuplicateKeyError:
        return error(
            "Salary slip already exists for this month",
            409
        )

    except ValueError as exc:
        return error(str(exc))

    except Exception as exc:
        print("Salary creation error:", exc)
        return error("Unable to create salary slip", 500)


# ============================================================
# 6. BULK SALARY DISTRIBUTION
# ============================================================

@compensation_bp.route(
    "/bulk",
    methods=["POST"]
)
@admin_required
def bulk_salary_distribution():

    data = get_json()

    mentor_ids = data.get("mentorIds", [])
    month = data.get("month")

    if not isinstance(mentor_ids, list) or not mentor_ids:
        return error("mentorIds list is required")

    if not valid_month(month):
        return error("Valid month is required: YYYY-MM")

    results = {
        "created": [],
        "failed": []
    }

    for mentor_id in mentor_ids:

        try:
            slip = build_salary_slip(
                mentor_id,
                month,
                data
            )

            slip["createdBy"] = "admin"

            salary_slips_col.insert_one(slip)

            results["created"].append(mentor_id)

        except DuplicateKeyError:

            results["failed"].append({
                "mentorId": mentor_id,
                "reason": "Salary already exists"
            })

        except Exception as exc:

            results["failed"].append({
                "mentorId": mentor_id,
                "reason": str(exc)
            })

    return jsonify({
        "success": True,
        "message": "Bulk salary processing completed",
        "results": results
    })


# ============================================================
# 7. FIXED SALARY BULK DISTRIBUTION
# ============================================================

@compensation_bp.route(
    "/bulk-fixed",
    methods=["POST"]
)
@admin_required
def bulk_fixed_salary():

    data = get_json()

    mentor_ids = data.get("mentorIds", [])
    month = data.get("month")

    try:
        fixed_amount = money(data.get("fixedAmount"))
    except ValueError as exc:
        return error(str(exc))

    if fixed_amount < 0:
        return error("Salary cannot be negative")

    if not isinstance(mentor_ids, list) or not mentor_ids:
        return error("mentorIds list is required")

    if not valid_month(month):
        return error("Valid month is required")

    # Common fixed salary template.
    template = data.get("template", {})

    earnings = template.get("earnings", [])

    if not earnings:
        earnings = [{
            "name": "BASIC PAY",
            "masterAmount": fixed_amount,
            "amount": fixed_amount,
            "ytd": 0
        }]
    else:
        # The fixed amount becomes the BASIC PAY amount.
        found_basic = False

        for row in earnings:
            if row.get("name", "").upper() == "BASIC PAY":
                row["masterAmount"] = fixed_amount
                row["amount"] = fixed_amount
                found_basic = True
                break

        if not found_basic:
            earnings.append({
                "name": "BASIC PAY",
                "masterAmount": fixed_amount,
                "amount": fixed_amount,
                "ytd": 0
            })

    common_data = {
        "month": month,
        "attendance": template.get("attendance", {}),
        "earnings": earnings,
        "deductions": template.get("deductions", []),
        "status": template.get("status", "generated")
    }

    results = {
        "created": [],
        "failed": []
    }

    for mentor_id in mentor_ids:

        try:
            slip = build_salary_slip(
                mentor_id,
                month,
                common_data
            )

            slip["fixedSalary"] = fixed_amount
            slip["createdBy"] = "admin"

            salary_slips_col.insert_one(slip)

            results["created"].append(mentor_id)

        except DuplicateKeyError:

            results["failed"].append({
                "mentorId": mentor_id,
                "reason": "Salary already exists"
            })

        except Exception as exc:

            results["failed"].append({
                "mentorId": mentor_id,
                "reason": str(exc)
            })

    return jsonify({
        "success": True,
        "message": "Fixed salary distribution completed",
        "results": results
    })


# ============================================================
# 8. GET INDIVIDUAL SALARY SLIP
# ============================================================

@compensation_bp.route(
    "/slip/<mentor_id>/<month>",
    methods=["GET"]
)
def get_salary_slip(mentor_id, month):

    user = getattr(g, "user", None)

    if not user:
        return error("Login required", 401)

    if user.get("role") == "admin":

        expected = os.getenv("SALARY_ADMIN_TOKEN")
        supplied = request.headers.get("X-Admin-Token")

        if not expected or supplied != expected:
            return error("Admin authorization required", 401)

    elif user.get("role") == "mentor":

        if not mentor_can_access(mentor_id):
            return error("Access denied", 403)

    else:
        return error("Access denied", 403)

    slip = salary_slips_col.find_one({
        "mentorId": mentor_id,
        "month": month
    })

    if not slip:
        return error("Salary slip not found", 404)

    slip = clean_document(slip)

    response = jsonify({
        "success": True,
        "slip": slip
    })

    # JSON attachment download.
    if request.args.get("download") == "1":

        response.headers["Content-Disposition"] = (
            f'attachment; filename="Salary_{mentor_id}_{month}.json"'
        )

    return response


# ============================================================
# 9. MONTHLY SALARY HISTORY
# ============================================================

@compensation_bp.route(
    "/history/<mentor_id>",
    methods=["GET"]
)
def salary_history(mentor_id):

    user = getattr(g, "user", None)

    if not user:
        return error("Login required", 401)

    if user.get("role") == "admin":

        expected = os.getenv("SALARY_ADMIN_TOKEN")
        supplied = request.headers.get("X-Admin-Token")

        if not expected or supplied != expected:
            return error("Admin authorization required", 401)

    elif user.get("role") == "mentor":

        if not mentor_can_access(mentor_id):
            return error("Access denied", 403)

    else:
        return error("Access denied", 403)

    slips = list(
        salary_slips_col.find(
            {"mentorId": mentor_id},
            {
                "mentorId": 1,
                "month": 1,
                "year": 1,
                "grossEarnings": 1,
                "grossDeductions": 1,
                "netTransfer": 1,
                "status": 1,
                "createdAt": 1
            }
        ).sort("month", -1)
    )

    return jsonify({
        "success": True,
        "mentorId": mentor_id,
        "totalSlips": len(slips),
        "history": clean_document(slips)
    })


# ============================================================
# 10. ADMIN: GET ALL SALARY SLIPS FOR A MONTH
# ============================================================

@compensation_bp.route(
    "/month/<month>",
    methods=["GET"]
)
@admin_required
def get_monthly_salary_records(month):

    if not valid_month(month):
        return error("Invalid month format")

    slips = list(
        salary_slips_col.find({
            "month": month
        }).sort("employee.name", 1)
    )

    return jsonify({
        "success": True,
        "month": month,
        "total": len(slips),
        "slips": clean_document(slips)
    })


# ============================================================
# 11. UPDATE EXISTING SALARY SLIP
# ============================================================

@compensation_bp.route(
    "/slip/<mentor_id>/<month>",
    methods=["PUT"]
)
@admin_required
def update_salary_slip(mentor_id, month):

    data = get_json()

    existing = salary_slips_col.find_one({
        "mentorId": mentor_id,
        "month": month
    })

    if not existing:
        return error("Salary slip not found", 404)

    try:
        updated = build_salary_slip(
            mentor_id,
            month,
            data
        )

        updated["createdAt"] = existing.get("createdAt")
        updated["updatedAt"] = now()
        updated["createdBy"] = existing.get("createdBy", "admin")

        salary_slips_col.replace_one(
            {"_id": existing["_id"]},
            updated
        )

        return jsonify({
            "success": True,
            "message": "Salary slip updated successfully",
            "slip": clean_document(updated)
        })

    except ValueError as exc:
        return error(str(exc))


# ============================================================
# 12. DELETE SALARY SLIP
# ============================================================

@compensation_bp.route(
    "/slip/<mentor_id>/<month>",
    methods=["DELETE"]
)
@admin_required
def delete_salary_slip(mentor_id, month):

    result = salary_slips_col.delete_one({
        "mentorId": mentor_id,
        "month": month
    })

    if result.deleted_count == 0:
        return error("Salary slip not found", 404)

    return jsonify({
        "success": True,
        "message": "Salary slip deleted successfully"
    })


# ============================================================
# 13. DELETE ALL COMPENSATION DATA OF A MENTOR
# ============================================================

def delete_mentor_compensation(mentor_id):
    """
    Import and call this helper from the existing mentor
    deletion route BEFORE deleting the mentor account.
    """

    profiles_deleted = salary_profiles_col.delete_many({
        "mentorId": mentor_id
    })

    slips_deleted = salary_slips_col.delete_many({
        "mentorId": mentor_id
    })

    return {
        "profilesDeleted": profiles_deleted.deleted_count,
        "salarySlipsDeleted": slips_deleted.deleted_count
    }


# ============================================================
# 14. SAVE COMMON SALARY TEMPLATE
# ============================================================

@compensation_bp.route(
    "/template",
    methods=["POST"]
)
@admin_required
def save_salary_template():

    data = get_json()

    template_name = str(
        data.get("templateName", "")
    ).strip()

    if not template_name:
        return error("Template name is required")

    template = {
        "templateName": template_name,
        "attendance": data.get("attendance", {}),
        "earnings": data.get("earnings", []),
        "deductions": data.get("deductions", []),
        "updatedAt": now()
    }

    salary_templates_col.update_one(
        {"templateName": template_name},
        {
            "$set": template,
            "$setOnInsert": {
                "createdAt": now()
            }
        },
        upsert=True
    )

    return jsonify({
        "success": True,
        "message": "Salary template saved successfully"
    })


# ============================================================
# 15. GET SAVED SALARY TEMPLATES
# ============================================================

@compensation_bp.route(
    "/templates",
    methods=["GET"]
)
@admin_required
def get_salary_templates():

    templates = list(
        salary_templates_col.find({}).sort(
            "updatedAt",
            -1
        )
    )

    return jsonify({
        "success": True,
        "templates": clean_document(templates)
    })


# ============================================================
# 16. INITIALIZE DATABASE INDEXES
# ============================================================

def initialize_compensation_indexes():

    # One salary slip per mentor per month.
    salary_slips_col.create_index(
        [
            ("mentorId", 1),
            ("month", 1)
        ],
        unique=True,
        name="unique_mentor_month_salary"
    )

    salary_profiles_col.create_index(
        "mentorId",
        unique=True,
        name="unique_salary_profile_mentor"
    )

    salary_templates_col.create_index(
        "templateName",
        unique=True,
        name="unique_salary_template_name"
    )


try:
    initialize_compensation_indexes()
    print("Compensation indexes initialized")

except Exception as exc:
    print("Compensation index initialization error:", exc)