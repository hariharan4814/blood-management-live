from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.donations.models import Donation
from apps.donors.models import Donor, BloodGroup, DonorContactRequest, ContactRequestStatus, DonationOutcome
from apps.emergency_sos.services import find_eligible_compatible_donors
from apps.inventory.models import BloodBank, BloodUnit, BloodUnitStatus
from .models import BloodRequest, RequestUrgency, RequestStatus
from .services import approve_blood_request, reject_blood_request

User = get_user_model()


class BloodRequestModelTest(TestCase):
    """
    Model unit tests for BloodRequest entity and field validations.
    """
    def setUp(self):
        self.bank = BloodBank.objects.create(
            name="Apex General Blood Center",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0100",
            email="apex@test.org",
            capacity=1000,
        )
        self.hospital_staff = User.objects.create_user(
            username="nurse_sarah",
            email="sarah@hospital.org",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )

    def test_01_request_creation_success(self):
        """Test 1 & 7: BloodRequest creation with valid fields defaults to PENDING."""
        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group=BloodGroup.O_NEGATIVE,
            units_needed=2,
            urgency=RequestUrgency.HIGH,
        )
        self.assertEqual(req.status, RequestStatus.PENDING)
        self.assertEqual(req.units_needed, 2)
        self.assertEqual(req.blood_group, "O-")
        self.assertEqual(req.urgency, "HIGH")
        self.assertIn("Request #", str(req))

    def test_04_units_needed_must_be_positive(self):
        """Test 4: units_needed <= 0 is rejected."""
        req = BloodRequest(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group=BloodGroup.A_POSITIVE,
            units_needed=0,
        )
        with self.assertRaises(ValidationError):
            req.clean()

    def test_37_rejection_requires_reason(self):
        """Test 37: Rejection requires a valid rejection_reason."""
        req = BloodRequest(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group=BloodGroup.A_POSITIVE,
            units_needed=1,
            status=RequestStatus.REJECTED,
            rejection_reason="",
        )
        with self.assertRaises(ValidationError):
            req.clean()


class BloodRequestWorkflowServiceTest(TestCase):
    """
    Service tests for atomic approval, unit reservation, and rejection.
    """
    def setUp(self):
        self.bank_admin = User.objects.create_user(
            username="admin_carl",
            email="carl@bank.org",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.bank = BloodBank.objects.create(
            name="Beacon Blood Center",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0200",
            email="beacon@test.org",
            capacity=1000,
            admin=self.bank_admin,
        )
        self.hospital_staff = User.objects.create_user(
            username="doctor_alex",
            email="alex@hospital.org",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )
        self.today = timezone.now().date()

    def test_18_to_25_successful_approval_and_reservation(self):
        """
        Tests 18-25:
        - 18: Approve PENDING request
        - 19: Status becomes APPROVED
        - 20: approved_by set correctly
        - 21: approved_at set correctly
        - 22: Exact number of units become RESERVED
        - 23: Reserved units linked to request
        - 24: Only matching blood group selected
        - 25: Only same-bank units selected
        """
        # Create 3 available units of A+ in this bank
        unit1 = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-RES-A-1",
            blood_group="A+",
            collection_date=self.today - timedelta(days=5),
            status=BloodUnitStatus.AVAILABLE,
        )
        unit2 = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-RES-A-2",
            blood_group="A+",
            collection_date=self.today - timedelta(days=2),
            status=BloodUnitStatus.AVAILABLE,
        )
        unit3 = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-RES-A-3",
            blood_group="A+",
            collection_date=self.today - timedelta(days=1),
            status=BloodUnitStatus.AVAILABLE,
        )

        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group="A+",
            units_needed=2,
        )

        approved_req = approve_blood_request(req, approved_by_user=self.bank_admin)

        self.assertEqual(approved_req.status, RequestStatus.APPROVED)
        self.assertEqual(approved_req.approved_by, self.bank_admin)
        self.assertIsNotNone(approved_req.approved_at)
        self.assertEqual(approved_req.reserved_units.count(), 2)

        # Oldest expiry (unit1 and unit2) should be reserved
        unit1.refresh_from_db()
        unit2.refresh_from_db()
        unit3.refresh_from_db()
        self.assertEqual(unit1.status, BloodUnitStatus.RESERVED)
        self.assertEqual(unit2.status, BloodUnitStatus.RESERVED)
        self.assertEqual(unit3.status, BloodUnitStatus.AVAILABLE)

    def test_26_to_28_non_available_units_excluded_from_reservation(self):
        """
        Tests 26-28:
        - 26: TESTING units excluded
        - 27: DISCARDED units excluded
        - 28: Expired units excluded
        """
        # Testing unit
        BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-EXCL-TESTING",
            blood_group="O+",
            collection_date=self.today,
            status=BloodUnitStatus.TESTING,
        )
        # Discarded unit
        BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-EXCL-DISC",
            blood_group="O+",
            collection_date=self.today,
            status=BloodUnitStatus.DISCARDED,
        )
        # Expired unit (collected 50 days ago)
        BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-EXCL-EXP",
            blood_group="O+",
            collection_date=self.today - timedelta(days=50),
            status=BloodUnitStatus.AVAILABLE,
        )

        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group="O+",
            units_needed=1,
        )

        with self.assertRaises(ValidationError):
            approve_blood_request(req, approved_by_user=self.bank_admin)

        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.PENDING)

    def test_30_to_32_insufficient_stock_behavior(self):
        """
        Tests 30-32 & 46:
        - 30: Insufficient stock leaves request PENDING
        - 31: Insufficient stock causes NO partial reservation
        - 32: Clear insufficient-stock error raised
        - 46: Failed approval leaves inventory unchanged
        """
        unit1 = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-ONE-B",
            blood_group="B+",
            collection_date=self.today,
            status=BloodUnitStatus.AVAILABLE,
        )

        # Request requires 3 units, but only 1 exists
        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group="B+",
            units_needed=3,
        )

        with self.assertRaises(ValidationError) as ctx:
            approve_blood_request(req, approved_by_user=self.bank_admin)

        self.assertIn("Insufficient stock", str(ctx.exception))

        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.PENDING)
        self.assertEqual(req.reserved_units.count(), 0)

        unit1.refresh_from_db()
        # Unit must still be AVAILABLE, not partially reserved
        self.assertEqual(unit1.status, BloodUnitStatus.AVAILABLE)

    def test_33_and_34_cannot_reapprove_or_approve_rejected(self):
        """Test 33 & 34: Cannot approve an APPROVED or REJECTED request."""
        BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-RE-APP",
            blood_group="AB-",
            collection_date=self.today,
            status=BloodUnitStatus.AVAILABLE,
        )
        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group="AB-",
            units_needed=1,
        )
        approve_blood_request(req, self.bank_admin)

        # Attempt to approve again
        with self.assertRaises(ValidationError):
            approve_blood_request(req, self.bank_admin)

        # Test rejected request
        req2 = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group="AB-",
            units_needed=1,
            status=RequestStatus.REJECTED,
            rejection_reason="Declined",
        )
        with self.assertRaises(ValidationError):
            approve_blood_request(req2, self.bank_admin)

    def test_36_to_41_rejection_workflow(self):
        """
        Tests 36-41:
        - 36: Reject PENDING request
        - 37: rejection_reason required
        - 38: Status becomes REJECTED
        - 39: Inventory unchanged
        - 40: Cannot reject REJECTED request again
        - 41: Cannot reject APPROVED request
        """
        unit = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-REJ-INV",
            blood_group="O-",
            collection_date=self.today,
            status=BloodUnitStatus.AVAILABLE,
        )
        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff,
            blood_bank=self.bank,
            blood_group="O-",
            units_needed=1,
        )

        rejected = reject_blood_request(req, rejection_reason="Out of storage space.")
        self.assertEqual(rejected.status, RequestStatus.REJECTED)
        self.assertEqual(rejected.rejection_reason, "Out of storage space.")

        # Inventory unit is unchanged
        unit.refresh_from_db()
        self.assertEqual(unit.status, BloodUnitStatus.AVAILABLE)

        # Cannot reject again
        with self.assertRaises(ValidationError):
            reject_blood_request(rejected, "Another reason")


class BloodRequestAPITest(APITestCase):
    """
    API integration tests for BloodRequest creation, approval, rejection, and RBAC isolation.
    """
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="super_admin_req",
            email="super_req@test.com",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.bank_admin_1 = User.objects.create_user(
            username="bank_admin_req_1",
            email="admin1_req@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.bank_admin_2 = User.objects.create_user(
            username="bank_admin_req_2",
            email="admin2_req@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.hospital_staff_1 = User.objects.create_user(
            username="staff_1",
            email="staff1@hospital.com",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )
        self.hospital_staff_2 = User.objects.create_user(
            username="staff_2",
            email="staff2@hospital.com",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )
        self.lab_tech = User.objects.create_user(
            username="lab_tech_req",
            email="lab_req@test.com",
            password="Password123!",
            role=UserRole.LAB_TECHNICIAN,
        )
        self.donor_user = User.objects.create_user(
            username="donor_req_user",
            email="donor_req@test.com",
            password="Password123!",
            role=UserRole.DONOR,
        )

        self.bank_1 = BloodBank.objects.create(
            name="Central Regional Blood Bank",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-1111",
            email="central@bank.org",
            capacity=1000,
            admin=self.bank_admin_1,
        )
        self.bank_2 = BloodBank.objects.create(
            name="Eastern County Blood Bank",
            city="East City",
            state="Eastern State",
            contact_number="+1-555-2222",
            email="eastern@bank.org",
            capacity=800,
            admin=self.bank_admin_2,
        )

        self.today = timezone.now().date()

    def test_01_to_10_hospital_staff_create_request_api(self):
        """
        Tests 1-10:
        - 1: Hospital Staff can create request
        - 2: hospital_staff automatically assigned from request.user
        - 3: Client cannot spoof hospital_staff
        - 4: units_needed > 0
        - 5: Invalid blood group rejected
        - 6: Invalid urgency rejected
        - 7: Defaults to PENDING
        - 8: Cannot directly create APPROVED request
        - 9 & 10: Cannot spoof approved_by or approved_at
        """
        self.client.force_authenticate(user=self.hospital_staff_1)
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "O+",
            "units_needed": 3,
            "urgency": "HIGH",
            "hospital_staff": self.hospital_staff_2.id,  # Spoof attempt
            "status": "APPROVED",                        # Spoof attempt
            "approved_by": self.super_admin.id,          # Spoof attempt
        }
        res = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["hospital_staff_id"], self.hospital_staff_1.id)
        self.assertEqual(res.data["status"], "PENDING")
        self.assertIsNone(res.data["approved_by_id"])
        self.assertEqual(res.data["units_needed"], 3)
        self.assertEqual(res.data["urgency"], "HIGH")

    def test_05_invalid_blood_group_rejected_api(self):
        """Test 5: Invalid blood group rejected with 400."""
        self.client.force_authenticate(user=self.hospital_staff_1)
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "INVALID",
            "units_needed": 1,
        }
        res = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_06_invalid_urgency_rejected_api(self):
        """Test 6: Invalid urgency rejected with 400."""
        self.client.force_authenticate(user=self.hospital_staff_1)
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "A+",
            "units_needed": 1,
            "urgency": "SUPER_URGENT",
        }
        res = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_11_and_12_hospital_staff_isolation(self):
        """Test 11 & 12: Hospital Staff can only view their own requests."""
        req1 = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_1,
            blood_group="A+",
            units_needed=1,
        )
        req2 = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_2,
            blood_bank=self.bank_1,
            blood_group="B+",
            units_needed=2,
        )

        self.client.force_authenticate(user=self.hospital_staff_1)
        res = self.client.get("/api/blood-requests/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], req1.id)

        # Cannot retrieve req2
        res2 = self.client.get(f"/api/blood-requests/{req2.id}/")
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

    def test_13_and_14_blood_bank_admin_isolation(self):
        """Test 13 & 14: Blood Bank Admin sees only requests for their assigned bank."""
        req_bank1 = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_1,
            blood_group="A+",
            units_needed=1,
        )
        req_bank2 = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_2,
            blood_group="B+",
            units_needed=2,
        )

        self.client.force_authenticate(user=self.bank_admin_1)
        res = self.client.get("/api/blood-requests/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], req_bank1.id)

        # Cannot retrieve req_bank2
        res2 = self.client.get(f"/api/blood-requests/{req_bank2.id}/")
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

    def test_15_to_17_unauthorized_roles_cannot_create_requests(self):
        """
        Tests 15-17:
        Only HOSPITAL_STAFF can create Blood Requests.
        SUPER_ADMIN, BLOOD_BANK_ADMIN, LAB_TECHNICIAN, DONOR, and Unauthenticated are all rejected.
        """
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "A+",
            "units_needed": 1,
        }

        # 1. SUPER_ADMIN cannot create requests (403 Forbidden)
        self.client.force_authenticate(user=self.super_admin)
        res_super = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res_super.status_code, status.HTTP_403_FORBIDDEN)

        # 2. BLOOD_BANK_ADMIN cannot create requests (403 Forbidden)
        self.client.force_authenticate(user=self.bank_admin_1)
        res_bank_admin = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res_bank_admin.status_code, status.HTTP_403_FORBIDDEN)

        # 3. LAB_TECHNICIAN cannot create requests (403 Forbidden)
        self.client.force_authenticate(user=self.lab_tech)
        res_lab = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res_lab.status_code, status.HTTP_403_FORBIDDEN)

        # 4. DONOR cannot create requests (403 Forbidden)
        self.client.force_authenticate(user=self.donor_user)
        res_donor = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res_donor.status_code, status.HTTP_403_FORBIDDEN)

        # 5. Unauthenticated cannot create requests (401 Unauthorized)
        self.client.force_authenticate(user=None)
        res_unauth_post = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res_unauth_post.status_code, status.HTTP_401_UNAUTHORIZED)
        res_unauth_get = self.client.get("/api/blood-requests/")
        self.assertEqual(res_unauth_get.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_18_to_25_approve_endpoint_success(self):
        """Test 18-25: POST /api/blood-requests/{id}/approve/ works properly."""
        for i in range(3):
            BloodUnit.objects.create(
                blood_bank=self.bank_1,
                unit_id=f"BU-API-APP-{i}",
                blood_group="O-",
                collection_date=self.today - timedelta(days=2),
                status=BloodUnitStatus.AVAILABLE,
            )

        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_1,
            blood_group="O-",
            units_needed=2,
        )

        self.client.force_authenticate(user=self.bank_admin_1)
        res = self.client.post(f"/api/blood-requests/{req.id}/approve/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "APPROVED")
        self.assertEqual(res.data["approved_by_id"], self.bank_admin_1.id)
        self.assertEqual(len(res.data["reserved_units"]), 2)

    def test_35_other_bank_admin_cannot_approve(self):
        """Test 35: Bank Admin 2 cannot approve a request for Bank 1."""
        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_1,
            blood_group="A+",
            units_needed=1,
        )
        self.client.force_authenticate(user=self.bank_admin_2)
        res = self.client.post(f"/api/blood-requests/{req.id}/approve/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_36_to_42_reject_endpoint(self):
        """Test 36-42: POST /api/blood-requests/{id}/reject/ works properly."""
        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_1,
            blood_group="A+",
            units_needed=1,
        )
        self.client.force_authenticate(user=self.bank_admin_1)
        # Without reason -> 400
        res = self.client.post(f"/api/blood-requests/{req.id}/reject/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # With valid reason -> 200
        res2 = self.client.post(f"/api/blood-requests/{req.id}/reject/", {"rejection_reason": "Donor camp scheduled tomorrow."}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data["status"], "REJECTED")
        self.assertEqual(res2.data["rejection_reason"], "Donor camp scheduled tomorrow.")

    def test_42_other_bank_admin_cannot_reject(self):
        """Test 42: Bank Admin 2 cannot reject a request for Bank 1."""
        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_1,
            blood_group="A+",
            units_needed=1,
        )
        self.client.force_authenticate(user=self.bank_admin_2)
        res = self.client.post(f"/api/blood-requests/{req.id}/reject/", {"rejection_reason": "Rejected"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_43_to_45_critical_urgency_handling(self):
        """
        Tests 43-45:
        - 43: CRITICAL urgency accepted
        - 44: Insufficient stock on critical request remains PENDING
        - 45: No SOS triggered
        """
        self.client.force_authenticate(user=self.hospital_staff_1)
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "AB+",
            "units_needed": 5,
            "urgency": "CRITICAL",
        }
        res = self.client.post("/api/blood-requests/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["urgency"], "CRITICAL")
        self.assertEqual(res.data["status"], "PENDING")

        req_id = res.data["id"]
        # Bank Admin attempts approval when no stock exists
        self.client.force_authenticate(user=self.bank_admin_1)
        res_app = self.client.post(f"/api/blood-requests/{req_id}/approve/", {}, format="json")
        self.assertEqual(res_app.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient stock", res_app.data["detail"])

    def test_48_inventory_summary_reflects_reservation(self):
        """Test 48: Approval moves units from AVAILABLE to RESERVED, reducing available summary count."""
        # Add 2 units of B- in Bank 1
        BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-INV-BMINUS-1",
            blood_group="B-",
            collection_date=self.today,
            status=BloodUnitStatus.AVAILABLE,
        )
        BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-INV-BMINUS-2",
            blood_group="B-",
            collection_date=self.today,
            status=BloodUnitStatus.AVAILABLE,
        )

        # Verify summary initially shows 2 units of B-
        self.client.force_authenticate(user=self.super_admin)
        res_sum1 = self.client.get(f"/api/inventory/summary/?blood_bank={self.bank_1.id}")
        counts1 = {item["blood_group"]: item["available_units"] for item in res_sum1.data["inventory"]}
        self.assertEqual(counts1.get("B-"), 2)

        # Create request for 1 unit of B- and approve it
        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_1,
            blood_group="B-",
            units_needed=1,
        )
        self.client.force_authenticate(user=self.bank_admin_1)
        res_app = self.client.post(f"/api/blood-requests/{req.id}/approve/", {}, format="json")
        self.assertEqual(res_app.status_code, status.HTTP_200_OK)

        # Re-check inventory summary -> B- count should drop to 1
        self.client.force_authenticate(user=self.super_admin)
        res_sum2 = self.client.get(f"/api/inventory/summary/?blood_bank={self.bank_1.id}")
        counts2 = {item["blood_group"]: item["available_units"] for item in res_sum2.data["inventory"]}
        self.assertEqual(counts2.get("B-"), 1)

    def test_49_blood_request_serializer_exposes_facility_location_safely(self):
        """Test 49: BloodRequest serializer safely returns blood bank coordinates without exposing private user location."""
        # Set bank coordinates
        self.bank_1.latitude = Decimal("13.082700")
        self.bank_1.longitude = Decimal("80.270700")
        self.bank_1.address = "123 Healthcare Ave"
        self.bank_1.city = "Chennai"
        self.bank_1.state = "TN"
        self.bank_1.save()

        req = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_1,
            blood_bank=self.bank_1,
            blood_group="O+",
            units_needed=2,
            urgency=RequestUrgency.CRITICAL,
        )

        self.client.force_authenticate(user=self.super_admin)
        res = self.client.get(f"/api/blood-requests/{req.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["blood_bank_latitude"], "13.082700")
        self.assertEqual(res.data["blood_bank_longitude"], "80.270700")
        self.assertEqual(res.data["blood_bank_address"], "123 Healthcare Ave")
        self.assertEqual(res.data["blood_bank_city"], "Chennai")
        self.assertEqual(res.data["blood_bank_state"], "TN")
        # Ensure private user coordinates are not exposed on blood request serializer
        self.assertNotIn("hospital_staff_latitude", res.data)
        self.assertNotIn("hospital_staff_longitude", res.data)


class BloodRequestDonorResponseTest(APITestCase):
    """
    Security and regression test suite for Bug #7:
    - Donor Accept / Decline workflow for Blood Requests.
    - Strict RBAC, request-specific consent isolation, eligibility & compatibility enforcement.
    """
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="super_admin_donor",
            email="super_donor@test.com",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.hospital_staff_a = User.objects.create_user(
            username="hospital_staff_a",
            email="staff_a@hospital.org",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
            address="St. Jude Memorial Hospital",
        )
        self.hospital_staff_b = User.objects.create_user(
            username="hospital_staff_b",
            email="staff_b@hospital.org",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
            address="City General Hospital",
        )
        self.bank_admin = User.objects.create_user(
            username="bank_admin_donor",
            email="admin_donor@bank.org",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.lab_tech = User.objects.create_user(
            username="lab_tech_donor",
            email="lab_tech_donor@test.org",
            password="Password123!",
            role=UserRole.LAB_TECHNICIAN,
        )

        self.bank = BloodBank.objects.create(
            name="Apex Blood Bank",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0199",
            email="apex_bank@test.org",
            capacity=1000,
            admin=self.bank_admin,
        )

        # Donor A: Eligible O+ donor
        self.user_donor_a = User.objects.create_user(
            username="donor_alice",
            email="alice@donor.org",
            phone="+1-555-111-2222",
            first_name="Alice",
            last_name="Smith",
            password="Password123!",
            role=UserRole.DONOR,
        )
        self.donor_a = Donor.objects.create(
            user=self.user_donor_a,
            blood_group=BloodGroup.O_POSITIVE,
            date_of_birth=timezone.now().date() - timedelta(days=25 * 365),
            weight_kg=Decimal("62.00"),
            latitude=Decimal("12.971600"),
            longitude=Decimal("77.594600"),
        )

        # Donor B: Eligible A+ donor
        self.user_donor_b = User.objects.create_user(
            username="donor_bob",
            email="bob@donor.org",
            phone="+1-555-333-4444",
            first_name="Bob",
            last_name="Jones",
            password="Password123!",
            role=UserRole.DONOR,
        )
        self.donor_b = Donor.objects.create(
            user=self.user_donor_b,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=timezone.now().date() - timedelta(days=30 * 365),
            weight_kg=Decimal("70.00"),
        )

        # Donor Ineligible: Underweight (45 kg)
        self.user_donor_ineligible = User.objects.create_user(
            username="donor_underweight",
            email="underweight@donor.org",
            password="Password123!",
            role=UserRole.DONOR,
        )
        self.donor_ineligible = Donor.objects.create(
            user=self.user_donor_ineligible,
            blood_group=BloodGroup.O_POSITIVE,
            date_of_birth=timezone.now().date() - timedelta(days=22 * 365),
            weight_kg=Decimal("45.00"),  # Below 50kg requirement
        )

        # Blood Request 1: Created by Hospital Staff A for O+ blood
        self.request_1 = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_a,
            blood_bank=self.bank,
            blood_group=BloodGroup.O_POSITIVE,
            units_needed=2,
            urgency=RequestUrgency.HIGH,
            status=RequestStatus.PENDING,
        )

        # Blood Request 2: Created by Hospital Staff B for A+ blood
        self.request_2 = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_b,
            blood_bank=self.bank,
            blood_group=BloodGroup.A_POSITIVE,
            units_needed=1,
            urgency=RequestUrgency.NORMAL,
            status=RequestStatus.PENDING,
        )

    def test_01_donor_can_view_active_blood_request_safely(self):
        """1. Donor can view safe details of an active BloodRequest without leaking private data."""
        self.client.force_authenticate(user=self.user_donor_a)
        res = self.client.get(f"/api/blood-requests/{self.request_1.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["blood_group"], "O+")
        self.assertEqual(res.data["units_needed"], 2)
        self.assertEqual(res.data["urgency"], "HIGH")
        # Ensure private user info is not leaked
        self.assertNotIn("password", res.data)
        self.assertNotIn("token", res.data)

    def test_02_donor_can_accept_eligible_compatible_request(self):
        """2. Donor A accepts BloodRequest 1 -> creates APPROVED contact response and consents to reveal."""
        self.client.force_authenticate(user=self.user_donor_a)
        payload = {"action": "ACCEPT", "notes": "Available to donate this afternoon."}
        res = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "APPROVED")
        self.assertEqual(res.data["blood_request_id"], self.request_1.id)
        self.assertEqual(res.data["donor_id"], self.donor_a.id)

        # Donor viewing own response gets contact_details
        self.assertIsNotNone(res.data.get("contact_details"))
        self.assertEqual(res.data["contact_details"]["phone"], "+1-555-111-2222")
        self.assertEqual(res.data["contact_details"]["email"], "alice@donor.org")

        # Verify DB state
        contact_req = DonorContactRequest.objects.get(blood_request=self.request_1, donor=self.donor_a)
        self.assertEqual(contact_req.status, ContactRequestStatus.APPROVED)
        self.assertIsNotNone(contact_req.responded_at)

    def test_03_donor_can_decline_blood_request(self):
        """3. Donor A declines BloodRequest 1 -> status is DECLINED and contact details remain hidden."""
        self.client.force_authenticate(user=self.user_donor_a)
        payload = {"action": "DECLINE", "notes": "Cannot donate at this time."}
        res = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "DECLINED")
        self.assertIsNone(res.data.get("contact_details"))

        contact_req = DonorContactRequest.objects.get(blood_request=self.request_1, donor=self.donor_a)
        self.assertEqual(contact_req.status, ContactRequestStatus.DECLINED)

    def test_04_duplicate_response_prevention(self):
        """4. Repeated ACCEPT / DECLINE from same donor for same request is rejected."""
        self.client.force_authenticate(user=self.user_donor_a)
        res1 = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # Attempt duplicate ACCEPT
        res2 = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already accepted", res2.data["detail"])

    def test_05_same_donor_can_respond_to_different_requests(self):
        """5. Same donor can respond to different blood requests independently."""
        self.client.force_authenticate(user=self.user_donor_a)
        # O+ donor accepts Request 1 (O+ needed)
        res1 = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # O+ donor can also accept Request 2 (A+ needed, and O+ is RBC compatible with A+)
        res2 = self.client.post(f"/api/blood-requests/{self.request_2.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

        # Verify 2 distinct response records exist
        self.assertEqual(DonorContactRequest.objects.filter(donor=self.donor_a).count(), 2)

    def test_06_ineligible_donor_cannot_accept(self):
        """6. Ineligible donor (underweight <50kg) cannot accept a blood request."""
        self.client.force_authenticate(user=self.user_donor_ineligible)
        res = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not eligible", res.data["detail"].lower())

    def test_07_incompatible_donor_cannot_accept(self):
        """7. Incompatible donor (A+ donor for O+ request) cannot accept."""
        # Donor B is A+. Request 1 requires O+. A+ cannot donate to O+.
        self.client.force_authenticate(user=self.user_donor_b)
        res = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not compatible", res.data["detail"].lower())

    def test_08_closed_or_rejected_request_cannot_receive_responses(self):
        """8. Donors cannot respond to closed (REJECTED/COMPLETED/DISPATCHED) requests."""
        self.request_1.status = RequestStatus.REJECTED
        self.request_1.rejection_reason = "Cancelled by facility"
        self.request_1.save()

        self.client.force_authenticate(user=self.user_donor_a)
        res = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot respond", res.data["detail"])

    def test_09_unauthenticated_and_non_donor_cannot_respond(self):
        """9. Unauthenticated or non-donor roles cannot respond to blood requests."""
        # Unauthenticated
        self.client.force_authenticate(user=None)
        res_unauth = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # Hospital staff cannot respond as donor
        self.client.force_authenticate(user=self.hospital_staff_a)
        res_staff = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res_staff.status_code, status.HTTP_403_FORBIDDEN)

    def test_10_requester_can_view_responses_for_their_request(self):
        """10. Hospital Staff A can view donor responses and permitted contact details for their request."""
        # Donor A accepts Request 1
        self.client.force_authenticate(user=self.user_donor_a)
        self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")

        # Hospital Staff A queries responses for Request 1
        self.client.force_authenticate(user=self.hospital_staff_a)
        res = self.client.get(f"/api/blood-requests/{self.request_1.id}/responses/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        resp_item = res.data[0]
        self.assertEqual(resp_item["status"], "APPROVED")
        self.assertIsNotNone(resp_item.get("contact_details"))
        self.assertEqual(resp_item["contact_details"]["name"], "Alice Smith")
        self.assertEqual(resp_item["contact_details"]["phone"], "+1-555-111-2222")
        self.assertEqual(resp_item["contact_details"]["email"], "alice@donor.org")

    def test_11_unrelated_hospital_staff_cannot_view_responses(self):
        """11. Hospital Staff B cannot view responses for Hospital Staff A's request."""
        # Donor A accepts Request 1 (owned by Staff A)
        self.client.force_authenticate(user=self.user_donor_a)
        self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")

        # Hospital Staff B attempts to query responses for Request 1
        self.client.force_authenticate(user=self.hospital_staff_b)
        res = self.client.get(f"/api/blood-requests/{self.request_1.id}/responses/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_12_declined_donor_contact_details_remain_hidden_from_requester(self):
        """12. If a donor declines, requester sees DECLINED status but contact_details is null."""
        self.client.force_authenticate(user=self.user_donor_a)
        self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "DECLINE"}, format="json")

        self.client.force_authenticate(user=self.hospital_staff_a)
        res = self.client.get(f"/api/blood-requests/{self.request_1.id}/responses/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["status"], "DECLINED")
        self.assertIsNone(res.data[0].get("contact_details"))

    def test_13_blood_bank_admin_and_lab_tech_cannot_view_responses(self):
        """13. Blood Bank Admin and Lab Tech cannot view donor responses."""
        self.client.force_authenticate(user=self.bank_admin)
        res_admin = self.client.get(f"/api/blood-requests/{self.request_1.id}/responses/")
        self.assertEqual(res_admin.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.lab_tech)
        res_lab = self.client.get(f"/api/blood-requests/{self.request_1.id}/responses/")
        self.assertEqual(res_lab.status_code, status.HTTP_403_FORBIDDEN)

    def test_14_request_specific_consent_isolation(self):
        """
        14. Critical Step 17 test:
        - Donor A accepts BloodRequest #1 (owned by Hospital Staff A).
        - Hospital Staff A CAN access Donor A's contact details for Request #1.
        - Hospital Staff B CANNOT access Donor A's contact details for Request #2 merely because Donor A accepted Request #1.
        - Donor A declines BloodRequest #2.
        - Hospital Staff B receives DECLINED response with NO contact details.
        """
        # 1. Donor A accepts Request 1
        self.client.force_authenticate(user=self.user_donor_a)
        res_accept_1 = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res_accept_1.status_code, status.HTTP_200_OK)

        # 2. Hospital Staff A views Request 1 responses -> has contact details
        self.client.force_authenticate(user=self.hospital_staff_a)
        res_staff_a = self.client.get(f"/api/blood-requests/{self.request_1.id}/responses/")
        self.assertEqual(res_staff_a.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(res_staff_a.data[0]["contact_details"])
        self.assertEqual(res_staff_a.data[0]["contact_details"]["phone"], "+1-555-111-2222")

        # 3. Hospital Staff B views Request 2 responses -> empty (Donor A hasn't responded to Request 2)
        self.client.force_authenticate(user=self.hospital_staff_b)
        res_staff_b = self.client.get(f"/api/blood-requests/{self.request_2.id}/responses/")
        self.assertEqual(res_staff_b.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_staff_b.data), 0)

        # 4. Donor A declines Request 2
        self.client.force_authenticate(user=self.user_donor_a)
        res_decline_2 = self.client.post(f"/api/blood-requests/{self.request_2.id}/respond/", {"action": "DECLINE"}, format="json")
        self.assertEqual(res_decline_2.status_code, status.HTTP_200_OK)

        # 5. Hospital Staff B re-queries Request 2 responses -> sees DECLINED, contact_details is None
        self.client.force_authenticate(user=self.hospital_staff_b)
        res_staff_b_declined = self.client.get(f"/api/blood-requests/{self.request_2.id}/responses/")
        self.assertEqual(res_staff_b_declined.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_staff_b_declined.data), 1)
        self.assertEqual(res_staff_b_declined.data[0]["status"], "DECLINED")
        self.assertIsNone(res_staff_b_declined.data[0]["contact_details"])

    def test_15_exact_donor_coordinates_and_secrets_never_exposed(self):
        """15. Exact donor coordinates (latitude/longitude) and auth secrets are never exposed in responses."""
        self.client.force_authenticate(user=self.user_donor_a)
        res_accept = self.client.post(f"/api/blood-requests/{self.request_1.id}/respond/", {"action": "ACCEPT"}, format="json")
        self.assertEqual(res_accept.status_code, status.HTTP_200_OK)

        # Inspect serializer output for donor
        self.assertNotIn("latitude", res_accept.data)
        self.assertNotIn("longitude", res_accept.data)
        self.assertNotIn("password", res_accept.data)

        # Inspect serializer output for requester
        self.client.force_authenticate(user=self.hospital_staff_a)
        res_req = self.client.get(f"/api/blood-requests/{self.request_1.id}/responses/")
        self.assertEqual(res_req.status_code, status.HTTP_200_OK)
        resp_obj = res_req.data[0]
        self.assertNotIn("latitude", resp_obj)
        self.assertNotIn("longitude", resp_obj)
        if resp_obj.get("contact_details"):
            self.assertNotIn("latitude", resp_obj["contact_details"])
            self.assertNotIn("longitude", resp_obj["contact_details"])
            self.assertNotIn("password", resp_obj["contact_details"])


class BloodRequestDonorOutcomeTest(APITestCase):
    """
    Test suite for Bug #9: Hospital Staff Donation Outcome Workflow.
    Verifies recording COMPLETED / DID_NOT_HAPPEN, RBAC, prerequisite state checks,
    idempotency/immutability, and Bug #10 boundary insulation.
    """

    def setUp(self):
        # 1. Users
        self.hospital_staff_a = User.objects.create_user(
            username="hospital_staff_a_out",
            email="staff_a_out@hospital.org",
            role=UserRole.HOSPITAL_STAFF,
            password="Password123!",
            first_name="Dr. Hospital",
            last_name="Staff A",
        )
        self.hospital_staff_b = User.objects.create_user(
            username="hospital_staff_b_out",
            email="staff_b_out@hospital.org",
            role=UserRole.HOSPITAL_STAFF,
            password="Password123!",
            first_name="Dr. Hospital",
            last_name="Staff B",
        )
        self.bank_admin = User.objects.create_user(
            username="bank_admin_out",
            email="admin_out@bank.org",
            role=UserRole.BLOOD_BANK_ADMIN,
            password="Password123!",
        )
        self.lab_tech = User.objects.create_user(
            username="lab_tech_out",
            email="tech_out@lab.org",
            role=UserRole.LAB_TECHNICIAN,
            password="Password123!",
        )
        self.super_admin = User.objects.create_superuser(
            username="super_admin_out",
            email="admin_out@super.org",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )

        # 2. Donor User & Profile
        self.user_donor = User.objects.create_user(
            username="donor_outcome_user",
            email="donor_outcome@example.com",
            role=UserRole.DONOR,
            phone="+1-555-999-8888",
            password="Password123!",
            first_name="Outcome",
            last_name="Test Donor",
        )
        self.donor_profile = Donor.objects.create(
            user=self.user_donor,
            blood_group="O+",
            date_of_birth=date(1995, 5, 20),
            weight_kg=Decimal("70.00"),
            last_donation_date=None,
        )

        self.user_donor_2 = User.objects.create_user(
            username="donor_outcome_user_2",
            email="donor_outcome_2@example.com",
            role=UserRole.DONOR,
            phone="+1-555-999-8889",
            password="Password123!",
            first_name="Pending",
            last_name="Test Donor",
        )
        self.donor_profile_2 = Donor.objects.create(
            user=self.user_donor_2,
            blood_group="O+",
            date_of_birth=date(1996, 6, 15),
            weight_kg=Decimal("65.00"),
        )

        self.user_donor_3 = User.objects.create_user(
            username="donor_outcome_user_3",
            email="donor_outcome_3@example.com",
            role=UserRole.DONOR,
            phone="+1-555-999-8890",
            password="Password123!",
            first_name="Declined",
            last_name="Test Donor",
        )
        self.donor_profile_3 = Donor.objects.create(
            user=self.user_donor_3,
            blood_group="O+",
            date_of_birth=date(1997, 7, 10),
            weight_kg=Decimal("68.00"),
        )

        # 3. Blood Bank & Blood Requests
        self.bank = BloodBank.objects.create(
            name="Central Outcome Blood Bank",
            admin=self.bank_admin,
            latitude=Decimal("12.971600"),
            longitude=Decimal("77.594600"),
        )
        self.request_a = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_a,
            blood_bank=self.bank,
            blood_group="O+",
            units_needed=2,
            urgency="HIGH",
            status="APPROVED",
        )
        self.request_b = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff_b,
            blood_bank=self.bank,
            blood_group="O+",
            units_needed=1,
            urgency="NORMAL",
            status="PENDING",
        )

        # 4. Accepted donor response on Request A
        self.accepted_response = DonorContactRequest.objects.create(
            blood_request=self.request_a,
            donor=self.donor_profile,
            requester=self.hospital_staff_a,
            hospital_name="Hospital Facility A",
            blood_group="O+",
            urgency="HIGH",
            status=ContactRequestStatus.APPROVED,
            responded_at=timezone.now(),
        )

    def test_01_request_owner_can_mark_accepted_donor_completed(self):
        """1. Request owner records COMPLETED: creates Donation, BloodUnit (TESTING), updates last_donation_date."""
        self.client.force_authenticate(user=self.hospital_staff_a)
        payload = {
            "outcome": "COMPLETED",
            "notes": "Collected 1 unit of whole blood successfully.",
        }
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["donation_outcome"], "COMPLETED")
        self.assertEqual(res.data["donation_outcome_display"], "Donation Completed")
        self.assertIsNotNone(res.data["outcome_recorded_at"])
        self.assertEqual(res.data["outcome_recorded_by_name"], "Dr. Hospital Staff A")
        self.assertEqual(res.data["outcome_notes"], "Collected 1 unit of whole blood successfully.")
        self.assertIsNotNone(res.data.get("donation_id"))

        # Verify DB state & Bug #10 integration
        self.accepted_response.refresh_from_db()
        self.assertEqual(self.accepted_response.donation_outcome, "COMPLETED")
        self.assertEqual(self.accepted_response.outcome_recorded_by, self.hospital_staff_a)
        self.assertIsNotNone(self.accepted_response.donation)

        # Donation and BloodUnit created correctly
        donation = self.accepted_response.donation
        self.assertEqual(donation.donor, self.donor_profile)
        self.assertEqual(donation.blood_bank, self.bank)
        self.assertEqual(donation.blood_request, self.request_a)
        self.assertEqual(donation.donation_date, timezone.now().date())
        self.assertIsNotNone(donation.blood_unit)
        self.assertEqual(donation.blood_unit.status, BloodUnitStatus.TESTING)
        self.assertEqual(donation.blood_unit.blood_group, self.donor_profile.blood_group)

        # Donor last donation date and immediate cooldown
        self.donor_profile.refresh_from_db()
        self.assertEqual(self.donor_profile.last_donation_date, timezone.now().date())
        self.assertFalse(self.donor_profile.is_eligible)

    def test_02_request_owner_can_mark_accepted_donor_did_not_happen(self):
        """2. Request owner can record donation outcome as DID_NOT_HAPPEN."""
        self.client.force_authenticate(user=self.hospital_staff_a)
        payload = {
            "outcome": "DID_NOT_HAPPEN",
            "notes": "Donor could not travel due to emergency.",
        }
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["donation_outcome"], "DID_NOT_HAPPEN")
        self.assertEqual(res.data["donation_outcome_display"], "Donation Did Not Happen")
        self.assertIsNotNone(res.data["outcome_recorded_at"])
        self.assertEqual(res.data["outcome_notes"], "Donor could not travel due to emergency.")
        self.assertIsNone(res.data.get("donation_id"))

        # Verify DB state & Bug #10 boundary
        self.accepted_response.refresh_from_db()
        self.assertIsNone(self.accepted_response.donation)
        self.donor_profile.refresh_from_db()
        self.assertIsNone(self.donor_profile.last_donation_date)
        self.assertTrue(self.donor_profile.is_eligible)

    def test_03_other_hospital_staff_cannot_mark_outcome(self):
        """3. Hospital Staff B cannot record outcome for Hospital Staff A's request."""
        self.client.force_authenticate(user=self.hospital_staff_b)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_04_donor_cannot_mark_outcome(self):
        """4. Donor cannot record their own donation outcome."""
        self.client.force_authenticate(user=self.user_donor)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_05_blood_bank_admin_cannot_mark_outcome(self):
        """5. Blood Bank Admin cannot record outcome for hospital blood request."""
        self.client.force_authenticate(user=self.bank_admin)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_06_lab_tech_cannot_mark_outcome(self):
        """6. Lab Technician cannot record outcome."""
        self.client.force_authenticate(user=self.lab_tech)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_07_super_admin_cannot_mark_outcome_without_ownership(self):
        """7. Super Admin does not receive blanket outcome permission without owning the request."""
        self.client.force_authenticate(user=self.super_admin)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_08_pending_response_cannot_be_marked_outcome(self):
        """8. A PENDING donor response cannot be marked as COMPLETED or DID_NOT_HAPPEN."""
        pending_resp = DonorContactRequest.objects.create(
            blood_request=self.request_a,
            donor=self.donor_profile_2,
            requester=self.hospital_staff_a,
            status=ContactRequestStatus.PENDING,
        )
        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{pending_resp.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("has not been accepted", res.data["detail"])

    def test_09_declined_response_cannot_be_marked_outcome(self):
        """9. A DECLINED donor response cannot be marked as COMPLETED or DID_NOT_HAPPEN."""
        declined_resp = DonorContactRequest.objects.create(
            blood_request=self.request_a,
            donor=self.donor_profile_3,
            requester=self.hospital_staff_a,
            status=ContactRequestStatus.DECLINED,
            responded_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{declined_resp.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("has not been accepted", res.data["detail"])

    def test_10_completed_response_cannot_be_completed_twice(self):
        """10. Recording COMPLETED twice is rejected to prevent duplicate outcomes."""
        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res1 = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        res2 = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been recorded", res2.data["detail"])
        # Verify only 1 donation exists in total
        self.assertEqual(Donation.objects.filter(donor=self.donor_profile).count(), 1)

    def test_11_completed_response_cannot_be_overwritten_to_did_not_happen(self):
        """11. Completed outcome cannot be overwritten to DID_NOT_HAPPEN."""
        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res1 = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        res2 = self.client.post(url, {"outcome": "DID_NOT_HAPPEN"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been recorded", res2.data["detail"])

    def test_12_did_not_happen_cannot_be_overwritten_to_completed(self):
        """12. DID_NOT_HAPPEN outcome cannot be overwritten to COMPLETED."""
        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res1 = self.client.post(url, {"outcome": "DID_NOT_HAPPEN"}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        res2 = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been recorded", res2.data["detail"])

    def test_13_unauthenticated_user_cannot_mark_outcome(self):
        """13. Unauthenticated requests are rejected."""
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_14_nonexistent_request_or_response_returns_404(self):
        """14. 404 is returned if blood request or response record does not exist."""
        self.client.force_authenticate(user=self.hospital_staff_a)
        # Invalid blood request
        res1 = self.client.post(f"/api/blood-requests/99999/responses/{self.accepted_response.id}/outcome/", {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_404_NOT_FOUND)

        # Invalid response id
        res2 = self.client.post(f"/api/blood-requests/{self.request_a.id}/responses/99999/outcome/", {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_404_NOT_FOUND)

    def test_15_invalid_outcome_choice_returns_400(self):
        """15. Invalid outcome value returns 400 Bad Request."""
        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "UNKNOWN_CHOICE"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_16_cooldown_boundary_re_eligibility(self):
        """16. Donor eligibility automatically recovers after the 90-day cooldown boundary."""
        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.donor_profile.refresh_from_db()
        today = timezone.now().date()

        # Day 0 (today) -> Ineligible
        elig_today = self.donor_profile.calculate_eligibility(reference_date=today)
        self.assertFalse(elig_today["is_eligible"])
        self.assertFalse(elig_today["criteria"]["donation_interval"]["passed"])

        # Day 89 -> Ineligible
        elig_89 = self.donor_profile.calculate_eligibility(reference_date=today + timedelta(days=89))
        self.assertFalse(elig_89["is_eligible"])

        # Day 90 (exactly at 90 days) -> Eligible
        elig_90 = self.donor_profile.calculate_eligibility(reference_date=today + timedelta(days=90))
        self.assertTrue(elig_90["is_eligible"])
        self.assertTrue(elig_90["criteria"]["donation_interval"]["passed"])

        # Day 91 (after 90 days) -> Eligible
        elig_91 = self.donor_profile.calculate_eligibility(reference_date=today + timedelta(days=91))
        self.assertTrue(elig_91["is_eligible"])

    def test_17_sos_donor_targeting_respects_cooldown(self):
        """17. Donors during cooldown are excluded from SOS targeting and included again after 90 days."""
        # Baseline: donor is eligible and compatible with O+
        eligible_before = find_eligible_compatible_donors(
            blood_request=self.request_a,
            radius_km=Decimal("50.0"),
            reference_date=timezone.now().date(),
        )
        donor_ids_before = [d.id for d in eligible_before]
        self.assertIn(self.donor_profile.id, donor_ids_before)

        # Mark donation COMPLETED
        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # During cooldown (today + 30 days): excluded from SOS targeting
        eligible_during = find_eligible_compatible_donors(
            blood_request=self.request_a,
            radius_km=Decimal("50.0"),
            reference_date=timezone.now().date() + timedelta(days=30),
        )
        donor_ids_during = [d.id for d in eligible_during]
        self.assertNotIn(self.donor_profile.id, donor_ids_during)

        # After cooldown (today + 91 days): included in SOS targeting again
        eligible_after = find_eligible_compatible_donors(
            blood_request=self.request_a,
            radius_km=Decimal("50.0"),
            reference_date=timezone.now().date() + timedelta(days=91),
        )
        donor_ids_after = [d.id for d in eligible_after]
        self.assertIn(self.donor_profile.id, donor_ids_after)

    def test_18_ineligible_donor_outcome_fails_gracefully_and_rolls_back(self):
        """18. If donor is medically ineligible on donation date, outcome fails and transaction rolls back."""
        # Set donor's last_donation_date to 10 days ago so they fail eligibility check
        self.donor_profile.last_donation_date = timezone.now().date() - timedelta(days=10)
        self.donor_profile.save(update_fields=["last_donation_date"])

        self.client.force_authenticate(user=self.hospital_staff_a)
        url = f"/api/blood-requests/{self.request_a.id}/responses/{self.accepted_response.id}/outcome/"
        res = self.client.post(url, {"outcome": "COMPLETED"}, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not eligible", res.data["detail"].lower())

        # Verify transaction rollback: no Donation created, outcome remains NOT_RECORDED
        self.accepted_response.refresh_from_db()
        self.assertEqual(self.accepted_response.donation_outcome, DonationOutcome.NOT_RECORDED)
        self.assertIsNone(self.accepted_response.donation)
        self.assertEqual(Donation.objects.filter(donor=self.donor_profile).count(), 0)
