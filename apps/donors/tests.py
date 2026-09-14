from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.donors.models import Donor, BloodGroup, DonorContactRequest, ContactRequestStatus
from apps.notifications.models import Notification
from apps.donors.services import calculate_donor_eligibility

User = get_user_model()


class DonorModelAndEligibilityUnitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="donor_unit_test",
            email="donor_unit@test.com",
            password="SecurePassword123!",
            role=UserRole.DONOR,
            phone="+1234567890",
            is_verified=True,
        )
        self.today = timezone.now().date()

    def get_dob_for_age(self, age):
        try:
            return date(self.today.year - age, self.today.month, self.today.day)
        except ValueError:
            # Leap year Feb 29 fallback
            return date(self.today.year - age, self.today.month, self.today.day - 1)

    def test_donor_profile_creation_success(self):
        dob = self.get_dob_for_age(25)
        donor = Donor.objects.create(
            user=self.user,
            blood_group=BloodGroup.O_POSITIVE,
            date_of_birth=dob,
            weight_kg=Decimal("68.50"),
            latitude=Decimal("12.971598"),
            longitude=Decimal("77.594566"),
            last_donation_date=self.today - timedelta(days=120),
        )
        self.assertEqual(donor.user, self.user)
        self.assertEqual(donor.blood_group, "O+")
        self.assertEqual(donor.age, 25)
        self.assertTrue(donor.is_eligible)
        self.assertIn("donor_unit_test (O+)", str(donor))

    def test_one_to_one_relationship_enforced(self):
        dob = self.get_dob_for_age(25)
        Donor.objects.create(
            user=self.user,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=dob,
            weight_kg=Decimal("60.00"),
        )
        with self.assertRaises(Exception):
            Donor.objects.create(
                user=self.user,
                blood_group=BloodGroup.B_POSITIVE,
                date_of_birth=dob,
                weight_kg=Decimal("65.00"),
            )

    def test_all_valid_blood_groups(self):
        valid_groups = [choice[0] for choice in BloodGroup.choices]
        self.assertEqual(len(valid_groups), 16)
        for idx, bg in enumerate(valid_groups):
            u = User.objects.create_user(
                username=f"donor_bg_{idx}",
                email=f"donor_bg_{idx}@test.com",
                password="SecurePassword123!",
                role=UserRole.DONOR,
            )
            donor = Donor.objects.create(
                user=u,
                blood_group=bg,
                date_of_birth=self.get_dob_for_age(20),
                weight_kg=Decimal("55.00"),
            )
            self.assertEqual(donor.blood_group, bg)

    def test_future_date_of_birth_rejection(self):
        donor = Donor(
            user=self.user,
            blood_group=BloodGroup.O_POSITIVE,
            date_of_birth=self.today + timedelta(days=10),
            weight_kg=Decimal("60.00"),
        )
        with self.assertRaises(ValidationError):
            donor.clean()

    def test_future_last_donation_date_rejection(self):
        donor = Donor(
            user=self.user,
            blood_group=BloodGroup.O_POSITIVE,
            date_of_birth=self.get_dob_for_age(25),
            weight_kg=Decimal("60.00"),
            last_donation_date=self.today + timedelta(days=5),
        )
        with self.assertRaises(ValidationError):
            donor.clean()

    def test_invalid_weight_rejection(self):
        donor = Donor(
            user=self.user,
            blood_group=BloodGroup.O_POSITIVE,
            date_of_birth=self.get_dob_for_age(25),
            weight_kg=Decimal("0.00"),
        )
        with self.assertRaises(ValidationError):
            donor.clean()

    def test_eligibility_logic_eligible_donor(self):
        dob = self.get_dob_for_age(30)
        res = calculate_donor_eligibility(
            date_of_birth=dob,
            weight_kg=Decimal("70.00"),
            last_donation_date=self.today - timedelta(days=100),
            reference_date=self.today,
        )
        self.assertTrue(res["is_eligible"])
        self.assertEqual(len(res["reasons"]), 0)
        self.assertTrue(res["criteria"]["age"]["passed"])
        self.assertTrue(res["criteria"]["weight"]["passed"])
        self.assertTrue(res["criteria"]["donation_interval"]["passed"])

    def test_eligibility_logic_underage_donor(self):
        dob = self.get_dob_for_age(17)
        res = calculate_donor_eligibility(
            date_of_birth=dob,
            weight_kg=Decimal("60.00"),
            reference_date=self.today,
        )
        self.assertFalse(res["is_eligible"])
        self.assertFalse(res["criteria"]["age"]["passed"])
        self.assertIn("at least 18 years old", res["reasons"][0])

    def test_eligibility_logic_over_age_donor(self):
        dob = self.get_dob_for_age(66)
        res = calculate_donor_eligibility(
            date_of_birth=dob,
            weight_kg=Decimal("65.00"),
            reference_date=self.today,
        )
        self.assertFalse(res["is_eligible"])
        self.assertFalse(res["criteria"]["age"]["passed"])
        self.assertIn("at most 65 years old", res["reasons"][0])

    def test_eligibility_logic_underweight_donor(self):
        dob = self.get_dob_for_age(22)
        res = calculate_donor_eligibility(
            date_of_birth=dob,
            weight_kg=Decimal("48.50"),
            reference_date=self.today,
        )
        self.assertFalse(res["is_eligible"])
        self.assertFalse(res["criteria"]["weight"]["passed"])
        self.assertIn("at least 50.0 kg", res["reasons"][0])

    def test_eligibility_logic_within_90_day_cooldown(self):
        dob = self.get_dob_for_age(25)
        res = calculate_donor_eligibility(
            date_of_birth=dob,
            weight_kg=Decimal("65.00"),
            last_donation_date=self.today - timedelta(days=45),
            reference_date=self.today,
        )
        self.assertFalse(res["is_eligible"])
        self.assertFalse(res["criteria"]["donation_interval"]["passed"])
        self.assertEqual(res["criteria"]["donation_interval"]["days_since_last_donation"], 45)
        self.assertEqual(res["criteria"]["donation_interval"]["days_until_next_eligible"], 45)
        self.assertIn("wait at least 90 days", res["reasons"][0])

    def test_eligibility_logic_first_time_donor_null_donation_date(self):
        dob = self.get_dob_for_age(22)
        res = calculate_donor_eligibility(
            date_of_birth=dob,
            weight_kg=Decimal("55.00"),
            last_donation_date=None,
            reference_date=self.today,
        )
        self.assertTrue(res["is_eligible"])
        self.assertTrue(res["criteria"]["donation_interval"]["passed"])
        self.assertIsNone(res["criteria"]["donation_interval"]["days_since_last_donation"])


class DonorAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.today = timezone.now().date()

        # Donor 1
        self.donor_user = User.objects.create_user(
            username="donor_api_1",
            email="donor1@example.com",
            password="SecurePassword123!",
            role=UserRole.DONOR,
            phone="+1112223333",
            is_verified=True,
        )

        # Donor 2
        self.donor_user_2 = User.objects.create_user(
            username="donor_api_2",
            email="donor2@example.com",
            password="SecurePassword123!",
            role=UserRole.DONOR,
            phone="+1112224444",
            is_verified=True,
        )

        # Hospital Staff
        self.staff_user = User.objects.create_user(
            username="hospital_staff_user",
            email="staff@example.com",
            password="SecurePassword123!",
            role=UserRole.HOSPITAL_STAFF,
            phone="+1112225555",
            is_verified=True,
        )

        # Super Admin
        self.admin_user = User.objects.create_superuser(
            username="super_admin_user",
            email="admin@example.com",
            password="AdminPassword123!",
            role=UserRole.SUPER_ADMIN,
            is_verified=True,
        )

        self.me_url = reverse("donors:donor_me")
        self.eligibility_url = reverse("donors:donor_me_eligibility")
        self.admin_list_url = reverse("donors:donor_list")

    def get_dob_for_age(self, age):
        try:
            return date(self.today.year - age, self.today.month, self.today.day)
        except ValueError:
            return date(self.today.year - age, self.today.month, self.today.day - 1)

    def test_unauthenticated_requests_rejected(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(self.eligibility_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(self.admin_list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_donor_role_cannot_access_donor_me_endpoints(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(self.eligibility_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_donor_get_profile_before_creation_returns_404(self):
        self.client.force_authenticate(user=self.donor_user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("Donor profile not found", response.json()["detail"])

    def test_donor_create_profile_via_post_and_put(self):
        self.client.force_authenticate(user=self.donor_user)
        dob = self.get_dob_for_age(24).isoformat()
        payload = {
            "blood_group": "O+",
            "date_of_birth": dob,
            "weight_kg": "65.50",
            "latitude": "12.971598",
            "longitude": "77.594566",
            "last_donation_date": None,
        }
        # Create via PUT
        response = self.client.put(self.me_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["username"], "donor_api_1")
        self.assertEqual(data["blood_group"], "O+")
        self.assertEqual(data["weight_kg"], "65.50")
        self.assertEqual(data["age"], 24)
        self.assertTrue(data["is_eligible"])

    def test_donor_update_profile_patch(self):
        # Create profile first
        dob = self.get_dob_for_age(28)
        donor = Donor.objects.create(
            user=self.donor_user,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=dob,
            weight_kg=Decimal("72.00"),
        )
        self.client.force_authenticate(user=self.donor_user)

        patch_payload = {
            "weight_kg": "75.00",
            "blood_group": "A-",
            "latitude": "13.082680",
            "longitude": "80.270721",
        }
        response = self.client.patch(self.me_url, patch_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["weight_kg"], "75.00")
        self.assertEqual(data["blood_group"], "A-")
        self.assertEqual(data["latitude"], "13.082680")

        donor.refresh_from_db()
        self.assertEqual(donor.blood_group, "A-")
        self.assertEqual(donor.weight_kg, Decimal("75.00"))

    def test_donor_get_eligibility_endpoint(self):
        dob = self.get_dob_for_age(22)
        Donor.objects.create(
            user=self.donor_user,
            blood_group=BloodGroup.B_POSITIVE,
            date_of_birth=dob,
            weight_kg=Decimal("58.00"),
            last_donation_date=self.today - timedelta(days=120),
        )
        self.client.force_authenticate(user=self.donor_user)
        response = self.client.get(self.eligibility_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["is_eligible"])
        self.assertEqual(data["criteria"]["age"]["value"], 22)
        self.assertEqual(data["criteria"]["weight"]["value_kg"], 58.0)
        self.assertEqual(data["criteria"]["donation_interval"]["days_since_last_donation"], 120)

    def test_donor_cannot_access_other_donor_profile(self):
        dob = self.get_dob_for_age(30)
        donor2 = Donor.objects.create(
            user=self.donor_user_2,
            blood_group=BloodGroup.AB_POSITIVE,
            date_of_birth=dob,
            weight_kg=Decimal("80.00"),
        )
        # Donor 1 logs in and hits /me/
        self.client.force_authenticate(user=self.donor_user)
        response = self.client.get(self.me_url)
        # Donor 1 has no profile yet -> 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Donor 1 cannot access admin donor detail endpoint
        admin_detail_url = reverse("donors:donor_detail", kwargs={"pk": donor2.id})
        response = self.client.get(admin_detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_serializer_validation_invalid_latitude_longitude(self):
        self.client.force_authenticate(user=self.donor_user)
        payload = {
            "blood_group": "O+",
            "date_of_birth": self.get_dob_for_age(20).isoformat(),
            "weight_kg": "60.00",
            "latitude": "95.000000",  # > 90
            "longitude": "200.000000",  # > 180
        }
        response = self.client.put(self.me_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", response.json())
        self.assertIn("longitude", response.json())

    def test_serializer_validation_invalid_blood_group(self):
        self.client.force_authenticate(user=self.donor_user)
        payload = {
            "blood_group": "INVALID_BG",
            "date_of_birth": self.get_dob_for_age(20).isoformat(),
            "weight_kg": "60.00",
        }
        response = self.client.put(self.me_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("blood_group", response.json())

    def test_super_admin_can_list_and_view_donors(self):
        dob = self.get_dob_for_age(25)
        d1 = Donor.objects.create(
            user=self.donor_user,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=dob,
            weight_kg=Decimal("60.00"),
        )
        d2 = Donor.objects.create(
            user=self.donor_user_2,
            blood_group=BloodGroup.O_NEGATIVE,
            date_of_birth=dob,
            weight_kg=Decimal("70.00"),
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.admin_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 2)

        # Test filtering by blood_group
        response = self.client.get(f"{self.admin_list_url}?blood_group=O-")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["blood_group"], "O-")

        # Test detail view
        detail_url = reverse("donors:donor_detail", kwargs={"pk": d1.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["username"], "donor_api_1")

    def test_donor_profile_patch_subgroup_blood_group(self):
        self.client.force_authenticate(user=self.donor_user)
        # Create profile with A1+
        res = self.client.patch(self.me_url, {
            "blood_group": "A1+",
            "date_of_birth": "1998-05-10",
            "weight_kg": "65.00"
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["blood_group"], "A1+")

        # Update profile to A2B+
        res2 = self.client.patch(self.me_url, {"blood_group": "A2B+"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data["blood_group"], "A2B+")

        # Check GET /api/donors/me/
        res3 = self.client.get(self.me_url)
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(res3.data["blood_group"], "A2B+")

    def test_invalid_blood_group_rejected_on_donor_profile(self):
        self.client.force_authenticate(user=self.donor_user)
        res = self.client.patch(self.me_url, {"blood_group": "XYZ+"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("blood_group", res.data)


class DonorContactConsentTests(TestCase):
    """
    Unit and integration tests for Requirement 4: Donor Contact Access & Privacy Consent.
    """
    def setUp(self):
        self.client = APIClient()

        # Donor user and profile
        self.donor_user = User.objects.create_user(
            username="voluntary_donor",
            email="donor.private@example.com",
            password="SecureDonorPass123!",
            phone="+91-9876500001",
            first_name="Priya",
            last_name="Sharma",
            address="12 Secret Lane, Chennai",
            role=UserRole.DONOR,
        )
        self.donor = Donor.objects.create(
            user=self.donor_user,
            blood_group=BloodGroup.O_POSITIVE,
            date_of_birth=timezone.now().date() - timezone.timedelta(days=26 * 365),
            weight_kg=Decimal("58.00"),
            latitude=Decimal("13.085000"),
            longitude=Decimal("80.275000"),
        )

        # Requester 1 (Hospital Staff)
        self.requester1 = User.objects.create_user(
            username="hospital_requester_1",
            email="staff1@hospital.org",
            password="StaffPass123!",
            role=UserRole.HOSPITAL_STAFF,
        )

        # Requester 2 (Another Staff user)
        self.requester2 = User.objects.create_user(
            username="hospital_requester_2",
            email="staff2@hospital.org",
            password="StaffPass123!",
            role=UserRole.HOSPITAL_STAFF,
        )

        # Blood Bank Admin
        self.bank_admin = User.objects.create_user(
            username="bank_admin_consent",
            email="admin@bank.org",
            password="AdminPass123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )

        # Super Admin
        self.super_admin = User.objects.create_superuser(
            username="super_admin_consent",
            email="super@admin.org",
            password="SuperPass123!",
            role=UserRole.SUPER_ADMIN,
        )

        self.contact_requests_url = reverse("donors:donor_contact_requests")
        self.contact_details_url = reverse("donors:donor_contact_details", kwargs={"pk": self.donor.id})

    def test_contact_request_creation_and_notification(self):
        """1. Permitted user creates contact request; in-app notification sent to donor."""
        self.client.force_authenticate(user=self.requester1)
        payload = {
            "donor_id": self.donor.id,
            "reason": "Emergency surgery patient requiring O+ blood urgently at Apollo Hospital.",
        }
        res = self.client.post(self.contact_requests_url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        req_id = res.data["id"]
        self.assertEqual(res.data["status"], "PENDING")

        # In-app notification created for the target donor
        from apps.notifications.models import Notification
        notif = Notification.objects.filter(recipient=self.donor_user).first()
        self.assertIsNotNone(notif)
        self.assertIn("New Donor Contact Request", notif.title)
        self.assertIn("Emergency surgery", notif.message)

    def test_pending_request_exposes_no_private_contact_info(self):
        """2. PENDING request exposes no private contact information (returns 403)."""
        from apps.donors.models import DonorContactRequest, ContactRequestStatus

        DonorContactRequest.objects.create(
            requester=self.requester1,
            donor=self.donor,
            reason="Blood reservation inquiry",
            status=ContactRequestStatus.PENDING,
        )

        self.client.force_authenticate(user=self.requester1)
        res = self.client.get(self.contact_details_url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("phone", str(res.data))
        self.assertNotIn("email", str(res.data))

    def test_declined_request_exposes_no_private_contact_info(self):
        """3. DECLINED request exposes no private contact information (returns 403)."""
        from apps.donors.models import DonorContactRequest, ContactRequestStatus

        DonorContactRequest.objects.create(
            requester=self.requester1,
            donor=self.donor,
            reason="Blood reservation inquiry",
            status=ContactRequestStatus.DECLINED,
        )

        self.client.force_authenticate(user=self.requester1)
        res = self.client.get(self.contact_details_url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_approved_request_discloses_contact_info_only_to_approved_requester(self):
        """4. APPROVED request exposes contact info to requester 1, but NOT to requester 2."""
        from apps.donors.models import DonorContactRequest, ContactRequestStatus

        # Create approved request for requester 1
        contact_req = DonorContactRequest.objects.create(
            requester=self.requester1,
            donor=self.donor,
            reason="Clinical need for pediatric unit",
            status=ContactRequestStatus.PENDING,
        )

        # Donor approves the request
        self.client.force_authenticate(user=self.donor_user)
        respond_url = reverse("donors:donor_contact_request_respond", kwargs={"pk": contact_req.id})
        res_respond = self.client.post(respond_url, {"status": "APPROVED"}, format="json")
        self.assertEqual(res_respond.status_code, status.HTTP_200_OK)
        self.assertEqual(res_respond.data["status"], "APPROVED")

        # Requester 1 can now access private contact details
        self.client.force_authenticate(user=self.requester1)
        res_details = self.client.get(self.contact_details_url)
        self.assertEqual(res_details.status_code, status.HTTP_200_OK)
        self.assertEqual(res_details.data["phone"], "+91-9876500001")
        self.assertEqual(res_details.data["email"], "donor.private@example.com")
        self.assertEqual(res_details.data["full_name"], "Priya Sharma")
        self.assertEqual(res_details.data["address"], "12 Secret Lane, Chennai")

        # Requester 2 CANNOT access donor contact details
        self.client.force_authenticate(user=self.requester2)
        res_details_req2 = self.client.get(self.contact_details_url)
        self.assertEqual(res_details_req2.status_code, status.HTTP_403_FORBIDDEN)

    def test_admins_cannot_bypass_donor_consent(self):
        """5. Super Admin and Blood Bank Admin cannot bypass donor consent to read private details."""
        # Without approved consent request:
        # Super Admin denied
        self.client.force_authenticate(user=self.super_admin)
        res_super = self.client.get(self.contact_details_url)
        self.assertEqual(res_super.status_code, status.HTTP_403_FORBIDDEN)

        # Blood Bank Admin denied
        self.client.force_authenticate(user=self.bank_admin)
        res_bank = self.client.get(self.contact_details_url)
        self.assertEqual(res_bank.status_code, status.HTTP_403_FORBIDDEN)


class DonorContactAccessAPITests(TestCase):
    """
    Comprehensive tests for privacy-preserving nearby donor discovery and contact access workflow.
    """
    def setUp(self):
        self.client = APIClient()
        self.today = timezone.now().date()

        # Donor 1 (Target Donor)
        self.donor_user = User.objects.create_user(
            username="target_donor",
            email="target_donor@example.com",
            first_name="Jane",
            last_name="Doe",
            password="SecurePassword123!",
            role=UserRole.DONOR,
            phone="+919876543210",
            is_verified=True,
        )
        self.donor_profile = Donor.objects.create(
            user=self.donor_user,
            blood_group=BloodGroup.O_POSITIVE,
            date_of_birth=self.today - timedelta(days=25 * 365),
            weight_kg=Decimal("65.00"),
            latitude=Decimal("13.082700"),
            longitude=Decimal("80.270700"),
        )

        # Donor 2 (Other Donor)
        self.other_donor_user = User.objects.create_user(
            username="other_donor",
            email="other_donor@example.com",
            password="SecurePassword123!",
            role=UserRole.DONOR,
            phone="+919876543211",
            is_verified=True,
        )
        self.other_donor_profile = Donor.objects.create(
            user=self.other_donor_user,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=self.today - timedelta(days=28 * 365),
            weight_kg=Decimal("70.00"),
            latitude=Decimal("13.085000"),
            longitude=Decimal("80.275000"),
        )

        # Hospital Staff User
        self.hospital_staff = User.objects.create_user(
            username="city_hospital_staff",
            email="staff@cityhospital.org",
            first_name="Dr. Alan",
            last_name="Grant",
            password="SecurePassword123!",
            role=UserRole.HOSPITAL_STAFF,
            phone="+919876543299",
            is_verified=True,
        )

        # Super Admin User
        self.super_admin = User.objects.create_user(
            username="system_superadmin",
            email="admin@bloodmgmt.org",
            password="SecurePassword123!",
            role=UserRole.SUPER_ADMIN,
            is_verified=True,
        )

        self.contact_req_url = reverse("donors:donor_contact_request_list_create")
        self.nearby_url = reverse("common:nearby_search")

    def test_nearby_donor_limited_info_and_no_private_exposure(self):
        """
        Verifies that nearby donor results only expose limited fields and omit phone, email, full names, exact coords.
        """
        self.client.force_authenticate(user=self.hospital_staff)
        res = self.client.get(f"{self.nearby_url}?lat=13.0827&lng=80.2707&radius=10&type=donors")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        donors = res.json()["results"]["donors"]
        self.assertTrue(len(donors) >= 1)

        d1 = donors[0]
        self.assertIn("donor_id", d1)
        self.assertIn("blood_group", d1)
        self.assertIn("is_eligible", d1)
        self.assertIn("distance_km", d1)
        self.assertIn("approximate_latitude", d1)
        self.assertIn("approximate_longitude", d1)

        # Ensure NO sensitive fields are leaked in nearby search
        self.assertNotIn("phone", d1)
        self.assertNotIn("email", d1)
        self.assertNotIn("first_name", d1)
        self.assertNotIn("last_name", d1)
        self.assertNotIn("password", d1)
        self.assertNotIn("address", d1)

    def test_hospital_can_create_contact_request(self):
        """
        Hospital staff creates a contact request and donor receives an in-app notification.
        """
        self.client.force_authenticate(user=self.hospital_staff)
        payload = {
            "donor_id": self.donor_profile.id,
            "hospital_name": "City General Hospital",
            "blood_group": "O+",
            "urgency": "HIGH",
            "message": "Urgent requirement for trauma surgery patient.",
        }
        res = self.client.post(self.contact_req_url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["status"], "PENDING")
        self.assertEqual(data["donor_id"], self.donor_profile.id)
        self.assertEqual(data["hospital_name"], "City General Hospital")
        self.assertIsNone(data["contact_details"])  # Must be None when PENDING

        # Verify donor received in-app notification
        notifications = Notification.objects.filter(recipient=self.donor_user)
        self.assertTrue(notifications.exists())
        self.assertIn("Contact", notifications.first().title)

    def test_non_hospital_user_cannot_create_contact_request(self):
        """
        Donors or unprivileged users cannot request contact access.
        """
        self.client.force_authenticate(user=self.other_donor_user)
        payload = {
            "donor_id": self.donor_profile.id,
            "hospital_name": "Unauthorized Clinic",
        }
        res = self.client.post(self.contact_req_url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_rejected(self):
        """
        Unauthenticated requests are strictly rejected with 401.
        """
        res = self.client.post(self.contact_req_url, {"donor_id": self.donor_profile.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_duplicate_pending_request_is_prevented(self):
        """
        Prevents multiple pending requests to the same donor by the same hospital staff.
        """
        self.client.force_authenticate(user=self.hospital_staff)
        payload = {
            "donor_id": self.donor_profile.id,
            "hospital_name": "City General Hospital",
        }
        # First request succeeds
        res1 = self.client.post(self.contact_req_url, payload, format="json")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Second identical pending request fails
        res2 = self.client.post(self.contact_req_url, payload, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pending contact request", res2.json()["detail"])

    def test_donor_can_approve_contact_request(self):
        """
        Target donor approves request. Requester receives notification and can access contact details.
        """
        # Create request as hospital staff
        req_obj = DonorContactRequest.objects.create(
            donor=self.donor_profile,
            requester=self.hospital_staff,
            hospital_name="City General Hospital",
            blood_group="O+",
            status=ContactRequestStatus.PENDING,
        )

        # Approve as target donor
        self.client.force_authenticate(user=self.donor_user)
        respond_url = reverse("donors:donor_contact_request_respond", kwargs={"pk": req_obj.id})
        res = self.client.post(respond_url, {"action": "APPROVE"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["status"], "APPROVED")

        # Check notification sent to hospital staff
        staff_notifs = Notification.objects.filter(recipient=self.hospital_staff)
        self.assertTrue(staff_notifs.exists())
        self.assertIn("Approved", staff_notifs.first().title)

        # Hospital checks request detail and sees phone & email
        self.client.force_authenticate(user=self.hospital_staff)
        detail_url = reverse("donors:donor_contact_request_detail", kwargs={"pk": req_obj.id})
        res_detail = self.client.get(detail_url)
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        details = res_detail.json()["contact_details"]
        self.assertIsNotNone(details)
        self.assertEqual(details["phone"], "+919876543210")
        self.assertEqual(details["email"], "target_donor@example.com")
        self.assertEqual(details["name"], "Jane Doe")

    def test_donor_can_decline_contact_request(self):
        """
        Target donor declines request. Hospital does NOT receive contact details.
        """
        req_obj = DonorContactRequest.objects.create(
            donor=self.donor_profile,
            requester=self.hospital_staff,
            hospital_name="City General Hospital",
            blood_group="O+",
            status=ContactRequestStatus.PENDING,
        )

        self.client.force_authenticate(user=self.donor_user)
        respond_url = reverse("donors:donor_contact_request_respond", kwargs={"pk": req_obj.id})
        res = self.client.post(respond_url, {"action": "DECLINE"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["status"], "DECLINED")

        # Hospital checks request detail and contact_details is None
        self.client.force_authenticate(user=self.hospital_staff)
        detail_url = reverse("donors:donor_contact_request_detail", kwargs={"pk": req_obj.id})
        res_detail = self.client.get(detail_url)
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertIsNone(res_detail.json()["contact_details"])

    def test_donor_cannot_approve_request_for_another_donor(self):
        """
        Donor B cannot respond to a request intended for Donor A.
        """
        req_obj = DonorContactRequest.objects.create(
            donor=self.donor_profile,
            requester=self.hospital_staff,
            hospital_name="City General Hospital",
            status=ContactRequestStatus.PENDING,
        )

        # Other donor attempts to approve
        self.client.force_authenticate(user=self.other_donor_user)
        respond_url = reverse("donors:donor_contact_request_respond", kwargs={"pk": req_obj.id})
        res = self.client.post(respond_url, {"action": "APPROVE"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
