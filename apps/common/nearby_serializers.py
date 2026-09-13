from decimal import Decimal
from rest_framework import serializers
from apps.donors.models import BloodGroup


class NearbyQueryParamSerializer(serializers.Serializer):
    """
    Validates geographical search center coordinates and filters.
    """
    lat = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90.000000"),
        max_value=Decimal("90.000000"),
        required=True,
        help_text="Center latitude coordinate (-90.0 to 90.0).",
    )
    lng = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180.000000"),
        max_value=Decimal("180.000000"),
        required=True,
        help_text="Center longitude coordinate (-180.0 to 180.0).",
    )
    radius = serializers.FloatField(
        required=False,
        default=10.0,
        min_value=0.5,
        max_value=100.0,
        help_text="Search radius in kilometers (default 10 km, max 100 km).",
    )
    type = serializers.CharField(
        required=False,
        default="all",
        help_text="Entity types to include: 'all' or comma-separated 'donors,hospitals,blood_banks'.",
    )
    blood_group = serializers.ChoiceField(
        choices=BloodGroup.choices,
        required=False,
        allow_blank=True,
        help_text="Filter donors by blood group (e.g. O+, A-).",
    )
    only_eligible = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Filter donors to only medically eligible individuals.",
    )
    all_hospitals = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Return all registered hospitals regardless of radius.",
    )


class NearbyDonorSerializer(serializers.Serializer):
    """
    Privacy-preserving representation of a nearby blood donor.
    Exact residential address, full name, phone number, and precise GPS coordinates are withheld.
    """
    id = serializers.CharField(help_text="Identifier format: DONOR-{id}")
    donor_id = serializers.IntegerField()
    blood_group = serializers.CharField()
    is_eligible = serializers.BooleanField()
    age = serializers.IntegerField(allow_null=True)
    last_donation_date = serializers.DateField(allow_null=True)
    distance_km = serializers.FloatField(help_text="Great-circle distance in kilometers.")
    approximate_latitude = serializers.FloatField(help_text="Fuzzed coordinate (~1.1 km resolution).")
    approximate_longitude = serializers.FloatField(help_text="Fuzzed coordinate (~1.1 km resolution).")


class NearbyHospitalSerializer(serializers.Serializer):
    """
    Representation of a partner hospital facility with verified coordinates.
    """
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    contact_number = serializers.CharField()
    email = serializers.EmailField()
    beds = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    distance_km = serializers.FloatField()
    rating = serializers.FloatField(allow_null=True, required=False)
    review_count = serializers.IntegerField(default=0, required=False)


class NearbyBloodBankSerializer(serializers.Serializer):
    """
    Representation of an active blood bank facility with verified coordinates.
    """
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    contact_number = serializers.CharField()
    email = serializers.EmailField()
    capacity = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    distance_km = serializers.FloatField()
    rating = serializers.FloatField(allow_null=True, required=False)
    review_count = serializers.IntegerField(default=0, required=False)


class NearbySearchResultsSerializer(serializers.Serializer):
    """
    Composite response for nearby proximity search.
    """
    search_center = serializers.DictField()
    results = serializers.DictField()
    total_count = serializers.IntegerField()
    donor_access_note = serializers.CharField(required=False, allow_null=True)
