from django.urls import path
from .views import (
    DonorMeProfileView,
    DonorMeEligibilityView,
    DonorAdminListView,
    DonorAdminDetailView,
    DonorContactRequestListCreateView,
    DonorContactRequestDetailView,
    DonorContactRequestRespondView,
    DonorContactDetailsView,
)

app_name = "donors"

urlpatterns = [
    path("me/", DonorMeProfileView.as_view(), name="donor_me"),
    path("me/eligibility/", DonorMeEligibilityView.as_view(), name="donor_me_eligibility"),
    path("contact-requests/", DonorContactRequestListCreateView.as_view(), name="donor_contact_requests"),
    path("contact-requests/", DonorContactRequestListCreateView.as_view(), name="donor_contact_request_list_create"),
    path("contact-requests/<int:pk>/", DonorContactRequestDetailView.as_view(), name="donor_contact_request_detail"),
    path("contact-requests/<int:pk>/respond/", DonorContactRequestRespondView.as_view(), name="donor_contact_request_respond"),
    path("<int:pk>/contact-details/", DonorContactDetailsView.as_view(), name="donor_contact_details"),
    path("", DonorAdminListView.as_view(), name="donor_list"),
    path("<int:pk>/", DonorAdminDetailView.as_view(), name="donor_detail"),
]
