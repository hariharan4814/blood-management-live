from rest_framework import permissions
from apps.accounts.models import UserRole


class IsSuperAdminOrAssignedBankAdmin(permissions.BasePermission):
    """
    Permission for Blood Bank administrative and operational access:
    - SUPER_ADMIN: Full read/write access to all blood banks.
    - BLOOD_BANK_ADMIN: Read/write access only to their assigned blood bank. Cannot create new blood banks.
    - HOSPITAL_STAFF: Read-only access (GET/HEAD/OPTIONS) to active blood banks for target facility selection.
    - Other roles: Denied access.
    """
    message = "You do not have permission to manage this blood bank."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.user.is_super_admin:
            return True

        if request.user.role == UserRole.BLOOD_BANK_ADMIN:
            # Blood bank admins can view their assigned banks and update them,
            # but cannot create new blood bank entities (SUPER_ADMIN only).
            if request.method == "POST":
                return False
            return True

        if request.user.role == UserRole.HOSPITAL_STAFF:
            # Hospital staff can only view active blood bank facilities to select a target for requests.
            return request.method in permissions.SAFE_METHODS

        return False

    def has_object_permission(self, request, view, obj):
        if request.user.is_super_admin:
            return True

        if request.user.role == UserRole.BLOOD_BANK_ADMIN:
            # Check if obj is BloodBank
            if hasattr(obj, "admin"):
                return obj.admin_id == request.user.id
            # Check if obj is BloodUnit
            if hasattr(obj, "blood_bank"):
                return obj.blood_bank.admin_id == request.user.id

        if request.user.role == UserRole.HOSPITAL_STAFF:
            if request.method in permissions.SAFE_METHODS:
                if hasattr(obj, "is_active"):
                    return bool(obj.is_active)
            return False

        return False


class IsInventoryManagerOrReadOnly(permissions.BasePermission):
    """
    Permission for BloodUnit management:
    - SUPER_ADMIN: Full access.
    - BLOOD_BANK_ADMIN: Full access scoped to their assigned blood bank.
    - LAB_TECHNICIAN: Read-only access (GET/HEAD/OPTIONS) for future test inspection workflows.
    - Other roles: Denied.
    """
    message = "You do not have permission to access or modify blood unit inventory."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.user.is_super_admin:
            return True

        if request.user.role == UserRole.BLOOD_BANK_ADMIN:
            return True

        if request.user.role == UserRole.LAB_TECHNICIAN:
            # Lab technicians get read-only access in this step
            return request.method in permissions.SAFE_METHODS

        return False

    def has_object_permission(self, request, view, obj):
        if request.user.is_super_admin:
            return True

        if request.user.role == UserRole.BLOOD_BANK_ADMIN:
            if hasattr(obj, "blood_bank"):
                return obj.blood_bank.admin_id == request.user.id
            return False

        if request.user.role == UserRole.LAB_TECHNICIAN:
            return request.method in permissions.SAFE_METHODS

        return False


class CanViewInventorySummary(permissions.BasePermission):
    """
    Permission to view computed inventory summary:
    - SUPER_ADMIN: Allowed for all banks.
    - BLOOD_BANK_ADMIN: Allowed for their assigned bank.
    - LAB_TECHNICIAN: Allowed read access.
    """
    message = "You do not have permission to view inventory stock summaries."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        return request.user.is_super_admin or request.user.role in [
            UserRole.BLOOD_BANK_ADMIN,
            UserRole.LAB_TECHNICIAN,
        ]
