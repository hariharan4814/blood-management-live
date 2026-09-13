from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from apps.accounts.models import UserRole

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_standard_user(self):
        user = User.objects.create_user(
            username="johndoe",
            email="john@example.com",
            password="SecurePassword123!",
            phone="+1122334455"
        )
        self.assertEqual(user.username, "johndoe")
        self.assertEqual(user.email, "john@example.com")
        self.assertEqual(user.role, UserRole.DONOR)
        self.assertFalse(user.is_verified)
        self.assertTrue(user.is_donor)
        self.assertFalse(user.is_super_admin)
        self.assertIn("Donor", str(user))

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            username="superadmin",
            email="admin@example.com",
            password="SuperAdminPassword123!",
            role=UserRole.SUPER_ADMIN,
            is_verified=True
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_super_admin)
        self.assertTrue(admin.is_verified)


class AuthenticationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="StrongPassword123!",
            role=UserRole.DONOR,
            phone="+1234567890",
            is_verified=True
        )
        self.login_url = reverse("accounts:token_obtain_pair")
        self.refresh_url = reverse("accounts:token_refresh")
        self.register_url = reverse("accounts:register")
        self.me_url = reverse("accounts:current_user")

    def test_public_registration_donor_success(self):
        payload = {
            "username": "newdonor",
            "email": "newdonor@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "role": UserRole.DONOR,
            "phone": "+1999888777"
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["message"], "Registration successful")
        self.assertIn("user", data)
        self.assertEqual(data["user"]["username"], "newdonor")
        self.assertEqual(data["user"]["email"], "newdonor@example.com")
        self.assertEqual(data["user"]["role"], UserRole.DONOR)
        self.assertEqual(data["user"]["phone"], "+1999888777")
        self.assertFalse(data["user"]["is_verified"])
        self.assertNotIn("password", data["user"])

    def test_public_registration_hospital_staff_success(self):
        payload = {
            "username": "hospitalstaff1",
            "email": "staff1@hospital.local",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "role": UserRole.HOSPITAL_STAFF,
            "phone": "+1555666777",
            "latitude": 13.0827,
            "longitude": 80.2707,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["user"]["role"], UserRole.HOSPITAL_STAFF)

    def test_public_registration_super_admin_rejected(self):
        payload = {
            "username": "fakeadmin",
            "email": "fakeadmin@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "role": UserRole.SUPER_ADMIN,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.json())

    def test_public_registration_blood_bank_admin_rejected(self):
        payload = {
            "username": "fakebbadmin",
            "email": "fakebbadmin@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "role": UserRole.BLOOD_BANK_ADMIN,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.json())

    def test_public_registration_lab_technician_rejected(self):
        payload = {
            "username": "fakelabtech",
            "email": "fakelabtech@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "role": UserRole.LAB_TECHNICIAN,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.json())

    def test_registration_password_mismatch(self):
        payload = {
            "username": "mismatchuser",
            "email": "mismatch@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "DifferentPassword123!",
            "role": UserRole.DONOR,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.json())

    def test_registration_duplicate_username(self):
        payload = {
            "username": "testuser",
            "email": "unique@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "role": UserRole.DONOR,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.json())

    def test_registration_duplicate_email(self):
        payload = {
            "username": "uniqueuser",
            "email": "testuser@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "role": UserRole.DONOR,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.json())

    def test_login_successful(self):
        payload = {
            "username": "testuser",
            "password": "StrongPassword123!"
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertIn("user", data)
        self.assertEqual(data["user"]["username"], "testuser")
        self.assertEqual(data["user"]["email"], "testuser@example.com")
        self.assertEqual(data["user"]["role"], UserRole.DONOR)
        self.assertEqual(data["user"]["phone"], "+1234567890")
        self.assertTrue(data["user"]["is_verified"])
        self.assertNotIn("password", data["user"])

    def test_login_with_email_successful(self):
        payload = {
            "username": "testuser@example.com",
            "password": "StrongPassword123!"
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("access", data)
        self.assertEqual(data["user"]["username"], "testuser")
        self.assertEqual(data["user"]["email"], "testuser@example.com")

    def test_login_invalid_credentials(self):
        payload = {
            "username": "testuser",
            "password": "wrongpassword"
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_refresh(self):
        login_response = self.client.post(
            self.login_url,
            {"username": "testuser", "password": "StrongPassword123!"},
            format="json"
        )
        refresh_token = login_response.json()["refresh"]

        refresh_response = self.client.post(
            self.refresh_url,
            {"refresh": refresh_token},
            format="json"
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh_response.json())

    def test_current_user_authenticated(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["id"], self.user.id)
        self.assertEqual(data["username"], "testuser")
        self.assertEqual(data["email"], "testuser@example.com")
        self.assertEqual(data["role"], UserRole.DONOR)
        self.assertNotIn("password", data)

    def test_current_user_unauthenticated(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserManagementAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="adminuser",
            email="admin@example.com",
            password="AdminPassword123!",
            role=UserRole.SUPER_ADMIN,
            is_verified=True
        )
        self.donor = User.objects.create_user(
            username="donoruser",
            email="donor@example.com",
            password="DonorPassword123!",
            role=UserRole.DONOR,
            phone="+1112223333",
            is_verified=False
        )
        self.hospital_staff = User.objects.create_user(
            username="staffuser",
            email="staff@example.com",
            password="StaffPassword123!",
            role=UserRole.HOSPITAL_STAFF,
            phone="+1112224444",
            is_verified=True
        )
        self.users_url = reverse("user_management:user_list")
        self.donor_detail_url = reverse("user_management:user_detail", kwargs={"pk": self.donor.id})
        self.admin_detail_url = reverse("user_management:user_detail", kwargs={"pk": self.admin.id})

    def test_super_admin_can_list_users(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("results", data)
        self.assertIn("count", data)
        self.assertEqual(data["count"], 3)

    def test_non_super_admin_cannot_list_users(self):
        self.client.force_authenticate(user=self.donor)
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.hospital_staff)
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_list_users(self):
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_super_admin_can_retrieve_user_detail(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.donor_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["username"], "donoruser")
        self.assertEqual(data["role"], UserRole.DONOR)
        self.assertNotIn("password", data)

    def test_non_super_admin_cannot_retrieve_user_detail(self):
        self.client.force_authenticate(user=self.donor)
        response = self.client.get(self.donor_detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_update_user_patch(self):
        self.client.force_authenticate(user=self.admin)
        patch_payload = {
            "role": UserRole.LAB_TECHNICIAN,
            "is_verified": True,
            "phone": "+1999000111"
        }
        response = self.client.patch(self.donor_detail_url, patch_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["role"], UserRole.LAB_TECHNICIAN)
        self.assertTrue(data["is_verified"])
        self.assertEqual(data["phone"], "+1999000111")

        self.donor.refresh_from_db()
        self.assertEqual(self.donor.role, UserRole.LAB_TECHNICIAN)
        self.assertTrue(self.donor.is_verified)

    def test_non_super_admin_cannot_update_user(self):
        self.client.force_authenticate(user=self.hospital_staff)
        patch_payload = {"role": UserRole.SUPER_ADMIN}
        response = self.client.patch(self.donor_detail_url, patch_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_delete_other_user(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(self.donor_detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=self.donor.id).exists())

    def test_super_admin_self_deletion_safeguard(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(self.admin_detail_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.filter(id=self.admin.id).exists())

    def test_super_admin_can_provision_user_post(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "username": "new_lab_tech",
            "email": "labtech@example.com",
            "password": "SecurePassword123!",
            "role": UserRole.LAB_TECHNICIAN,
            "first_name": "Lab",
            "last_name": "Tech",
            "phone": "+1999888777",
            "is_active": True,
        }
        response = self.client.post(self.users_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["username"], "new_lab_tech")
        self.assertEqual(data["role"], UserRole.LAB_TECHNICIAN)
        self.assertTrue(User.objects.filter(username="new_lab_tech").exists())

    def test_non_super_admin_cannot_provision_user(self):
        self.client.force_authenticate(user=self.hospital_staff)
        payload = {
            "username": "unauthorized_user",
            "email": "unauth@example.com",
            "password": "SecurePassword123!",
            "role": UserRole.BLOOD_BANK_ADMIN,
        }
        response = self.client.post(self.users_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class HospitalRegistrationAndLoginTests(TestCase):
    """
    Unit and integration tests for Requirement 1 & 2: Hospital Registration & Login.
    """
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse("accounts:register")
        self.login_url = reverse("accounts:token_obtain_pair")

    def test_hospital_registration_persists_facility_and_staff(self):
        """Tests 1-5: Hospital registration saves facility, location, contact person and sets role HOSPITAL_STAFF."""
        from apps.blood_requests.models import Hospital

        payload = {
            "hospital_name": "City Care Specialty Hospital",
            "contact_person_name": "Dr. Sarah Johnson",
            "email": "sarah.johnson@citycare.health",
            "phone": "+91-9876543210",
            "password": "SecureHospitalPass123!",
            "password_confirm": "SecureHospitalPass123!",
            "role": UserRole.HOSPITAL_STAFF,
            "city": "Chennai",
            "state": "Tamil Nadu",
            "address": "45 Medical Park Road, Central District",
            "latitude": 13.082700,
            "longitude": 80.270700,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 1. User persisted
        user = User.objects.filter(email="sarah.johnson@citycare.health").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, UserRole.HOSPITAL_STAFF)
        self.assertEqual(user.first_name, "Dr.")
        self.assertEqual(user.last_name, "Sarah Johnson")
        self.assertAlmostEqual(float(user.latitude), 13.0827, places=4)
        self.assertAlmostEqual(float(user.longitude), 80.2707, places=4)

        # 2. Hospital facility record persisted
        hospital = Hospital.objects.filter(name="City Care Specialty Hospital").first()
        self.assertIsNotNone(hospital)
        self.assertEqual(hospital.city, "Chennai")
        self.assertEqual(hospital.state, "Tamil Nadu")
        self.assertEqual(hospital.contact_number, "+91-9876543210")
        self.assertAlmostEqual(float(hospital.latitude), 13.0827, places=4)
        self.assertAlmostEqual(float(hospital.longitude), 80.2707, places=4)
        self.assertTrue(hospital.is_active)

        # 3. Association verified
        self.assertEqual(user.hospital, hospital)

    def test_hospital_login_using_email_and_password_without_staff_id(self):
        """Tests 6-7: Hospital can log in using Email + Password, Staff ID is not required."""
        from apps.blood_requests.models import Hospital

        hospital = Hospital.objects.create(
            name="Metro Hospital",
            city="Chennai",
            is_active=True,
        )
        user = User.objects.create_user(
            username="metro_staff",
            email="desk@metrohospital.org",
            password="MetroPassword123!",
            role=UserRole.HOSPITAL_STAFF,
            hospital=hospital,
            is_verified=True,
        )

        login_payload = {
            "username": "desk@metrohospital.org",  # Email used as login identifier
            "password": "MetroPassword123!",
        }
        response = self.client.post(self.login_url, login_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["user"]["role"], UserRole.HOSPITAL_STAFF)
        self.assertEqual(data["user"]["email"], "desk@metrohospital.org")
        self.assertEqual(data["user"]["hospital_name"], "Metro Hospital")

    def test_hospital_registration_requires_latitude_and_longitude(self):
        """Verify registration is rejected if either latitude or longitude is missing/null."""
        payload_missing_lat = {
            "hospital_name": "No Lat Hospital",
            "contact_person_name": "Dr. Test",
            "email": "nolat@hospital.test",
            "password": "SecureHospitalPass123!",
            "password_confirm": "SecureHospitalPass123!",
            "role": UserRole.HOSPITAL_STAFF,
            "longitude": 80.2707,
        }
        res_lat = self.client.post(self.register_url, payload_missing_lat, format="json")
        self.assertEqual(res_lat.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", res_lat.json())

        payload_missing_lng = {
            "hospital_name": "No Lng Hospital",
            "contact_person_name": "Dr. Test",
            "email": "nolng@hospital.test",
            "password": "SecureHospitalPass123!",
            "password_confirm": "SecureHospitalPass123!",
            "role": UserRole.HOSPITAL_STAFF,
            "latitude": 13.0827,
        }
        res_lng = self.client.post(self.register_url, payload_missing_lng, format="json")
        self.assertEqual(res_lng.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("longitude", res_lng.json())

    def test_hospital_registration_invalid_coordinate_ranges(self):
        """Verify registration is rejected if coordinates exceed valid geographic boundaries."""
        payload_invalid_lat = {
            "hospital_name": "Out of Range Hospital",
            "contact_person_name": "Dr. Test",
            "email": "range@hospital.test",
            "password": "SecureHospitalPass123!",
            "password_confirm": "SecureHospitalPass123!",
            "role": UserRole.HOSPITAL_STAFF,
            "latitude": 95.0,  # Invalid latitude (> 90)
            "longitude": 80.2707,
        }
        res_lat = self.client.post(self.register_url, payload_invalid_lat, format="json")
        self.assertEqual(res_lat.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", res_lat.json())

        payload_invalid_lng = {
            "hospital_name": "Out of Range Hospital",
            "contact_person_name": "Dr. Test",
            "email": "rangelng@hospital.test",
            "password": "SecureHospitalPass123!",
            "password_confirm": "SecureHospitalPass123!",
            "role": UserRole.HOSPITAL_STAFF,
            "latitude": 13.0827,
            "longitude": 200.0,  # Invalid longitude (> 180)
        }
        res_lng = self.client.post(self.register_url, payload_invalid_lng, format="json")
        self.assertEqual(res_lng.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("longitude", res_lng.json())

    def test_hospital_registration_with_both_hospital_name_and_hospital_alias(self):
        """Regression test: browser payload containing both hospital_name and hospital creates 1 Hospital and 1 User without TypeError."""
        from apps.blood_requests.models import Hospital

        payload = {
            "name": "Dr. Harini",
            "contact_person_name": "Dr. Harini",
            "email": "harini@multispecialty.health",
            "phone": "+91-9876500000",
            "password": "SecureHospitalPass123!",
            "password_confirm": "SecureHospitalPass123!",
            "role": UserRole.HOSPITAL_STAFF,
            "city": "Chennai",
            "state": "Tamil Nadu",
            "address": "123 Grand Trunk Road",
            "hospital_name": "Harini Multi Specialty Hospital",
            "hospital": "Harini Multi Specialty Hospital",
            "latitude": 13.0827,
            "longitude": 80.2707,
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify exactly one hospital created
        hospitals = Hospital.objects.filter(name="Harini Multi Specialty Hospital")
        self.assertEqual(hospitals.count(), 1)
        hospital_record = hospitals.first()

        # Verify user created and linked
        user = User.objects.filter(email="harini@multispecialty.health").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, UserRole.HOSPITAL_STAFF)
        self.assertEqual(user.hospital, hospital_record)
