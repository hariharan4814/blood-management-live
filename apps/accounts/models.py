from decimal import Decimal
import os
import uuid
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


def user_profile_image_path(instance, filename):
    """
    Generates a unique and secure upload path for user profile images.
    Example: profile_images/user_1_a1b2c3d4.jpg
    """
    ext = os.path.splitext(filename)[1].lower()
    unique_id = uuid.uuid4().hex[:8]
    user_id = instance.id or "new"
    return f"profile_images/user_{user_id}_{unique_id}{ext}"


class UserRole(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
    BLOOD_BANK_ADMIN = "BLOOD_BANK_ADMIN", "Blood Bank Admin"
    HOSPITAL_STAFF = "HOSPITAL_STAFF", "Hospital Staff"
    LAB_TECHNICIAN = "LAB_TECHNICIAN", "Lab Technician"
    DONOR = "DONOR", "Donor"


class User(AbstractUser):
    """
    Centralized Custom User model supporting Role-Based Access Control (RBAC).
    """
    email = models.EmailField(unique=True, help_text="Unique email address for user authentication.")
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.DONOR,
        help_text="Role-based access level for the user."
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Primary contact phone number."
    )
    profile_image = models.ImageField(
        upload_to=user_profile_image_path,
        null=True,
        blank=True,
        help_text="User profile display picture."
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Designates whether the user's email/account has been verified."
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
        help_text="User coordinate latitude (-90.0 to 90.0).",
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
        help_text="User coordinate longitude (-180.0 to 180.0).",
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Physical address or location description.",
    )
    hospital = models.ForeignKey(
        "blood_requests.Hospital",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members",
        help_text="Associated hospital facility entity for Hospital Staff.",
    )

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else self.username

    @property
    def is_super_admin(self):
        return self.role == UserRole.SUPER_ADMIN or self.is_superuser

    @property
    def is_blood_bank_admin(self):
        return self.role == UserRole.BLOOD_BANK_ADMIN

    @property
    def is_hospital_staff(self):
        return self.role == UserRole.HOSPITAL_STAFF

    @property
    def is_lab_technician(self):
        return self.role == UserRole.LAB_TECHNICIAN

    @property
    def is_donor(self):
        return self.role == UserRole.DONOR

