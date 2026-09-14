from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from .models import Donor, BloodGroup, DonorContactRequest, ContactRequestStatus, DonationOutcome
from .privacy import public_username


class DonorProfileSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for Donor profile representation.
    """
    user_id = serializers.ReadOnlyField(source="user.id")
    username = serializers.ReadOnlyField(source="user.username")
    email = serializers.ReadOnlyField(source="user.email")
    phone = serializers.ReadOnlyField(source="user.phone")
    age = serializers.ReadOnlyField()
    is_eligible = serializers.ReadOnlyField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        user = getattr(self.context.get("request"), "user", None)
        if not user or not user.is_authenticated or user.id != instance.user_id:
            for field in ("email", "phone", "date_of_birth", "weight_kg", "latitude", "longitude"):
                data.pop(field, None)
            data["username"] = public_username(instance.user)
        return data

    class Meta:
        model = Donor
        fields = [
            "id",
            "user_id",
            "username",
            "email",
            "phone",
            "blood_group",
            "date_of_birth",
            "age",
            "weight_kg",
            "latitude",
            "longitude",
            "last_donation_date",
            "is_eligible",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user_id",
            "username",
            "email",
            "phone",
            "age",
            "is_eligible",
            "created_at",
            "updated_at",
        ]


class DonorProfileInputSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating donor profiles.
    """
    date_of_birth = serializers.DateField(required=True)
    blood_group = serializers.ChoiceField(
        choices=BloodGroup.choices,
        help_text="ABO and Rh blood group (A+, A-, B+, B-, AB+, AB-, O+, O-)."
    )
    weight_kg = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("1.00"),
        help_text="Body weight in kg."
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

    class Meta:
        model = Donor
        fields = [
            "blood_group",
            "date_of_birth",
            "weight_kg",
            "latitude",
            "longitude",
            "last_donation_date",
        ]

    def validate_date_of_birth(self, value):
        today = timezone.now().date()
        if value > today:
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate_last_donation_date(self, value):
        if self.instance:
            latest = self.instance.donations.order_by("-donation_date").first()
            if latest and (value is None or value < latest.donation_date):
                raise serializers.ValidationError("Last donation date cannot precede a recorded donation.")
        if value is not None:
            today = timezone.now().date()
            if value > today:
                raise serializers.ValidationError("Last donation date cannot be in the future.")
        return value

    def validate(self, attrs):
        dob = attrs.get("date_of_birth") or (
            self.instance.date_of_birth if self.instance else None
        )
        last_donation = attrs.get("last_donation_date")
        if last_donation and dob and last_donation < dob:
            raise serializers.ValidationError(
                {"last_donation_date": "Last donation date cannot be before date of birth."}
            )
        return attrs

    def update(self, instance, validated_data):
        donor = super().update(instance, validated_data)
        user = donor.user
        updated_user = False

        if "latitude" in validated_data:
            user.latitude = validated_data["latitude"]
            updated_user = True
        if "longitude" in validated_data:
            user.longitude = validated_data["longitude"]
            updated_user = True

        if updated_user:
            user.save(update_fields=["latitude", "longitude"])

        return donor

    def create(self, validated_data):
        donor = super().create(validated_data)
        user = donor.user
        updated_user = False

        if "latitude" in validated_data:
            user.latitude = validated_data["latitude"]
            updated_user = True
        if "longitude" in validated_data:
            user.longitude = validated_data["longitude"]
            updated_user = True

        if updated_user:
            user.save(update_fields=["latitude", "longitude"])

        return donor


class EligibilityAgeCriteriaSerializer(serializers.Serializer):
    passed = serializers.BooleanField()
    value = serializers.IntegerField(allow_null=True)
    requirement = serializers.CharField()


class EligibilityWeightCriteriaSerializer(serializers.Serializer):
    passed = serializers.BooleanField()
    value_kg = serializers.FloatField(allow_null=True)
    requirement = serializers.CharField()


class EligibilityIntervalCriteriaSerializer(serializers.Serializer):
    passed = serializers.BooleanField()
    last_donation_date = serializers.CharField(allow_null=True)
    days_since_last_donation = serializers.IntegerField(allow_null=True)
    days_until_next_eligible = serializers.IntegerField()
    requirement = serializers.CharField()


class EligibilityCriteriaSerializer(serializers.Serializer):
    age = EligibilityAgeCriteriaSerializer()
    weight = EligibilityWeightCriteriaSerializer()
    donation_interval = EligibilityIntervalCriteriaSerializer()


class DonorEligibilityResponseSerializer(serializers.Serializer):
    is_eligible = serializers.BooleanField()
    criteria = EligibilityCriteriaSerializer()
    reasons = serializers.ListField(child=serializers.CharField())


class DonorContactRequestSerializer(serializers.ModelSerializer):
    """
    Representation of a donor contact access request.

    Donor phone/email are disclosed only when the request is APPROVED
    and the authenticated user is the specific authorized requester or
    the target donor.
    """
    donor_id = serializers.IntegerField(source="donor.id", read_only=True)
    donor_display = serializers.SerializerMethodField()
    donor_blood_group = serializers.CharField(
        source="donor.blood_group",
        read_only=True,
    )
    requester_id = serializers.IntegerField(
        source="requester.id",
        read_only=True,
    )
    requester_name = serializers.SerializerMethodField()
    requester_username = serializers.CharField(
        source="requester.username",
        read_only=True,
    )
    requester_role = serializers.CharField(
        source="requester.role",
        read_only=True,
    )
    blood_request_id = serializers.IntegerField(
        source="blood_request.id",
        read_only=True,
        allow_null=True,
    )
    donation_id = serializers.IntegerField(
        source="donation.id",
        read_only=True,
        allow_null=True,
    )
    donation_outcome_display = serializers.CharField(
        source="get_donation_outcome_display",
        read_only=True,
    )
    outcome_recorded_by_name = serializers.SerializerMethodField()
    contact_details = serializers.SerializerMethodField()

    class Meta:
        model = DonorContactRequest
        fields = [
            "id",
            "blood_request",
            "blood_request_id",
            "donor_id",
            "donor_display",
            "donor_blood_group",
            "requester_id",
            "requester_username",
            "requester_name",
            "requester_role",
            "hospital_name",
            "blood_group",
            "urgency",
            "message",
            "reason",
            "status",
            "responded_at",
            "donation",
            "donation_id",
            "donation_outcome",
            "donation_outcome_display",
            "outcome_recorded_at",
            "outcome_recorded_by",
            "outcome_recorded_by_name",
            "outcome_notes",
            "created_at",
            "updated_at",
            "contact_details",
        ]
        read_only_fields = [
            "id",
            "blood_request",
            "blood_request_id",
            "donor_id",
            "donor_display",
            "donor_blood_group",
            "requester_id",
            "requester_username",
            "requester_name",
            "requester_role",
            "status",
            "responded_at",
            "donation",
            "donation_id",
            "donation_outcome",
            "donation_outcome_display",
            "outcome_recorded_at",
            "outcome_recorded_by",
            "outcome_recorded_by_name",
            "created_at",
            "updated_at",
            "contact_details",
        ]

    def get_donor_display(self, obj):
        return f"Donor #{obj.donor_id}"

    def get_requester_name(self, obj):
        return obj.requester.full_name or obj.requester.username

    def get_outcome_recorded_by_name(self, obj):
        if obj.outcome_recorded_by:
            return (
                obj.outcome_recorded_by.full_name
                or obj.outcome_recorded_by.username
            )
        return None

    def get_contact_details(self, obj):
        if obj.status != ContactRequestStatus.APPROVED:
            return None

        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            return None

        # Contact information is disclosed only to the specific requester
        # or to the donor who owns the profile.
        if (
            user.id == obj.requester_id
            or (
                hasattr(user, "donor_profile")
                and user.donor_profile.id == obj.donor_id
            )
        ):
            return {
                "name": (
                    obj.donor.user.full_name
                    or obj.donor.user.username
                ),
                "phone": obj.donor.user.phone or "",
                "email": obj.donor.user.email,
                "blood_group": obj.donor.blood_group,
            }

        return None


class DonorContactRequestCreateSerializer(serializers.Serializer):
    """
    Input serializer for hospitals/clinical staff initiating a contact request.
    """
    donor_id = serializers.IntegerField(
        required=True,
        help_text="ID of the target Donor.",
    )
    blood_request_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Optional Blood Request ID.",
    )
    hospital_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        default="",
    )
    blood_group = serializers.ChoiceField(
        choices=BloodGroup.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    urgency = serializers.ChoiceField(
        choices=["NORMAL", "HIGH", "CRITICAL"],
        default="NORMAL",
        required=False,
    )
    message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        default="",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        min_length=5,
        default="",
        help_text="Clinical justification for accessing donor contact.",
    )

    def validate_donor_id(self, value):
        if not Donor.objects.filter(
            id=value,
            user__is_active=True,
        ).exists():
            raise serializers.ValidationError(
                "Target donor does not exist or is inactive."
            )
        return value

    def validate_reason(self, value):
        return value.strip()

    def validate_blood_request_id(self, value):
        if value is None:
            return value
        from apps.blood_requests.models import BloodRequest, RequestStatus
        from apps.accounts.models import UserRole
        user = self.context["request"].user
        if user.role != UserRole.HOSPITAL_STAFF or not BloodRequest.objects.filter(
            pk=value, hospital_staff=user,
            status__in=[RequestStatus.PENDING, RequestStatus.APPROVED],
        ).exists():
            raise serializers.ValidationError("Select an active blood request that you created.")
        return value

    def validate(self, attrs):
        if attrs.get("blood_request_id") and DonorContactRequest.objects.filter(
            blood_request_id=attrs["blood_request_id"], donor_id=attrs["donor_id"],
        ).exists():
            raise serializers.ValidationError("This donor already has a response for this blood request.")
        return attrs


class DonorContactRequestRespondSerializer(serializers.Serializer):
    """
    Input serializer for donors approving or declining a contact request.
    """
    action = serializers.ChoiceField(
        choices=[
            "APPROVE",
            "DECLINE",
            "APPROVED",
            "DECLINED",
            "ACCEPT",
            "ACCEPTED",
        ],
        help_text="Decision action: ACCEPT or DECLINE.",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        default="",
    )


class DonorPrivateContactSerializer(serializers.ModelSerializer):
    """
    Consent-protected representation of a donor's private contact details.
    Only disclosed when explicit approval has been granted to the requesting party.
    """
    user_id = serializers.ReadOnlyField(source="user.id")
    username = serializers.ReadOnlyField(source="user.username")
    full_name = serializers.SerializerMethodField()
    email = serializers.ReadOnlyField(source="user.email")
    phone = serializers.ReadOnlyField(source="user.phone")
    address = serializers.ReadOnlyField(source="user.address")

    class Meta:
        model = Donor
        fields = [
            "id",
            "user_id",
            "username",
            "full_name",
            "email",
            "phone",
            "address",
            "blood_group",
            "is_eligible",
        ]
        read_only_fields = fields

    def get_full_name(self, obj) -> str:
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return name if name else obj.user.username


class DonorOutcomeRecordSerializer(serializers.Serializer):
    """
    Input serializer for Hospital Staff recording the actual outcome
    of a donor donation interaction.
    """
    outcome = serializers.ChoiceField(
        choices=[
            DonationOutcome.COMPLETED,
            DonationOutcome.DID_NOT_HAPPEN,
        ],
        help_text="Recorded donation outcome: COMPLETED or DID_NOT_HAPPEN.",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        default="",
        help_text="Optional clinical or operational notes.",
    )
