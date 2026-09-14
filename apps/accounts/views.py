from django.contrib.auth import get_user_model
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from .models import UserRole
from .serializers import (
    UserSerializer,
    UserRegistrationSerializer,
    UserAdminCreateSerializer,
    UserAdminUpdateSerializer,
    CustomTokenObtainPairSerializer,
)
from .permissions import IsSuperAdmin

User = get_user_model()


@extend_schema_view(
    post=extend_schema(
        summary="User Login",
        description="Authenticate user with username/password and obtain JWT access and refresh tokens along with user profile metadata.",
        tags=["Authentication"]
    )
)
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


@extend_schema_view(
    post=extend_schema(
        summary="Refresh JWT Token",
        description="Submit a valid refresh token to obtain a fresh access token.",
        tags=["Authentication"]
    )
)
class CustomTokenRefreshView(TokenRefreshView):
    pass


@extend_schema_view(
    post=extend_schema(
        summary="Public User Registration",
        description="Register a new user account as DONOR or HOSPITAL_STAFF. Privileged roles (SUPER_ADMIN, BLOOD_BANK_ADMIN, LAB_TECHNICIAN) are rejected.",
        request=UserRegistrationSerializer,
        responses={
            201: OpenApiResponse(
                description="Registration successful",
                response=UserSerializer
            ),
            400: OpenApiResponse(description="Validation error")
        },
        tags=["Authentication"]
    )
)
class UserRegistrationView(generics.CreateAPIView):
    """
    Public registration endpoint strictly restricted to DONOR and HOSPITAL_STAFF roles.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Return the new registrant's own submitted details only on this response.
        user_data = UserSerializer(user, context={"newly_registered_user": user}).data
        return Response(
            {
                "message": "Registration successful",
                "user": user_data
            },
            status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    get=extend_schema(
        summary="Get Current User Profile",
        description="Retrieve the profile metadata of the currently authenticated user.",
        responses={200: UserSerializer},
        tags=["Authentication"]
    )
)
class CurrentUserView(generics.RetrieveAPIView):
    """
    Retrieve profile information for the currently authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


# ==========================================
# SUPER ADMIN USER MANAGEMENT ENDPOINTS
# ==========================================

@extend_schema_view(
    get=extend_schema(
        summary="List System Users",
        description="List all system users with pagination support. Restricted to Super Administrators.",
        responses={200: UserSerializer(many=True)},
        tags=["User Management"]
    ),
    post=extend_schema(
        summary="Create System User (Admin)",
        description="Provision a new system user with any role. Restricted to Super Administrators.",
        request=UserAdminCreateSerializer,
        responses={201: UserSerializer},
        tags=["User Management"]
    )
)
class UserListView(generics.ListCreateAPIView):
    """
    Super Admin endpoint to list all registered users or provision new accounts.
    """
    queryset = User.objects.all().order_by("-date_joined")
    permission_classes = [IsSuperAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserAdminCreateSerializer
        return UserSerializer


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve User Details",
        description="Retrieve detailed user profile by ID. Restricted to Super Administrators.",
        responses={200: UserSerializer},
        tags=["User Management"]
    ),
    patch=extend_schema(
        summary="Update User Profile",
        description="Update user safe fields (username, email, role, phone, is_verified, is_active, names). Restricted to Super Administrators.",
        request=UserAdminUpdateSerializer,
        responses={200: UserSerializer},
        tags=["User Management"]
    ),
    delete=extend_schema(
        summary="Delete User",
        description="Delete a user account. Includes safeguard preventing self-deletion by the requesting Super Admin.",
        responses={
            204: OpenApiResponse(description="User deleted successfully"),
            400: OpenApiResponse(description="Self-deletion blocked"),
            404: OpenApiResponse(description="User not found")
        },
        tags=["User Management"]
    )
)
class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Super Admin endpoint to retrieve, update, or delete a specific user account.
    """
    queryset = User.objects.all()
    permission_classes = [IsSuperAdmin]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return UserAdminUpdateSerializer
        return UserSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.id == request.user.id:
            return Response(
                {"detail": "You cannot delete your own Super Administrator account."},
                status=status.HTTP_400_BAD_REQUEST
            )
        self.perform_destroy(instance)
        return Response(
            {"detail": f"User '{instance.username}' was deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )
