from flask import Blueprint, request, jsonify
from db import db

student_profile_bp = Blueprint(
    "student_profile_bp",
    __name__,
    url_prefix="/api/student-profile"
)


@student_profile_bp.route("/<enrollment>", methods=["GET"])
def get_student_profile(enrollment):

    try:
        enrollment = enrollment.strip()

        if not enrollment:
            return jsonify({
                "success": False,
                "message": "Enrollment number is required"
            }), 400

        # =====================================================
        # 1. FIND STUDENT
        # =====================================================

        student = db.students.find_one({
            "enrollment": enrollment
        })

        if not student:
            return jsonify({
                "success": False,
                "message": "Student not found"
            }), 404

        # =====================================================
        # 2. STUDENT NAME
        # =====================================================

        student_name = (
            student.get("name")
            or student.get("fullName")
            or student.get("studentName")
            or ""
        )

        # =====================================================
        # 3. FINE INFORMATION
        # =====================================================

        fine = db.fines.find_one({
            "enrollment": enrollment
        })

        current_fine = 0
        fine_reason = "No fine"

        if fine:
            current_fine = fine.get(
                "currentFine",
                fine.get(
                    "amount",
                    fine.get("fineAmount", 0)
                )
            )

            fine_reason = fine.get(
                "reason",
                fine.get(
                    "fineReason",
                    "No reason provided"
                )
            )

        # =====================================================
        # 4. ATTENDANCE
        # =====================================================

        attendance_records = list(
            db.attendance.find({
                "enrollment": enrollment
            })
        )

        total_classes = 0
        attended_classes = 0

        for record in attendance_records:

            # Different possible field names
            total_classes += record.get(
                "totalClasses",
                record.get("total", 0)
            )

            attended_classes += record.get(
                "present",
                record.get(
                    "presentClasses",
                    record.get("attended", 0)
                )
            )

        if total_classes > 0:
            attendance_percentage = round(
                (attended_classes / total_classes) * 100,
                2
            )
        else:
            attendance_percentage = 0

        # =====================================================
        # 5. ASSIGNMENTS
        # =====================================================

        assignments = list(
            db.assignments.find({
                "enrollment": enrollment
            })
        )

        total_assignments = len(assignments)
        submitted_assignments = 0

        for assignment in assignments:

            status = str(
                assignment.get("status", "")
            ).lower()

            submitted = assignment.get(
                "submitted",
                assignment.get(
                    "isSubmitted",
                    False
                )
            )

            if submitted or status in [
                "submitted",
                "complete",
                "completed"
            ]:
                submitted_assignments += 1

        pending_assignments = (
            total_assignments - submitted_assignments
        )

        # =====================================================
        # 6. REWARDS
        # =====================================================

        reward = db.rewards.find_one({
            "enrollment": enrollment
        })

        rewards = 0

        if reward:
            rewards = reward.get(
                "rewards",
                reward.get(
                    "points",
                    reward.get("rewardPoints", 0)
                )
            )

        # =====================================================
        # 7. FINAL RESPONSE
        # =====================================================

        return jsonify({
            "success": True,

            "student": {
                "enrollment": enrollment,
                "name": student_name,

                "fine": {
                    "amount": current_fine,
                    "reason": fine_reason
                },

                "attendance": {
                    "percentage": attendance_percentage,
                    "attendedClasses": attended_classes,
                    "totalClasses": total_classes
                },

                "assignments": {
                    "total": total_assignments,
                    "submitted": submitted_assignments,
                    "pending": pending_assignments
                },

                "rewards": rewards
            }
        }), 200

    except Exception as e:

        print(
            "Student profile error:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "Internal server error",
            "error": str(e)
        }), 500