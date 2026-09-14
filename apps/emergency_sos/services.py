import logging
from decimal import Decimal
from typing import List, Optional, Tuple
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.blood_requests.models import BloodRequest, RequestStatus, RequestUrgency
from apps.donors.models import Donor
from apps.donors.services import calculate_donor_eligibility
from apps.inventory.models import BloodUnit, BloodUnitStatus
from apps.notifications.email_service import send_notification_email
from apps.notifications.models import Notification, NotificationType
from apps.notifications.services import create_notification

from .compatibility import (
    calculate_haversine_distance_km,
    get_compatible_donor_blood_groups,
    get_all_compatible_donor_blood_groups,
)
from .models import SOSBroadcast, SOSRecipient, SOSStatus

logger = logging.getLogger(__name__)
User = get_user_model()


def check_inventory_shortage(blood_request: BloodRequest) -> Tuple[bool, int, int]:
    """
    Evaluates available, non-expired inventory for the requested blood group
    at the specified target blood bank.

    Returns:
        tuple: (has_shortage: bool, available_count: int, shortage_count: int)
    """
    today = timezone.now().date()
    available_units = BloodUnit.objects.filter(
        blood_bank=blood_request.blood_bank,
        blood_group=blood_request.blood_group,
        status=BloodUnitStatus.AVAILABLE,
        expiry_date__gte=today,
    )
    available_count = available_units.count()
    shortage_count = max(0, blood_request.units_needed - available_count)
    has_shortage = available_count < blood_request.units_needed

    return has_shortage, available_count, shortage_count


from datetime import date


def find_eligible_compatible_donors(
    blood_request: BloodRequest,
    radius_km: Optional[Decimal] = None,
    reference_date: Optional[date] = None,
) -> List[Donor]:
    """
    Finds all active donors who:
    1. Have an ABO/Rh blood group compatible with the requested blood group.
    2. Satisfy medical eligibility (age 18-65, weight >= 50kg, 90-day cooldown).
    3. Fall within geographical distance if radius_km is specified and coordinates exist.

    Returns:
        List of eligible Donor model instances.
    """
    compatible_groups = get_all_compatible_donor_blood_groups(blood_request.blood_group)

    # Query active donor profiles
    candidate_donors = (
        Donor.objects.select_related("user")
        .filter(
            user__is_active=True,
            user__role=UserRole.DONOR,
            blood_group__in=compatible_groups,
        )
        .order_by("id")
    )

    matched_donors = []
    bank = blood_request.blood_bank

    for donor in candidate_donors:
        # Medical eligibility verification
        eligibility = calculate_donor_eligibility(
            date_of_birth=donor.date_of_birth,
            weight_kg=donor.weight_kg,
            last_donation_date=donor.last_donation_date,
            reference_date=reference_date,
        )
        if not eligibility.get("is_eligible", False):
            continue

        # Optional geographical radius filtering
        if radius_km is not None and float(radius_km) > 0:
            if bank.latitude is not None and bank.longitude is not None:
                if donor.latitude is not None and donor.longitude is not None:
                    distance = calculate_haversine_distance_km(
                        donor.latitude,
                        donor.longitude,
                        bank.latitude,
                        bank.longitude,
                    )
                    if distance is not None and distance > float(radius_km):
                        continue

        matched_donors.append(donor)

    return matched_donors


def trigger_sos_broadcast(
    blood_request: BloodRequest,
    triggered_by_user,
    radius_km: Optional[Decimal] = None,
    custom_message: Optional[str] = None,
) -> SOSBroadcast:
    """
    Validates trigger conditions and launches an Emergency SOS broadcast:
    1. Validates blood request status (must be active: PENDING or APPROVED).
    2. Validates clinical urgency (must be CRITICAL).
    3. Validates that an ACTIVE broadcast does not already exist.
    4. Validates legitimate stock shortage.
    5. Dispatches in-app notifications and safe email alerts to matched eligible donors.
    6. Records SOSBroadcast and SOSRecipient audit logs.
    """
    # 1. Validate request status
    if blood_request.status not in (RequestStatus.PENDING, RequestStatus.APPROVED):
        raise ValidationError(
            f"Cannot trigger Emergency SOS for blood request with status '{blood_request.get_status_display()}'."
        )

    # 2. Validate clinical urgency
    if blood_request.urgency != RequestUrgency.CRITICAL:
        raise ValidationError(
            f"Emergency SOS can only be triggered for CRITICAL urgency blood requests (current urgency: '{blood_request.get_urgency_display()}')."
        )

    # 3. Prevent duplicate active broadcasts
    if SOSBroadcast.objects.filter(blood_request=blood_request, status=SOSStatus.ACTIVE).exists():
        raise ValidationError(
            "An ACTIVE Emergency SOS broadcast already exists for this blood request."
        )

    # 4. Validate inventory shortage
    has_shortage, available_count, shortage = check_inventory_shortage(blood_request)
    if not has_shortage:
        raise ValidationError(
            f"Cannot trigger SOS: Target blood bank has sufficient stock "
            f"({available_count} units available for {blood_request.units_needed} units requested)."
        )

    # 5. Identify matching eligible donors
    matched_donors = find_eligible_compatible_donors(blood_request, radius_km=radius_km)

    # 6. Compose broadcast content
    title = f"🚨 EMERGENCY: Critical {blood_request.blood_group} Blood Shortage"
    if custom_message and custom_message.strip():
        message = custom_message.strip()
    else:
        message = (
            f"URGENT: {blood_request.blood_bank.name} has a critical shortage of {blood_request.blood_group} blood "
            f"for emergency blood request #{blood_request.id} ({shortage} unit(s) short). "
            f"Your compatible blood donation is urgently needed. Please contact the blood bank immediately."
        )

    recipients_to_email = []

    # 7. Atomic creation of broadcast, in-app notifications, and audit records
    with transaction.atomic():
        sos_broadcast = SOSBroadcast.objects.create(
            blood_request=blood_request,
            triggered_by=triggered_by_user,
            status=SOSStatus.ACTIVE,
            blood_group=blood_request.blood_group,
            units_needed=blood_request.units_needed,
            available_units_at_trigger=available_count,
            shortage_units=shortage,
            radius_km=radius_km,
            total_donors_targeted=len(matched_donors),
            title=title,
            message=message,
        )

        for donor in matched_donors:
            # Create in-app notification
            notification = create_notification(
                recipient=donor.user,
                title=title,
                message=message,
                notification_type=NotificationType.SOS,
            )

            # Create recipient audit record
            recipient_record = SOSRecipient.objects.create(
                sos_broadcast=sos_broadcast,
                donor=donor,
                user=donor.user,
                notification=notification,
                email_attempted=False,
                email_sent=False,
            )
            recipients_to_email.append((recipient_record, donor))

    # 8. Dispatch emails safely (isolated per recipient so one failure does not affect others)
    for recipient_record, donor in recipients_to_email:
        if donor.user.email:
            recipient_record.email_attempted = True
            email_ctx = {
                "title": title,
                "message": message,
                "blood_group": blood_request.blood_group,
                "donor_blood_group": donor.blood_group,
                "urgency": blood_request.urgency,
                "units_needed": blood_request.units_needed,
                "shortage_units": shortage,
                "blood_bank_name": blood_request.blood_bank.name,
                "blood_bank_city": blood_request.blood_bank.city,
                "blood_bank_state": blood_request.blood_bank.state,
                "blood_bank_contact": blood_request.blood_bank.contact_number,
            }
            try:
                sent = send_notification_email(
                    recipient=donor.user,
                    subject=f"🚨 URGENT EMERGENCY: {blood_request.blood_group} Blood Needed",
                    message=message,
                    template_name="emergency_sos/emails/sos_emergency_email.html",
                    context=email_ctx,
                    fail_silently=True,
                )
                recipient_record.email_sent = bool(sent)
                if not sent:
                    recipient_record.delivery_error = "Email delivery failed or SMTP not configured."
            except Exception as e:
                recipient_record.email_sent = False
                recipient_record.delivery_error = str(e)

            recipient_record.save(update_fields=["email_attempted", "email_sent", "delivery_error"])

    return sos_broadcast


def cancel_sos_broadcast(
    sos_broadcast: SOSBroadcast,
    cancelled_by_user,
    reason: str,
) -> SOSBroadcast:
    """
    Cancels an active SOS broadcast with an explanation reason.
    """
    if sos_broadcast.status != SOSStatus.ACTIVE:
        raise ValidationError(
            f"Cannot cancel SOS broadcast with current status '{sos_broadcast.get_status_display()}'."
        )

    if not reason or not reason.strip():
        raise ValidationError({"reason": "A cancellation reason is required."})

    sos_broadcast.status = SOSStatus.CANCELLED
    sos_broadcast.cancelled_by = cancelled_by_user
    sos_broadcast.cancelled_at = timezone.now()
    sos_broadcast.cancellation_reason = reason.strip()
    sos_broadcast.save(
        update_fields=[
            "status",
            "cancelled_by",
            "cancelled_at",
            "cancellation_reason",
            "updated_at",
        ]
    )

    return sos_broadcast
