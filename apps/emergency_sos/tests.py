from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.blood_requests.models import BloodRequest, RequestStatus, RequestUrgency
from apps.donors.models import BloodGroup, Donor
from apps.emergency_sos.compatibility import (
    calculate_haversine_distance_km,
    get_all_compatible_donor_blood_groups,
    get_compatible_donor_blood_groups,
    is_blood_compatible,
)
from apps.emergency_sos.models import SOSBroadcast, SOSRecipient, SOSStatus
from apps.emergency_sos.services import (
    cancel_sos_broadcast,
    check_inventory_shortage,
    find_eligible_compatible_donors,
    trigger_sos_broadcast,
)
from apps.inventory.models import BloodBank, BloodUnit, BloodUnitStatus

User = get_user_model()


class EmergencySOSTestsBase(TestCase):
    """
    Base test class setting up users, blood banks, donors, and inventory.
    """

    def setUp(self):
        self.client = APIClient()
        self.today = timezone.now().date()

        # 1. Users with distinct RBAC roles
        self.super_admin = User.objects.create_user(
            username="super_admin_user",
            email="superadmin@example.com",
            password="StrongPassword123!",
            role=UserRole.SUPER_ADMIN,
        )

        self.bb_admin = User.objects.create_user(
            username="bb_admin_user",
            email="bbadmin@example.com",
            password="StrongPassword123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )

        self.hospital_staff1 = User.objects.create_user(
            username="hospital_staff_one",
            email="staff1@hospital.org",
            password="StrongPassword123!",
            role=UserRole.HOSPITAL_STAFF,
        )

        self.hospital_staff2 = User.objects.create_user(
            username="hospital_staff_two",
            email="staff2@hospital.org",
            password="StrongPassword123!",
            role=UserRole.HOSPITAL_STAFF,
        )

        self.lab_tech = User.objects.create_user(
            username="lab_tech_user",
            email="labtech@example.com",
            password="StrongPassword123!",
            role=UserRole.LAB_TECHNICIAN,
        )

        # 2. Blood Bank (Downtown Metro Blood Bank with GPS coordinates)
        self.blood_bank = BloodBank.objects.create(
            name="Downtown Metro Blood Bank",
            address="100 Healthcare Blvd",
            city="Metropolis",
            state="NY",
            contact_number="+1-555-0100",
            email="downtown@bloodbank.org",
            capacity=1000,
            latitude=Decimal("40.712800"),
            longitude=Decimal("-74.006000"),
            admin=self.bb_admin,
            is_active=True,
        )

        # 3. Donor Accounts & Profiles
        # Donor 1: O- (Universal Donor, Eligible, Near bank)
        self.donor_user_o_neg = User.objects.create_user(
            username="donor_one_oneg",
            email="oneg_donor@example.com",
            password="StrongPassword123!",
            role=UserRole.DONOR,
            first_name="Oliver",
            last_name="Negative",
        )
        self.donor_o_neg = Donor.objects.create(
            user=self.donor_user_o_neg,
            blood_group=BloodGroup.O_NEGATIVE,
            date_of_birth=self.today - timedelta(days=30 * 365),  # 30 years old
            weight_kg=Decimal("72.0"),
            last_donation_date=self.today - timedelta(days=120),  # Cooldown passed
            latitude=Decimal("40.720000"),
            longitude=Decimal("-74.000000"),  # ~1 km away
        )

        # Donor 2: A+ (Compatible with A+, Eligible, Near bank)
        self.donor_user_a_pos = User.objects.create_user(
            username="donor_two_apos",
            email="apos_donor@example.com",
            password="StrongPassword123!",
            role=UserRole.DONOR,
            first_name="Alice",
            last_name="Positive",
        )
        self.donor_a_pos = Donor.objects.create(
            user=self.donor_user_a_pos,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=self.today - timedelta(days=25 * 365),  # 25 years old
            weight_kg=Decimal("60.0"),
            last_donation_date=self.today - timedelta(days=100),  # Cooldown passed
            latitude=Decimal("40.730000"),
            longitude=Decimal("-73.990000"),  # ~2 km away
        )

        # Donor 3: B+ (Incompatible with A+ recipient, Eligible)
        self.donor_user_b_pos = User.objects.create_user(
            username="donor_three_bpos",
            email="bpos_donor@example.com",
            password="StrongPassword123!",
            role=UserRole.DONOR,
            first_name="Bob",
            last_name="Positive",
        )
        self.donor_b_pos = Donor.objects.create(
            user=self.donor_user_b_pos,
            blood_group=BloodGroup.B_POSITIVE,
            date_of_birth=self.today - timedelta(days=28 * 365),
            weight_kg=Decimal("80.0"),
            last_donation_date=None,  # First time donor
        )

        # Donor 4: A+ (Compatible, but Medically INELIGIBLE - recently donated 20 days ago)
        self.donor_user_a_pos_ineligible = User.objects.create_user(
            username="donor_four_ineligible",
            email="ineligible@example.com",
            password="StrongPassword123!",
            role=UserRole.DONOR,
            first_name="Ian",
            last_name="Ineligible",
        )
        self.donor_a_pos_ineligible = Donor.objects.create(
            user=self.donor_user_a_pos_ineligible,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=self.today - timedelta(days=35 * 365),
            weight_kg=Decimal("65.0"),
            last_donation_date=self.today - timedelta(days=20),  # In cooldown!
        )

        # 4. Standard Critical Blood Request for 4 units of A+ blood
        self.critical_request = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff1,
            blood_bank=self.blood_bank,
            blood_group=BloodGroup.A_POSITIVE,
            units_needed=4,
            urgency=RequestUrgency.CRITICAL,
            status=RequestStatus.PENDING,
        )

        # 5. Inventory: Add only 1 unit of A+ (available stock = 1, required = 4 -> shortage = 3)
        self.unit1 = BloodUnit.objects.create(
            blood_bank=self.blood_bank,
            unit_id="BU-TEST-001",
            blood_group=BloodGroup.A_POSITIVE,
            collection_date=self.today - timedelta(days=5),
            expiry_date=self.today + timedelta(days=37),
            status=BloodUnitStatus.AVAILABLE,
        )


class CompatibilityAndDistanceUnitTests(TestCase):
    """
    Unit tests for RBC blood compatibility and Haversine distance calculations.
    """

    def test_blood_compatibility_matrix(self):
        # A+ accepts A+, A-, O+, O-
        a_pos_compatible = get_compatible_donor_blood_groups(BloodGroup.A_POSITIVE)
        self.assertIn(BloodGroup.A_POSITIVE, a_pos_compatible)
        self.assertIn(BloodGroup.A_NEGATIVE, a_pos_compatible)
        self.assertIn(BloodGroup.O_POSITIVE, a_pos_compatible)
        self.assertIn(BloodGroup.O_NEGATIVE, a_pos_compatible)
        self.assertNotIn(BloodGroup.B_POSITIVE, a_pos_compatible)
        self.assertNotIn(BloodGroup.AB_POSITIVE, a_pos_compatible)

        # O- accepts ONLY O-
        o_neg_compatible = get_compatible_donor_blood_groups(BloodGroup.O_NEGATIVE)
        self.assertEqual(o_neg_compatible, [BloodGroup.O_NEGATIVE])

        # AB+ (Universal recipient) accepts all 8 blood groups
        ab_pos_compatible = get_compatible_donor_blood_groups(BloodGroup.AB_POSITIVE)
        self.assertEqual(len(ab_pos_compatible), 8)

    def test_is_blood_compatible_helper(self):
        self.assertTrue(is_blood_compatible(BloodGroup.O_NEGATIVE, BloodGroup.AB_POSITIVE))
        self.assertTrue(is_blood_compatible(BloodGroup.O_NEGATIVE, BloodGroup.A_POSITIVE))
        self.assertFalse(is_blood_compatible(BloodGroup.B_POSITIVE, BloodGroup.A_POSITIVE))
        self.assertFalse(is_blood_compatible(BloodGroup.AB_POSITIVE, BloodGroup.O_POSITIVE))

    def test_subgroup_compatibility_mapping(self):
        # A1+ and A2+ belong to A+ family
        self.assertTrue(is_blood_compatible(BloodGroup.A1_POSITIVE, BloodGroup.A_POSITIVE))
        self.assertTrue(is_blood_compatible(BloodGroup.A2_POSITIVE, BloodGroup.A_POSITIVE))
        # A1- can donate to A+ recipient
        self.assertTrue(is_blood_compatible(BloodGroup.A1_NEGATIVE, BloodGroup.A_POSITIVE))
        # A1B+ and A2B+ belong to AB+ family
        self.assertTrue(is_blood_compatible(BloodGroup.A1B_POSITIVE, BloodGroup.AB_POSITIVE))
        self.assertTrue(is_blood_compatible(BloodGroup.A2B_POSITIVE, BloodGroup.AB_POSITIVE))
        # Universal donor O- can donate to A1+ and A2B+
        self.assertTrue(is_blood_compatible(BloodGroup.O_NEGATIVE, BloodGroup.A1_POSITIVE))
        self.assertTrue(is_blood_compatible(BloodGroup.O_NEGATIVE, BloodGroup.A2B_POSITIVE))
        # Incompatible blood groups across families
        self.assertFalse(is_blood_compatible(BloodGroup.A1_POSITIVE, BloodGroup.B_POSITIVE))
        self.assertFalse(is_blood_compatible(BloodGroup.A2B_POSITIVE, BloodGroup.A_POSITIVE))
        self.assertFalse(is_blood_compatible(BloodGroup.B_POSITIVE, BloodGroup.A1_POSITIVE))

        # Expanded compatible groups includes subgroups
        a1_pos_all = get_all_compatible_donor_blood_groups(BloodGroup.A1_POSITIVE)
        self.assertIn(BloodGroup.A1_POSITIVE, a1_pos_all)
        self.assertIn(BloodGroup.A2_POSITIVE, a1_pos_all)
        self.assertIn(BloodGroup.A_POSITIVE, a1_pos_all)
        self.assertIn(BloodGroup.A1_NEGATIVE, a1_pos_all)
        self.assertIn(BloodGroup.A2_NEGATIVE, a1_pos_all)
        self.assertIn(BloodGroup.A_NEGATIVE, a1_pos_all)
        self.assertIn(BloodGroup.O_POSITIVE, a1_pos_all)
        self.assertIn(BloodGroup.O_NEGATIVE, a1_pos_all)
        self.assertNotIn(BloodGroup.B_POSITIVE, a1_pos_all)
        self.assertNotIn(BloodGroup.AB_POSITIVE, a1_pos_all)

    def test_subgroup_rh_compatibility(self):
        # Rh+ cannot donate to Rh-
        self.assertFalse(is_blood_compatible(BloodGroup.A1_POSITIVE, BloodGroup.A1_NEGATIVE))
        self.assertFalse(is_blood_compatible(BloodGroup.A2_POSITIVE, BloodGroup.A_NEGATIVE))
        # Rh- can donate to Rh+
        self.assertTrue(is_blood_compatible(BloodGroup.A1_NEGATIVE, BloodGroup.A1_POSITIVE))
        self.assertTrue(is_blood_compatible(BloodGroup.A2_NEGATIVE, BloodGroup.A_POSITIVE))

    def test_haversine_distance_calculation(self):
        # Distance between NYC (40.7128, -74.0060) and Philadelphia (39.9526, -75.1652) is ~130 km
        dist = calculate_haversine_distance_km(
            Decimal("40.7128"),
            Decimal("-74.0060"),
            Decimal("39.9526"),
            Decimal("-75.1652"),
        )
        self.assertIsNotNone(dist)
        self.assertAlmostEqual(dist, 130.0, delta=10.0)

    def test_haversine_distance_with_none_coordinates(self):
        dist = calculate_haversine_distance_km(None, Decimal("-74.0"), Decimal("40.0"), Decimal("-75.0"))
        self.assertIsNone(dist)


class SOSTriggerValidationTests(EmergencySOSTestsBase):
    """
    Test suite for SOS trigger validation, shortage calculation, and duplicate protection.
    """

    def test_valid_critical_request_with_shortage_triggers_sos_successfully(self):
        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data

        self.assertEqual(data["blood_request"], self.critical_request.id)
        self.assertEqual(data["status"], "ACTIVE")
        self.assertEqual(data["blood_group"], "A+")
        self.assertEqual(data["units_needed"], 4)
        self.assertEqual(data["available_units_at_trigger"], 1)
        self.assertEqual(data["shortage_units"], 3)
        self.assertEqual(data["total_donors_targeted"], 2)  # donor_o_neg and donor_a_pos
        self.assertIn("🚨 EMERGENCY", data["title"])

        # Check database record
        broadcast = SOSBroadcast.objects.get(pk=data["id"])
        self.assertEqual(broadcast.status, SOSStatus.ACTIVE)
        self.assertEqual(broadcast.triggered_by, self.hospital_staff1)

    def test_non_critical_urgency_rejected(self):
        normal_request = BloodRequest.objects.create(
            hospital_staff=self.hospital_staff1,
            blood_bank=self.blood_bank,
            blood_group=BloodGroup.A_POSITIVE,
            units_needed=4,
            urgency=RequestUrgency.NORMAL,  # Not CRITICAL
            status=RequestStatus.PENDING,
        )
        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post(f"/api/blood-requests/{normal_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("CRITICAL", str(response.data))

    def test_sufficient_inventory_prevents_sos(self):
        # Create 5 available units for 4 units needed
        for i in range(5):
            BloodUnit.objects.create(
                blood_bank=self.blood_bank,
                unit_id=f"BU-AVAIL-{i}",
                blood_group=BloodGroup.A_POSITIVE,
                collection_date=self.today,
                expiry_date=self.today + timedelta(days=42),
                status=BloodUnitStatus.AVAILABLE,
            )

        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sufficient stock", str(response.data).lower())

    def test_rejected_or_completed_request_cannot_trigger_sos(self):
        self.critical_request.status = RequestStatus.REJECTED
        self.critical_request.rejection_reason = "Cannot fulfill."
        self.critical_request.save()

        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_blood_request_id_returns_404(self):
        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post("/api/blood-requests/99999/sos/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_duplicate_active_sos_on_same_request_prevented(self):
        self.client.force_authenticate(user=self.hospital_staff1)
        # First trigger
        res1 = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Second trigger while first is still ACTIVE
        res2 = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ACTIVE", str(res2.data))


class SOSPermissionsTests(EmergencySOSTestsBase):
    """
    Test suite for Role-Based Access Control and ownership restrictions on SOS endpoints.
    """

    def test_hospital_staff_who_owns_request_can_trigger(self):
        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_other_hospital_staff_cannot_trigger_for_unowned_request(self):
        self.client.force_authenticate(user=self.hospital_staff2)  # Different hospital staff
        response = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_trigger_sos(self):
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_blood_bank_admin_cannot_trigger_sos(self):
        self.client.force_authenticate(user=self.bb_admin)
        response = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_donor_and_lab_technician_cannot_trigger_sos(self):
        self.client.force_authenticate(user=self.donor_user_o_neg)
        response_donor = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response_donor.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.lab_tech)
        response_lab = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response_lab.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_denied_sos_trigger(self):
        response = self.client.post(f"/api/blood-requests/{self.critical_request.id}/sos/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_broadcast_list_scoping_by_role(self):
        broadcast = trigger_sos_broadcast(self.critical_request, self.hospital_staff1)

        # Hospital Staff 1 can see their broadcast
        self.client.force_authenticate(user=self.hospital_staff1)
        res_staff1 = self.client.get("/api/sos/")
        self.assertEqual(res_staff1.status_code, status.HTTP_200_OK)
        results = res_staff1.data.get("results", res_staff1.data)
        self.assertEqual(len(results), 1)

        # Hospital Staff 2 sees 0 broadcasts
        self.client.force_authenticate(user=self.hospital_staff2)
        res_staff2 = self.client.get("/api/sos/")
        self.assertEqual(res_staff2.status_code, status.HTTP_200_OK)
        results2 = res_staff2.data.get("results", res_staff2.data)
        self.assertEqual(len(results2), 0)

        # Blood Bank Admin for the target bank can see the broadcast
        self.client.force_authenticate(user=self.bb_admin)
        res_bb = self.client.get("/api/sos/")
        self.assertEqual(res_bb.status_code, status.HTTP_200_OK)
        results_bb = res_bb.data.get("results", res_bb.data)
        self.assertEqual(len(results_bb), 1)

        # Super Admin sees all broadcasts
        self.client.force_authenticate(user=self.super_admin)
        res_admin = self.client.get("/api/sos/")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        results_admin = res_admin.data.get("results", res_admin.data)
        self.assertEqual(len(results_admin), 1)

        # Donor cannot view SOS broadcast list
        self.client.force_authenticate(user=self.donor_user_o_neg)
        res_donor = self.client.get("/api/sos/")
        self.assertEqual(res_donor.status_code, status.HTTP_200_OK)
        results_donor = res_donor.data.get("results", res_donor.data)
        self.assertEqual(len(results_donor), 0)


class SOSDonorMatchingTests(EmergencySOSTestsBase):
    """
    Test suite for donor compatibility, eligibility, and exclusion logic.
    """

    def test_donor_matching_logic(self):
        matched = find_eligible_compatible_donors(self.critical_request)
        matched_ids = [d.id for d in matched]

        # O- (Universal donor, eligible) must be matched
        self.assertIn(self.donor_o_neg.id, matched_ids)
        # A+ (Compatible, eligible) must be matched
        self.assertIn(self.donor_a_pos.id, matched_ids)
        # B+ (Incompatible with A+ recipient) must be excluded
        self.assertNotIn(self.donor_b_pos.id, matched_ids)
        # Ineligible A+ (cooldown active) must be excluded
        self.assertNotIn(self.donor_a_pos_ineligible.id, matched_ids)

    def test_inactive_user_donor_excluded(self):
        self.donor_user_a_pos.is_active = False
        self.donor_user_a_pos.save()

        matched = find_eligible_compatible_donors(self.critical_request)
        matched_ids = [d.id for d in matched]

        self.assertNotIn(self.donor_a_pos.id, matched_ids)
        self.assertIn(self.donor_o_neg.id, matched_ids)

    def test_zero_eligible_donors_handled_safely(self):
        # Set all donors to inactive
        User.objects.filter(role=UserRole.DONOR).update(is_active=False)

        broadcast = trigger_sos_broadcast(self.critical_request, self.hospital_staff1)
        self.assertEqual(broadcast.total_donors_targeted, 0)
        self.assertEqual(SOSRecipient.objects.filter(sos_broadcast=broadcast).count(), 0)


class SOSLocationRadiusTests(EmergencySOSTestsBase):
    """
    Test suite for geographical Haversine distance and radius filtering.
    """

    def setUp(self):
        super().setUp()
        # Add a far donor: 150 km north (latitude 42.0628)
        self.donor_user_far = User.objects.create_user(
            username="donor_far_away",
            email="far@example.com",
            password="StrongPassword123!",
            role=UserRole.DONOR,
        )
        self.donor_far = Donor.objects.create(
            user=self.donor_user_far,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=self.today - timedelta(days=22 * 365),
            weight_kg=Decimal("68.0"),
            last_donation_date=None,
            latitude=Decimal("42.062800"),  # ~150 km away
            longitude=Decimal("-74.006000"),
        )

    def test_radius_filter_excludes_distant_donors(self):
        # Request with 25 km radius
        matched_25km = find_eligible_compatible_donors(self.critical_request, radius_km=Decimal("25.0"))
        matched_ids = [d.id for d in matched_25km]

        # Near donors (1-2 km) are included
        self.assertIn(self.donor_o_neg.id, matched_ids)
        self.assertIn(self.donor_a_pos.id, matched_ids)
        # Far donor (150 km) is excluded
        self.assertNotIn(self.donor_far.id, matched_ids)

    def test_no_radius_includes_all_compatible_donors(self):
        matched_all = find_eligible_compatible_donors(self.critical_request, radius_km=None)
        matched_ids = [d.id for d in matched_all]

        self.assertIn(self.donor_o_neg.id, matched_ids)
        self.assertIn(self.donor_a_pos.id, matched_ids)
        self.assertIn(self.donor_far.id, matched_ids)


class SOSNotificationAndEmailAuditTests(EmergencySOSTestsBase):
    """
    Test suite for in-app notification creation, professional email delivery, and audit tracking.
    """

    def test_in_app_notifications_and_emails_created(self):
        broadcast = trigger_sos_broadcast(self.critical_request, self.hospital_staff1)

        # Check in-app notifications
        notifs_o_neg = self.donor_user_o_neg.notifications.filter(notification_type="SOS")
        self.assertEqual(notifs_o_neg.count(), 1)
        notif = notifs_o_neg.first()
        self.assertIn("🚨 EMERGENCY", notif.title)
        self.assertIn("Downtown Metro Blood Bank", notif.message)
        self.assertFalse(notif.is_read)

        notifs_a_pos = self.donor_user_a_pos.notifications.filter(notification_type="SOS")
        self.assertEqual(notifs_a_pos.count(), 1)

        # Ineligible and incompatible donors receive no notification
        self.assertEqual(self.donor_user_b_pos.notifications.count(), 0)
        self.assertEqual(self.donor_user_a_pos_ineligible.notifications.count(), 0)

        # Check SOSRecipient audit records
        recipients = SOSRecipient.objects.filter(sos_broadcast=broadcast)
        self.assertEqual(recipients.count(), 2)
        for recip in recipients:
            self.assertTrue(recip.email_attempted)
            self.assertTrue(recip.email_sent)
            self.assertEqual(recip.delivery_error, "")

        # Check mail outbox (Django test email backend)
        self.assertEqual(len(mail.outbox), 2)
        sent_emails = [m.to[0] for m in mail.outbox]
        self.assertIn("oneg_donor@example.com", sent_emails)
        self.assertIn("apos_donor@example.com", sent_emails)

        # Verify multipart HTML email content
        sent_html = mail.outbox[0].alternatives[0][0]
        self.assertIn("EMERGENCY BLOOD ALERT", sent_html)
        self.assertIn("Downtown Metro Blood Bank", sent_html)

    def test_email_failure_does_not_rollback_sos_broadcast(self):
        # Mock send_notification_email to simulate SMTP connection error
        with patch("apps.emergency_sos.services.send_notification_email", side_effect=Exception("SMTP Server Unreachable")):
            broadcast = trigger_sos_broadcast(self.critical_request, self.hospital_staff1)

            # SOS broadcast still created and active
            self.assertIsNotNone(broadcast.id)
            self.assertEqual(broadcast.status, SOSStatus.ACTIVE)

            # Audit logs capture delivery failure safely
            recipients = SOSRecipient.objects.filter(sos_broadcast=broadcast)
            self.assertEqual(recipients.count(), 2)
            for recip in recipients:
                self.assertTrue(recip.email_attempted)
                self.assertFalse(recip.email_sent)
                self.assertIn("SMTP Server Unreachable", recip.delivery_error)


class SOSCancellationTests(EmergencySOSTestsBase):
    """
    Test suite for cancelling active SOS broadcasts and audit endpoints.
    """

    def setUp(self):
        super().setUp()
        self.broadcast = trigger_sos_broadcast(self.critical_request, self.hospital_staff1)

    def test_cancel_active_broadcast_succeeds(self):
        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post(
            f"/api/sos/{self.broadcast.id}/cancel/",
            {"reason": "Patient received emergency transfer to regional facility."},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertEqual(response.data["cancellation_reason"], "Patient received emergency transfer to regional facility.")

        self.broadcast.refresh_from_db()
        self.assertEqual(self.broadcast.status, SOSStatus.CANCELLED)
        self.assertEqual(self.broadcast.cancelled_by, self.hospital_staff1)
        self.assertIsNotNone(self.broadcast.cancelled_at)

    def test_cancel_without_reason_rejected(self):
        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post(
            f"/api/sos/{self.broadcast.id}/cancel/",
            {"reason": "   "},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", response.data)

    def test_cancel_already_cancelled_broadcast_rejected(self):
        cancel_sos_broadcast(self.broadcast, self.hospital_staff1, "Initial reason.")

        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.post(
            f"/api/sos/{self.broadcast.id}/cancel/",
            {"reason": "Second cancel attempt."},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthorized_user_cannot_cancel(self):
        self.client.force_authenticate(user=self.hospital_staff2)  # Different hospital staff
        response = self.client.post(
            f"/api/sos/{self.broadcast.id}/cancel/",
            {"reason": "Unauthorized attempt."},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_sos_recipients_audit_endpoint(self):
        self.client.force_authenticate(user=self.hospital_staff1)
        response = self.client.get(f"/api/sos/{self.broadcast.id}/recipients/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 2)
        donor_usernames = [r["donor_username"] for r in results]
        self.assertIn("donor_one_oneg", donor_usernames)
        self.assertIn("donor_two_apos", donor_usernames)
        for r in results:
            self.assertIn("distance_km", r)
            self.assertIsNotNone(r["distance_km"])
            self.assertIsInstance(r["distance_km"], float)
            self.assertGreater(r["distance_km"], 0)

    def test_sos_blood_request_detail_exposes_facility_coordinates(self):
        """Test: SOS broadcast blood_request_detail includes facility coordinates and address."""
        self.blood_bank.latitude = Decimal("13.082700")
        self.blood_bank.longitude = Decimal("80.270700")
        self.blood_bank.address = "456 Central Blood Bank Way"
        self.blood_bank.city = "Metropolis"
        self.blood_bank.save()

        self.client.force_authenticate(user=self.super_admin)
        response = self.client.get(f"/api/sos/{self.broadcast.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        detail = response.data.get("blood_request_detail", {})
        self.assertEqual(detail.get("blood_bank_name"), self.blood_bank.name)
        self.assertEqual(detail.get("blood_bank_latitude"), "13.082700")
        self.assertEqual(detail.get("blood_bank_longitude"), "80.270700")
        self.assertEqual(detail.get("blood_bank_address"), "456 Central Blood Bank Way")
        self.assertEqual(detail.get("blood_bank_city"), "Metropolis")


class SOSDonorPreviewAPITests(EmergencySOSTestsBase):
    """
    Unit and integration tests for read-only dynamic donor preview endpoint (Bug #4).
    """

    def test_01_authorized_hospital_staff_can_preview_donors(self):
        """Test: Authorized hospital staff who created the request can preview eligible donors."""
        self.client.force_authenticate(user=self.hospital_staff1)
        res = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=25")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["blood_request_id"], self.critical_request.id)
        self.assertEqual(res.data["blood_group_requested"], "A+")
        self.assertEqual(res.data["radius_km"], 25.0)
        self.assertIn("donors", res.data)
        self.assertGreaterEqual(res.data["eligible_donors_count"], 1)

        # Inspect donor payload structure
        first_donor = res.data["donors"][0]
        self.assertIn("id", first_donor)
        self.assertIn("donor_id", first_donor)
        self.assertIn("blood_group", first_donor)
        self.assertIn("is_eligible", first_donor)
        self.assertTrue(first_donor["is_eligible"])
        self.assertIn("distance_km", first_donor)
        self.assertIn("approximate_latitude", first_donor)
        self.assertIn("approximate_longitude", first_donor)

    def test_02_super_admin_and_blood_bank_admin_can_preview_donors(self):
        """Test: Super Admin and assigned Blood Bank Admin can preview eligible donors."""
        self.client.force_authenticate(user=self.super_admin)
        res_admin = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=50")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.bb_admin)
        res_bank = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=50")
        self.assertEqual(res_bank.status_code, status.HTTP_200_OK)

    def test_03_unauthorized_roles_denied_preview(self):
        """Test: Other hospital staff, lab tech, donor, and unauthenticated users are rejected."""
        # Unauthenticated
        res_unauth = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/")
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # Different hospital staff
        self.client.force_authenticate(user=self.hospital_staff2)
        res_other = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/")
        self.assertEqual(res_other.status_code, status.HTTP_403_FORBIDDEN)

        # Lab Tech
        self.client.force_authenticate(user=self.lab_tech)
        res_tech = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/")
        self.assertEqual(res_tech.status_code, status.HTTP_403_FORBIDDEN)

        # Donor
        self.client.force_authenticate(user=self.donor_user_o_neg)
        res_donor = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/")
        self.assertEqual(res_donor.status_code, status.HTTP_403_FORBIDDEN)

    def test_04_compatibility_and_medical_eligibility_filter(self):
        """Test: Only compatible and medically eligible donors are returned."""
        self.client.force_authenticate(user=self.hospital_staff1)
        res = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=100")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        donor_ids = [d["donor_id"] for d in res.data["donors"]]

        # Compatible donors (A+ request receives O- and A+)
        self.assertIn(self.donor_o_neg.id, donor_ids)
        self.assertIn(self.donor_a_pos.id, donor_ids)

        # Incompatible donors (B+ cannot donate to A+)
        self.assertNotIn(self.donor_b_pos.id, donor_ids)

        # Medically ineligible donor (under 90-day cooldown)
        self.assertNotIn(self.donor_a_pos_ineligible.id, donor_ids)

    def test_05_radius_filtering_behavior(self):
        """Test: Radius parameter correctly bounds returned donors."""
        self.client.force_authenticate(user=self.hospital_staff1)

        # 5 km radius includes nearby donors (~1 km, ~2.5 km)
        res_small = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=5")
        self.assertEqual(res_small.status_code, status.HTTP_200_OK)
        donor_ids_small = [d["donor_id"] for d in res_small.data["donors"]]
        self.assertIn(self.donor_o_neg.id, donor_ids_small)
        self.assertIn(self.donor_a_pos.id, donor_ids_small)

        # Donors further away are not included
        for d in res_small.data["donors"]:
            if d["distance_km"] is not None:
                self.assertLessEqual(d["distance_km"], 5.0)

    def test_06_real_distance_and_fuzzed_coordinates(self):
        """Test: Distance is real Haversine calculation and coordinates are fuzzed to 2 decimal places."""
        self.client.force_authenticate(user=self.hospital_staff1)
        res = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=25")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        for d in res.data["donors"]:
            # Real calculated distance
            self.assertIsNotNone(d["distance_km"])
            self.assertIsInstance(d["distance_km"], float)
            self.assertGreater(d["distance_km"], 0)

            # Fuzzed coordinate check (maximum 2 decimal places)
            if d["approximate_latitude"] is not None:
                lat_str = str(d["approximate_latitude"])
                decimals = len(lat_str.split(".")[1]) if "." in lat_str else 0
                self.assertLessEqual(decimals, 2)

            # Verify no private PII exposed
            self.assertNotIn("email", d)
            self.assertNotIn("phone", d)
            self.assertNotIn("home_address", d)
            self.assertNotIn("exact_latitude", d)

    def test_07_preview_is_strictly_read_only(self):
        """Test: Calling preview never creates broadcasts, recipient records, or email alerts."""
        mail.outbox.clear()
        initial_broadcast_count = SOSBroadcast.objects.count()
        initial_recipient_count = SOSRecipient.objects.count()

        self.client.force_authenticate(user=self.hospital_staff1)
        res = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=25")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Check DB and email outbox unchanged
        self.assertEqual(SOSBroadcast.objects.count(), initial_broadcast_count)
        self.assertEqual(SOSRecipient.objects.count(), initial_recipient_count)
        self.assertEqual(len(mail.outbox), 0)

    def test_08_invalid_radius_and_not_found(self):
        """Test: Invalid radius values return 400, missing blood request returns 404."""
        self.client.force_authenticate(user=self.hospital_staff1)

        # Negative radius
        res_neg = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=-10")
        self.assertEqual(res_neg.status_code, status.HTTP_400_BAD_REQUEST)

        # Radius > 100
        res_large = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=150")
        self.assertEqual(res_large.status_code, status.HTTP_400_BAD_REQUEST)

        # Non-numeric radius
        res_abc = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=abc")
        self.assertEqual(res_abc.status_code, status.HTTP_400_BAD_REQUEST)

        # 404 not found
        res_404 = self.client.get("/api/blood-requests/999999/sos/preview/")
        self.assertEqual(res_404.status_code, status.HTTP_404_NOT_FOUND)


class SOSRecipientRealDistanceTests(EmergencySOSTestsBase):
    """
    Test suite verifying real Haversine distance calculation and donor privacy on SOS recipients.
    """

    def setUp(self):
        super().setUp()
        self.broadcast = trigger_sos_broadcast(self.critical_request, self.hospital_staff1)

    def test_recipient_distance_is_real_haversine_calculation(self):
        """Test: Distance in SOS recipient record exactly matches canonical Haversine calculation."""
        self.client.force_authenticate(user=self.hospital_staff1)
        res = self.client.get(f"/api/sos/{self.broadcast.id}/recipients/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 2)

        for item in results:
            self.assertIn("distance_km", item)
            self.assertIsNotNone(item["distance_km"])
            self.assertIsInstance(item["distance_km"], float)

            # Determine expected real distance based on donor
            if item["donor_username"] == self.donor_user_o_neg.username:
                expected_dist = calculate_haversine_distance_km(
                    self.blood_bank.latitude,
                    self.blood_bank.longitude,
                    self.donor_o_neg.latitude,
                    self.donor_o_neg.longitude,
                )
                self.assertAlmostEqual(item["distance_km"], round(float(expected_dist), 2), places=2)
            elif item["donor_username"] == self.donor_user_a_pos.username:
                expected_dist = calculate_haversine_distance_km(
                    self.blood_bank.latitude,
                    self.blood_bank.longitude,
                    self.donor_a_pos.latitude,
                    self.donor_a_pos.longitude,
                )
                self.assertAlmostEqual(item["distance_km"], round(float(expected_dist), 2), places=2)

    def test_recipient_distance_matches_donor_preview_distance(self):
        """Test: Recipient distance and donor preview distance are identical."""
        self.client.force_authenticate(user=self.hospital_staff1)

        # 1. Fetch preview distance
        preview_res = self.client.get(f"/api/blood-requests/{self.critical_request.id}/sos/preview/?radius_km=25")
        self.assertEqual(preview_res.status_code, status.HTTP_200_OK)
        preview_map = {d["donor_id"]: d["distance_km"] for d in preview_res.data["donors"]}

        # 2. Fetch recipient distance
        recip_res = self.client.get(f"/api/sos/{self.broadcast.id}/recipients/")
        self.assertEqual(recip_res.status_code, status.HTTP_200_OK)
        recip_list = recip_res.data.get("results", recip_res.data)

        for r in recip_list:
            donor_id = r["donor"]
            self.assertIn(donor_id, preview_map)
            self.assertEqual(r["distance_km"], preview_map[donor_id])

    def test_recipient_distance_handles_null_coordinates_safely(self):
        """Test: When blood bank or donor coordinates are None, distance_km returns None without error."""
        # Create a donor with None coordinates
        no_coord_user = User.objects.create_user(
            username="donor_no_coords",
            email="nocoords@example.com",
            password="StrongPassword123!",
            role=UserRole.DONOR,
        )
        no_coord_donor = Donor.objects.create(
            user=no_coord_user,
            blood_group=BloodGroup.A_POSITIVE,
            date_of_birth=self.today - timedelta(days=25 * 365),
            weight_kg=Decimal("60.0"),
            last_donation_date=self.today - timedelta(days=100),
            latitude=None,
            longitude=None,
        )
        # Create recipient directly
        recip = SOSRecipient.objects.create(
            sos_broadcast=self.broadcast,
            donor=no_coord_donor,
            user=no_coord_user,
            email_attempted=False,
            email_sent=False,
        )

        self.client.force_authenticate(user=self.hospital_staff1)
        res = self.client.get(f"/api/sos/{self.broadcast.id}/recipients/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        no_coord_result = next((r for r in results if r["id"] == recip.id), None)
        self.assertIsNotNone(no_coord_result)
        self.assertIsNone(no_coord_result["distance_km"])

    def test_recipient_serializer_preserves_donor_privacy(self):
        """Test: Exact donor coordinates, phone numbers, and addresses are NOT exposed in recipient API."""
        self.client.force_authenticate(user=self.hospital_staff1)
        res = self.client.get(f"/api/sos/{self.broadcast.id}/recipients/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)

        for r in results:
            self.assertNotIn("latitude", r)
            self.assertNotIn("longitude", r)
            self.assertNotIn("phone", r)
            self.assertNotIn("phone_number", r)
            self.assertNotIn("address", r)
            self.assertNotIn("home_address", r)
            self.assertNotIn("email", r)
            # Safe fields only
            self.assertIn("id", r)
            self.assertIn("sos_broadcast", r)
            self.assertIn("donor", r)
            self.assertIn("donor_username", r)
            self.assertIn("donor_blood_group", r)
            self.assertIn("distance_km", r)
