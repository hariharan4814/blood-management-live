from rest_framework import serializers

from apps.accounts.models import User
from apps.blood_requests.models import BloodRequest
from .compatibility import calculate_haversine_distance_km
from .models import SOSBroadcast, SOSRecipient, SOSStatus


class TriggerSOSRequestSerializer(serializers.Serializer):
    """
    Serializer for triggering an Emergency SOS Broadcast.
    """
    radius_km = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Optional radius in kilometers to filter eligible donors by location.",
    )
    custom_message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        help_text="Optional custom broadcast alert message (defaults to standard emergency notice).",
    )


class SOSCancelRequestSerializer(serializers.Serializer):
    """
    Serializer for cancelling an active SOS broadcast.
    """
    reason = serializers.CharField(
        required=True,
        max_length=1000,
        help_text="Mandatory explanation for cancelling the active SOS broadcast.",
    )

    def validate_reason(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("A cancellation reason is required.")
        return value.strip()


class SOSBloodRequestSummarySerializer(serializers.ModelSerializer):
    """
    Summary representation of associated Blood Request for SOS endpoints.
    """
    hospital_staff_username = serializers.CharField(source="hospital_staff.username", read_only=True)
    blood_bank_name = serializers.CharField(source="blood_bank.name", read_only=True)
    blood_bank_latitude = serializers.DecimalField(source="blood_bank.latitude", max_digits=9, decimal_places=6, read_only=True)
    blood_bank_longitude = serializers.DecimalField(source="blood_bank.longitude", max_digits=9, decimal_places=6, read_only=True)
    blood_bank_address = serializers.CharField(source="blood_bank.address", read_only=True)
    blood_bank_city = serializers.CharField(source="blood_bank.city", read_only=True)
    urgency_display = serializers.CharField(source="get_urgency_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = BloodRequest
        fields = [
            "id",
            "hospital_staff_username",
            "blood_bank_name",
            "blood_bank_latitude",
            "blood_bank_longitude",
            "blood_bank_address",
            "blood_bank_city",
            "blood_group",
            "units_needed",
            "urgency",
            "urgency_display",
            "status",
            "status_display",
            "created_at",
        ]


class SOSBroadcastSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing Emergency SOS Broadcasts.
    """
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    triggered_by_username = serializers.CharField(source="triggered_by.username", read_only=True)
    cancelled_by_username = serializers.CharField(source="cancelled_by.username", read_only=True)
    blood_request_detail = SOSBloodRequestSummarySerializer(source="blood_request", read_only=True)

    class Meta:
        model = SOSBroadcast
        fields = [
            "id",
            "blood_request",
            "blood_request_detail",
            "triggered_by",
            "triggered_by_username",
            "status",
            "status_display",
            "blood_group",
            "units_needed",
            "available_units_at_trigger",
            "shortage_units",
            "radius_km",
            "total_donors_targeted",
            "title",
            "message",
            "created_at",
            "updated_at",
            "completed_at",
            "cancelled_at",
            "cancelled_by",
            "cancelled_by_username",
            "cancellation_reason",
        ]
        read_only_fields = fields


class SOSRecipientSerializer(serializers.ModelSerializer):
    """
    Serializer for auditing donor recipients targeted by an SOS broadcast.
    """
    donor_username = serializers.SerializerMethodField()

    def get_donor_username(self, obj):
        from apps.donors.privacy import public_username
        return public_username(obj.user)
    donor_blood_group = serializers.CharField(source="donor.blood_group", read_only=True)
    distance_km = serializers.SerializerMethodField(help_text="Real great-circle distance in km between donor and emergency facility.")

    class Meta:
        model = SOSRecipient
        fields = [
            "id",
            "sos_broadcast",
            "donor",
            "donor_username",
            "donor_blood_group",
            "distance_km",
            "notification",
            "email_attempted",
            "email_sent",
            "delivery_error",
            "created_at",
        ]
        read_only_fields = fields

    def get_distance_km(self, obj) -> float | None:
        try:
            if not obj.donor or not obj.sos_broadcast or not obj.sos_broadcast.blood_request:
                return None
            bank = obj.sos_broadcast.blood_request.blood_bank
            if not bank or bank.latitude is None or bank.longitude is None:
                return None
            if obj.donor.latitude is None or obj.donor.longitude is None:
                return None
            dist = calculate_haversine_distance_km(
                bank.latitude, bank.longitude, round(float(obj.donor.latitude), 2), round(float(obj.donor.longitude), 2)
            )
            return round(float(dist), 2) if dist is not None else None
        except Exception:
            return None


class SOSDonorPreviewItemSerializer(serializers.Serializer):
    """
    Privacy-preserving representation of a compatible, eligible donor for SOS map preview.
    Exact residential address, full name, phone number, and precise GPS coordinates are withheld.
    """
    id = serializers.CharField(help_text="Opaque marker identifier (e.g. DONOR-12)")
    donor_id = serializers.IntegerField(help_text="Donor identifier")
    blood_group = serializers.CharField(help_text="Donor ABO/Rh blood group")
    is_eligible = serializers.BooleanField(default=True, help_text="Medical eligibility status")
    distance_km = serializers.FloatField(allow_null=True, help_text="Real great-circle distance from facility (km)")
    approximate_latitude = serializers.FloatField(allow_null=True, help_text="Fuzzed coordinate (~1.1 km precision)")
    approximate_longitude = serializers.FloatField(allow_null=True, help_text="Fuzzed coordinate (~1.1 km precision)")


class SOSDonorPreviewResponseSerializer(serializers.Serializer):
    """
    Response schema for Emergency SOS donor preview before broadcast dispatch.
    """
    blood_request_id = serializers.IntegerField()
    blood_group_requested = serializers.CharField()
    units_needed = serializers.IntegerField()
    radius_km = serializers.FloatField(allow_null=True)
    center_latitude = serializers.FloatField(allow_null=True)
    center_longitude = serializers.FloatField(allow_null=True)
    eligible_donors_count = serializers.IntegerField()
    donors = SOSDonorPreviewItemSerializer(many=True)
