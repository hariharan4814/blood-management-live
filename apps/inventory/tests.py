from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.donors.models import BloodGroup
from .models import BloodBank, BloodUnit, BloodUnitStatus, RBC_SHELF_LIFE_DAYS
from .services import get_bank_inventory_summary

User = get_user_model()


class BloodBankModelTest(TestCase):
    """
    Model unit tests for BloodBank entity and field validations.
    """
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="superadmin",
            email="superadmin@test.com",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.bank_admin = User.objects.create_user(
            username="bankadmin",
            email="bankadmin@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )

    def test_01_blood_bank_creation_success(self):
        """Test 1: BloodBank creation with valid fields."""
        bank = BloodBank.objects.create(
            name="Red Cross Central Blood Bank",
            address="100 Medical Blvd",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0199",
            email="contact@redcrosscentral.org",
            capacity=500,
            latitude=Decimal("40.712776"),
            longitude=Decimal("-74.005974"),
            is_active=True,
            admin=self.bank_admin,
        )
        self.assertEqual(bank.name, "Red Cross Central Blood Bank")
        self.assertEqual(bank.capacity, 500)
        self.assertTrue(bank.is_active)
        self.assertEqual(str(bank), "Red Cross Central Blood Bank (Metropolis, Central State)")

    def test_02_negative_capacity_rejection(self):
        """Test 2: Negative capacity rejection."""
        bank = BloodBank(
            name="Invalid Bank",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0100",
            email="test@bank.org",
            capacity=-10,
        )
        with self.assertRaises(ValidationError):
            bank.clean()

    def test_03_invalid_latitude_rejection(self):
        """Test 3: Latitude out of range (-90 to 90) rejection."""
        bank = BloodBank(
            name="Invalid Lat Bank",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0100",
            email="test@bank.org",
            capacity=100,
            latitude=Decimal("95.000000"),
        )
        with self.assertRaises(ValidationError):
            bank.clean()

    def test_04_invalid_longitude_rejection(self):
        """Test 4: Longitude out of range (-180 to 180) rejection."""
        bank = BloodBank(
            name="Invalid Long Bank",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0100",
            email="test@bank.org",
            capacity=100,
            longitude=Decimal("-185.000000"),
        )
        with self.assertRaises(ValidationError):
            bank.clean()

    def test_05_invalid_admin_role_rejection(self):
        """Test: Assigned admin must have BLOOD_BANK_ADMIN or SUPER_ADMIN role."""
        donor_user = User.objects.create_user(
            username="donoruser",
            email="donoruser@test.com",
            password="Password123!",
            role=UserRole.DONOR,
        )
        bank = BloodBank(
            name="Test Bank",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0100",
            email="test@bank.org",
            capacity=100,
            admin=donor_user,
        )
        with self.assertRaises(ValidationError):
            bank.clean()


class BloodUnitModelTest(TestCase):
    """
    Model unit tests for BloodUnit entity, 42-day expiry rule, and lifecycle status.
    """
    def setUp(self):
        self.bank = BloodBank.objects.create(
            name="City Blood Center",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0123",
            email="city@center.org",
            capacity=300,
        )

    def test_08_blood_unit_creation_success(self):
        """Test 8: BloodUnit creation with valid fields."""
        today = timezone.now().date()
        unit = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-TEST-001",
            blood_group=BloodGroup.O_POSITIVE,
            collection_date=today,
        )
        self.assertEqual(unit.unit_id, "BU-TEST-001")
        self.assertEqual(unit.status, BloodUnitStatus.TESTING)
        self.assertEqual(unit.expiry_date, today + timedelta(days=42))

    def test_09_default_status_is_testing(self):
        """Test 9: BloodUnit creation defaults to TESTING status."""
        today = timezone.now().date()
        unit = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-TEST-002",
            blood_group=BloodGroup.A_POSITIVE,
            collection_date=today,
        )
        self.assertEqual(unit.status, BloodUnitStatus.TESTING)

    def test_10_unique_unit_id(self):
        """Test 10: BloodUnit unit_id must be unique."""
        today = timezone.now().date()
        BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-DUPLICATE-001",
            blood_group=BloodGroup.B_POSITIVE,
            collection_date=today,
        )
        with self.assertRaises(Exception):
            BloodUnit.objects.create(
                blood_bank=self.bank,
                unit_id="BU-DUPLICATE-001",
                blood_group=BloodGroup.AB_POSITIVE,
                collection_date=today,
            )

    def test_11_valid_blood_groups(self):
        """Test 11: All 8 ABO/Rh blood groups can be assigned."""
        today = timezone.now().date()
        for idx, (bg_code, _) in enumerate(BloodGroup.choices):
            unit = BloodUnit.objects.create(
                blood_bank=self.bank,
                unit_id=f"BU-BG-{idx}",
                blood_group=bg_code,
                collection_date=today,
            )
            self.assertEqual(unit.blood_group, bg_code)

    def test_13_future_collection_date_rejection(self):
        """Test 13: Future collection date rejection."""
        tomorrow = timezone.now().date() + timedelta(days=1)
        unit = BloodUnit(
            blood_bank=self.bank,
            unit_id="BU-FUTURE-001",
            blood_group=BloodGroup.O_NEGATIVE,
            collection_date=tomorrow,
        )
        with self.assertRaises(ValidationError):
            unit.clean()

    def test_14_automatic_expiry_date_42_days(self):
        """Test 14: Automatic expiry date = collection_date + 42 days."""
        collection_date = timezone.now().date() - timedelta(days=10)
        unit = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-EXP-001",
            blood_group=BloodGroup.A_NEGATIVE,
            collection_date=collection_date,
        )
        self.assertEqual(unit.expiry_date, collection_date + timedelta(days=42))

    def test_15_inconsistent_expiry_date_rejection(self):
        """Test 15: Client cannot arbitrarily bypass 42-day expiry rule."""
        collection_date = timezone.now().date() - timedelta(days=5)
        invalid_expiry = collection_date + timedelta(days=60)
        unit = BloodUnit(
            blood_bank=self.bank,
            unit_id="BU-OVERRIDE-001",
            blood_group=BloodGroup.B_NEGATIVE,
            collection_date=collection_date,
            expiry_date=invalid_expiry,
        )
        with self.assertRaises(ValidationError):
            unit.clean()

    def test_16_expired_unit_is_not_available_stock(self):
        """Test 16: Expired units are excluded from available stock."""
        # Collected 50 days ago -> expired 8 days ago
        old_collection = timezone.now().date() - timedelta(days=50)
        expired_unit = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-EXPIRED-001",
            blood_group=BloodGroup.O_POSITIVE,
            collection_date=old_collection,
            status=BloodUnitStatus.AVAILABLE,
        )
        self.assertTrue(expired_unit.is_expired)
        self.assertFalse(expired_unit.is_available_stock)


class BloodBankAPITest(APITestCase):
    """
    API integration tests for BloodBank endpoints and RBAC.
    """
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="super_admin_user",
            email="super_admin@test.com",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.bank_admin_1 = User.objects.create_user(
            username="bank_admin_1",
            email="bank_admin_1@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.bank_admin_2 = User.objects.create_user(
            username="bank_admin_2",
            email="bank_admin_2@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.hospital_staff = User.objects.create_user(
            username="hospital_staff_user",
            email="hospital@test.com",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )
        self.donor_user = User.objects.create_user(
            username="donor_user",
            email="donor@test.com",
            password="Password123!",
            role=UserRole.DONOR,
        )
        self.lab_tech = User.objects.create_user(
            username="lab_tech_user",
            email="labtech@test.com",
            password="Password123!",
            role=UserRole.LAB_TECHNICIAN,
        )

        self.bank_1 = BloodBank.objects.create(
            name="Bank One",
            city="City A",
            state="State A",
            contact_number="+1-111-1111",
            email="bank1@test.com",
            capacity=200,
            admin=self.bank_admin_1,
        )
        self.bank_2 = BloodBank.objects.create(
            name="Bank Two",
            city="City B",
            state="State B",
            contact_number="+1-222-2222",
            email="bank2@test.com",
            capacity=300,
            admin=self.bank_admin_2,
        )

    def test_06_super_admin_can_create_and_list_all_banks(self):
        """Test 6: SUPER_ADMIN can create and list all blood banks."""
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.get("/api/blood-banks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see both banks
        self.assertEqual(len(response.data.get("results", response.data)), 2)

        # Super Admin creates a new bank
        create_payload = {
            "name": "New Alpha Blood Bank",
            "city": "Capital City",
            "state": "Capital State",
            "contact_number": "+1-999-8888",
            "email": "alpha@bank.org",
            "capacity": 400,
        }
        res = self.client.post("/api/blood-banks/", create_payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "New Alpha Blood Bank")

    def test_05_invalid_email_rejection(self):
        """Test 5: Invalid email format rejection during creation."""
        self.client.force_authenticate(user=self.super_admin)
        payload = {
            "name": "Bad Email Bank",
            "city": "City X",
            "state": "State X",
            "contact_number": "+1-000-0000",
            "email": "not-an-email",
            "capacity": 100,
        }
        res = self.client.post("/api/blood-banks/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", res.data)

    def test_02_negative_capacity_rejection_api(self):
        """Test 2: Negative capacity rejection via API."""
        self.client.force_authenticate(user=self.super_admin)
        payload = {
            "name": "Negative Cap Bank",
            "city": "City X",
            "state": "State X",
            "contact_number": "+1-000-0000",
            "email": "cap@bank.org",
            "capacity": -50,
        }
        res = self.client.post("/api/blood-banks/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_03_invalid_latitude_rejection_api(self):
        """Test 3: Invalid latitude rejection via API."""
        self.client.force_authenticate(user=self.super_admin)
        payload = {
            "name": "Invalid Lat Bank",
            "city": "City X",
            "state": "State X",
            "contact_number": "+1-000-0000",
            "email": "lat@bank.org",
            "capacity": 100,
            "latitude": 99.5,
        }
        res = self.client.post("/api/blood-banks/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_04_invalid_longitude_rejection_api(self):
        """Test 4: Invalid longitude rejection via API."""
        self.client.force_authenticate(user=self.super_admin)
        payload = {
            "name": "Invalid Long Bank",
            "city": "City X",
            "state": "State X",
            "contact_number": "+1-000-0000",
            "email": "long@bank.org",
            "capacity": 100,
            "longitude": -190.0,
        }
        res = self.client.post("/api/blood-banks/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_07_unauthorized_access_rejection(self):
        """Test 7: Unauthenticated users are rejected with 401."""
        res = self.client.get("/api/blood-banks/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        res = self.client.post("/api/blood-banks/", {"name": "Test"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_25_super_admin_can_manage_all_banks(self):
        """Test 25: SUPER_ADMIN can update any blood bank."""
        self.client.force_authenticate(user=self.super_admin)
        res = self.client.patch(f"/api/blood-banks/{self.bank_1.id}/", {"capacity": 550}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["capacity"], 550)

    def test_26_blood_bank_admin_isolation(self):
        """Test 26: BLOOD_BANK_ADMIN can only view/manage their assigned bank."""
        self.client.force_authenticate(user=self.bank_admin_1)
        # Bank Admin 1 listing banks should only see Bank 1
        res = self.client.get("/api/blood-banks/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.bank_1.id)

        # Bank Admin 1 cannot access Bank 2 detail
        res2 = self.client.get(f"/api/blood-banks/{self.bank_2.id}/")
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

        # Bank Admin 1 cannot update Bank 2
        res3 = self.client.patch(f"/api/blood-banks/{self.bank_2.id}/", {"capacity": 999}, format="json")
        self.assertEqual(res3.status_code, status.HTTP_403_FORBIDDEN)

        # Bank Admin 1 cannot create new banks
        res4 = self.client.post("/api/blood-banks/", {"name": "Unauthorized Bank"}, format="json")
        self.assertEqual(res4.status_code, status.HTTP_403_FORBIDDEN)

    def test_27a_hospital_staff_can_list_active_blood_banks(self):
        """Test 27a: HOSPITAL_STAFF can list active blood banks with safe public fields."""
        self.client.force_authenticate(user=self.hospital_staff)
        res = self.client.get("/api/blood-banks/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 2)
        bank_data = results[0]
        self.assertIn("id", bank_data)
        self.assertIn("name", bank_data)
        self.assertIn("city", bank_data)
        self.assertIn("state", bank_data)
        self.assertIn("contact_number", bank_data)
        # Verify sensitive administrative/inventory fields are excluded
        self.assertNotIn("admin_email", bank_data)
        self.assertNotIn("admin_username", bank_data)
        self.assertNotIn("total_units_count", bank_data)
        self.assertNotIn("capacity", bank_data)

    def test_27b_hospital_staff_cannot_see_inactive_blood_banks(self):
        """Test 27b: Inactive blood banks are excluded from Hospital Staff listing."""
        inactive_bank = BloodBank.objects.create(
            name="Inactive Reserve Bank",
            city="Coimbatore",
            state="Tamil Nadu",
            contact_number="+91-9000000000",
            email="inactive@bank.org",
            capacity=100,
            is_active=False,
        )
        self.client.force_authenticate(user=self.hospital_staff)
        res = self.client.get("/api/blood-banks/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        bank_ids = [b["id"] for b in results]
        self.assertNotIn(inactive_bank.id, bank_ids)

        # Direct detail GET of inactive bank is rejected with 403
        res_detail = self.client.get(f"/api/blood-banks/{inactive_bank.id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_403_FORBIDDEN)

    def test_27c_hospital_staff_cannot_create_modify_or_delete_blood_banks(self):
        """Test 27c: HOSPITAL_STAFF is strictly forbidden from creating, updating, or deleting blood banks."""
        self.client.force_authenticate(user=self.hospital_staff)
        # Cannot POST
        res_post = self.client.post("/api/blood-banks/", {"name": "Hospital Bank"}, format="json")
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot PATCH
        res_patch = self.client.patch(f"/api/blood-banks/{self.bank_1.id}/", {"capacity": 999}, format="json")
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot PUT
        res_put = self.client.put(f"/api/blood-banks/{self.bank_1.id}/", {"name": "New Name"}, format="json")
        self.assertEqual(res_put.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot DELETE
        res_del = self.client.delete(f"/api/blood-banks/{self.bank_1.id}/")
        self.assertEqual(res_del.status_code, status.HTTP_403_FORBIDDEN)

    def test_28_donor_rejected(self):
        """Test 28: DONOR cannot perform blood bank administration."""
        self.client.force_authenticate(user=self.donor_user)
        res = self.client.get("/api/blood-banks/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_29_lab_tech_no_write_privileges_on_banks(self):
        """Test 29: LAB_TECHNICIAN cannot create or update blood banks."""
        self.client.force_authenticate(user=self.lab_tech)
        res = self.client.get("/api/blood-banks/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        res2 = self.client.post("/api/blood-banks/", {"name": "Lab Bank"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)


class BloodUnitAPITest(APITestCase):
    """
    API integration tests for BloodUnit endpoints, expiry calculation, and workflow statuses.
    """
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="super_unit_admin",
            email="super_unit@test.com",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.bank_admin_1 = User.objects.create_user(
            username="bank_admin_unit_1",
            email="bank_unit_1@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.bank_admin_2 = User.objects.create_user(
            username="bank_admin_unit_2",
            email="bank_unit_2@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.hospital_staff = User.objects.create_user(
            username="hospital_unit_user",
            email="hospital_unit@test.com",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )
        self.donor_user = User.objects.create_user(
            username="donor_unit_user",
            email="donor_unit@test.com",
            password="Password123!",
            role=UserRole.DONOR,
        )
        self.lab_tech = User.objects.create_user(
            username="lab_tech_unit_user",
            email="lab_unit@test.com",
            password="Password123!",
            role=UserRole.LAB_TECHNICIAN,
        )

        self.bank_1 = BloodBank.objects.create(
            name="Apex Blood Bank",
            city="Apex City",
            state="Apex State",
            contact_number="+1-333-3333",
            email="apex@bank.org",
            capacity=500,
            admin=self.bank_admin_1,
        )
        self.bank_2 = BloodBank.objects.create(
            name="Beacon Blood Bank",
            city="Beacon City",
            state="Beacon State",
            contact_number="+1-444-4444",
            email="beacon@bank.org",
            capacity=400,
            admin=self.bank_admin_2,
        )

    def test_08_blood_unit_creation_api(self):
        """Test 8 & 9: BloodUnit creation via API defaults to TESTING status."""
        self.client.force_authenticate(user=self.bank_admin_1)
        today = timezone.now().date()
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "O+",
            "collection_date": str(today),
        }
        res = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "TESTING")
        self.assertEqual(res.data["blood_group"], "O+")
        self.assertTrue(res.data["unit_id"].startswith("BU-"))
        expected_expiry = today + timedelta(days=42)
        self.assertEqual(res.data["expiry_date"], str(expected_expiry))

    def test_12_invalid_blood_group_rejection(self):
        """Test 12: Invalid blood group rejection."""
        self.client.force_authenticate(user=self.bank_admin_1)
        today = timezone.now().date()
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "INVALID_BG",
            "collection_date": str(today),
        }
        res = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_13_future_collection_date_rejection_api(self):
        """Test 13: Future collection date rejection via API."""
        self.client.force_authenticate(user=self.bank_admin_1)
        future_date = timezone.now().date() + timedelta(days=3)
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "A+",
            "collection_date": str(future_date),
        }
        res = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("collection_date", res.data)

    def test_15_client_cannot_override_expiry_or_status_on_creation(self):
        """Test 15: Client cannot override expiry date or bypass TESTING status on creation."""
        self.client.force_authenticate(user=self.bank_admin_1)
        today = timezone.now().date()
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "B+",
            "collection_date": str(today),
            "expiry_date": "2099-01-01",  # Arbitrary override attempt
            "status": "AVAILABLE",        # Arbitrary status attempt
        }
        res = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Verify server derived the strict 42-day expiry and enforced TESTING status
        expected_expiry = today + timedelta(days=42)
        self.assertEqual(res.data["expiry_date"], str(expected_expiry))
        self.assertEqual(res.data["status"], "TESTING")

    def test_26_bank_admin_cannot_create_or_view_units_for_other_bank(self):
        """Test 26: Bank Admin cannot create or access blood units for another bank."""
        self.client.force_authenticate(user=self.bank_admin_1)
        today = timezone.now().date()

        # Attempt to create unit for Bank 2
        payload = {
            "blood_bank": self.bank_2.id,
            "blood_group": "AB+",
            "collection_date": str(today),
        }
        res = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Create unit in Bank 2 as Super Admin
        unit_2 = BloodUnit.objects.create(
            blood_bank=self.bank_2,
            unit_id="BU-BANK2-001",
            blood_group="AB+",
            collection_date=today,
        )

        # Bank Admin 1 cannot access unit_2 detail
        res2 = self.client.get(f"/api/blood-units/{unit_2.id}/")
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

    def test_29_lab_tech_read_only_access_to_units(self):
        """Test 29: LAB_TECHNICIAN can read blood units but cannot create them."""
        today = timezone.now().date()
        unit = BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-LAB-001",
            blood_group="O-",
            collection_date=today,
        )

        self.client.force_authenticate(user=self.lab_tech)
        # Can list units
        res = self.client.get("/api/blood-units/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Can retrieve unit
        res2 = self.client.get(f"/api/blood-units/{unit.id}/")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

        # Cannot create unit
        res3 = self.client.post("/api/blood-units/", {
            "blood_bank": self.bank_1.id,
            "blood_group": "O-",
            "collection_date": str(today),
        }, format="json")
        self.assertEqual(res3.status_code, status.HTTP_403_FORBIDDEN)

    def test_30_unauthenticated_requests_rejected(self):
        """Test 30: Unauthenticated requests to /api/blood-units/ are rejected."""
        res = self.client.get("/api/blood-units/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        res2 = self.client.post("/api/blood-units/", {}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_31_super_admin_can_create_blood_unit_for_any_bank(self):
        """Test 31: Super Admin can create blood units for any active blood bank."""
        self.client.force_authenticate(user=self.super_admin)
        today = timezone.now().date()
        payload = {
            "blood_bank": self.bank_2.id,
            "blood_group": "AB-",
            "collection_date": str(today),
            "unit_id": "BU-SUPER-001",
        }
        res = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["unit_id"], "BU-SUPER-001")
        self.assertEqual(res.data["blood_bank"], self.bank_2.id)
        self.assertEqual(res.data["status"], "TESTING")

    def test_32_hospital_staff_and_donor_denied_blood_unit_creation(self):
        """Test 32: Hospital Staff and Donor are denied blood unit creation."""
        today = timezone.now().date()
        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "A+",
            "collection_date": str(today),
        }

        self.client.force_authenticate(user=self.hospital_staff)
        res_hosp = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res_hosp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.donor_user)
        res_donor = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res_donor.status_code, status.HTTP_403_FORBIDDEN)

    def test_33_duplicate_unit_id_rejected(self):
        """Test 33: Explicitly supplying an existing unit_id is rejected."""
        self.client.force_authenticate(user=self.bank_admin_1)
        today = timezone.now().date()
        BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-EXISTING-001",
            blood_group="B+",
            collection_date=today,
        )

        payload = {
            "blood_bank": self.bank_1.id,
            "blood_group": "B+",
            "collection_date": str(today),
            "unit_id": "BU-EXISTING-001",
        }
        res = self.client.post("/api/blood-units/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unit_id", res.data)

    def test_34_missing_required_fields_rejected(self):
        """Test 34: Missing required fields are rejected."""
        self.client.force_authenticate(user=self.bank_admin_1)
        # Missing collection_date and blood_group
        res = self.client.post("/api/blood-units/", {"blood_bank": self.bank_1.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("blood_group", res.data)
        self.assertIn("collection_date", res.data)



class InventorySummaryAPITest(APITestCase):
    """
    API integration tests for Inventory Summary computation, filtering, and exclusion rules.
    """
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="super_inv_admin",
            email="super_inv@test.com",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.bank_admin_1 = User.objects.create_user(
            username="inv_admin_1",
            email="inv_admin_1@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.bank_admin_2 = User.objects.create_user(
            username="inv_admin_2",
            email="inv_admin_2@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.donor_user = User.objects.create_user(
            username="donor_inv_user",
            email="donor_inv@test.com",
            password="Password123!",
            role=UserRole.DONOR,
        )

        self.bank_1 = BloodBank.objects.create(
            name="Metro Central Bank",
            city="Metro City",
            state="Metro State",
            contact_number="+1-555-5555",
            email="metro@bank.org",
            capacity=1000,
            admin=self.bank_admin_1,
        )
        self.bank_2 = BloodBank.objects.create(
            name="Valley Blood Bank",
            city="Valley City",
            state="Valley State",
            contact_number="+1-666-6666",
            email="valley@bank.org",
            capacity=800,
            admin=self.bank_admin_2,
        )

        today = timezone.now().date()

        # 17. AVAILABLE non-expired unit -> MUST be counted (3 units of A+)
        for i in range(3):
            BloodUnit.objects.create(
                blood_bank=self.bank_1,
                unit_id=f"BU-AVAIL-A-{i}",
                blood_group="A+",
                collection_date=today - timedelta(days=5),
                status=BloodUnitStatus.AVAILABLE,
            )

        # AVAILABLE non-expired unit -> (2 units of O-)
        for i in range(2):
            BloodUnit.objects.create(
                blood_bank=self.bank_1,
                unit_id=f"BU-AVAIL-O-{i}",
                blood_group="O-",
                collection_date=today - timedelta(days=10),
                status=BloodUnitStatus.AVAILABLE,
            )

        # 18. TESTING unit -> MUST NOT be counted
        BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-TESTING-A",
            blood_group="A+",
            collection_date=today,
            status=BloodUnitStatus.TESTING,
        )

        # 19. RESERVED unit -> MUST NOT be counted
        BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-RESERVED-A",
            blood_group="A+",
            collection_date=today - timedelta(days=2),
            status=BloodUnitStatus.RESERVED,
        )

        # 20. DISPATCHED unit -> MUST NOT be counted
        BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-DISPATCHED-A",
            blood_group="A+",
            collection_date=today - timedelta(days=3),
            status=BloodUnitStatus.DISPATCHED,
        )

        # 21. DISCARDED unit -> MUST NOT be counted
        BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-DISCARDED-A",
            blood_group="A+",
            collection_date=today - timedelta(days=4),
            status=BloodUnitStatus.DISCARDED,
        )

        # 22. Expired AVAILABLE unit -> MUST NOT be counted
        expired_date = today - timedelta(days=50)  # expired 8 days ago
        BloodUnit.objects.create(
            blood_bank=self.bank_1,
            unit_id="BU-EXPIRED-AVAIL-A",
            blood_group="A+",
            collection_date=expired_date,
            status=BloodUnitStatus.AVAILABLE,
        )

        # Units in Bank 2 (4 units of B+)
        for i in range(4):
            BloodUnit.objects.create(
                blood_bank=self.bank_2,
                unit_id=f"BU-BANK2-B-{i}",
                blood_group="B+",
                collection_date=today - timedelta(days=1),
                status=BloodUnitStatus.AVAILABLE,
            )

    def test_17_to_22_inventory_summary_counts_only_available_non_expired(self):
        """
        Tests 17-22:
        - 17: AVAILABLE units are counted
        - 18: TESTING units are excluded
        - 19: RESERVED units are excluded
        - 20: DISPATCHED units are excluded
        - 21: DISCARDED units are excluded
        - 22: Expired AVAILABLE units are excluded
        """
        self.client.force_authenticate(user=self.super_admin)
        res = self.client.get(f"/api/inventory/summary/?blood_bank={self.bank_1.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        inventory_list = res.data["inventory"]
        counts = {item["blood_group"]: item["available_units"] for item in inventory_list}

        # Expected counts for Bank 1:
        # A+: Exactly 3 available (1 testing, 1 reserved, 1 dispatched, 1 discarded, 1 expired excluded)
        self.assertEqual(counts.get("A+"), 3)
        # O-: Exactly 2 available
        self.assertEqual(counts.get("O-"), 2)
        # B+: 0 in Bank 1 (the 4 units are in Bank 2)
        self.assertEqual(counts.get("B+"), 0)
        # Total available = 3 + 2 = 5
        self.assertEqual(res.data["total_available_units"], 5)

    def test_23_summary_groups_counts_correctly_by_blood_group(self):
        """Test 23: Summary groups counts correctly for all blood groups."""
        self.client.force_authenticate(user=self.super_admin)
        res = self.client.get(f"/api/inventory/summary/?blood_bank={self.bank_1.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        inventory = res.data["inventory"]
        groups_present = [item["blood_group"] for item in inventory]
        for bg, _ in BloodGroup.choices:
            self.assertIn(bg, groups_present)

    def test_24_summary_filters_correctly_by_blood_bank(self):
        """Test 24: Summary filters correctly by blood bank."""
        self.client.force_authenticate(user=self.super_admin)
        res = self.client.get(f"/api/inventory/summary/?blood_bank={self.bank_2.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["blood_bank"]["id"], self.bank_2.id)

        inventory_list = res.data["inventory"]
        counts = {item["blood_group"]: item["available_units"] for item in inventory_list}
        self.assertEqual(counts.get("B+"), 4)
        self.assertEqual(counts.get("A+"), 0)
        self.assertEqual(res.data["total_available_units"], 4)

    def test_26_bank_admin_summary_isolation(self):
        """Test 26: Blood Bank Admin automatically receives their assigned bank's summary and cannot access other bank."""
        self.client.force_authenticate(user=self.bank_admin_1)
        # Calling without params returns Bank 1
        res = self.client.get("/api/inventory/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["blood_bank"]["id"], self.bank_1.id)
        self.assertEqual(res.data["total_available_units"], 5)

        # Calling with Bank 2 param returns 403 Forbidden
        res2 = self.client.get(f"/api/inventory/summary/?blood_bank={self.bank_2.id}")
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

    def test_28_donor_cannot_view_inventory_summary(self):
        """Test 28: DONOR cannot access inventory summary."""
        self.client.force_authenticate(user=self.donor_user)
        res = self.client.get("/api/inventory/summary/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class BloodUnitStatusContractTests(APITestCase):
    """
    Regression test suite verifying canonical BloodUnitStatus choices and contract consistency.
    """

    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="super_admin_contract",
            email="super_contract@test.com",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.bank_admin = User.objects.create_user(
            username="bank_admin_contract",
            email="bank_contract@test.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.bank = BloodBank.objects.create(
            name="Contract Test Blood Bank",
            city="Metropolis",
            state="Central State",
            contact_number="+1-555-0199",
            email="contract@bank.org",
            capacity=500,
            admin=self.bank_admin,
            is_active=True,
        )
        self.unit = BloodUnit.objects.create(
            blood_bank=self.bank,
            unit_id="BU-CONTRACT-001",
            blood_group=BloodGroup.O_POSITIVE,
            collection_date=timezone.now().date(),
            status=BloodUnitStatus.TESTING,
        )

    def test_canonical_status_choices_exact(self):
        """Test: BloodUnitStatus defines strictly the 5 canonical choices."""
        expected_choices = {"TESTING", "AVAILABLE", "RESERVED", "DISPATCHED", "DISCARDED"}
        actual_choices = {choice[0] for choice in BloodUnitStatus.choices}
        self.assertEqual(actual_choices, expected_choices)
        self.assertNotIn("TRANSFUSED", actual_choices)
        self.assertNotIn("EXPIRED", actual_choices)

    def test_invalid_status_transfused_rejected_by_api(self):
        """Test: TRANSFUSED is not a valid BloodUnit status and is rejected by PATCH /api/blood-units/<id>/."""
        self.client.force_authenticate(user=self.super_admin)
        res = self.client.patch(
            f"/api/blood-units/{self.unit.id}/",
            {"status": "TRANSFUSED"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", res.data)

    def test_invalid_status_expired_rejected_by_api(self):
        """Test: EXPIRED is not a valid BloodUnit status choice (expiry is date-derived)."""
        self.client.force_authenticate(user=self.super_admin)
        res = self.client.patch(
            f"/api/blood-units/{self.unit.id}/",
            {"status": "EXPIRED"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", res.data)

    def test_initial_creation_always_testing_status(self):
        """Test: Creating a unit sets status to TESTING."""
        self.client.force_authenticate(user=self.super_admin)
        res = self.client.post(
            "/api/blood-units/",
            {
                "blood_bank": self.bank.id,
                "blood_group": "A+",
                "collection_date": str(timezone.now().date()),
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "TESTING")
        self.assertEqual(res.data["status_display"], "Testing")

    def test_status_filter_accepts_all_canonical_statuses(self):
        """Test: Filtering /api/blood-units/ with each canonical status works correctly."""
        self.client.force_authenticate(user=self.super_admin)
        for canonical_status in ["TESTING", "AVAILABLE", "RESERVED", "DISPATCHED", "DISCARDED"]:
            res = self.client.get(f"/api/blood-units/?status={canonical_status}")
            self.assertEqual(res.status_code, status.HTTP_200_OK)
