from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.models import UserRole
from .services import calculate_donor_eligibility


class BloodGroup(models.TextChoices):
    # Standard ABO and Rh
    O_POSITIVE = "O+", "O+"
    O_NEGATIVE = "O-", "O-"
    A_POSITIVE = "A+", "A+"
    A_NEGATIVE = "A-", "A-"
    B_POSITIVE = "B+", "B+"
    B_NEGATIVE = "B-", "B-"
    AB_POSITIVE = "AB+", "AB+"
    AB_NEGATIVE = "AB-", "AB-"

    # Subgroups
    A1_POSITIVE = "A1+", "A1+"
    A1_NEGATIVE = "A1-", "A1-"
    A2_POSITIVE = "A2+", "A2+"
    A2_NEGATIVE = "A2-", "A2-"
    A1B_POSITIVE = "A1B+", "A1B+"
    A1B_NEGATIVE = "A1B-", "A1B-"
    A2B_POSITIVE = "A2B+", "A2B+"
    A2B_NEGATIVE = "A2B-", "A2B-"


def normalize_blood_group(value: str) -> str:
    """
    Normalizes blood group strings by stripping whitespace and checking against canonical values.
    Raises ValidationError if invalid.
    """
    if not value or not isinstance(value, str):
        raise ValidationError(f"Invalid blood group: {value}")
    cleaned = value.strip().upper()
    valid_values = {choice[0] for choice in BloodGroup.choices}
    if cleaned not in valid_values:
        raise ValidationError(f"'{value}' is not a valid blood group. Must be one of: {', '.join(sorted(valid_values))}")
    return cleaned


class Donor(models.Model):
    """
    Donor profile entity linked One-to-One with User.
    Stores medical attributes, location coordinates, and donation history.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="donor_profile",
        help_text="User account associated with this donor profile.",
    )
    blood_group = models.CharField(
        max_length=5,
        choices=BloodGroup.choices,
        help_text="Verified or self-reported ABO and Rh blood group.",
    )
    date_of_birth = models.DateField(
        help_text="Date of birth to verify age eligibility (18–65 years).",
    )
    weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1.00"))],
        help_text="Body weight in kilograms (minimum 50.0 kg required for donation).",
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-90.000000")),
            MaxValueValidator(Decimal("90.000000")),
        ],
        help_text="Donor coordinate latitude for emergency radius matching.",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-180.000000")),
            MaxValueValidator(Decimal("180.000000")),
        ],
        help_text="Donor coordinate longitude for emergency radius matching.",
    )
    last_donation_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of the most recent blood donation (null for first-time donors).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "donors"
        verbose_name = "Donor"
        verbose_name_plural = "Donors"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} ({self.blood_group})"

    def clean(self):
        super().clean()
        today = timezone.now().date()

        # Enforce that only DONOR role users have a donor profile
        if hasattr(self, "user") and self.user:
            if self.user.role != UserRole.DONOR:
                raise ValidationError(
                    {"user": f"Only users with the '{UserRole.DONOR}' role can have a Donor profile."}
                )

        if self.date_of_birth and self.date_of_birth > today:
            raise ValidationError({"date_of_birth": "Date of birth cannot be in the future."})

        if self.last_donation_date:
            if self.last_donation_date > today:
                raise ValidationError({"last_donation_date": "Last donation date cannot be in the future."})
            if self.date_of_birth and self.last_donation_date < self.date_of_birth:
                raise ValidationError({"last_donation_date": "Last donation date cannot precede date of birth."})

        if self.weight_kg is not None and self.weight_kg <= Decimal("0.00"):
            raise ValidationError({"weight_kg": "Weight must be greater than 0 kg."})

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )

    def calculate_eligibility(self, reference_date=None):
        return calculate_donor_eligibility(
            date_of_birth=self.date_of_birth,
            weight_kg=self.weight_kg,
            last_donation_date=self.last_donation_date,
            reference_date=reference_date,
        )

    @property
    def is_eligible(self):
        return self.calculate_eligibility().get("is_eligible", False)


class ContactRequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    DECLINED = "DECLINED", "Declined"


class DonorContactRequest(models.Model):
    """
    Explicit donor consent request model.
    Allows permitted users/organizations to request private contact details
    from a donor. Only after explicit donor approval can private contact
    information (phone, email, full address) be accessed by the requester.
    """
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_donor_contact_requests",
        help_text="User requesting access to donor contact details.",
    )
    donor = models.ForeignKey(
        Donor,
        on_delete=models.CASCADE,
        related_name="contact_requests",
        help_text="Target donor whose contact details are requested.",
    )
    reason = models.TextField(
        help_text="Clinical or emergency justification for requesting donor contact.",
    )
    status = models.CharField(
        max_length=20,
        choices=ContactRequestStatus.choices,
        default=ContactRequestStatus.PENDING,
        help_text="Current consent status (PENDING, APPROVED, DECLINED).",
    )
    responded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the donor accepted or declined the request.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "donor_contact_requests"
        verbose_name = "Donor Contact Request"
        verbose_name_plural = "Donor Contact Requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["requester", "donor", "status"]),
            models.Index(fields=["donor", "status"]),
        ]

    def __str__(self):
        return f"Request #{self.id}: {self.requester.username} -> {self.donor.user.username} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.reason is not None:
            self.reason = self.reason.strip()
        if not self.reason:
            raise ValidationError({"reason": "A valid reason for requesting donor contact is required."})

        if hasattr(self, "requester") and hasattr(self, "donor") and self.donor:
            if self.requester_id == self.donor.user_id:
                raise ValidationError({"donor": "You cannot submit a contact request to yourself."})
