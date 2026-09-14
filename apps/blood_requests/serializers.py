from rest_framework import serializers

from apps.donors.models import BloodGroup
from apps.inventory.models import BloodBank, BloodUnit
from .models import BloodRequest, RequestUrgency, RequestStatus, Hospital


class ReservedUnitBriefSerializer(serializers.ModelSerializer):
    """
    Compact representation of BloodUnit records reserved for an approved request.
    """
    class Meta:
        model = BloodUnit
        fields = [
            "id",
            "unit_id",
            "blood_group",
            "status",
            "collection_date",
            "expiry_date",
        ]
        read_only_fields = fields


class BloodRequestSerializer(serializers.ModelSerializer):
    """
    Detailed representation serializer for BloodRequest entities.
    """
    hospital_staff_id = serializers.ReadOnlyField()
    hospital_staff_username = serializers.ReadOnlyField(source="hospital_staff.username")
    hospital_staff_email = serializers.ReadOnlyField(source="hospital_staff.email")
    blood_bank_id = serializers.ReadOnlyField()
    blood_bank_name = serializers.ReadOnlyField(source="blood_bank.name")
    blood_bank_latitude = serializers.DecimalField(source="blood_bank.latitude", max_digits=9, decimal_places=6, read_only=True)
    blood_bank_longitude = serializers.DecimalField(source="blood_bank.longitude", max_digits=9, decimal_places=6, read_only=True)
    blood_bank_address = serializers.CharField(source="blood_bank.address", read_only=True)
    blood_bank_city = serializers.CharField(source="blood_bank.city", read_only=True)
    blood_bank_state = serializers.CharField(source="blood_bank.state", read_only=True)
    urgency_display = serializers.CharField(source="get_urgency_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    approved_by_id = serializers.ReadOnlyField()
    approved_by_username = serializers.SerializerMethodField()
    reserved_units = ReservedUnitBriefSerializer(many=True, read_only=True)
    reserved_units_count = serializers.SerializerMethodField()

    def get_approved_by_username(self, obj):
        return obj.approved_by.username if obj.approved_by else None

    class Meta:
        model = BloodRequest
        fields = [
            "id",
            "hospital_staff_id",
            "hospital_staff_username",
            "hospital_staff_email",
            "blood_bank",
            "blood_bank_id",
            "blood_bank_name",
            "blood_bank_latitude",
            "blood_bank_longitude",
            "blood_bank_address",
            "blood_bank_city",
            "blood_bank_state",
            "blood_group",
            "units_needed",
            "urgency",
            "urgency_display",
            "status",
            "status_display",
            "rejection_reason",
            "approved_by_id",
            "approved_by_username",
            "approved_at",
            "reserved_units",
            "reserved_units_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "hospital_staff_id",
            "hospital_staff_username",
            "hospital_staff_email",
            "blood_bank_id",
            "blood_bank_name",
            "blood_bank_latitude",
            "blood_bank_longitude",
            "blood_bank_address",
            "blood_bank_city",
            "blood_bank_state",
            "urgency_display",
            "status",
            "status_display",
            "rejection_reason",
            "approved_by_id",
            "approved_by_username",
            "approved_at",
            "reserved_units",
            "reserved_units_count",
            "created_at",
            "updated_at",
        ]

    def get_reserved_units_count(self, obj):
        return obj.reserved_units.count()


class BloodRequestCreateSerializer(serializers.ModelSerializer):
    """
    Input serializer for Hospital Staff to create a new blood request.
    Enforces that hospital_staff is set from the request and status defaults to PENDING.
    """
    blood_bank = serializers.PrimaryKeyRelatedField(
        queryset=BloodBank.objects.filter(is_active=True),
        required=True,
        help_text="ID of the target Blood Bank facility."
    )
    blood_group = serializers.ChoiceField(
        choices=BloodGroup.choices,
        required=True,
        help_text="Requested ABO/Rh blood group."
    )
    units_needed = serializers.IntegerField(
        min_value=1,
        required=True,
        help_text="Number of blood units needed (minimum 1)."
    )
    urgency = serializers.ChoiceField(
        choices=RequestUrgency.choices,
        default=RequestUrgency.NORMAL,
        help_text="Urgency level (NORMAL, HIGH, CRITICAL)."
    )

    class Meta:
        model = BloodRequest
        fields = [
            "blood_bank",
            "blood_group",
            "units_needed",
            "urgency",
        ]

    def validate_units_needed(self, value):
        if value < 1:
            raise serializers.ValidationError("Units needed must be at least 1.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        validated_data["hospital_staff"] = user
        validated_data["status"] = RequestStatus.PENDING
        validated_data["rejection_reason"] = ""
        validated_data["approved_by"] = None
        validated_data["approved_at"] = None

        return BloodRequest.objects.create(**validated_data)


class BloodRequestRejectSerializer(serializers.Serializer):
    """
    Serializer for Blood Bank Admin to reject a pending blood request with an explanation reason.
    """
    rejection_reason = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="Mandatory explanation reason for rejecting the request."
    )

    def validate_rejection_reason(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("A non-empty rejection reason is required.")
        return value.strip()


class HospitalSerializer(serializers.ModelSerializer):
    """
    Representation serializer for Hospital facility entities.
    Includes approved review aggregate rating and count.
    """
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Hospital
        fields = [
            "id",
            "name",
            "address",
            "city",
            "state",
            "contact_number",
            "email",
            "beds",
            "latitude",
            "longitude",
            "is_active",
            "average_rating",
            "review_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "average_rating", "review_count", "created_at", "updated_at"]

    def get_average_rating(self, obj) -> float | None:
        from django.db.models import Avg
        from apps.common.models import ReviewStatus
        avg = obj.reviews.filter(status=ReviewStatus.APPROVED).aggregate(Avg("rating"))["rating__avg"]
        return round(float(avg), 1) if avg is not None else None

    def get_review_count(self, obj) -> int:
        from apps.common.models import ReviewStatus
        return obj.reviews.filter(status=ReviewStatus.APPROVED).count()
