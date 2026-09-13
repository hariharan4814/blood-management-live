from django.db.models import Q
from rest_framework import generics, status, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse

from apps.accounts.models import UserRole
from .models import BloodBank, BloodUnit, BloodUnitStatus
from .permissions import (
    IsSuperAdminOrAssignedBankAdmin,
    IsInventoryManagerOrReadOnly,
    CanViewInventorySummary,
)
from .serializers import (
    BloodBankSerializer,
    BloodBankPublicSerializer,
    BloodBankInputSerializer,
    BloodUnitSerializer,
    BloodUnitCreateSerializer,
    BloodUnitStatusUpdateSerializer,
    InventorySummaryResponseSerializer,
)
from .services import get_bank_inventory_summary, get_all_banks_inventory_summary


# ========================================================
# BLOOD BANK VIEWS
# ========================================================

@extend_schema_view(
    get=extend_schema(
        summary="List Blood Banks",
        description="Retrieve a list of blood banks. Super Admins see all banks; Blood Bank Admins see only their assigned bank; Hospital Staff see active banks for target selection.",
        responses={200: BloodBankSerializer(many=True)},
        tags=["Blood Banks"],
    ),
    post=extend_schema(
        summary="Create Blood Bank",
        description="Register a new blood bank facility. Restricted strictly to Super Administrators.",
        request=BloodBankInputSerializer,
        responses={201: BloodBankSerializer, 400: OpenApiResponse(description="Validation error.")},
        tags=["Blood Banks"],
    )
)
class BloodBankListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsSuperAdminOrAssignedBankAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BloodBankInputSerializer
        user = self.request.user
        if user and getattr(user, "role", None) == UserRole.HOSPITAL_STAFF:
            return BloodBankPublicSerializer
        return BloodBankSerializer

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return BloodBank.objects.none()

        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if is_admin:
            qs = BloodBank.objects.all()
        elif user.role == UserRole.BLOOD_BANK_ADMIN:
            qs = BloodBank.objects.filter(admin=user)
        elif user.role == UserRole.HOSPITAL_STAFF:
            qs = BloodBank.objects.filter(is_active=True)
        else:
            qs = BloodBank.objects.none()

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
            raise PermissionDenied("Only Super Administrators can create blood bank records.")
        serializer.save()

    def create(self, request, *args, **kwargs):
        user = request.user
        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if not is_admin:
            raise PermissionDenied("Only Super Administrators can create blood bank records.")
        input_serializer = self.get_serializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        blood_bank = input_serializer.save()
        output_serializer = BloodBankSerializer(blood_bank)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve Blood Bank Details",
        description="Retrieve details of a specific blood bank. Super Admin, assigned Admin, or authenticated users (active only).",
        responses={200: BloodBankSerializer, 403: OpenApiResponse(description="Permission denied."), 404: OpenApiResponse(description="Not found.")},
        tags=["Blood Banks"],
    ),
    patch=extend_schema(
        summary="Partial Update Blood Bank",
        description="Update details of a blood bank. Super Admin or assigned Blood Bank Admin only.",
        request=BloodBankInputSerializer,
        responses={200: BloodBankSerializer, 400: OpenApiResponse(description="Validation error.")},
        tags=["Blood Banks"],
    ),
    put=extend_schema(
        summary="Full Update Blood Bank",
        description="Fully update a blood bank record. Super Admin or assigned Blood Bank Admin only.",
        request=BloodBankInputSerializer,
        responses={200: BloodBankSerializer, 400: OpenApiResponse(description="Validation error.")},
        tags=["Blood Banks"],
    ),
    delete=extend_schema(
        summary="Delete Blood Bank",
        description="Delete a blood bank facility. Super Admin only.",
        responses={204: OpenApiResponse(description="Blood bank deleted.")},
        tags=["Blood Banks"],
    ),
)
class BloodBankDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = BloodBank.objects.all()
    permission_classes = [IsSuperAdminOrAssignedBankAdmin]

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return BloodBankInputSerializer
        user = self.request.user
        if user and getattr(user, "role", None) == UserRole.HOSPITAL_STAFF:
            return BloodBankPublicSerializer
        return BloodBankSerializer

    def check_permissions(self, request):
        super().check_permissions(request)
        user = request.user
        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if request.method in ["PUT", "PATCH", "DELETE"] and not (is_admin or user.role == UserRole.BLOOD_BANK_ADMIN):
            raise PermissionDenied("Only Super Administrators or assigned Blood Bank Admins can modify blood bank records.")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if request.method in permissions.SAFE_METHODS:
            if not is_admin and not obj.is_active and (user.role != UserRole.BLOOD_BANK_ADMIN or obj.admin_id != user.id):
                raise PermissionDenied("Cannot view inactive blood bank.")
        else:
            if not is_admin and (user.role != UserRole.BLOOD_BANK_ADMIN or obj.admin_id != user.id):
                raise PermissionDenied("You do not have permission to manage this blood bank.")

    def perform_destroy(self, instance):
        user = self.request.user
        is_admin = getattr(user, "is_super_admin", False) or user.is_superuser
        if not is_admin:
            raise PermissionDenied("Only Super Administrators can delete blood bank records.")
        instance.delete()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        input_serializer = BloodBankInputSerializer(instance, data=request.data, partial=partial)
        input_serializer.is_valid(raise_exception=True)
        updated_instance = input_serializer.save()
        output_serializer = BloodBankSerializer(updated_instance)
        return Response(output_serializer.data, status=status.HTTP_200_OK)


# ========================================================
# BLOOD UNIT VIEWS
# ========================================================

@extend_schema_view(
    get=extend_schema(
        summary="List Blood Units",
        description="Retrieve blood units with optional filtering by blood_bank, blood_group, and status. Scoped by user role.",
        parameters=[
            OpenApiParameter("blood_bank", int, description="Filter by Blood Bank ID", required=False),
            OpenApiParameter("blood_group", str, description="Filter by Blood Group (e.g. A+, O-)", required=False),
            OpenApiParameter("status", str, description="Filter by Status (TESTING, AVAILABLE, RESERVED, DISPATCHED, DISCARDED)", required=False),
        ],
        responses={200: BloodUnitSerializer(many=True)},
        tags=["Blood Units"],
    ),
    post=extend_schema(
        summary="Create Blood Unit",
        description="Create a new unit-level blood inventory item. Automatically sets status to TESTING and derives expiry date (collection_date + 42 days).",
        request=BloodUnitCreateSerializer,
        responses={201: BloodUnitSerializer, 400: OpenApiResponse(description="Validation error."), 403: OpenApiResponse(description="Permission denied.")},
        tags=["Blood Units"],
    )
)
class BloodUnitListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsInventoryManagerOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BloodUnitCreateSerializer
        return BloodUnitSerializer

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return BloodUnit.objects.none()

        queryset = BloodUnit.objects.select_related("blood_bank").all().order_by("-collection_date", "-created_at")

        # RBAC data isolation
        if user.role == UserRole.BLOOD_BANK_ADMIN:
            queryset = queryset.filter(blood_bank__admin=user)
        elif not (user.is_super_admin or user.role == UserRole.LAB_TECHNICIAN):
            return BloodUnit.objects.none()

        # Query parameter filters
        blood_bank_param = self.request.query_params.get("blood_bank")
        if blood_bank_param:
            queryset = queryset.filter(blood_bank_id=blood_bank_param)

        blood_group_param = self.request.query_params.get("blood_group")
        if blood_group_param:
            queryset = queryset.filter(blood_group__iexact=blood_group_param)

        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status__iexact=status_param)

        return queryset

    def create(self, request, *args, **kwargs):
        user = request.user
        serializer = BloodUnitCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_bank = serializer.validated_data["blood_bank"]

        # Blood Bank Admins can only create units for their assigned bank
        if user.role == UserRole.BLOOD_BANK_ADMIN and not user.is_super_admin:
            if target_bank.admin_id != user.id:
                return Response(
                    {"detail": "You are only authorized to create blood units for your assigned blood bank."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        blood_unit = serializer.save()
        output_serializer = BloodUnitSerializer(blood_unit)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve Blood Unit Details",
        description="Retrieve full details of an individual blood unit.",
        responses={200: BloodUnitSerializer, 403: OpenApiResponse(description="Permission denied."), 404: OpenApiResponse(description="Not found.")},
        tags=["Blood Units"],
    ),
    patch=extend_schema(
        summary="Controlled Status Update for Blood Unit",
        description="Update lifecycle status of a blood unit (e.g. AVAILABLE, RESERVED, DISPATCHED, DISCARDED).",
        request=BloodUnitStatusUpdateSerializer,
        responses={200: BloodUnitSerializer, 400: OpenApiResponse(description="Invalid transition."), 403: OpenApiResponse(description="Permission denied.")},
        tags=["Blood Units"],
    )
)
class BloodUnitDetailView(generics.RetrieveUpdateAPIView):
    queryset = BloodUnit.objects.select_related("blood_bank").all()
    permission_classes = [IsInventoryManagerOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ["PATCH", "PUT"]:
            return BloodUnitStatusUpdateSerializer
        return BloodUnitSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = BloodUnitStatusUpdateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updated_instance = serializer.save()
        return Response(BloodUnitSerializer(updated_instance).data, status=status.HTTP_200_OK)


# ========================================================
# INVENTORY SUMMARY VIEW
# ========================================================

@extend_schema_view(
    get=extend_schema(
        summary="Get Inventory Stock Summary",
        description="Dynamically computes available stock grouped by blood group (A+, A-, B+, B-, AB+, AB-, O+, O-). "
                    "Only AVAILABLE, non-expired units (expiry_date >= today) are counted. "
                    "TESTING, RESERVED, DISPATCHED, DISCARDED, and expired units are strictly excluded.",
        parameters=[
            OpenApiParameter("blood_bank", int, description="Filter by Blood Bank ID", required=False),
        ],
        responses={200: InventorySummaryResponseSerializer},
        tags=["Inventory Summary"],
    )
)
class InventorySummaryView(APIView):
    permission_classes = [CanViewInventorySummary]

    def get(self, request):
        user = request.user
        bank_id_param = request.query_params.get("blood_bank")

        # Role-based Blood Bank scoping
        if user.role == UserRole.BLOOD_BANK_ADMIN and not user.is_super_admin:
            assigned_bank = BloodBank.objects.filter(admin=user).first()
            if not assigned_bank:
                return Response(
                    {"detail": "No blood bank is assigned to your account."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if bank_id_param and str(assigned_bank.id) != str(bank_id_param):
                return Response(
                    {"detail": "You do not have permission to view inventory for another blood bank."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            summary = get_bank_inventory_summary(assigned_bank)
            return Response(summary, status=status.HTTP_200_OK)

        # Super Admin / Lab Technician with specific bank filter
        if bank_id_param:
            bank = BloodBank.objects.filter(id=bank_id_param).first()
            if not bank:
                return Response(
                    {"detail": f"Blood bank with ID {bank_id_param} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            summary = get_bank_inventory_summary(bank)
            return Response(summary, status=status.HTTP_200_OK)

        # Super Admin / Lab Tech without specific bank filter
        banks = BloodBank.objects.filter(is_active=True).order_by("name")
        if banks.count() == 1:
            summary = get_bank_inventory_summary(banks.first())
            return Response(summary, status=status.HTTP_200_OK)
        elif banks.exists():
            summaries = get_all_banks_inventory_summary(banks)
            return Response({"summaries": summaries, "total_blood_banks": len(summaries)}, status=status.HTTP_200_OK)
        else:
            return Response(
                {
                    "blood_bank": None,
                    "inventory": [],
                    "total_available_units": 0,
                    "message": "No active blood banks found.",
                },
                status=status.HTTP_200_OK,
            )
