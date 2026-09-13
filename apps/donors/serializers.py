from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from .models import Donor, BloodGroup


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
        read_only_fields = ["id", "user_id", "username", "email", "phone", "age", "is_eligible", "created_at", "updated_at"]


class DonorProfileInputSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating donor profiles.
    """
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
        if value is not None:
            today = timezone.now().date()
            if value > today:
                raise serializers.ValidationError("Last donation date cannot be in the future.")
        return value

    def validate(self, attrs):
        dob = attrs.get("date_of_birth") or (self.instance.date_of_birth if self.instance else None)
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
    Representation serializer for donor contact requests.
    """
    requester_id = serializers.ReadOnlyField(source="requester.id")
    requester_username = serializers.ReadOnlyField(source="requester.username")
    requester_name = serializers.SerializerMethodField()
    requester_role = serializers.ReadOnlyField(source="requester.role")
    donor_id = serializers.ReadOnlyField(source="donor.id")
    donor_blood_group = serializers.ReadOnlyField(source="donor.blood_group")

    class Meta:
        from .models import DonorContactRequest
        model = DonorContactRequest
        fields = [
            "id",
            "requester_id",
            "requester_username",
            "requester_name",
            "requester_role",
            "donor_id",
            "donor_blood_group",
            "reason",
            "status",
            "responded_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_requester_name(self, obj) -> str:
        name = f"{obj.requester.first_name} {obj.requester.last_name}".strip()
        return name if name else obj.requester.username


class DonorContactRequestCreateSerializer(serializers.Serializer):
    """
    Input serializer for submitting a new donor contact access request.
    """
    donor_id = serializers.IntegerField(required=True, help_text="ID of target Donor.")
    reason = serializers.CharField(
        required=True,
        min_length=5,
        help_text="Clinical justification or emergency need for accessing donor contact."
    )

    def validate_donor_id(self, value):
        if not Donor.objects.filter(id=value).exists():
            raise serializers.ValidationError("Designated donor profile does not exist.")
        return value

    def validate_reason(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("A non-empty reason is required.")
        return value.strip()


class DonorContactRequestRespondSerializer(serializers.Serializer):
    """
    Input serializer for donors to accept or decline a contact request.
    """
    status = serializers.ChoiceField(
        choices=["APPROVED", "DECLINED"],
        required=True,
        help_text="Decision response: APPROVED or DECLINED."
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
            "latitude",
            "longitude",
            "is_eligible",
        ]
        read_only_fields = fields

    def get_full_name(self, obj) -> str:
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return name if name else obj.user.username

