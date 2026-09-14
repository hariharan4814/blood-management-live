from decimal import Decimal
from django.db.models import Avg
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.blood_requests.models import Hospital
from apps.donors.models import Donor
from apps.emergency_sos.compatibility import calculate_haversine_distance_km
from apps.inventory.models import BloodBank
from .models import ReviewStatus

from .nearby_serializers import (
    NearbyBloodBankSerializer,
    NearbyDonorSerializer,
    NearbyHospitalSerializer,
    NearbyQueryParamSerializer,
    NearbySearchResultsSerializer,
)

# Roles permitted to query nearby voluntary donors
AUTHORIZED_DONOR_SEARCH_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.BLOOD_BANK_ADMIN,
    UserRole.HOSPITAL_STAFF,
    UserRole.LAB_TECHNICIAN,
    UserRole.DONOR,
}


class NearbySearchView(APIView):
    """
    Unified Proximity Search API.
    Calculates great-circle distance (Haversine formula) to locate nearby
    Blood Banks, Hospitals, and eligible Donors within a user-defined radius.
    Enforces privacy controls and strict role-based access for donor discovery.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Search Nearby Resources",
        description=(
            "Find nearby Blood Banks, Hospitals, and Donors within a given radius (km). "
            "Authoritative distance is computed on the backend using the Haversine formula. "
            "Donor discovery is restricted to SUPER_ADMIN, BLOOD_BANK_ADMIN, and HOSPITAL_STAFF, "
            "with coordinates fuzzed to 2 decimal places for privacy."
        ),
        parameters=[
            OpenApiParameter("lat", float, description="Center latitude coordinate (-90 to 90)", required=True),
            OpenApiParameter("lng", float, description="Center longitude coordinate (-180 to 180)", required=True),
            OpenApiParameter("radius", float, description="Search radius in km (default 10, max 100)", required=False),
            OpenApiParameter("type", str, description="Types: 'all' or comma-separated 'donors,hospitals,blood_banks'", required=False),
            OpenApiParameter("blood_group", str, description="Optional blood group filter (e.g. O+, A-)", required=False),
            OpenApiParameter("only_eligible", bool, description="Only medically eligible donors (default true)", required=False),
        ],
        responses={
            200: NearbySearchResultsSerializer,
            400: "Invalid query parameters or coordinates",
            401: "Authentication credentials required",
            403: "Unauthorized entity search",
        },
        tags=["Nearby Proximity & Map"],
    )
    def get(self, request):
        query_serializer = NearbyQueryParamSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        validated = query_serializer.validated_data

        center_lat = float(validated["lat"]) if validated.get("lat") is not None else None
        center_lng = float(validated["lng"]) if validated.get("lng") is not None else None
        radius_km = float(validated.get("radius", 10.0))
        type_param = validated.get("type", "all").strip().lower()
        blood_group_filter = validated.get("blood_group")
        only_eligible = validated.get("only_eligible", True)

        all_donors = validated.get("all_donors", False)
        all_blood_banks = validated.get("all_blood_banks", False)
        all_hospitals = validated.get("all_hospitals", False)

        type_tokens = [t.strip() for t in type_param.split(",") if t.strip()]
        search_all = "all" in type_tokens or not type_tokens

        include_donors = all_donors or search_all or "donors" in type_tokens
        include_hospitals = all_hospitals or search_all or "hospitals" in type_tokens
        include_blood_banks = (
            all_blood_banks or search_all or "blood_banks" in type_tokens or "bloodbanks" in type_tokens
        )

        user = request.user
        is_super_admin = getattr(user, "is_super_admin", False) or user.is_superuser or user.role == UserRole.SUPER_ADMIN
        can_view_donors = (
            is_super_admin
            or user.role in AUTHORIZED_DONOR_SEARCH_ROLES
        )

        # STRICT RBAC: Only Super Admin can request all_donors or all_blood_banks administrative layers
        if all_donors and not is_super_admin:
            return Response(
                {"detail": "Showing all registered donors is restricted to Super Administrators."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if all_blood_banks and not is_super_admin:
            return Response(
                {"detail": "Showing all registered blood banks is restricted to Super Administrators."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # If non-super admin explicitly asked ONLY for donors but is unauthorized, return 403
        if include_donors and not can_view_donors:
            if type_tokens == ["donors"]:
                return Response(
                    {"detail": "Donor discovery is restricted to authorized clinical and administrative personnel."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        blood_banks_results = []
        hospitals_results = []
        donors_results = []
        donor_access_note = None

        # 1. Blood Banks
        if include_blood_banks:
            banks_qs = BloodBank.objects.filter(
                latitude__isnull=False,
                longitude__isnull=False,
            )
            if not is_super_admin and not all_blood_banks:
                banks_qs = banks_qs.filter(is_active=True)

            for bank in banks_qs:
                dist = (
                    calculate_haversine_distance_km(center_lat, center_lng, bank.latitude, bank.longitude)
                    if (center_lat is not None and center_lng is not None)
                    else None
                )
                if not all_blood_banks and (dist is None or dist > radius_km):
                    continue

                avg_rating = bank.reviews.filter(status=ReviewStatus.APPROVED).aggregate(Avg("rating"))["rating__avg"]
                rating = round(float(avg_rating), 1) if avg_rating is not None else None
                review_count = bank.reviews.filter(status=ReviewStatus.APPROVED).count()
                blood_banks_results.append({
                    "id": bank.id,
                    "name": bank.name,
                    "address": bank.address,
                    "city": bank.city,
                    "state": bank.state,
                    "contact_number": bank.contact_number,
                    "email": bank.email,
                    "capacity": bank.capacity,
                    "latitude": float(bank.latitude),
                    "longitude": float(bank.longitude),
                    "is_active": bank.is_active,
                    "distance_km": round(dist, 2) if dist is not None else None,
                    "rating": rating,
                    "review_count": review_count,
                })
            if center_lat is not None and center_lng is not None:
                blood_banks_results.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0))

        # 2. Hospitals
        if include_hospitals:
            hospitals_qs = Hospital.objects.filter(
                latitude__isnull=False,
                longitude__isnull=False,
            )
            if not is_super_admin:
                hospitals_qs = hospitals_qs.filter(is_active=True)

            for hospital in hospitals_qs:
                dist = (
                    calculate_haversine_distance_km(center_lat, center_lng, hospital.latitude, hospital.longitude)
                    if (center_lat is not None and center_lng is not None)
                    else None
                )
                if not all_hospitals and (dist is None or dist > radius_km):
                    continue

                avg_rating = hospital.reviews.filter(status=ReviewStatus.APPROVED).aggregate(Avg("rating"))["rating__avg"]
                rating = round(float(avg_rating), 1) if avg_rating is not None else None
                review_count = hospital.reviews.filter(status=ReviewStatus.APPROVED).count()
                hospitals_results.append({
                    "id": hospital.id,
                    "name": hospital.name,
                    "address": hospital.address,
                    "city": hospital.city,
                    "state": hospital.state,
                    "contact_number": hospital.contact_number,
                    "email": hospital.email,
                    "beds": hospital.beds,
                    "latitude": float(hospital.latitude),
                    "longitude": float(hospital.longitude),
                    "is_active": hospital.is_active,
                    "distance_km": round(dist, 2) if dist is not None else None,
                    "rating": rating,
                    "review_count": review_count,
                })
            if center_lat is not None and center_lng is not None:
                hospitals_results.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0))

        # 3. Donors (with privacy protection)
        if include_donors:
            if can_view_donors:
                donor_qs = Donor.objects.select_related("user").filter(
                    user__is_active=True,
                    latitude__isnull=False,
                    longitude__isnull=False,
                )
                if blood_group_filter:
                    donor_qs = donor_qs.filter(blood_group__iexact=blood_group_filter)

                for donor in donor_qs:
                    # Use the same approximate point for matching and distances;
                    # exact distances from arbitrary centers enable triangulation.
                    fuzzed_lat = round(float(donor.latitude), 2)
                    fuzzed_lng = round(float(donor.longitude), 2)
                    dist = (
                        calculate_haversine_distance_km(center_lat, center_lng, fuzzed_lat, fuzzed_lng)
                        if (center_lat is not None and center_lng is not None)
                        else None
                    )
                    if not all_donors and (dist is None or dist > radius_km):
                        continue

                    eligibility = donor.calculate_eligibility()
                    is_eligible = eligibility.get("is_eligible", False)

                    # In standard proximity search with only_eligible=True, filter out ineligible donors.
                    # In all_donors mode, include all donors and label is_eligible accurately.
                    if not all_donors and only_eligible and not is_eligible:
                        continue

                    # Privacy fuzzing: round coordinate to 2 decimals (~1.1 km precision)
                    fuzzed_lat = round(float(donor.latitude), 2)
                    fuzzed_lng = round(float(donor.longitude), 2)

                    donors_results.append({
                        "id": f"DONOR-{donor.id}",
                        "donor_id": donor.id,
                        "blood_group": donor.blood_group,
                        "is_eligible": is_eligible,
                        "age": donor.age,
                        "last_donation_date": donor.last_donation_date,
                        "distance_km": round(dist, 2) if dist is not None else None,
                        "approximate_latitude": fuzzed_lat,
                        "approximate_longitude": fuzzed_lng,
                    })
                if center_lat is not None and center_lng is not None:
                    donors_results.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0))
            else:
                donor_access_note = "Donor discovery is restricted to authorized clinical and administrative personnel."

        total_count = (
            len(blood_banks_results) + len(hospitals_results) + len(donors_results)
        )

        response_data = {
            "search_center": {
                "latitude": center_lat,
                "longitude": center_lng,
                "radius_km": radius_km,
            } if (center_lat is not None and center_lng is not None) else None,
            "results": {
                "donors": donors_results,
                "hospitals": hospitals_results,
                "blood_banks": blood_banks_results,
            },
            "total_count": total_count,
        }
        if donor_access_note:
            response_data["donor_access_note"] = donor_access_note

        return Response(response_data, status=status.HTTP_200_OK)
