from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import UserRole
from apps.blood_requests.models import Hospital
from apps.inventory.models import BloodBank
from .models import Review, ReviewStatus, ReviewTargetType


class ReviewUserBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.role == UserRole.DONOR:
            from apps.donors.privacy import public_username
            data["username"] = public_username(instance)
            data["full_name"] = public_username(instance)
        return data


class ReviewSerializer(serializers.ModelSerializer):
    reviewer = ReviewUserBriefSerializer(read_only=True)
    reviewed_by = ReviewUserBriefSerializer(read_only=True)
    target_type = serializers.CharField(read_only=True)
    target_name = serializers.CharField(read_only=True)
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "reviewer",
            "hospital",
            "blood_bank",
            "target_type",
            "target_name",
            "target_id",
            "rating",
            "comment",
            "status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reviewer",
            "target_type",
            "target_name",
            "target_id",
            "status",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]

    def get_target_id(self, obj) -> int | None:
        return obj.hospital_id or obj.blood_bank_id


class ReviewCreateSerializer(serializers.Serializer):
    hospital = serializers.PrimaryKeyRelatedField(
        queryset=Hospital.objects.all(),
        required=False,
        allow_null=True
    )
    blood_bank = serializers.PrimaryKeyRelatedField(
        queryset=BloodBank.objects.all(),
        required=False,
        allow_null=True
    )
    rating = serializers.IntegerField(
        min_value=1,
        max_value=5,
        required=True,
        error_messages={
            "min_value": "Rating must be between 1 and 5 stars.",
            "max_value": "Rating must be between 1 and 5 stars.",
        }
    )
    comment = serializers.CharField(
        required=True,
        min_length=3,
        max_length=2000,
        error_messages={
            "blank": "Review comment cannot be empty.",
            "min_length": "Review comment must be at least 3 characters long.",
        }
    )

    def validate_comment(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Review comment cannot be empty or whitespace only.")
        return cleaned

    def validate(self, attrs):
        hospital = attrs.get("hospital")
        blood_bank = attrs.get("blood_bank")

        if not hospital and not blood_bank:
            raise serializers.ValidationError("A review must specify either a hospital or a blood bank.")
        if hospital and blood_bank:
            raise serializers.ValidationError("A review cannot target both a hospital and a blood bank.")

        # Ensure target facility is active
        if hospital and not hospital.is_active:
            raise serializers.ValidationError("Cannot review an inactive hospital.")
        if blood_bank and not blood_bank.is_active:
            raise serializers.ValidationError("Cannot review an inactive blood bank.")

        return attrs

    def create(self, validated_data):
        reviewer = self.context["request"].user
        hospital = validated_data.get("hospital")
        blood_bank = validated_data.get("blood_bank")
        rating = validated_data["rating"]
        comment = validated_data["comment"]

        # Duplicate handling: Check for existing review from this user on this entity
        lookup = {"reviewer": reviewer}
        if hospital:
            lookup["hospital"] = hospital
        else:
            lookup["blood_bank"] = blood_bank

        existing = Review.objects.filter(**lookup).first()
        if existing:
            # Update existing review and reset status to PENDING for re-moderation
            existing.rating = rating
            existing.comment = comment
            existing.status = ReviewStatus.PENDING
            existing.reviewed_by = None
            existing.reviewed_at = None
            existing.rejection_reason = ""
            existing.save()
            return existing

        return Review.objects.create(
            reviewer=reviewer,
            hospital=hospital,
            blood_bank=blood_bank,
            rating=rating,
            comment=comment,
            status=ReviewStatus.PENDING,
        )


class ReviewModerateSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500
    )
