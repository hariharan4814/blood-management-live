from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import UserRole
from apps.donors.models import BloodGroup
from .models import BloodBank, BloodUnit, BloodUnitStatus, RBC_SHELF_LIFE_DAYS
from .services import generate_unit_id, calculate_blood_unit_expiry

User = get_user_model()


# ========================================================
# BLOOD BANK SERIALIZERS
# ========================================================

class BloodBankSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for BloodBank representation.
    """
    admin_id = serializers.ReadOnlyField(source="admin.id")
    admin_username = serializers.ReadOnlyField(source="admin.username")
    admin_email = serializers.ReadOnlyField(source="admin.email")
    total_units_count = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = BloodBank
        fields = [
            "id",
            "name",
            "address",
            "city",
            "state",
            "contact_number",
            "email",
            "capacity",
            "latitude",
            "longitude",
            "is_active",
            "admin",
            "admin_id",
            "admin_username",
            "admin_email",
            "total_units_count",
            "average_rating",
            "review_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "admin_id",
            "admin_username",
            "admin_email",
            "total_units_count",
            "average_rating",
            "review_count",
            "created_at",
            "updated_at",
        ]

    def get_total_units_count(self, obj):
        return obj.blood_units.count()

    def get_average_rating(self, obj) -> float | None:
        from django.db.models import Avg
        from apps.common.models import ReviewStatus
        avg = obj.reviews.filter(status=ReviewStatus.APPROVED).aggregate(Avg("rating"))["rating__avg"]
        return round(float(avg), 1) if avg is not None else None

    def get_review_count(self, obj) -> int:
        from apps.common.models import ReviewStatus
        return obj.reviews.filter(status=ReviewStatus.APPROVED).count()


class BloodBankPublicSerializer(serializers.ModelSerializer):
    """
    Safe, minimal serializer for Hospital Staff to select active target facilities.
    Excludes sensitive administrative credentials, internal metrics, and PII.
    """
    class Meta:
        model = BloodBank
        fields = [
            "id",
            "name",
            "address",
            "city",
            "state",
            "contact_number",
            "is_active",
        ]
        read_only_fields = fields


class BloodBankInputSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating BloodBank records.
    """
    name = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Name of the blood bank facility."
    )
    city = serializers.CharField(max_length=100, required=True)
    state = serializers.CharField(max_length=100, required=True)
    contact_number = serializers.CharField(max_length=30, required=True)
    email = serializers.EmailField(required=True)
    capacity = serializers.IntegerField(
        min_value=0,
        default=0,
        help_text="Non-negative storage capacity in units."
    )
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        min_value=Decimal("-90.000000"),
        max_value=Decimal("90.000000"),
        help_text="Latitude coordinate (-90.0 to 90.0)."
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        min_value=Decimal("-180.000000"),
        max_value=Decimal("180.000000"),
        help_text="Longitude coordinate (-180.0 to 180.0)."
    )
    admin = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
        help_text="User ID of the assigned Blood Bank Administrator."
    )

    class Meta:
        model = BloodBank
        fields = [
            "name",
            "address",
            "city",
            "state",
            "contact_number",
            "email",
            "capacity",
            "latitude",
            "longitude",
            "is_active",
            "admin",
        ]

    def validate_capacity(self, value):
        if value < 0:
            raise serializers.ValidationError("Capacity must not be negative.")
        return value

    def validate_admin(self, value):
        if value is not None:
            if value.role not in [UserRole.BLOOD_BANK_ADMIN, UserRole.SUPER_ADMIN] and not value.is_superuser:
                raise serializers.ValidationError(
                    "Assigned admin user must have the BLOOD_BANK_ADMIN or SUPER_ADMIN role."
                )
        return value


# ========================================================
# BLOOD UNIT SERIALIZERS
# ========================================================

class BloodUnitSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for BloodUnit representation.
    """
    blood_bank_id = serializers.ReadOnlyField(source="blood_bank.id")
    blood_bank_name = serializers.ReadOnlyField(source="blood_bank.name")
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_available_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = BloodUnit
        fields = [
            "id",
            "unit_id",
            "blood_bank",
            "blood_bank_id",
            "blood_bank_name",
            "blood_group",
            "collection_date",
            "expiry_date",
            "status",
            "status_display",
            "is_expired",
            "is_available_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "blood_bank_id",
            "blood_bank_name",
            "expiry_date",
            "status_display",
            "is_expired",
            "is_available_stock",
            "created_at",
            "updated_at",
        ]


class BloodUnitCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating blood units.
    - Expiry date is automatically calculated as collection_date + 42 days.
    - Status defaults to TESTING and cannot be overridden by client during creation.
    - Generates a unique unit_id if not explicitly provided.
    """
    unit_id = serializers.CharField(
        max_length=60,
        required=False,
        allow_blank=True,
        help_text="Optional custom unit identifier (auto-generated if omitted)."
    )
    blood_bank = serializers.PrimaryKeyRelatedField(
        queryset=BloodBank.objects.filter(is_active=True),
        required=True,
        help_text="Blood Bank facility ID storing this unit."
    )
    blood_group = serializers.ChoiceField(
        choices=BloodGroup.choices,
        help_text="ABO and Rh blood group (A+, A-, B+, B-, AB+, AB-, O+, O-)."
    )
    collection_date = serializers.DateField(
        required=True,
        help_text="Collection date (cannot be in the future)."
    )

    class Meta:
        model = BloodUnit
        fields = [
            "unit_id",
            "blood_bank",
            "blood_group",
            "collection_date",
        ]

    def validate_collection_date(self, value):
        today = timezone.now().date()
        if value > today:
            raise serializers.ValidationError("Collection date cannot be in the future.")
        return value

    def validate_unit_id(self, value):
        if value:
            if BloodUnit.objects.filter(unit_id=value).exists():
                raise serializers.ValidationError("A blood unit with this unit_id already exists.")
        return value

    def create(self, validated_data):
        # Auto-generate unit_id if not supplied
        unit_id = validated_data.get("unit_id")
        if not unit_id:
            while True:
                candidate_id = generate_unit_id()
                if not BloodUnit.objects.filter(unit_id=candidate_id).exists():
                    unit_id = candidate_id
                    break
            validated_data["unit_id"] = unit_id

        # Calculate 42-day RBC expiry automatically
        collection_date = validated_data["collection_date"]
        validated_data["expiry_date"] = calculate_blood_unit_expiry(collection_date)

        # Force initial lifecycle status to TESTING
        validated_data["status"] = BloodUnitStatus.TESTING

        return BloodUnit.objects.create(**validated_data)


class BloodUnitStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Controlled status update serializer for administrators.
    """
    status = serializers.ChoiceField(
        choices=BloodUnitStatus.choices,
        required=True,
        help_text="Target status for the blood unit."
    )

    class Meta:
        model = BloodUnit
        fields = ["status"]

    def validate_status(self, new_status):
        instance = self.instance
        if not instance:
            return new_status

        current_status = instance.status
        # Discarded units cannot be transitioned back to usable states
        if current_status == BloodUnitStatus.DISCARDED and new_status != BloodUnitStatus.DISCARDED:
            raise serializers.ValidationError(
                "A discarded blood unit cannot be transitioned back to another status."
            )
        # Dispatched units cannot be reactivated
        if current_status == BloodUnitStatus.DISPATCHED and new_status != BloodUnitStatus.DISPATCHED:
            raise serializers.ValidationError(
                "A dispatched blood unit cannot be transitioned back to another status."
            )
        return new_status


# ========================================================
# INVENTORY SUMMARY SERIALIZERS
# ========================================================

class BloodBankBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()


class InventoryGroupStockSerializer(serializers.Serializer):
    blood_group = serializers.CharField()
    available_units = serializers.IntegerField()


class InventorySummaryResponseSerializer(serializers.Serializer):
    blood_bank = BloodBankBriefSerializer()
    inventory = InventoryGroupStockSerializer(many=True)
    total_available_units = serializers.IntegerField()
