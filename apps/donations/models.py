from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.donors.models import Donor
from apps.inventory.models import BloodBank, BloodUnit


class CampStatus(models.TextChoices):
    UPCOMING = "UPCOMING", "Upcoming"
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class CampRegistrationStatus(models.TextChoices):
    REGISTERED = "REGISTERED", "Registered"
    CANCELLED = "CANCELLED", "Cancelled"
    ATTENDED = "ATTENDED", "Attended"


class DonationCamp(models.Model):
    """
    Blood donation camp organized by a specific Blood Bank.
    """
    blood_bank = models.ForeignKey(
        BloodBank,
        on_delete=models.CASCADE,
        related_name="donation_camps",
        help_text="Blood bank facility organizing this donation camp.",
    )
    name = models.CharField(
        max_length=255,
        help_text="Name or title of the donation camp.",
    )
    location = models.CharField(
        max_length=255,
        help_text="Physical venue or location of the camp.",
    )
    camp_date = models.DateField(
        help_text="Scheduled date for the donation camp.",
    )
    organizer = models.CharField(
        max_length=255,
        help_text="Organizing institution, NGO, college, or corporate sponsor.",
    )
    target_units = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Target units of blood expected to be collected (must be greater than 0).",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Additional details, camp timing, instructions, or notes.",
    )
    status = models.CharField(
        max_length=20,
        choices=CampStatus.choices,
        default=CampStatus.UPCOMING,
        help_text="Current lifecycle status of the donation camp.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_donation_camps",
        help_text="User who created the donation camp record.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "donation_camps"
        verbose_name = "Donation Camp"
        verbose_name_plural = "Donation Camps"
        ordering = ["-camp_date", "-created_at"]

    def __str__(self):
        return f"{self.name} ({self.camp_date}) - {self.get_status_display()}"

    def clean(self):
        super().clean()
        if self.target_units is not None and self.target_units < 1:
            raise ValidationError({"target_units": "Target units must be greater than 0."})

        if self.created_by:
            if (
                self.created_by.role not in [UserRole.BLOOD_BANK_ADMIN, UserRole.SUPER_ADMIN]
                and not self.created_by.is_superuser
            ):
                raise ValidationError(
                    {"created_by": "Camp creator must be a Blood Bank Administrator or Super Admin."}
                )


class DonationCampRegistration(models.Model):
    """
    Donor registration or expression of interest to attend a Donation Camp.
    """
    donor = models.ForeignKey(
        Donor,
        on_delete=models.CASCADE,
        related_name="camp_registrations",
        help_text="Donor registering for the camp.",
    )
    camp = models.ForeignKey(
        DonationCamp,
        on_delete=models.CASCADE,
        related_name="registrations",
        help_text="Donation camp the donor is registering for.",
    )
    status = models.CharField(
        max_length=20,
        choices=CampRegistrationStatus.choices,
        default=CampRegistrationStatus.REGISTERED,
        help_text="Registration status (REGISTERED, CANCELLED, ATTENDED).",
    )
    registered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the donor registered.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "donation_camp_registrations"
        verbose_name = "Donation Camp Registration"
        verbose_name_plural = "Donation Camp Registrations"
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["donor", "camp"],
                name="unique_donor_camp_registration",
            )
        ]

    def __str__(self):
        return f"Registration: {self.donor.user.username} for {self.camp.name} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if hasattr(self, "camp") and self.camp:
            if self.camp.status == CampStatus.CANCELLED:
                raise ValidationError({"camp": "Cannot register for a CANCELLED donation camp."})


class Donation(models.Model):
    """
    Actual completed blood collection record.
    Created either during a DonationCamp or as a Walk-in donation directly at a BloodBank.
    """
    donor = models.ForeignKey(
        Donor,
        on_delete=models.CASCADE,
        related_name="donations",
        help_text="Donor who gave blood.",
    )
    blood_bank = models.ForeignKey(
        BloodBank,
        on_delete=models.CASCADE,
        related_name="donations",
        help_text="Blood bank where the blood was collected or processed.",
    )
    camp = models.ForeignKey(
        DonationCamp,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
        help_text="Optional donation camp where blood was collected (null for walk-ins).",
    )
    blood_request = models.ForeignKey(
        "blood_requests.BloodRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
        help_text="Associated Blood Request if this donation fulfilled a specific request.",
    )
    blood_unit = models.OneToOneField(
        BloodUnit,
        on_delete=models.PROTECT,
        related_name="donation",
        help_text="Physical blood unit collected from this donation.",
    )
    donation_date = models.DateField(
        default=timezone.now,
        help_text="Date when the donation occurred.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_donations",
        help_text="Blood bank administrator user who recorded this donation.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "donations"
        verbose_name = "Donation"
        verbose_name_plural = "Donations"
        ordering = ["-donation_date", "-created_at"]

    def __str__(self):
        camp_info = f" via {self.camp.name}" if self.camp else " (Walk-in)"
        return f"Donation #{self.id}: {self.donor.user.username}{camp_info} on {self.donation_date}"

    def clean(self):
        super().clean()
        today = timezone.now().date()

        if self.donation_date and self.donation_date > today:
            raise ValidationError({"donation_date": "Donation date cannot be in the future."})

        if hasattr(self, "donor") and self.donor and self.donor.date_of_birth:
            if self.donation_date and self.donation_date < self.donor.date_of_birth:
                raise ValidationError({"donation_date": "Donation date cannot precede donor date of birth."})

        if self.camp:
            if hasattr(self, "blood_bank") and self.blood_bank:
                if self.camp.blood_bank_id != self.blood_bank_id:
                    raise ValidationError({"camp": "Donation camp does not belong to the specified blood bank."})
            if self.camp.status == CampStatus.CANCELLED:
                raise ValidationError({"camp": "Cannot record a donation for a CANCELLED donation camp."})

        if hasattr(self, "blood_unit") and self.blood_unit:
            if hasattr(self, "blood_bank") and self.blood_bank:
                if self.blood_unit.blood_bank_id != self.blood_bank_id:
                    raise ValidationError({"blood_unit": "Blood unit must belong to the same blood bank as the donation."})
            if hasattr(self, "donor") and self.donor:
                if self.blood_unit.blood_group != self.donor.blood_group:
                    raise ValidationError({"blood_unit": "Blood unit blood group must match the donor blood group."})
