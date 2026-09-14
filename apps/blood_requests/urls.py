from django.urls import path
from apps.emergency_sos.views import TriggerBloodRequestSOSView, BloodRequestSOSPreviewView
from .views import (
    BloodRequestListCreateView,
    BloodRequestDetailView,
    BloodRequestApproveView,
    BloodRequestRejectView,
    BloodRequestDonorRespondView,
    BloodRequestDonorResponsesListView,
    BloodRequestDonorOutcomeView,
)

urlpatterns = [
    path("", BloodRequestListCreateView.as_view(), name="blood-request-list-create"),
    path("<int:pk>/", BloodRequestDetailView.as_view(), name="blood-request-detail"),
    path("<int:pk>/approve/", BloodRequestApproveView.as_view(), name="blood-request-approve"),
    path("<int:pk>/reject/", BloodRequestRejectView.as_view(), name="blood-request-reject"),
    path("<int:pk>/sos/", TriggerBloodRequestSOSView.as_view(), name="blood-request-sos"),
    path("<int:pk>/sos/preview/", BloodRequestSOSPreviewView.as_view(), name="blood-request-sos-preview"),
    path("<int:pk>/respond/", BloodRequestDonorRespondView.as_view(), name="blood-request-donor-respond"),
    path("<int:pk>/responses/", BloodRequestDonorResponsesListView.as_view(), name="blood-request-donor-responses"),
    path("<int:pk>/responses/<int:response_id>/outcome/", BloodRequestDonorOutcomeView.as_view(), name="blood-request-donor-outcome"),
]
