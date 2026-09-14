from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.donors.models import BloodGroup, Donor
from .models import UserRole
from .validators import validate_phone_number, validate_profile_image

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for retrieving and updating personal user profile details.
    Restricts edits to safe fields only (first_name, last_name, email, phone, blood_group).
    """
    full_name = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    profile_image_url = serializers.SerializerMethodField(read_only=True)
    blood_group = serializers.ChoiceField(
        choices=BloodGroup.choices,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="ABO and Rh blood group for the user's donor profile.",
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "role_display",
            "phone",
            "blood_group",
            "latitude",
            "longitude",
            "address",
            "profile_image",
            "profile_image_url",
            "is_verified",
            "is_active",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "username",
            "role",
            "role_display",
            "full_name",
            "profile_image",
            "profile_image_url",
            "is_verified",
            "is_active",
            "date_joined",
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_profile_image_url(self, obj):
        if obj.profile_image and hasattr(obj.profile_image, "url"):
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return None

    def validate_first_name(self, value):
        if value is not None:
            return value.strip()
        return ""

    def validate_last_name(self, value):
        if value is not None:
            return value.strip()
        return ""

    def validate_email(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Email address cannot be empty.")

        clean_email = value.strip().lower()
        user_id = self.instance.id if self.instance else None
        if User.objects.filter(email__iexact=clean_email).exclude(id=user_id).exists():
            raise serializers.ValidationError("A user with this email address already exists.")

        return clean_email

    def validate_phone(self, value):
        if not value or not str(value).strip():
            return None
        try:
            return validate_phone_number(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages[0] if hasattr(e, "messages") else str(e))

    def validate(self, attrs):
        # Strict security filter: strip out any administrative or security fields if present
        protected_fields = [
            "role", "is_staff", "is_superuser", "is_verified",
            "is_active", "password", "date_joined", "last_login", "id"
        ]
        for field in protected_fields:
            attrs.pop(field, None)
        return attrs

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if hasattr(instance, "donor_profile") and instance.donor_profile:
            ret["blood_group"] = instance.donor_profile.blood_group
        else:
            ret["blood_group"] = None
        return ret

    def update(self, instance, validated_data):
        blood_group = validated_data.pop("blood_group", None)
        user = super().update(instance, validated_data)
        # Bidirectional sync: if user has a donor profile and coordinates/blood_group updated, sync to donor profile
        if hasattr(user, "donor_profile") and user.donor_profile:
            donor = user.donor_profile
            updated_fields = []
            if "latitude" in validated_data:
                donor.latitude = validated_data["latitude"]
                updated_fields.append("latitude")
            if "longitude" in validated_data:
                donor.longitude = validated_data["longitude"]
                updated_fields.append("longitude")
            if blood_group is not None:
                donor.blood_group = blood_group
                updated_fields.append("blood_group")
            if updated_fields:
                donor.save(update_fields=updated_fields)
        elif blood_group:
            Donor.objects.create(
                user=user,
                blood_group=blood_group,
                latitude=user.latitude,
                longitude=user.longitude,
            )
        return user


class ProfileImageUploadSerializer(serializers.Serializer):
    """
    Serializer for multipart/form-data profile image upload.
    """
    profile_image = serializers.ImageField(
        required=True,
        help_text="Image file in JPEG, PNG, or WEBP format (max 2 MB)."
    )

    def validate_profile_image(self, value):
        try:
            return validate_profile_image(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages[0] if hasattr(e, "messages") else str(e))
