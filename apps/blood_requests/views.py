from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse

from apps.accounts.models import UserRole
from apps.donors.models import Donor, DonorContactRequest, ContactRequestStatus, DonationOutcome
from apps.donors.serializers import (
    DonorContactRequestSerializer,
    DonorContactRequestRespondSerializer,
    DonorOutcomeRecordSerializer,
)
from apps.emergency_sos.compatibility import is_blood_compatible
from apps.notifications.models import NotificationType
from apps.notifications.services import create_notification
from apps.donations.services import record_donation
from .models import BloodRequest, Hospital, RequestStatus
from .permissions import CanManageOrViewBloodRequests, IsAssignedBankAdminForAction
from .serializers import (
    BloodRequestSerializer,
    BloodRequestCreateSerializer,
    BloodRequestRejectSerializer,
    HospitalSerializer,
)
from .services import approve_blood_request, reject_blood_request


@extend_schema_view(
    get=extend_schema(
        summary="List Blood Requests",
        description="Retrieve blood requests. Hospital Staff see only their own requests; Blood Bank Admins see requests for their assigned bank; Super Admins see all.",
        parameters=[
            OpenApiParameter("status", str, description="Filter by status (PENDING, APPROVED, REJECTED)", required=False),
            OpenApiParameter("urgency", str, description="Filter by urgency (NORMAL, HIGH, CRITICAL)", required=False),
            OpenApiParameter("blood_group", str, description="Filter by blood group (e.g. A+, O-)", required=False),
            OpenApiParameter("blood_bank", int, description="Filter by Blood Bank ID", required=False),
        ],
        responses={200: BloodRequestSerializer(many=True)},
        tags=["Blood Requests"],
    ),
    post=extend_schema(
        summary="Create Blood Request",
        description="Submit a new blood request to a designated blood bank. Restricted to HOSPITAL_STAFF.",
        request=BloodRequestCreateSerializer,
        responses={201: BloodRequestSerializer, 400: OpenApiResponse(description="Validation error."), 403: OpenApiResponse(description="Permission denied.")},
        tags=["Blood Requests"],
    )
)
class BloodRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [CanManageOrViewBloodRequests]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BloodRequestCreateSerializer
        return BloodRequestSerializer

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return BloodRequest.objects.none()

        queryset = (
            BloodRequest.objects.select_related("hospital_staff", "blood_bank", "approved_by")
            .prefetch_related("reserved_units")
            .all()
            .order_by("-created_at")
        )

        # RBAC and data isolation
        if user.role == UserRole.HOSPITAL_STAFF and not user.is_super_admin:
            queryset = queryset.filter(hospital_staff=user)
        elif user.role == UserRole.BLOOD_BANK_ADMIN and not user.is_super_admin:
            queryset = queryset.filter(blood_bank__admin=user)
        elif user.role == UserRole.DONOR and not user.is_super_admin:
            queryset = queryset.filter(status__in=[RequestStatus.PENDING, RequestStatus.APPROVED])
        elif not user.is_super_admin:
            return BloodRequest.objects.none()

        # Query filters
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status__iexact=status_param)

        urgency_param = self.request.query_params.get("urgency")
        if urgency_param:
            queryset = queryset.filter(urgency__iexact=urgency_param)

        blood_group_param = self.request.query_params.get("blood_group")
        if blood_group_param:
            queryset = queryset.filter(blood_group__iexact=blood_group_param)

        blood_bank_param = self.request.query_params.get("blood_bank")
        if blood_bank_param:
            queryset = queryset.filter(blood_bank_id=blood_bank_param)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        blood_request = serializer.save()
        output_serializer = BloodRequestSerializer(blood_request)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve Blood Request Details",
        description="Retrieve details of a specific blood request, including reserved units if approved.",
        responses={200: BloodRequestSerializer, 403: OpenApiResponse(description="Permission denied."), 404: OpenApiResponse(description="Not found.")},
        tags=["Blood Requests"],
    )
)
class BloodRequestDetailView(generics.RetrieveAPIView):
    queryset = BloodRequest.objects.select_related("hospital_staff", "blood_bank", "approved_by").prefetch_related("reserved_units").all()
    serializer_class = BloodRequestSerializer
    permission_classes = [CanManageOrViewBloodRequests]


@extend_schema_view(
    post=extend_schema(
        summary="Approve Blood Request",
        description="Atomically approves a PENDING blood request by reserving the exact requested number of eligible AVAILABLE BloodUnits. "
                    "Restricted to the assigned Blood Bank Administrator.",
        request=None,
        responses={
            200: BloodRequestSerializer,
            400: OpenApiResponse(description="Insufficient stock or invalid request state."),
            403: OpenApiResponse(description="Permission denied."),
        },
        tags=["Blood Requests"],
    )
)
class BloodRequestApproveView(APIView):
    permission_classes = [IsAssignedBankAdminForAction]

    def post(self, request, pk):
        blood_request = BloodRequest.objects.filter(pk=pk).first()
        if not blood_request:
            return Response({"detail": "Blood request not found."}, status=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, blood_request)

        try:
            approved_request = approve_blood_request(blood_request, approved_by_user=request.user)
        except DjangoValidationError as e:
            msg = e.message if hasattr(e, "message") else (e.messages[0] if hasattr(e, "messages") else str(e))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        serializer = BloodRequestSerializer(approved_request)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        summary="Reject Blood Request",
        description="Rejects a PENDING blood request with a required explanation reason. "
                    "Restricted to the assigned Blood Bank Administrator.",
        request=BloodRequestRejectSerializer,
        responses={
            200: BloodRequestSerializer,
            400: OpenApiResponse(description="Missing rejection reason or invalid request state."),
            403: OpenApiResponse(description="Permission denied."),
        },
        tags=["Blood Requests"],
    )
)
class BloodRequestRejectView(APIView):
    permission_classes = [IsAssignedBankAdminForAction]

    def post(self, request, pk):
        blood_request = BloodRequest.objects.filter(pk=pk).first()
        if not blood_request:
            return Response({"detail": "Blood request not found."}, status=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, blood_request)

        serializer = BloodRequestRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rejection_reason = serializer.validated_data["rejection_reason"]

        try:
            rejected_request = reject_blood_request(blood_request, rejection_reason=rejection_reason)
        except DjangoValidationError as e:
            msg = e.message if hasattr(e, "message") else (e.messages[0] if hasattr(e, "messages") else str(e))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        output_serializer = BloodRequestSerializer(rejected_request)
        return Response(output_serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        summary="List Hospitals",
        description="List partner hospitals with search and status filtering.",
        parameters=[
            OpenApiParameter("search", str, description="Search by name, city, or state", required=False),
            OpenApiParameter("status", str, description="Filter by status: active, inactive, or all", required=False),
        ],
        responses={200: HospitalSerializer(many=True)},
        tags=["Hospitals"],
    ),
    post=extend_schema(
        summary="Create Hospital",
        description="Register a new partner hospital. Super Admin only.",
        request=HospitalSerializer,
        responses={201: HospitalSerializer, 403: OpenApiResponse(description="Permission denied.")},
        tags=["Hospitals"],
    ),
)
class HospitalListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HospitalSerializer

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Hospital.objects.none()

        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if is_admin:
            qs = Hospital.objects.all()
        else:
            qs = Hospital.objects.filter(is_active=True)

        status_param = self.request.query_params.get("status")
        if status_param == "active":
            qs = qs.filter(is_active=True)
        elif status_param == "inactive":
            qs = qs.filter(is_active=False)

        search = self.request.query_params.get("search")
        if search:
            search = search.strip()
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(city__icontains=search)
                | Q(state__icontains=search)
                | Q(address__icontains=search)
            )

        return qs.order_by("name")

    def perform_create(self, serializer):
        user = self.request.user
        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if not is_admin:
            raise PermissionDenied("Only Super Administrators can create hospital records.")
        serializer.save()


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve Hospital",
        description="Retrieve detailed information for a partner hospital.",
        responses={200: HospitalSerializer},
        tags=["Hospitals"],
    ),
    patch=extend_schema(
        summary="Update Hospital",
        description="Update hospital facility details. Restricted to Super Admin.",
        request=HospitalSerializer,
        responses={200: HospitalSerializer},
        tags=["Hospitals"],
    ),
    delete=extend_schema(
        summary="Delete Hospital",
        description="Delete hospital facility. Restricted to Super Admin.",
        responses={204: OpenApiResponse(description="Hospital deleted.")},
        tags=["Hospitals"],
    ),
)
class HospitalDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Hospital.objects.all()
    serializer_class = HospitalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        user = request.user
        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if request.method in ["PUT", "PATCH", "DELETE"] and not is_admin:
            raise PermissionDenied("Only Super Administrators can modify or delete hospital records.")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if request.method in permissions.SAFE_METHODS and not is_admin and not obj.is_active:
            raise PermissionDenied("Cannot view inactive hospital.")


@extend_schema_view(
    post=extend_schema(
        summary="Donor Respond to Blood Request",
        description="Eligible and compatible donor accepts ('ACCEPT') or declines ('DECLINE') an active blood request. "
                    "Accepting explicitly consents to reveal permitted contact details to the requesting Hospital Staff.",
        request=DonorContactRequestRespondSerializer,
        responses={
            200: DonorContactRequestSerializer,
            400: OpenApiResponse(description="Validation error, ineligibility, incompatibility, closed request, or duplicate response."),
            403: OpenApiResponse(description="Unauthorized or non-donor user."),
            404: OpenApiResponse(description="Blood request not found."),
        },
        tags=["Blood Requests"],
    )
)
class BloodRequestDonorRespondView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        user = request.user
        if user.role != UserRole.DONOR or not hasattr(user, "donor_profile"):
            return Response(
                {"detail": "Only registered donors can respond to blood requests."},
                status=status.HTTP_403_FORBIDDEN,
            )

        donor = user.donor_profile

        blood_request = BloodRequest.objects.select_for_update().filter(pk=pk).first()
        if not blood_request:
            return Response(
                {"detail": "Blood request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Only active requests (PENDING or APPROVED) can receive donor responses
        if blood_request.status not in [RequestStatus.PENDING, RequestStatus.APPROVED]:
            return Response(
                {"detail": f"Cannot respond to a blood request with status '{blood_request.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DonorContactRequestRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"].upper()
        notes = serializer.validated_data.get("notes", "")

        existing_response = DonorContactRequest.objects.select_for_update().filter(
            blood_request=blood_request,
            donor=donor,
        ).first()

        if existing_response and existing_response.donation_outcome != DonationOutcome.NOT_RECORDED:
            return Response({"detail": "A donation outcome has already been recorded for this response."}, status=status.HTTP_400_BAD_REQUEST)

        if action in ("APPROVE", "APPROVED", "ACCEPT", "ACCEPTED"):
            if existing_response and existing_response.status == ContactRequestStatus.APPROVED:
                return Response(
                    {"detail": "You have already accepted this blood request."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 1. Eligibility evaluation
            eligibility = donor.calculate_eligibility()
            if not eligibility.get("is_eligible", False):
                return Response(
                    {
                        "detail": "You are currently not eligible to donate.",
                        "reasons": eligibility.get("reasons", []),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 2. Blood group compatibility evaluation
            if not is_blood_compatible(donor.blood_group, blood_request.blood_group):
                return Response(
                    {
                        "detail": f"Your blood group ({donor.blood_group}) is not compatible with requested blood group ({blood_request.blood_group})."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 3. Create or update response atomically
            if existing_response:
                contact_req = existing_response
                contact_req.status = ContactRequestStatus.APPROVED
                contact_req.responded_at = timezone.now()
                if notes:
                    contact_req.message = notes
                contact_req.save()
            else:
                hospital_name = (
                    blood_request.hospital_staff.address
                    or getattr(blood_request.hospital_staff, "full_name", "")
                    or getattr(blood_request.blood_bank, "name", "")
                    or "Hospital Facility"
                )
                contact_req = DonorContactRequest.objects.create(
                    blood_request=blood_request,
                    donor=donor,
                    requester=blood_request.hospital_staff,
                    hospital_name=hospital_name,
                    blood_group=blood_request.blood_group,
                    urgency=blood_request.urgency,
                    message=notes or "Donor accepted blood request and consented to contact reveal.",
                    status=ContactRequestStatus.APPROVED,
                    responded_at=timezone.now(),
                )

            # In-app notification to requesting hospital staff
            donor_display = donor.user.full_name or f"Donor #{donor.id}"
            create_notification(
                recipient=blood_request.hospital_staff,
                title="Donor Accepted Blood Request",
                message=f"{donor_display} ({donor.blood_group}) accepted Blood Request #{blood_request.id} and shared contact details.",
                notification_type=NotificationType.DONATION,
            )
        else:
            # DECLINE action
            if existing_response and existing_response.status == ContactRequestStatus.DECLINED:
                return Response(
                    {"detail": "You have already declined this blood request."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if existing_response:
                contact_req = existing_response
                contact_req.status = ContactRequestStatus.DECLINED
                contact_req.responded_at = timezone.now()
                if notes:
                    contact_req.message = notes
                contact_req.save()
            else:
                hospital_name = (
                    blood_request.hospital_staff.address
                    or getattr(blood_request.hospital_staff, "full_name", "")
                    or getattr(blood_request.blood_bank, "name", "")
                    or "Hospital Facility"
                )
                contact_req = DonorContactRequest.objects.create(
                    blood_request=blood_request,
                    donor=donor,
                    requester=blood_request.hospital_staff,
                    hospital_name=hospital_name,
                    blood_group=blood_request.blood_group,
                    urgency=blood_request.urgency,
                    message=notes or "Donor declined blood request.",
                    status=ContactRequestStatus.DECLINED,
                    responded_at=timezone.now(),
                )

            # In-app notification to requesting hospital staff
            create_notification(
                recipient=blood_request.hospital_staff,
                title="Donor Declined Blood Request",
                message=f"A donor declined Blood Request #{blood_request.id}.",
                notification_type=NotificationType.DONATION,
            )

        return Response(
            DonorContactRequestSerializer(contact_req, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        summary="List Donor Responses for Blood Request",
        description="List all donor responses for a specific blood request. Restricted to the requesting Hospital Staff owner and Super Admin.",
        responses={
            200: DonorContactRequestSerializer(many=True),
            403: OpenApiResponse(description="Permission denied."),
            404: OpenApiResponse(description="Blood request not found."),
        },
        tags=["Blood Requests"],
    )
)
class BloodRequestDonorResponsesListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        user = request.user
        blood_request = BloodRequest.objects.filter(pk=pk).first()
        if not blood_request:
            return Response({"detail": "Blood request not found."}, status=status.HTTP_404_NOT_FOUND)

        is_owner = blood_request.hospital_staff_id == user.id
        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser

        if not (is_owner or is_admin):
            return Response(
                {"detail": "You do not have permission to view donor responses for this blood request."},
                status=status.HTTP_403_FORBIDDEN,
            )

        responses_qs = (
            DonorContactRequest.objects.filter(blood_request=blood_request)
            .select_related("donor__user", "requester")
            .order_by("-responded_at", "-created_at")
        )

        serializer = DonorContactRequestSerializer(responses_qs, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        summary="Record Donation Outcome",
        description="Record the actual clinical outcome of a donor response (COMPLETED or DID_NOT_HAPPEN). Restricted to the requesting Hospital Staff owner of the BloodRequest.",
        request=DonorOutcomeRecordSerializer,
        responses={
            200: DonorContactRequestSerializer,
            400: OpenApiResponse(description="Validation error or state mismatch."),
            403: OpenApiResponse(description="Permission denied."),
            404: OpenApiResponse(description="Not found."),
        },
        tags=["Blood Requests"],
    )
)
class BloodRequestDonorOutcomeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, response_id):
        user = request.user
        blood_request = BloodRequest.objects.filter(pk=pk).first()
        if not blood_request:
            return Response({"detail": "Blood request not found."}, status=status.HTTP_404_NOT_FOUND)

        # STRICT RBAC: ONLY the specific Hospital Staff who owns this blood request can record the outcome
        if user.role != UserRole.HOSPITAL_STAFF or blood_request.hospital_staff_id != user.id:
            return Response(
                {"detail": "Only the Hospital Staff who created this blood request can record a donation outcome."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            contact_req = (
                DonorContactRequest.objects.select_for_update()
                .filter(id=response_id, blood_request=blood_request)
                .first()
            )
            if not contact_req:
                return Response(
                    {"detail": "Donor response not found for this blood request."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Validate input
            serializer = DonorOutcomeRecordSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            outcome = serializer.validated_data["outcome"]
            notes = serializer.validated_data.get("notes", "")

            # PREREQUISITE: Donor must have ACCEPTED/APPROVED the request
            if contact_req.status != ContactRequestStatus.APPROVED:
                return Response(
                    {"detail": "Cannot record donation outcome for a donor response that has not been accepted."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # IDEMPOTENCY / IMMUTABILITY: Prevent overwriting or duplicate outcomes
            if contact_req.donation_outcome in [DonationOutcome.COMPLETED, DonationOutcome.DID_NOT_HAPPEN]:
                return Response(
                    {"detail": f"A donation outcome ({contact_req.get_donation_outcome_display()}) has already been recorded for this response."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Record outcome server-side
            contact_req.donation_outcome = outcome
            contact_req.outcome_recorded_at = timezone.now()
            contact_req.outcome_recorded_by = user
            if notes:
                contact_req.outcome_notes = notes

            # For COMPLETED donations, atomically create Donation and BloodUnit, and update donor's last_donation_date
            if outcome == DonationOutcome.COMPLETED:
                try:
                    donation = record_donation(
                        donor=contact_req.donor,
                        blood_bank=blood_request.blood_bank,
                        blood_request=blood_request,
                        donation_date=timezone.now().date(),
                        created_by=user,
                    )
                    contact_req.donation = donation
                except DjangoValidationError as e:
                    msg = e.message if hasattr(e, "message") else (e.messages[0] if hasattr(e, "messages") else str(e))
                    return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

            contact_req.save(
                update_fields=[
                    "donation_outcome",
                    "outcome_recorded_at",
                    "outcome_recorded_by",
                    "outcome_notes",
                    "donation",
                    "updated_at",
                ]
            )

            # In-app notification to donor
            if outcome == DonationOutcome.COMPLETED:
                create_notification(
                    recipient=contact_req.donor.user,
                    title="Donation Completed Recorded",
                    message=f"Hospital staff recorded your donation for Blood Request #{blood_request.id} as completed. Thank you!",
                    notification_type=NotificationType.DONATION,
                )
            else:
                create_notification(
                    recipient=contact_req.donor.user,
                    title="Donation Outcome Recorded",
                    message=f"Hospital staff recorded that donation did not take place for Blood Request #{blood_request.id}.",
                    notification_type=NotificationType.DONATION,
                )

            return Response(
                DonorContactRequestSerializer(contact_req, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
