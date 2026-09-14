from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, OpenApiResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.blood_requests.models import BloodRequest
from apps.blood_requests.permissions import CanManageOrViewBloodRequests
from .compatibility import calculate_haversine_distance_km
from .models import SOSBroadcast, SOSRecipient, SOSStatus
from .permissions import CanManageSOSBroadcast, CanTriggerSOS
from .serializers import (
    SOSBroadcastSerializer,
    SOSCancelRequestSerializer,
    SOSDonorPreviewResponseSerializer,
    SOSRecipientSerializer,
    TriggerSOSRequestSerializer,
)
from .services import cancel_sos_broadcast, find_eligible_compatible_donors, trigger_sos_broadcast


@extend_schema(
    summary="Trigger Emergency SOS Broadcast",
    description="Launch an Emergency SOS broadcast for a critical blood request with matching inventory shortage. Notifies eligible compatible donors via in-app notifications and email.",
    request=TriggerSOSRequestSerializer,
    responses={
        201: OpenApiResponse(response=SOSBroadcastSerializer, description="SOS broadcast successfully launched"),
        400: OpenApiResponse(description="Validation error (e.g. non-critical urgency, sufficient stock, active duplicate)"),
        403: OpenApiResponse(description="Permission denied"),
        404: OpenApiResponse(description="Blood request not found"),
    },
    tags=["Emergency SOS"],
)
class TriggerBloodRequestSOSView(APIView):
    """
    Endpoint to trigger an Emergency SOS broadcast for a specific BloodRequest.
    """
    permission_classes = [CanTriggerSOS]

    def post(self, request, pk, *args, **kwargs):
        try:
            blood_request = BloodRequest.objects.select_related("blood_bank", "hospital_staff").get(pk=pk)
        except BloodRequest.DoesNotExist:
            return Response(
                {"detail": f"Blood request with ID #{pk} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        self.check_object_permissions(request, blood_request)

        serializer = TriggerSOSRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        radius_km = serializer.validated_data.get("radius_km")
        custom_message = serializer.validated_data.get("custom_message")

        try:
            broadcast = trigger_sos_broadcast(
                blood_request=blood_request,
                triggered_by_user=request.user,
                radius_km=radius_km,
                custom_message=custom_message,
            )
        except DjangoValidationError as exc:
            msg = exc.messages if hasattr(exc, "messages") else [str(exc)]
            return Response(
                {"detail": msg[0] if len(msg) == 1 else msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_serializer = SOSBroadcastSerializer(broadcast)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Preview Eligible Donors for Emergency SOS",
    description="Read-only preview of medically eligible, compatible donors within the specified radius for a blood request before triggering an SOS broadcast.",
    parameters=[
        OpenApiParameter("radius_km", float, description="Search radius in kilometers (default 25 km, min 1, max 100)", required=False),
        OpenApiParameter("radius", float, description="Alias for radius_km", required=False),
    ],
    responses={
        200: SOSDonorPreviewResponseSerializer,
        400: OpenApiResponse(description="Invalid query parameters or radius"),
        403: OpenApiResponse(description="Permission denied"),
        404: OpenApiResponse(description="Blood request not found"),
    },
    tags=["Emergency SOS"],
)
class BloodRequestSOSPreviewView(APIView):
    """
    Read-only preview endpoint to display eligible compatible donors on the SOS map.
    Does NOT trigger an SOS broadcast, does NOT create records, and does NOT send notifications.
    """
    permission_classes = [CanManageSOSBroadcast]

    def get(self, request, pk, *args, **kwargs):
        try:
            blood_request = BloodRequest.objects.select_related("blood_bank", "hospital_staff").get(pk=pk)
        except BloodRequest.DoesNotExist:
            return Response(
                {"detail": f"Blood request with ID #{pk} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        self.check_object_permissions(request, blood_request)

        # Parse radius parameter
        radius_param = request.query_params.get("radius_km") or request.query_params.get("radius")
        radius_km = None
        if radius_param is not None:
            try:
                radius_val = float(radius_param)
                if radius_val <= 0 or radius_val > 100:
                    return Response(
                        {"detail": "Radius must be a positive number up to 100 km."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                radius_km = Decimal(str(radius_val))
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid radius parameter."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Call canonical eligibility & compatibility service
        eligible_donors = find_eligible_compatible_donors(
            blood_request=blood_request,
            radius_km=radius_km,
        )

        bank = blood_request.blood_bank
        bank_lat = bank.latitude
        bank_lng = bank.longitude

        donors_results = []
        for donor in eligible_donors:
            dist = None
            if bank_lat is not None and bank_lng is not None and donor.latitude is not None and donor.longitude is not None:
                raw_dist = calculate_haversine_distance_km(bank_lat, bank_lng, donor.latitude, donor.longitude)
                if raw_dist is not None:
                    dist = round(float(raw_dist), 2)

            fuzzed_lat = round(float(donor.latitude), 2) if donor.latitude is not None else None
            fuzzed_lng = round(float(donor.longitude), 2) if donor.longitude is not None else None

            donors_results.append({
                "id": f"DONOR-{donor.id}",
                "donor_id": donor.id,
                "blood_group": donor.blood_group,
                "is_eligible": True,
                "distance_km": dist,
                "approximate_latitude": fuzzed_lat,
                "approximate_longitude": fuzzed_lng,
            })

        # Sort by distance (closest first), fallback to donor id
        donors_results.sort(key=lambda x: (x["distance_km"] if x["distance_km"] is not None else 9999, x["donor_id"]))

        response_data = {
            "blood_request_id": blood_request.id,
            "blood_group_requested": blood_request.blood_group,
            "units_needed": blood_request.units_needed,
            "radius_km": float(radius_km) if radius_km is not None else None,
            "center_latitude": float(bank_lat) if bank_lat is not None else None,
            "center_longitude": float(bank_lng) if bank_lng is not None else None,
            "eligible_donors_count": len(donors_results),
            "donors": donors_results,
        }

        return Response(response_data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        summary="List Emergency SOS Broadcasts",
        description="Retrieve a paginated list of Emergency SOS broadcasts filtered according to the user's role and facility responsibilities.",
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filter by SOS status (ACTIVE, COMPLETED, CANCELLED, EXPIRED).",
                required=False,
            ),
            OpenApiParameter(
                name="blood_group",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filter by requested blood group (e.g. A+, O-).",
                required=False,
            ),
        ],
        responses={200: SOSBroadcastSerializer(many=True)},
        tags=["Emergency SOS"],
    )
)
class SOSBroadcastListView(generics.ListAPIView):
    """
    List SOS Broadcasts scoped strictly by user role and ownership.
    """
    serializer_class = SOSBroadcastSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = SOSBroadcast.objects.select_related(
            "blood_request",
            "blood_request__blood_bank",
            "blood_request__hospital_staff",
            "triggered_by",
            "cancelled_by",
        ).all()

        # Role-based visibility scoping
        if user.is_superuser or user.role == UserRole.SUPER_ADMIN:
            pass  # Super admin can view all broadcasts
        elif user.role == UserRole.HOSPITAL_STAFF:
            queryset = queryset.filter(
                blood_request__hospital_staff=user
            )
        elif user.role == UserRole.BLOOD_BANK_ADMIN:
            queryset = queryset.filter(
                blood_request__blood_bank__admin=user
            )
        else:
            # Donors and Lab Technicians cannot access broadcast management listings
            return SOSBroadcast.objects.none()

        # Query filters
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        bg_param = self.request.query_params.get("blood_group")
        if bg_param:
            queryset = queryset.filter(blood_group=bg_param.upper())

        return queryset.order_by("-created_at")


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve Emergency SOS Broadcast",
        description="Retrieve detailed information regarding a specific Emergency SOS broadcast.",
        responses={200: SOSBroadcastSerializer, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        tags=["Emergency SOS"],
    )
)
class SOSBroadcastDetailView(generics.RetrieveAPIView):
    """
    Retrieve single SOS Broadcast with object-level permissions.
    """
    queryset = SOSBroadcast.objects.select_related(
        "blood_request",
        "blood_request__blood_bank",
        "blood_request__hospital_staff",
        "triggered_by",
        "cancelled_by",
    ).all()
    serializer_class = SOSBroadcastSerializer
    permission_classes = [CanManageSOSBroadcast]


@extend_schema(
    summary="Cancel Emergency SOS Broadcast",
    description="Cancel an active Emergency SOS broadcast with a mandatory explanation reason.",
    request=SOSCancelRequestSerializer,
    responses={
        200: OpenApiResponse(response=SOSBroadcastSerializer, description="SOS broadcast cancelled successfully"),
        400: OpenApiResponse(description="Invalid request or broadcast not active"),
        403: OpenApiResponse(description="Permission denied"),
        404: OpenApiResponse(description="SOS broadcast not found"),
    },
    tags=["Emergency SOS"],
)
class SOSBroadcastCancelView(APIView):
    """
    Endpoint to cancel an active Emergency SOS broadcast.
    """
    permission_classes = [CanManageSOSBroadcast]

    def post(self, request, pk, *args, **kwargs):
        try:
            broadcast = SOSBroadcast.objects.select_related(
                "blood_request",
                "blood_request__blood_bank",
                "blood_request__hospital_staff",
            ).get(pk=pk)
        except SOSBroadcast.DoesNotExist:
            return Response(
                {"detail": f"SOS Broadcast #{pk} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        self.check_object_permissions(request, broadcast)

        serializer = SOSCancelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data["reason"]

        try:
            cancelled_broadcast = cancel_sos_broadcast(
                sos_broadcast=broadcast,
                cancelled_by_user=request.user,
                reason=reason,
            )
        except DjangoValidationError as exc:
            msg = exc.messages if hasattr(exc, "messages") else [str(exc)]
            return Response(
                {"detail": msg[0] if len(msg) == 1 else msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_serializer = SOSBroadcastSerializer(cancelled_broadcast)
        return Response(output_serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        summary="List SOS Broadcast Recipients (Audit)",
        description="Retrieve the audit list of targeted donor recipients and delivery outcomes for a specific SOS broadcast.",
        responses={200: SOSRecipientSerializer(many=True), 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        tags=["Emergency SOS"],
    )
)
class SOSBroadcastRecipientsListView(generics.ListAPIView):
    """
    List targeted recipients and delivery audit log for an SOS Broadcast.
    """
    serializer_class = SOSRecipientSerializer
    permission_classes = [CanManageSOSBroadcast]

    def get_queryset(self):
        pk = self.kwargs.get("pk")
        try:
            broadcast = SOSBroadcast.objects.select_related(
                "blood_request",
                "blood_request__blood_bank",
                "blood_request__hospital_staff",
            ).get(pk=pk)
        except SOSBroadcast.DoesNotExist:
            return SOSRecipient.objects.none()

        self.check_object_permissions(self.request, broadcast)
        return SOSRecipient.objects.filter(sos_broadcast=broadcast).select_related(
            "donor", "user", "notification", "sos_broadcast__blood_request__blood_bank"
        ).order_by("-created_at")
