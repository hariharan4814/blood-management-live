from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from apps.donors.models import BloodGroup, Donor
from .models import UserRole

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model representation (safe fields only).
    """
    hospital_name = serializers.CharField(source="hospital.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "role",
            "phone",
            "is_verified",
            "first_name",
            "last_name",
            "hospital",
            "hospital_name",
            "address",
            "latitude",
            "longitude",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "hospital_name", "date_joined"]


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for public user registration.
    Restricted strictly to DONOR and HOSPITAL_STAFF roles.
    Supports registering individual Donors and partner Hospitals with location data.
    """
    username = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Unique username (auto-generated from email if omitted)."
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="User password meeting system complexity requirements."
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Password confirmation to prevent typing errors."
    )
    role = serializers.ChoiceField(
        choices=[
            (UserRole.DONOR, "Donor"),
            (UserRole.HOSPITAL_STAFF, "Hospital"),
        ],
        default=UserRole.DONOR,
        help_text="Public registration role (DONOR or HOSPITAL_STAFF only)."
    )
    blood_group = serializers.ChoiceField(
        choices=BloodGroup.choices,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="ABO and Rh blood group (used when registering as DONOR)."
    )
    contact_person_name = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Contact person name for hospital staff registration."
    )
    hospital_name = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Official name of the partner hospital."
    )
    hospital = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Alternative alias for hospital name."
    )
    city = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="City where facility or donor is situated."
    )
    state = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="State or province."
    )
    address = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Physical street address."
    )
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        min_value=-90,
        max_value=90,
        help_text="Latitude coordinate (-90 to 90)."
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        min_value=-180,
        max_value=180,
        help_text="Longitude coordinate (-180 to 180)."
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "password",
            "password_confirm",
            "role",
            "phone",
            "blood_group",
            "contact_person_name",
            "hospital_name",
            "hospital",
            "city",
            "state",
            "address",
            "latitude",
            "longitude",
        ]
        read_only_fields = ["id"]

    def validate_role(self, value):
        allowed_roles = [UserRole.DONOR, UserRole.HOSPITAL_STAFF]
        if value not in allowed_roles:
            raise serializers.ValidationError(
                f"Public registration is only permitted for {', '.join(allowed_roles)}. "
                "Privileged roles (SUPER_ADMIN, BLOOD_BANK_ADMIN, LAB_TECHNICIAN) must be provisioned by an administrator."
            )
        return value

    def validate_username(self, value):
        if value and User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        if password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})

        # Ensure username exists
        username = (attrs.get("username") or "").strip()
        email = (attrs.get("email") or "").strip()
        if not username and email:
            base_user = email.split("@")[0].lower()
            candidate = base_user
            counter = 1
            while User.objects.filter(username__iexact=candidate).exists():
                candidate = f"{base_user}_{counter}"
                counter += 1
            attrs["username"] = candidate

        role = attrs.get("role", UserRole.DONOR)
        if role == UserRole.HOSPITAL_STAFF:
            lat = attrs.get("latitude")
            lng = attrs.get("longitude")
            errors = {}
            if lat is None:
                errors["latitude"] = "Latitude is required for hospital registration."
            if lng is None:
                errors["longitude"] = "Longitude is required for hospital registration."
            if errors:
                raise serializers.ValidationError(errors)

            hosp_name = (attrs.get("hospital_name") or attrs.get("hospital") or "").strip()
            if not hosp_name:
                contact_person = (attrs.get("contact_person_name") or "").strip()
                username_val = attrs.get("username") or "Facility"
                hosp_name = f"Hospital ({contact_person or username_val})"
            attrs["hospital_name"] = hosp_name
            attrs.pop("hospital", None)

        # Validate password strength using Django's configured validators
        temp_user = User(
            username=attrs.get("username"),
            email=attrs.get("email"),
            phone=attrs.get("phone", "")
        )
        validate_password(password, user=temp_user)

        return attrs

    def create(self, validated_data):
        from apps.blood_requests.models import Hospital

        validated_data.pop("password_confirm", None)
        password = validated_data.pop("password")
        blood_group = validated_data.pop("blood_group", None)
        contact_person = (validated_data.pop("contact_person_name", "") or "").strip()
        
        # Explicitly extract and remove both hospital_name and hospital string fields
        # to ensure validated_data never contains a duplicate 'hospital' string argument
        hosp_name = (validated_data.pop("hospital_name", "") or "").strip()
        legacy_hosp = (validated_data.pop("hospital", "") or "").strip()
        if not hosp_name and legacy_hosp:
            hosp_name = legacy_hosp

        city = (validated_data.pop("city", "") or "").strip()
        state = (validated_data.pop("state", "") or "").strip()
        address = validated_data.get("address", "")
        phone = validated_data.get("phone", "")
        latitude = validated_data.get("latitude", None)
        longitude = validated_data.get("longitude", None)

        if contact_person:
            parts = contact_person.split(" ", 1)
            validated_data["first_name"] = parts[0]
            validated_data["last_name"] = parts[1] if len(parts) > 1 else ""

        hospital_obj = None
        if validated_data.get("role") == UserRole.HOSPITAL_STAFF:
            if not hosp_name:
                hosp_name = f"Hospital ({validated_data.get('username', 'Facility')})"

            hospital_obj = Hospital.objects.filter(name__iexact=hosp_name).first()
            if not hospital_obj:
                hospital_obj = Hospital.objects.create(
                    name=hosp_name,
                    address=address or "",
                    city=city or "Chennai",
                    state=state or "Tamil Nadu",
                    contact_number=phone or "",
                    email=validated_data.get("email", ""),
                    latitude=latitude,
                    longitude=longitude,
                    is_active=True,
                )
            else:
                # Update location if missing
                if latitude and longitude and (not hospital_obj.latitude or not hospital_obj.longitude):
                    hospital_obj.latitude = latitude
                    hospital_obj.longitude = longitude
                    hospital_obj.save(update_fields=["latitude", "longitude"])

        user = User.objects.create_user(
            password=password,
            is_verified=False,
            hospital=hospital_obj,
            **validated_data
        )

        if user.role == UserRole.DONOR:
            bg = blood_group if blood_group else BloodGroup.O_POSITIVE
            Donor.objects.create(
                user=user,
                blood_group=bg,
                date_of_birth=date(2000, 1, 1),
                weight_kg=Decimal("60.00"),
                latitude=latitude,
                longitude=longitude,
            )

        return user


class UserAdminCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for Super Admin user creation (POST /api/users/).
    Supports creating accounts for all roles (SUPER_ADMIN, BLOOD_BANK_ADMIN, LAB_TECHNICIAN, HOSPITAL_STAFF, DONOR).
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Initial password meeting system complexity requirements."
    )
    role = serializers.ChoiceField(
        choices=UserRole.choices,
        default=UserRole.DONOR,
        help_text="Assigned platform role."
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "password",
            "role",
            "phone",
            "first_name",
            "last_name",
            "is_active",
            "is_verified",
        ]
        read_only_fields = ["id"]

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value.strip()).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value.strip()

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value.strip()).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value.strip().lower()

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(
            password=password,
            **validated_data
        )
        return user


class UserAdminUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for Super Admin user updates (PATCH /api/users/{id}/).
    """
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "role",
            "phone",
            "is_verified",
            "first_name",
            "last_name",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]

    def validate_username(self, value):
        user_id = self.instance.id if self.instance else None
        if User.objects.filter(username__iexact=value).exclude(id=user_id).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        user_id = self.instance.id if self.instance else None
        if User.objects.filter(email__iexact=value).exclude(id=user_id).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer that embeds user information in token claims
    and returns user payload in the response body.
    Supports authenticating via either username or email address.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Custom claims
        token["username"] = user.username
        token["email"] = user.email
        token["role"] = user.role
        token["is_verified"] = user.is_verified
        return token

    def validate(self, attrs):
        # Allow logging in with either username or email
        username_or_email = attrs.get("username")
        if username_or_email and "@" in username_or_email:
            user_by_email = User.objects.filter(email__iexact=username_or_email.strip()).first()
            if user_by_email:
                attrs["username"] = user_by_email.username

        data = super().validate(attrs)
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": self.user.role,
            "phone": self.user.phone,
            "is_verified": self.user.is_verified,
            "hospital": self.user.hospital_id if self.user.hospital_id else None,
            "hospital_name": self.user.hospital.name if self.user.hospital else None,
        }
        return data
