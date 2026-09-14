from rest_framework import permissions
from apps.accounts.models import UserRole


class CanManageOrViewBloodRequests(permissions.BasePermission):
    """
    Permission class for listing, viewing, and creating blood requests:
    - POST: Restricted to HOSPITAL_STAFF.
    - GET:
      - HOSPITAL_STAFF: View only their own submitted requests.
      - BLOOD_BANK_ADMIN: View requests targeted to their assigned blood bank.
      - SUPER_ADMIN: View all blood requests.
    - Other roles (LAB_TECHNICIAN, DONOR, unauthenticated): Denied.
    """
    message = "You do not have permission to access or submit blood requests."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.method == "POST":
            # Only hospital staff can create blood requests (Super Admin, Blood Bank Admin, Lab Tech, Donor cannot create)
            return request.user.role == UserRole.HOSPITAL_STAFF

        # GET: Hospital Staff, Blood Bank Admin, Super Admin, Donor
        return (
            request.user.role in [UserRole.HOSPITAL_STAFF, UserRole.BLOOD_BANK_ADMIN, UserRole.DONOR]
            or request.user.is_super_admin
        )

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.user.is_super_admin:
            return True

        if request.user.role == UserRole.HOSPITAL_STAFF:
            return obj.hospital_staff_id == request.user.id

        if request.user.role == UserRole.BLOOD_BANK_ADMIN:
            return obj.blood_bank.admin_id == request.user.id

        if request.user.role == UserRole.DONOR:
            from .models import RequestStatus
            return request.method in permissions.SAFE_METHODS and obj.status in [RequestStatus.PENDING, RequestStatus.APPROVED]

        return False


class IsAssignedBankAdminForAction(permissions.BasePermission):
    """
    Permission class for approving and rejecting blood requests:
    - Restricted to BLOOD_BANK_ADMIN assigned to the targeted BloodBank (or SUPER_ADMIN).
    """
    message = "Only the designated Blood Bank Administrator for this facility can approve or reject this request."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        return request.user.role == UserRole.BLOOD_BANK_ADMIN or request.user.is_super_admin

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.user.is_super_admin:
            return True

        if request.user.role == UserRole.BLOOD_BANK_ADMIN:
            return obj.blood_bank.admin_id == request.user.id

        return False
