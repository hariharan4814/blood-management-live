from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.blood_requests.models import BloodRequest
from apps.donations.models import Donation
from apps.donations.services import record_donation
from apps.donors.models import Donor, DonorContactRequest, ContactRequestStatus
from apps.inventory.models import BloodBank, BloodUnit

User = get_user_model()


class FinalWorkflowSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="audit_admin", email="admin@example.test", role=UserRole.SUPER_ADMIN)
        cls.staff = User.objects.create_user(username="audit_staff", email="staff@example.test", role=UserRole.HOSPITAL_STAFF)
        cls.other = User.objects.create_user(username="audit_other", email="other@example.test", role=UserRole.HOSPITAL_STAFF)
        cls.bank_admin = User.objects.create_user(username="audit_bank", email="bank@example.test", role=UserRole.BLOOD_BANK_ADMIN)
        cls.user = User.objects.create_user(
            username="audit_donor", email="private@example.test", phone="1234567890",
            address="Private residence", role=UserRole.DONOR,
            latitude=Decimal("13.082723"), longitude=Decimal("80.270745"),
        )
        cls.donor = Donor.objects.create(
            user=cls.user, blood_group="O+", date_of_birth=date(1995, 1, 1), weight_kg=60,
            latitude=cls.user.latitude, longitude=cls.user.longitude,
        )
        cls.bank = BloodBank.objects.create(name="Audit bank", admin=cls.bank_admin)
        cls.blood_request = BloodRequest.objects.create(
            hospital_staff=cls.staff, blood_bank=cls.bank, blood_group="O+", units_needed=1,
        )

    def setUp(self):
        self.client = APIClient()

    def response(self, status=ContactRequestStatus.APPROVED):
        return DonorContactRequest.objects.create(
            donor=self.donor, requester=self.staff, blood_request=self.blood_request,
            status=status, reason="Safe local verification",
        )

    def outcome_url(self, response):
        return f"/api/blood-requests/{self.blood_request.pk}/responses/{response.pk}/outcome/"

    def test_admin_donor_list_and_detail_redact_private_fields(self):
        for user in (self.admin, self.bank_admin):
            self.client.force_authenticate(user)
            for url in ("/api/donors/", f"/api/donors/{self.donor.pk}/"):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)
                data = res.data["results"][0] if "results" in res.data else res.data
                for key in ("email", "phone", "latitude", "longitude", "date_of_birth", "weight_kg"):
                    self.assertNotIn(key, data)

    def test_user_admin_directory_does_not_bypass_donor_privacy(self):
        self.client.force_authenticate(self.admin)
        data = self.client.get(f"/api/users/{self.user.pk}/").data
        for key in ("email", "phone", "address", "latitude", "longitude"):
            self.assertNotIn(key, data)

    def test_donor_can_read_their_own_profile(self):
        self.client.force_authenticate(self.user)
        data = self.client.get("/api/donors/me/").data
        self.assertEqual(data["email"], self.user.email)
        self.assertEqual(Decimal(data["latitude"]), self.donor.latitude)

    def test_approved_contact_excludes_coordinates_and_other_staff(self):
        self.response()
        url = f"/api/donors/{self.donor.pk}/contact-details/"
        self.client.force_authenticate(self.staff)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["email"], self.user.email)
        self.assertNotIn("latitude", res.data)
        self.assertNotIn("longitude", res.data)
        for user in (self.other, self.admin):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_contact_cannot_be_attached_to_another_hospitals_request(self):
        self.client.force_authenticate(self.other)
        res = self.client.post("/api/donors/contact-requests/", {
            "donor_id": self.donor.pk, "blood_request_id": self.blood_request.pk,
            "reason": "Safe local verification",
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(DonorContactRequest.objects.exists())

    def test_duplicate_linked_contact_returns_validation_error(self):
        self.response()
        self.client.force_authenticate(self.staff)
        res = self.client.post("/api/donors/contact-requests/", {
            "donor_id": self.donor.pk, "blood_request_id": self.blood_request.pk,
            "reason": "Safe local verification",
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_generic_consent_endpoint_enforces_blood_request_eligibility(self):
        response = self.response(ContactRequestStatus.PENDING)
        self.donor.last_donation_date = timezone.now().date()
        self.donor.save()
        self.client.force_authenticate(self.user)
        res = self.client.post(f"/api/donors/contact-requests/{response.pk}/respond/", {"action": "ACCEPT"})
        self.assertEqual(res.status_code, 400)
        response.refresh_from_db()
        self.assertEqual(response.status, ContactRequestStatus.PENDING)

    def test_completed_outcome_cannot_be_changed_by_donor_response(self):
        response = self.response()
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(self.outcome_url(response), {"outcome": "COMPLETED"}).status_code, 200)
        self.client.force_authenticate(self.user)
        res = self.client.post(f"/api/blood-requests/{self.blood_request.pk}/respond/", {"action": "DECLINE"})
        self.assertEqual(res.status_code, 400)
        response.refresh_from_db()
        self.assertEqual(response.status, ContactRequestStatus.APPROVED)
        self.assertEqual(response.donation_outcome, "COMPLETED")

    def test_stale_donor_instance_cannot_bypass_canonical_cooldown(self):
        stale = Donor.objects.get(pk=self.donor.pk)
        record_donation(self.donor, self.bank)
        with self.assertRaises(ValidationError):
            record_donation(stale, self.bank)
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(BloodUnit.objects.count(), 1)

    def test_completion_rolls_back_collection_if_response_save_fails(self):
        response = self.response()
        self.client.force_authenticate(self.staff)
        with patch.object(DonorContactRequest, "save", side_effect=RuntimeError("local rollback probe")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.outcome_url(response), {"outcome": "COMPLETED"})
        self.assertFalse(Donation.objects.exists())
        self.assertFalse(BloodUnit.objects.exists())
        self.donor.refresh_from_db()
        self.assertIsNone(self.donor.last_donation_date)

    def test_pending_and_declined_never_disclose_contact(self):
        response = self.response(ContactRequestStatus.PENDING)
        self.client.force_authenticate(self.staff)
        for status in (ContactRequestStatus.PENDING, ContactRequestStatus.DECLINED):
            response.status = status
            response.save()
            data = self.client.get(f"/api/donors/contact-requests/{response.pk}/").data
            self.assertIsNone(data["contact_details"])
            self.assertEqual(self.client.get(f"/api/donors/{self.donor.pk}/contact-details/").status_code, 403)

    def test_new_registration_does_not_invent_medical_measurements(self):
        res = self.client.post("/api/auth/register/", {
            "username": "new_audit_donor", "email": "new@example.test", "role": "DONOR",
            "blood_group": "A+", "password": "AuditPassword723!", "password_confirm": "AuditPassword723!",
        }, format="json")
        self.assertEqual(res.status_code, 201)
        donor = Donor.objects.get(user__username="new_audit_donor")
        self.assertIsNone(donor.date_of_birth)
        self.assertIsNone(donor.weight_kg)
        self.assertFalse(donor.is_eligible)

    def test_incomplete_profile_cannot_invent_eligibility(self):
        self.client.force_authenticate(self.user)
        self.donor.delete()
        res = self.client.post("/api/donors/me/", {"blood_group": "O+"})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Donor.objects.filter(user=self.user).exists())

    def test_donor_cannot_clear_recorded_collection_to_bypass_cooldown(self):
        record_donation(self.donor, self.bank)
        self.client.force_authenticate(self.user)
        for value in (None, "2000-01-01"):
            res = self.client.patch("/api/donors/me/", {"last_donation_date": value}, format="json")
            self.assertEqual(res.status_code, 400)
        self.donor.refresh_from_db()
        self.assertFalse(self.donor.is_eligible)

    def test_email_username_is_redacted_from_admin_profile(self):
        self.user.username = self.user.email
        self.user.save()
        self.client.force_authenticate(self.admin)
        for url in (f"/api/donors/{self.donor.pk}/", f"/api/users/{self.user.pk}/"):
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200)
            self.assertNotIn(self.user.email, str(res.data))

    def test_admin_user_update_response_does_not_disclose_contact(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(f"/api/users/{self.user.pk}/", {"is_verified": True})
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("email", res.data)
        self.assertNotIn("phone", res.data)
