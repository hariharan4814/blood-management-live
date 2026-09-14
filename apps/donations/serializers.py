from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.accounts.models import UserRole
from apps.donors.models import Donor
from apps.inventory.models import BloodBank, BloodUnit
from .models import (
    DonationCamp,
    DonationCampRegistration,
    Donation,
    CampStatus,
    CampRegistrationStatus,
)
from .services import record_donation


class BloodUnitSummarySerializer(serializers.ModelSerializer):
    """
    Compact read-only serializer for BloodUnit created from a donation.
    """
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = BloodUnit
        fields = [
            "id",
            "unit_id",
            "blood_group",
            "collection_date",
            "expiry_date",
            "status",
            "status_display",
        ]
        read_only_fields = fields


class DonationCampSerializer(serializers.ModelSerializer):
    """
    Full detail representation serializer for DonationCamp entities.
    """
    blood_bank_id = serializers.ReadOnlyField()
    blood_bank_name = serializers.ReadOnlyField(source="blood_bank.name")
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_id = serializers.ReadOnlyField()
    created_by_username = serializers.SerializerMethodField()
    registrations_count = serializers.SerializerMethodField()
    donations_count = serializers.SerializerMethodField()

    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else None

    def get_registrations_count(self, obj):
        return obj.registrations.count()

    def get_donations_count(self, obj):
        return obj.donations.count()

    class Meta:
        model = DonationCamp
        fields = [
            "id",
            "blood_bank",
            "blood_bank_id",
            "blood_bank_name",
            "name",
            "location",
            "camp_date",
            "organizer",
            "target_units",
            "description",
            "status",
            "status_display",
            "registrations_count",
            "donations_count",
            "created_by_id",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "blood_bank_id",
            "blood_bank_name",
            "status_display",
            "registrations_count",
            "donations_count",
            "created_by_id",
            "created_by_username",
            "created_at",
            "updated_at",
        ]


class DonationCampCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating DonationCamp entities.
    Enforces server-side assignment of created_by and bank authorization.
    """
    blood_bank = serializers.PrimaryKeyRelatedField(
        queryset=BloodBank.objects.filter(is_active=True),
        required=True,
        help_text="ID of the Blood Bank organizing this camp.",
    )
    name = serializers.CharField(max_length=255, required=True)
    location = serializers.CharField(max_length=255, required=True)
    camp_date = serializers.DateField(required=True)
    organizer = serializers.CharField(max_length=255, required=True)
    target_units = serializers.IntegerField(min_value=1, required=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=CampStatus.choices,
        default=CampStatus.UPCOMING,
        required=False,
    )

    class Meta:
        model = DonationCamp
        fields = [
            "blood_bank",
            "name",
            "location",
            "camp_date",
            "organizer",
            "target_units",
            "description",
            "status",
        ]

    def validate_target_units(self, value):
        if value < 1:
            raise serializers.ValidationError("Target units must be greater than 0.")
        return value

    def validate_blood_bank(self, value):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            if request.user.role == UserRole.BLOOD_BANK_ADMIN and not request.user.is_super_admin:
                if value.admin_id != request.user.id:
                    raise serializers.ValidationError(
                        "You can only create or manage donation camps for your assigned blood bank."
                    )
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None
        validated_data["created_by"] = user
        return super().create(validated_data)


class DonationCampRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing DonationCampRegistration details.
    """
    donor_id = serializers.ReadOnlyField()
    donor_username = serializers.SerializerMethodField()

    def get_donor_username(self, obj):
        from apps.donors.privacy import public_username
        return public_username(obj.donor.user)
    donor_blood_group = serializers.ReadOnlyField(source="donor.blood_group")
    camp_id = serializers.ReadOnlyField()
    camp_name = serializers.ReadOnlyField(source="camp.name")
    camp_date = serializers.ReadOnlyField(source="camp.camp_date")
    camp_location = serializers.ReadOnlyField(source="camp.location")
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = DonationCampRegistration
        fields = [
            "id",
            "donor_id",
            "donor_username",
            "donor_blood_group",
            "camp_id",
            "camp_name",
            "camp_date",
            "camp_location",
            "status",
            "status_display",
            "registered_at",
            "updated_at",
        ]
        read_only_fields = fields


class DonationSerializer(serializers.ModelSerializer):
    """
    Detailed read-only serializer for Donation collection records.
    """
    donor_id = serializers.ReadOnlyField()
    donor_username = serializers.SerializerMethodField()

    def get_donor_username(self, obj):
        from apps.donors.privacy import public_username
        return public_username(obj.donor.user)
    donor_blood_group = serializers.ReadOnlyField(source="donor.blood_group")
    blood_bank_id = serializers.ReadOnlyField()
    blood_bank_name = serializers.ReadOnlyField(source="blood_bank.name")
    camp_id = serializers.ReadOnlyField()
    camp_name = serializers.SerializerMethodField()
    blood_unit = BloodUnitSummarySerializer(read_only=True)
    created_by_id = serializers.ReadOnlyField()
    created_by_username = serializers.SerializerMethodField()

    def get_camp_name(self, obj):
        return obj.camp.name if obj.camp else None

    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else None

    class Meta:
        model = Donation
        fields = [
            "id",
            "donor_id",
            "donor_username",
            "donor_blood_group",
            "blood_bank_id",
            "blood_bank_name",
            "camp_id",
            "camp_name",
            "blood_unit",
            "donation_date",
            "created_by_id",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DonationCreateSerializer(serializers.Serializer):
    """
    Serializer for Blood Bank Admin to record an actual blood donation (walk-in or camp).
    Triggers atomic creation of BloodUnit and updating donor last_donation_date.
    """
    donor = serializers.PrimaryKeyRelatedField(
        queryset=Donor.objects.all(),
        required=True,
        help_text="ID of the Donor who provided the blood.",
    )
    blood_bank = serializers.PrimaryKeyRelatedField(
        queryset=BloodBank.objects.filter(is_active=True),
        required=True,
        help_text="ID of the Blood Bank facility receiving the donation.",
    )
    camp = serializers.PrimaryKeyRelatedField(
        queryset=DonationCamp.objects.all(),
        required=False,
        allow_null=True,
        default=None,
        help_text="Optional ID of the Donation Camp where donation was collected (null for walk-in).",
    )
    donation_date = serializers.DateField(
        required=False,
        default=timezone.now().date,
        help_text="Date of donation (defaults to today).",
    )

    def validate_donation_date(self, value):
        today = timezone.now().date()
        if value > today:
            raise serializers.ValidationError("Donation date cannot be in the future.")
        return value

    def validate_blood_bank(self, value):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            if request.user.role == UserRole.BLOOD_BANK_ADMIN and not request.user.is_super_admin:
                if value.admin_id != request.user.id:
                    raise serializers.ValidationError(
                        "You can only record donations for your assigned blood bank."
                    )
        return value

    def validate(self, attrs):
        camp = attrs.get("camp")
        blood_bank = attrs.get("blood_bank")
        donor = attrs.get("donor")
        donation_date = attrs.get("donation_date") or timezone.now().date()

        if donor.date_of_birth and donation_date < donor.date_of_birth:
            raise serializers.ValidationError(
                {"donation_date": "Donation date cannot precede donor date of birth."}
            )

        if camp is not None:
            if camp.blood_bank_id != blood_bank.id:
                raise serializers.ValidationError(
                    {"camp": "Donation camp does not belong to the selected blood bank."}
                )
            if camp.status == CampStatus.CANCELLED:
                raise serializers.ValidationError(
                    {"camp": "Cannot record a donation for a CANCELLED donation camp."}
                )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        donor = validated_data["donor"]
        blood_bank = validated_data["blood_bank"]
        camp = validated_data.get("camp")
        donation_date = validated_data.get("donation_date")

        try:
            donation = record_donation(
                donor=donor,
                blood_bank=blood_bank,
                camp=camp,
                donation_date=donation_date,
                created_by=user,
            )
        except DjangoValidationError as e:
            if hasattr(e, "message_dict"):
                raise serializers.ValidationError(e.message_dict)
            elif hasattr(e, "messages"):
                raise serializers.ValidationError({"detail": e.messages[0]})
            else:
                raise serializers.ValidationError({"detail": str(e)})

        return donation
