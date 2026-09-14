from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.notifications.email_service import (
    extract_recipient_email,
    send_blood_request_email,
    send_camp_email,
    send_donation_email,
    send_eligibility_email,
    send_notification_email,
    validate_email_content,
)
from apps.notifications.models import (
    EmailRecipient,
    EmailRecipientType,
    Notification,
    NotificationType,
)
from apps.notifications.services import (
    create_bulk_notifications,
    create_notification,
    get_unread_notification_count,
    mark_all_notifications_as_read,
    mark_notification_as_read,
    validate_notification_content,
)

User = get_user_model()


class NotificationModelTests(TestCase):
    """
    Test suite for the Notification model and data integrity.
    """

    def setUp(self):
        self.donor_user = User.objects.create_user(
            username="donor_user",
            email="donor@example.com",
            password="StrongPassword123!",
            role=UserRole.DONOR,
        )

    def test_create_valid_notification(self):
        notification = Notification.objects.create(
            recipient=self.donor_user,
            title="Blood Donation Scheduled",
            message="Your blood donation appointment is confirmed for tomorrow at 10:00 AM.",
            notification_type=NotificationType.DONATION,
        )
        self.assertIsNotNone(notification.id)
        self.assertEqual(notification.recipient, self.donor_user)
        self.assertFalse(notification.is_read)
        self.assertEqual(notification.notification_type, NotificationType.DONATION)

    def test_notification_str_representation(self):
        notification = Notification.objects.create(
            recipient=self.donor_user,
            title="Camp Reminder",
            message="Don't forget the upcoming blood drive.",
            notification_type=NotificationType.CAMP,
        )
        self.assertIn("Camp Reminder", str(notification))
        self.assertIn("Unread", str(notification))
        notification.is_read = True
        notification.save()
        self.assertIn("Read", str(notification))

    def test_blank_title_rejected(self):
        with self.assertRaises(ValidationError):
            notification = Notification(
                recipient=self.donor_user,
                title="",
                message="Some valid message.",
            )
            notification.full_clean()

    def test_whitespace_only_title_rejected(self):
        with self.assertRaises(ValidationError):
            notification = Notification(
                recipient=self.donor_user,
                title="    ",
                message="Some valid message.",
            )
            notification.full_clean()

    def test_blank_message_rejected(self):
        with self.assertRaises(ValidationError):
            notification = Notification(
                recipient=self.donor_user,
                title="Valid Title",
                message="",
            )
            notification.full_clean()

    def test_whitespace_only_message_rejected(self):
        with self.assertRaises(ValidationError):
            notification = Notification(
                recipient=self.donor_user,
                title="Valid Title",
                message="   \n\t  ",
            )
            notification.full_clean()

    def test_whitespace_stripped_on_save(self):
        notification = Notification.objects.create(
            recipient=self.donor_user,
            title="  Urgent Request  ",
            message="  Patient needs O- blood immediately.  ",
        )
        self.assertEqual(notification.title, "Urgent Request")
        self.assertEqual(notification.message, "Patient needs O- blood immediately.")


class EmailRecipientModelTests(TestCase):
    """
    Test suite for the EmailRecipient model and data integrity.
    """

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_user",
            email="admin@example.com",
            password="StrongPassword123!",
            role=UserRole.SUPER_ADMIN,
        )

    def test_create_valid_email_recipient(self):
        recipient = EmailRecipient.objects.create(
            email="coordinator@hospital.org",
            name="Emergency Blood Desk",
            recipient_type=EmailRecipientType.EMERGENCY_DESK,
            created_by=self.admin_user,
        )
        self.assertIsNotNone(recipient.id)
        self.assertEqual(recipient.email, "coordinator@hospital.org")
        self.assertTrue(recipient.is_active)
        self.assertIn("coordinator@hospital.org", str(recipient))

    def test_email_lowercased_and_trimmed_on_save(self):
        recipient = EmailRecipient.objects.create(
            email="  CONTACT@BloodBank.Org  ",
            name="  Head Coordinator  ",
            recipient_type=EmailRecipientType.BLOOD_BANK,
        )
        self.assertEqual(recipient.email, "contact@bloodbank.org")
        self.assertEqual(recipient.name, "Head Coordinator")

    def test_invalid_email_format_rejected(self):
        with self.assertRaises(ValidationError):
            recipient = EmailRecipient(
                email="not-an-email",
                name="Test",
            )
            recipient.full_clean()

    def test_duplicate_email_rejected(self):
        EmailRecipient.objects.create(
            email="duplicate@example.com",
            name="Recipient One",
        )
        with self.assertRaises((IntegrityError, ValidationError)):
            dup = EmailRecipient(
                email="duplicate@example.com",
                name="Recipient Two",
            )
            dup.save()


class NotificationAPITests(TestCase):
    """
    Test suite for In-App Notifications REST APIs and object-level permissions.
    """

    def setUp(self):
        self.client = APIClient()

        # Users
        self.donor1 = User.objects.create_user(
            username="donor_one",
            email="donor1@example.com",
            password="Password123!",
            role=UserRole.DONOR,
        )
        self.donor2 = User.objects.create_user(
            username="donor_two",
            email="donor2@example.com",
            password="Password123!",
            role=UserRole.DONOR,
        )
        self.staff_user = User.objects.create_user(
            username="hospital_staff_user",
            email="staff@example.com",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )

        # Seed notifications for donor1
        self.n1 = Notification.objects.create(
            recipient=self.donor1,
            title="Welcome Donor",
            message="Thank you for registering.",
            notification_type=NotificationType.GENERAL,
            is_read=False,
        )
        self.n2 = Notification.objects.create(
            recipient=self.donor1,
            title="Blood Request Match",
            message="Urgent B+ blood needed at City Hospital.",
            notification_type=NotificationType.BLOOD_REQUEST,
            is_read=False,
        )
        self.n3 = Notification.objects.create(
            recipient=self.donor1,
            title="Donation Camp Tomorrow",
            message="Join our camp at Metro Hall.",
            notification_type=NotificationType.CAMP,
            is_read=True,
        )

        # Seed notification for donor2
        self.n_donor2 = Notification.objects.create(
            recipient=self.donor2,
            title="Private Donor Two Notification",
            message="Confidential test results available.",
            notification_type=NotificationType.ELIGIBILITY,
            is_read=False,
        )

    def test_unauthenticated_user_denied(self):
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_list_only_own_notifications(self):
        self.client.force_authenticate(user=self.donor1)
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Paginated response check
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 3)
        titles = [n["title"] for n in results]
        self.assertIn("Welcome Donor", titles)
        self.assertIn("Blood Request Match", titles)
        self.assertIn("Donation Camp Tomorrow", titles)
        self.assertNotIn("Private Donor Two Notification", titles)

    def test_notifications_ordered_newest_first(self):
        self.client.force_authenticate(user=self.donor1)
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        # First returned notification should be n3 (created last)
        self.assertEqual(results[0]["id"], self.n3.id)

    def test_filter_by_is_read(self):
        self.client.force_authenticate(user=self.donor1)

        # Filter unread
        response_unread = self.client.get("/api/notifications/?is_read=false")
        self.assertEqual(response_unread.status_code, status.HTTP_200_OK)
        results_unread = response_unread.data.get("results", response_unread.data)
        self.assertEqual(len(results_unread), 2)
        for item in results_unread:
            self.assertFalse(item["is_read"])

        # Filter read
        response_read = self.client.get("/api/notifications/?is_read=true")
        self.assertEqual(response_read.status_code, status.HTTP_200_OK)
        results_read = response_read.data.get("results", response_read.data)
        self.assertEqual(len(results_read), 1)
        self.assertTrue(results_read[0]["is_read"])

    def test_filter_by_notification_type(self):
        self.client.force_authenticate(user=self.donor1)
        response = self.client.get("/api/notifications/?notification_type=BLOOD_REQUEST")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["notification_type"], "BLOOD_REQUEST")

    def test_user_can_retrieve_own_notification_detail(self):
        self.client.force_authenticate(user=self.donor1)
        response = self.client.get(f"/api/notifications/{self.n1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Welcome Donor")
        self.assertEqual(response.data["recipient_detail"]["username"], "donor_one")

    def test_user_cannot_retrieve_other_users_notification_detail(self):
        self.client.force_authenticate(user=self.donor1)
        # Attempt to access donor2's notification
        response = self.client.get(f"/api/notifications/{self.n_donor2.id}/")
        self.assertIn(response.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_user_can_mark_own_notification_as_read(self):
        self.client.force_authenticate(user=self.donor1)
        self.assertFalse(self.n1.is_read)
        response = self.client.post(f"/api/notifications/{self.n1.id}/mark-read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_read"])

        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)

    def test_user_cannot_mark_other_users_notification_as_read(self):
        self.client.force_authenticate(user=self.donor1)
        # Attempt to mark donor2's notification as read
        response = self.client.post(f"/api/notifications/{self.n_donor2.id}/mark-read/")
        self.assertIn(response.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        self.n_donor2.refresh_from_db()
        self.assertFalse(self.n_donor2.is_read)

    def test_user_can_mark_all_notifications_as_read(self):
        self.client.force_authenticate(user=self.donor1)
        response = self.client.post("/api/notifications/mark-all-read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["marked_count"], 2)  # n1 and n2 were unread

        self.n1.refresh_from_db()
        self.n2.refresh_from_db()
        self.assertTrue(self.n1.is_read)
        self.assertTrue(self.n2.is_read)

        # Ensure donor2's unread notification was untouched
        self.n_donor2.refresh_from_db()
        self.assertFalse(self.n_donor2.is_read)

    def test_unread_count_endpoint(self):
        self.client.force_authenticate(user=self.donor1)
        response = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 2)


class EmailRecipientAPITests(TestCase):
    """
    Test suite for Email Recipient administrative management and RBAC.
    """

    def setUp(self):
        self.client = APIClient()

        self.super_admin = User.objects.create_user(
            username="super_admin",
            email="admin@example.com",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.blood_bank_admin = User.objects.create_user(
            username="bb_admin",
            email="bb_admin@example.com",
            password="Password123!",
            role=UserRole.BLOOD_BANK_ADMIN,
        )
        self.hospital_staff = User.objects.create_user(
            username="hospital_user",
            email="hospital@example.com",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )
        self.lab_tech = User.objects.create_user(
            username="lab_tech_user",
            email="lab@example.com",
            password="Password123!",
            role=UserRole.LAB_TECHNICIAN,
        )
        self.donor = User.objects.create_user(
            username="donor_usr",
            email="donor_user@example.com",
            password="Password123!",
            role=UserRole.DONOR,
        )

        self.recipient1 = EmailRecipient.objects.create(
            email="director@bloodbank.org",
            name="Medical Director",
            recipient_type=EmailRecipientType.ADMIN,
            is_active=True,
            created_by=self.super_admin,
        )

    def test_super_admin_can_list_and_create_recipients(self):
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.get("/api/notifications/recipients/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            "/api/notifications/recipients/",
            {
                "email": "emergency@cityhospital.org",
                "name": "ER Triage Team",
                "recipient_type": "EMERGENCY_DESK",
                "is_active": True,
            },
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["email"], "emergency@cityhospital.org")

    def test_blood_bank_admin_can_manage_recipients(self):
        self.client.force_authenticate(user=self.blood_bank_admin)
        response = self.client.get("/api/notifications/recipients/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        patch_response = self.client.patch(
            f"/api/notifications/recipients/{self.recipient1.id}/",
            {"is_active": False},
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertFalse(patch_response.data["is_active"])

    def test_hospital_staff_denied_access_to_recipient_management(self):
        self.client.force_authenticate(user=self.hospital_staff)
        response = self.client.get("/api/notifications/recipients/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_lab_technician_denied_access_to_recipient_management(self):
        self.client.force_authenticate(user=self.lab_tech)
        response = self.client.get("/api/notifications/recipients/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_donor_denied_access_to_recipient_management(self):
        self.client.force_authenticate(user=self.donor)
        response = self.client.get("/api/notifications/recipients/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_denied_access_to_recipients(self):
        response = self.client.get("/api/notifications/recipients/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_duplicate_email_rejected_via_api(self):
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.post(
            "/api/notifications/recipients/",
            {
                "email": "director@bloodbank.org",
                "name": "Duplicate Entry",
                "recipient_type": "ADMIN",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_admin_can_delete_recipient(self):
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.delete(f"/api/notifications/recipients/{self.recipient1.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(EmailRecipient.objects.filter(pk=self.recipient1.id).exists())

    def test_create_all_canonical_recipient_categories(self):
        """
        Verify that all canonical recipient categories can be created by an authorized admin.
        """
        self.client.force_authenticate(user=self.super_admin)
        categories = [
            ("EMERGENCY_DESK", "External Emergency Partner", "Emergency Desk Contact"),
            ("ADMIN", "System Administrator", "Administrator"),
            ("BLOOD_BANK", "Regional Coordinator", "Blood Bank Coordinator"),
            ("HOSPITAL", "City Hospital Contact", "Hospital Contact"),
            ("STAFF", "Operations Staff", "Staff Member"),
            ("GENERAL", "General Dispatch Subscriber", "General Subscriber"),
        ]

        for idx, (cat_code, name, expected_display) in enumerate(categories):
            email = f"recipient_{idx}_{cat_code.lower()}@example.org"
            response = self.client.post(
                "/api/notifications/recipients/",
                {
                    "email": email,
                    "name": name,
                    "recipient_type": cat_code,
                    "is_active": True,
                },
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED,
                f"Failed to create recipient with category '{cat_code}': {response.data}",
            )
            self.assertEqual(response.data["recipient_type"], cat_code)
            self.assertEqual(response.data["recipient_type_display"], expected_display)

            recipient = EmailRecipient.objects.get(email=email)
            self.assertEqual(recipient.recipient_type, cat_code)

    def test_invalid_recipient_type_rejected(self):
        """
        Verify that invalid recipient_type values (such as EXTERNAL_EMERGENCY or arbitrary strings)
        are rejected with HTTP 400 Bad Request.
        """
        self.client.force_authenticate(user=self.super_admin)
        invalid_types = ["EXTERNAL_EMERGENCY", "HOSPITAL_STAFF", "BLOOD_BANK_ADMIN", "DONOR", "SYSTEM_ADMIN", "INVALID_CHOICE"]

        for idx, invalid_type in enumerate(invalid_types):
            response = self.client.post(
                "/api/notifications/recipients/",
                {
                    "email": f"invalid_{idx}@example.org",
                    "name": f"Invalid {invalid_type}",
                    "recipient_type": invalid_type,
                },
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected 400 Bad Request for invalid recipient_type '{invalid_type}'",
            )
            self.assertIn("recipient_type", response.data)



class NotificationServiceTests(TestCase):
    """
    Test suite for the reusable notification service layer.
    """

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="service_user1",
            email="service1@example.com",
            password="Password123!",
            role=UserRole.DONOR,
        )
        self.user2 = User.objects.create_user(
            username="service_user2",
            email="service2@example.com",
            password="Password123!",
            role=UserRole.HOSPITAL_STAFF,
        )

    def test_create_notification_service_valid(self):
        notification = create_notification(
            recipient=self.user1,
            title="  Important Alert  ",
            message="  Inventory is running low for AB- blood.  ",
            notification_type=NotificationType.INVENTORY,
        )
        self.assertEqual(notification.title, "Important Alert")
        self.assertEqual(notification.message, "Inventory is running low for AB- blood.")
        self.assertEqual(notification.notification_type, NotificationType.INVENTORY)
        self.assertFalse(notification.is_read)

    def test_create_notification_service_by_user_id(self):
        notification = create_notification(
            recipient=self.user1.id,
            title="ID-based Recipient",
            message="Testing creation by primary key.",
        )
        self.assertEqual(notification.recipient, self.user1)

    def test_create_notification_blank_title_raises(self):
        with self.assertRaises(ValidationError):
            create_notification(
                recipient=self.user1,
                title="   ",
                message="Valid Message.",
            )

    def test_create_notification_blank_message_raises(self):
        with self.assertRaises(ValidationError):
            create_notification(
                recipient=self.user1,
                title="Valid Title",
                message="",
            )

    def test_create_notification_invalid_recipient_raises(self):
        with self.assertRaises(ValidationError):
            create_notification(
                recipient=99999,
                title="Valid Title",
                message="Valid Message",
            )

    def test_create_bulk_notifications_service(self):
        created = create_bulk_notifications(
            recipients=[self.user1, self.user2],
            title="System Maintenance",
            message="Server upgrade scheduled at midnight.",
            notification_type=NotificationType.SYSTEM,
        )
        self.assertEqual(len(created), 2)
        self.assertEqual(Notification.objects.filter(title="System Maintenance").count(), 2)

    def test_mark_notification_as_read_service(self):
        n = create_notification(
            recipient=self.user1,
            title="Read Service Test",
            message="Content.",
        )
        self.assertFalse(n.is_read)
        updated = mark_notification_as_read(n, self.user1)
        self.assertTrue(updated.is_read)

        # Attempting mark read with wrong user raises ValidationError
        with self.assertRaises(ValidationError):
            mark_notification_as_read(n, self.user2)

    def test_mark_all_notifications_as_read_service(self):
        create_notification(recipient=self.user1, title="N1", message="M1")
        create_notification(recipient=self.user1, title="N2", message="M2")
        count = mark_all_notifications_as_read(self.user1)
        self.assertEqual(count, 2)
        self.assertEqual(get_unread_notification_count(self.user1), 0)


class EmailServiceTests(TestCase):
    """
    Test suite for the professional email delivery service and HTML templates.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="email_recipient_user",
            email="recipient@healthcare.org",
            password="Password123!",
            role=UserRole.DONOR,
        )

    def test_extract_recipient_email_valid(self):
        self.assertEqual(extract_recipient_email("test@example.com"), "test@example.com")
        self.assertEqual(extract_recipient_email(self.user), "recipient@healthcare.org")

    def test_extract_recipient_email_invalid_raises(self):
        with self.assertRaises(ValidationError):
            extract_recipient_email("")

        with self.assertRaises(ValidationError):
            extract_recipient_email("not-an-email")

    def test_validate_email_content_valid(self):
        s, m = validate_email_content("  Subject  ", "  Message Body  ")
        self.assertEqual(s, "Subject")
        self.assertEqual(m, "Message Body")

    def test_validate_email_content_blank_raises(self):
        with self.assertRaises(ValidationError):
            validate_email_content("", "Message")

        with self.assertRaises(ValidationError):
            validate_email_content("Subject", "   ")

    def test_send_notification_email_dispatches_with_outbox(self):
        success = send_notification_email(
            recipient="test@example.com",
            subject="Blood Test Results Complete",
            message="Your routine blood screening has been processed successfully.",
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.subject, "Blood Test Results Complete")
        self.assertIn("test@example.com", sent.to)
        self.assertIn("processed successfully", sent.body)
        # Check multipart HTML alternative attached
        self.assertTrue(any(content_type == "text/html" for _, content_type in sent.alternatives))

    def test_send_notification_email_with_user_instance(self):
        success = send_notification_email(
            recipient=self.user,
            subject="Personal Health Notification",
            message="Your donor card is ready for download.",
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["recipient@healthcare.org"])

    def test_send_blood_request_email_helper(self):
        request_data = {
            "id": 104,
            "patient_name": "John Doe",
            "blood_group": "O+",
            "units_requested": 2,
            "urgency": "EMERGENCY",
            "hospital_name": "City General Hospital",
            "status": "APPROVED",
        }
        success = send_blood_request_email(
            recipient="doctor@hospital.org",
            subject="Blood Request #104 Approved",
            message="The requested blood units have been reserved for surgery.",
            request_data=request_data,
            action_url="http://localhost:8080/requests/104",
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        sent_html = mail.outbox[0].alternatives[0][0]
        self.assertIn("John Doe", sent_html)
        self.assertIn("O+", sent_html)
        self.assertIn("EMERGENCY", sent_html)
        self.assertIn("City General Hospital", sent_html)

    def test_send_donation_email_helper(self):
        donation_data = {
            "donor_name": "Jane Smith",
            "donation_date": "2026-08-21",
            "blood_group": "A+",
            "blood_bank_name": "Central Red Cross",
            "unit_id": "BU-998877",
            "next_eligible_date": "2026-11-21",
        }
        success = send_donation_email(
            recipient="jane.smith@example.com",
            subject="Thank You for Your Donation!",
            message="Your donation helps save lives across our regional network.",
            donation_data=donation_data,
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        sent_html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Jane Smith", sent_html)
        self.assertIn("BU-998877", sent_html)
        self.assertIn("2026-11-21", sent_html)

    def test_send_camp_email_helper(self):
        camp_data = {
            "camp_name": "Annual University Blood Drive",
            "venue": "Campus Student Center",
            "start_date": "2026-09-01",
            "end_date": "2026-09-03",
            "organizer_name": "Youth Red Cross",
            "blood_bank_name": "Central Blood Bank",
            "registration_status": "REGISTERED",
        }
        success = send_camp_email(
            recipient="student@university.edu",
            subject="Camp Registration Confirmed",
            message="You are confirmed to donate at the Annual University Blood Drive.",
            camp_data=camp_data,
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        sent_html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Annual University Blood Drive", sent_html)
        self.assertIn("Campus Student Center", sent_html)

    def test_send_eligibility_email_helper(self):
        eligibility_data = {
            "donor_name": "Robert Brown",
            "is_eligible": True,
            "next_eligible_date": "2026-08-21",
            "reasons": ["All medical criteria satisfied."],
        }
        success = send_eligibility_email(
            recipient="robert.b@example.com",
            subject="You are Eligible to Donate Blood",
            message="Your waiting period has passed and you are now eligible to donate.",
            eligibility_data=eligibility_data,
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        sent_html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Robert Brown", sent_html)
        self.assertIn("Eligible to Donate", sent_html)

    def test_send_email_graceful_failure_when_smtp_fails(self):
        # Mock EmailMultiAlternatives.send to raise an exception
        with patch.object(mail.EmailMultiAlternatives, "send", side_effect=Exception("SMTP server connection timeout")):
            # When fail_silently=True (default), returns False without raising exception
            result = send_notification_email(
                recipient="test@example.com",
                subject="Connection Test",
                message="Testing graceful failure.",
                fail_silently=True,
            )
            self.assertFalse(result)

            # When fail_silently=False, raises exception
            with self.assertRaises(Exception):
                send_notification_email(
                    recipient="test@example.com",
                    subject="Connection Test",
                    message="Testing fail loudly.",
                    fail_silently=False,
                )


class EmailManagementAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.super_admin = User.objects.create_superuser(
            username="admin_email_test",
            email="admin.email@test.com",
            password="AdminPassword123!",
            role=UserRole.SUPER_ADMIN,
            is_verified=True,
        )
        self.donor = User.objects.create_user(
            username="donor_email_test",
            email="donor.email@test.com",
            password="DonorPassword123!",
            role=UserRole.DONOR,
            is_verified=True,
        )

    def test_super_admin_get_email_status(self):
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.get("/api/notifications/email-status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("smtp_configured", data)
        self.assertIn("email_backend", data)
        self.assertIn("default_from_email", data)
        self.assertNotIn("password", data)

    def test_non_super_admin_cannot_get_email_status(self):
        self.client.force_authenticate(user=self.donor)
        response = self.client.get("/api/notifications/email-status/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_send_test_email(self):
        self.client.force_authenticate(user=self.super_admin)
        payload = {
            "recipient_email": "admin.verify@example.com",
            "subject": "Admin Verification Test",
            "message": "Testing SMTP delivery."
        }
        response = self.client.post("/api/notifications/test-email/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["success"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["admin.verify@example.com"])

    def test_non_super_admin_cannot_send_test_email(self):
        self.client.force_authenticate(user=self.donor)
        payload = {
            "recipient_email": "donor.verify@example.com",
            "subject": "Unauthorized Test",
            "message": "This should fail."
        }
        response = self.client.post("/api/notifications/test-email/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
