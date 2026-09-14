from datetime import date
from typing import Any, Optional
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.donors.models import Donor
from apps.donors.services import calculate_donor_eligibility
from apps.inventory.models import BloodBank, BloodUnit, BloodUnitStatus
from apps.inventory.services import generate_unit_id, calculate_blood_unit_expiry
from .models import Donation, DonationCamp, CampStatus, DonationCampRegistration, CampRegistrationStatus


@transaction.atomic
def record_donation(
    donor: Donor,
    blood_bank: BloodBank,
    camp: Optional[DonationCamp] = None,
    blood_request: Optional[Any] = None,
    donation_date: Optional[date] = None,
    created_by=None,
) -> Donation:
    """
    Atomically records an actual completed blood collection (walk-in or camp-based).

    Workflow:
    1. Validates donation_date (cannot be in the future, cannot precede donor DOB).
    2. Validates optional camp association (must match blood bank, cannot be CANCELLED).
    3. Validates donor medical eligibility via reused eligibility service.
    4. In an atomic transaction:
       - Creates exactly one BloodUnit in status TESTING with 42-day expiry.
       - Creates Donation record linking donor, blood bank, optional camp, blood unit, created_by.
       - Updates donor's last_donation_date to the donation_date.
       - Updates any active camp registration for this donor to ATTENDED.
    5. Returns the created Donation instance.

    On any validation or database failure, rolls back all changes completely.
    """
    # Serialize all collection paths for this donor, including different requests
    # and walk-in donations. Re-read eligibility inputs after acquiring the lock.
    donor = Donor.objects.select_for_update().get(pk=donor.pk)
    today = timezone.now().date()
    if donation_date is None:
        donation_date = today

    # 1. Validate donation date
    if donation_date > today:
        raise ValidationError({"donation_date": "Donation date cannot be in the future."})

    if donor.date_of_birth and donation_date < donor.date_of_birth:
        raise ValidationError({"donation_date": "Donation date cannot precede donor date of birth."})

    # 2. Validate optional camp
    if camp is not None:
        if camp.blood_bank_id != blood_bank.id:
            raise ValidationError({"camp": "Donation camp does not belong to the specified blood bank."})
        if camp.status == CampStatus.CANCELLED:
            raise ValidationError({"camp": "Cannot record a donation for a CANCELLED donation camp."})

    # 3. Validate donor eligibility (reusing calculate_donor_eligibility)
    eligibility = calculate_donor_eligibility(
        date_of_birth=donor.date_of_birth,
        weight_kg=donor.weight_kg,
        last_donation_date=donor.last_donation_date,
        reference_date=donation_date,
    )

    if not eligibility.get("is_eligible", False):
        reasons = eligibility.get("reasons", ["Donor does not meet medical eligibility requirements."])
        raise ValidationError({"donor": f"Donor is not eligible to donate blood: {'; '.join(reasons)}"})

    # 4. Atomic execution
    with transaction.atomic():
        unit_id = generate_unit_id(prefix="BU")
        expiry_date = calculate_blood_unit_expiry(donation_date)

        # Create BloodUnit in TESTING status
        blood_unit = BloodUnit.objects.create(
            blood_bank=blood_bank,
            unit_id=unit_id,
            blood_group=donor.blood_group,
            collection_date=donation_date,
            expiry_date=expiry_date,
            status=BloodUnitStatus.TESTING,
        )

        # Create Donation
        donation = Donation.objects.create(
            donor=donor,
            blood_bank=blood_bank,
            camp=camp,
            blood_request=blood_request,
            blood_unit=blood_unit,
            donation_date=donation_date,
            created_by=created_by,
        )

        # Update donor's last donation date
        donor.last_donation_date = donation_date
        donor.save(update_fields=["last_donation_date", "updated_at"])

        # If this was a camp donation, mark existing registration as ATTENDED
        if camp is not None:
            DonationCampRegistration.objects.filter(
                donor=donor,
                camp=camp,
                status=CampRegistrationStatus.REGISTERED,
            ).update(status=CampRegistrationStatus.ATTENDED, updated_at=timezone.now())

    return donation
