from rest_framework import permissions

from apps.accounts.models import UserRole


class CanTriggerSOS(permissions.BasePermission):
    """
    Permission allowing Hospital Staff (who created the blood request) or Super Administrators
    to trigger an emergency SOS broadcast.
    """
    message = "Only authorized Hospital Staff who submitted the request or Super Administrators may trigger an Emergency SOS."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                request.user.role in (UserRole.HOSPITAL_STAFF, UserRole.SUPER_ADMIN)
                or request.user.is_superuser
            )
        )

    def has_object_permission(self, request, view, obj):
        # obj can be a BloodRequest or an object with a blood_request attribute
        blood_request = obj if hasattr(obj, "hospital_staff") else getattr(obj, "blood_request", None)
        if not blood_request:
            return False

        if request.user.is_superuser or request.user.role == UserRole.SUPER_ADMIN:
            return True

        if request.user.role == UserRole.HOSPITAL_STAFF:
            return blood_request.hospital_staff_id == request.user.id

        return False


class CanManageSOSBroadcast(permissions.BasePermission):
    """
    Permission allowing authorized Hospital Staff (request owners), Blood Bank Admins (managing the bank),
    and Super Administrators to view or cancel an SOS Broadcast.
    """
    message = "You do not have permission to view or manage this Emergency SOS Broadcast."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                request.user.role in (UserRole.HOSPITAL_STAFF, UserRole.BLOOD_BANK_ADMIN, UserRole.SUPER_ADMIN)
                or request.user.is_superuser
            )
        )

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.role == UserRole.SUPER_ADMIN:
            return True

        blood_request = obj if hasattr(obj, "hospital_staff") else getattr(obj, "blood_request", None)
        if not blood_request:
            return False

        # Check hospital staff ownership
        if request.user.role == UserRole.HOSPITAL_STAFF:
            return (
                getattr(obj, "triggered_by_id", None) == request.user.id
                or blood_request.hospital_staff_id == request.user.id
            )

        # Check blood bank admin ownership
        if request.user.role == UserRole.BLOOD_BANK_ADMIN:
            return blood_request.blood_bank.admin_id == request.user.id

        return False
