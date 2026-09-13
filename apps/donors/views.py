from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from apps.accounts.models import UserRole
from apps.accounts.permissions import IsDonor, IsSuperAdmin, HasRoles
from apps.notifications.services import create_notification
from apps.notifications.models import NotificationType
from .models import Donor, BloodGroup, DonorContactRequest, ContactRequestStatus
from .serializers import (
    DonorProfileSerializer,
    DonorProfileInputSerializer,
    DonorEligibilityResponseSerializer,
    DonorContactRequestSerializer,
    DonorContactRequestCreateSerializer,
    DonorContactRequestRespondSerializer,
    DonorPrivateContactSerializer,
)


@extend_schema_view(
    get=extend_schema(
        summary="Get Current Donor Profile",
        description="Retrieve the profile of the currently authenticated donor.",
        responses={
            200: DonorProfileSerializer,
            404: OpenApiResponse(description="Donor profile has not been completed yet."),
        },
        tags=["Donor Management"],
    ),
    put=extend_schema(
        summary="Create / Full Update Donor Profile",
        description="Create or fully update the donor profile for the authenticated donor.",
        request=DonorProfileInputSerializer,
        responses={200: DonorProfileSerializer, 201: DonorProfileSerializer},
        tags=["Donor Management"],
    ),
    patch=extend_schema(
        summary="Partial Update Donor Profile",
        description="Partially update donor attributes (e.g. blood group, weight, location coordinates, last donation date).",
        request=DonorProfileInputSerializer,
        responses={200: DonorProfileSerializer, 201: DonorProfileSerializer},
        tags=["Donor Management"],
    ),
    post=extend_schema(
        summary="Create Donor Profile",
        description="Create donor profile for authenticated donor if not already existing.",
        request=DonorProfileInputSerializer,
        responses={201: DonorProfileSerializer, 400: OpenApiResponse(description="Validation error or profile already exists.")},
        tags=["Donor Management"],
    )
)
class DonorMeProfileView(APIView):
    """
    Profile endpoint for the authenticated DONOR.
    Allows retrieval and seamless creation/updating of the donor profile.
    """
    permission_classes = [IsDonor]

    def get(self, request):
        donor = Donor.objects.filter(user=request.user).first()
        if not donor:
            return Response(
                {"detail": "Donor profile not found. Please complete your donor profile."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DonorProfileSerializer(donor)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        return self._save_profile(request, partial=False)

    def patch(self, request):
        return self._save_profile(request, partial=True)

    def post(self, request):
        if Donor.objects.filter(user=request.user).exists():
            return Response(
                {"detail": "Donor profile already exists. Use PUT or PATCH to update."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._save_profile(request, partial=False)

    def _save_profile(self, request, partial=False):
        donor = Donor.objects.filter(user=request.user).first()
        is_new = donor is None

        save_data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if is_new:
            if not save_data.get("blood_group"):
                save_data["blood_group"] = BloodGroup.O_POSITIVE
            if not save_data.get("date_of_birth"):
                save_data["date_of_birth"] = "2000-01-01"
            if not save_data.get("weight_kg"):
                save_data["weight_kg"] = "60.00"

        serializer = DonorProfileInputSerializer(
            instance=donor,
            data=save_data,
            partial=partial if not is_new else False,
        )
        serializer.is_valid(raise_exception=True)

        if is_new:
            donor = serializer.save(user=request.user)
            res_status = status.HTTP_201_CREATED
        else:
            donor = serializer.save()
            res_status = status.HTTP_200_OK

        return Response(DonorProfileSerializer(donor).data, status=res_status)


@extend_schema_view(
    get=extend_schema(
        summary="Check Current Donor Eligibility",
        description="Dynamically evaluates and returns the donor's medical eligibility status and criteria breakdown (age, weight, 90-day cooldown).",
        responses={
            200: DonorEligibilityResponseSerializer,
            404: OpenApiResponse(description="Donor profile not found."),
        },
        tags=["Donor Management"],
    )
)
class DonorMeEligibilityView(APIView):
    """
    Dynamically computes donation eligibility for the authenticated DONOR.
    """
    permission_classes = [IsDonor]

    def get(self, request):
        donor = Donor.objects.filter(user=request.user).first()
        if not donor:
            return Response(
                {"detail": "Donor profile not found. Please complete your profile to check eligibility."},
                status=status.HTTP_404_NOT_FOUND,
            )
        eligibility_data = donor.calculate_eligibility()
        return Response(eligibility_data, status=status.HTTP_200_OK)


# ========================================================
# SUPER ADMIN DONOR ADMINISTRATION ENDPOINTS
# ========================================================

@extend_schema_view(
    get=extend_schema(
        summary="List All Donors (Admin)",
        description="List all donor profiles with pagination and optional filtering by blood group. Restricted to Super Administrators.",
        responses={200: DonorProfileSerializer(many=True)},
        tags=["Donor Management (Admin)"],
    )
)
class DonorAdminListView(generics.ListAPIView):
    """
    Super Admin and Blood Bank Admin endpoint to inspect donor records across the platform.
    """
    serializer_class = DonorProfileSerializer
    permission_classes = [HasRoles(UserRole.SUPER_ADMIN, UserRole.BLOOD_BANK_ADMIN)]

    def get_queryset(self):
        queryset = Donor.objects.select_related("user").all().order_by("-created_at")
        blood_group = self.request.query_params.get("blood_group")
        if blood_group:
            queryset = queryset.filter(blood_group__iexact=blood_group)
        return queryset


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve Donor Profile (Admin)",
        description="Retrieve a specific donor's profile by ID. Restricted to Super Administrators and Blood Bank Administrators.",
        responses={200: DonorProfileSerializer},
        tags=["Donor Management (Admin)"],
    )
)
class DonorAdminDetailView(generics.RetrieveAPIView):
    """
    Super Admin and Blood Bank Admin endpoint to view an individual donor profile.
    """
    queryset = Donor.objects.select_related("user").all()
    serializer_class = DonorProfileSerializer
    permission_classes = [HasRoles(UserRole.SUPER_ADMIN, UserRole.BLOOD_BANK_ADMIN)]


# ========================================================
# DONOR CONTACT CONSENT & PRIVACY VIEWS
# ========================================================

@extend_schema_view(
    get=extend_schema(
        summary="List Donor Contact Requests",
        description="List contact access requests sent by the current user or received if the user is a registered donor.",
        responses={200: DonorContactRequestSerializer(many=True)},
        tags=["Donor Contact Consent"],
    ),
    post=extend_schema(
        summary="Request Donor Contact Access",
        description="Submit an explicit contact request to a donor. Generates an in-app notification to the donor.",
        request=DonorContactRequestCreateSerializer,
        responses={
            201: DonorContactRequestSerializer,
            400: OpenApiResponse(description="Validation error or self-request."),
        },
        tags=["Donor Contact Consent"],
    ),
)
class DonorContactRequestListCreateView(APIView):
    """
    Handles submitting and listing donor contact consent requests.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role_filter = request.query_params.get("view_as")

        # Check if user has a donor profile
        donor_profile = Donor.objects.filter(user=user).first()

        if donor_profile and role_filter != "requester":
            # Return requests received by this donor
            requests_qs = DonorContactRequest.objects.filter(donor=donor_profile)
        else:
            # Return requests sent by this user
            requests_qs = DonorContactRequest.objects.filter(requester=user)

        status_param = request.query_params.get("status")
        if status_param:
            requests_qs = requests_qs.filter(status__iexact=status_param)

        requests_qs = requests_qs.select_related("requester", "donor__user").order_by("-created_at")
        serializer = DonorContactRequestSerializer(requests_qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DonorContactRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        donor_id = serializer.validated_data["donor_id"]
        reason = serializer.validated_data["reason"]
        donor = Donor.objects.select_related("user").filter(id=donor_id).first()

        if not donor:
            return Response({"detail": "Donor not found."}, status=status.HTTP_404_NOT_FOUND)

        if donor.user_id == request.user.id:
            return Response(
                {"detail": "You cannot request contact details for your own donor profile."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for existing pending request
        existing = DonorContactRequest.objects.filter(
            requester=request.user,
            donor=donor,
            status=ContactRequestStatus.PENDING,
        ).first()
        if existing:
            return Response(
                {"detail": "You already have a pending contact request for this donor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        contact_req = DonorContactRequest.objects.create(
            requester=request.user,
            donor=donor,
            reason=reason,
            status=ContactRequestStatus.PENDING,
        )

        # Create in-app notification for the target donor
        requester_label = request.user.first_name or request.user.username
        if request.user.role == UserRole.HOSPITAL_STAFF and request.user.hospital:
            requester_label = f"{request.user.hospital.name} staff ({requester_label})"

        create_notification(
            recipient=donor.user,
            title="New Donor Contact Request",
            message=f"{requester_label} has requested your contact details. Reason: {reason}",
            notification_type=NotificationType.GENERAL,
        )

        return Response(
            DonorContactRequestSerializer(contact_req).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    post=extend_schema(
        summary="Respond to Donor Contact Request",
        description="Accept (APPROVED) or Decline (DECLINED) a contact access request. Restricted to the requested Donor.",
        request=DonorContactRequestRespondSerializer,
        responses={
            200: DonorContactRequestSerializer,
            403: OpenApiResponse(description="Only the targeted donor can respond."),
            404: OpenApiResponse(description="Request not found."),
        },
        tags=["Donor Contact Consent"],
    ),
    patch=extend_schema(
        summary="Respond to Donor Contact Request",
        description="Accept (APPROVED) or Decline (DECLINED) a contact access request. Restricted to the requested Donor.",
        request=DonorContactRequestRespondSerializer,
        responses={
            200: DonorContactRequestSerializer,
            403: OpenApiResponse(description="Only the targeted donor can respond."),
            404: OpenApiResponse(description="Request not found."),
        },
        tags=["Donor Contact Consent"],
    ),
)
class DonorContactRequestRespondView(APIView):
    """
    Allows a donor to Accept or Decline a contact access request.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        return self._handle_response(request, pk)

    def patch(self, request, pk):
        return self._handle_response(request, pk)

    def _handle_response(self, request, pk):
        contact_req = DonorContactRequest.objects.select_related("donor__user", "requester").filter(pk=pk).first()
        if not contact_req:
            return Response({"detail": "Contact request not found."}, status=status.HTTP_404_NOT_FOUND)

        # Strictly enforce that only the target donor can respond
        if contact_req.donor.user_id != request.user.id:
            return Response(
                {"detail": "Only the target donor has authority to respond to this consent request."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = DonorContactRequestRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data["status"]

        contact_req.status = decision
        contact_req.responded_at = timezone.now()
        contact_req.save(update_fields=["status", "responded_at", "updated_at"])

        # Notify the requester of the decision
        donor_name = contact_req.donor.user.first_name or f"Donor #{contact_req.donor_id}"
        if decision == ContactRequestStatus.APPROVED:
            create_notification(
                recipient=contact_req.requester,
                title="Contact Request Approved",
                message=f"{donor_name} accepted your contact request. You can now access their permitted contact details.",
                notification_type=NotificationType.GENERAL,
            )
        else:
            create_notification(
                recipient=contact_req.requester,
                title="Contact Request Declined",
                message=f"{donor_name} declined your contact request.",
                notification_type=NotificationType.GENERAL,
            )

        return Response(DonorContactRequestSerializer(contact_req).data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve Permitted Donor Contact Details",
        description=(
            "Discloses full private contact details (phone, email, full name, address) "
            "strictly if the authenticated requester has an APPROVED contact request for this donor. "
            "Neither Super Admins nor Blood Bank Admins can bypass explicit donor consent."
        ),
        responses={
            200: DonorPrivateContactSerializer,
            403: OpenApiResponse(description="Explicit donor consent approval required."),
            404: OpenApiResponse(description="Donor not found."),
        },
        tags=["Donor Contact Consent"],
    )
)
class DonorContactDetailsView(APIView):
    """
    Privacy-protected contact disclosure endpoint.
    Guarantees that donor contact details are never exposed without explicit donor approval.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        donor = Donor.objects.select_related("user").filter(pk=pk).first()
        if not donor:
            return Response({"detail": "Donor not found."}, status=status.HTTP_404_NOT_FOUND)

        # Allow donors to view their own contact details
        if donor.user_id == request.user.id:
            return Response(DonorPrivateContactSerializer(donor).data, status=status.HTTP_200_OK)

        # For all other users (including SUPER_ADMIN and BLOOD_BANK_ADMIN),
        # verify an APPROVED contact request exists for THIS requester.
        has_approved_request = DonorContactRequest.objects.filter(
            requester=request.user,
            donor=donor,
            status=ContactRequestStatus.APPROVED,
        ).exists()

        if not has_approved_request:
            return Response(
                {
                    "detail": "Donor contact details are private and require explicit donor consent approval. "
                              "Submit a contact request to request authorization."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(DonorPrivateContactSerializer(donor).data, status=status.HTTP_200_OK)

