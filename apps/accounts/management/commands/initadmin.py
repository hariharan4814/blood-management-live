import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from apps.accounts.models import UserRole

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Safely provisions the initial SUPER_ADMIN Administrator account. "
        "Credentials are read strictly from environment variables (ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD)."
    )

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_USERNAME", "Administrator").strip()
        email = os.environ.get("ADMIN_EMAIL", "admin@bloodmgmt.org").strip().lower()
        password = os.environ.get("ADMIN_PASSWORD", "").strip()

        if not password:
            raise CommandError(
                "ADMIN_PASSWORD environment variable is missing or empty. "
                "Please set ADMIN_PASSWORD before running initadmin."
            )

        # Check by username
        user_by_username = User.objects.filter(username__iexact=username).first()
        # Check by email
        user_by_email = User.objects.filter(email__iexact=email).first()

        # If a matching user is found
        if user_by_username or user_by_email:
            existing_user = user_by_username or user_by_email

            # Check if this user is already a SUPER_ADMIN
            if existing_user.role == UserRole.SUPER_ADMIN and existing_user.is_superuser:
                self.stdout.write(
                    self.style.WARNING(
                        f"Administrator '{existing_user.username}' ({existing_user.email}) already exists as SUPER_ADMIN. "
                        "No changes made to existing credentials."
                    )
                )
                return

            # If user exists but belongs to a different role or lacks superuser status
            raise CommandError(
                f"A user with matching username '{username}' or email '{email}' already exists "
                f"with role '{existing_user.get_role_display()}'. "
                "Aborting bootstrap to prevent unauthorized account takeover."
            )

        # Create fresh SUPER_ADMIN
        admin_user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            role=UserRole.SUPER_ADMIN,
            is_verified=True,
            first_name="Platform",
            last_name="Administrator",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully initialized SUPER_ADMIN '{admin_user.username}' ({admin_user.email})."
            )
        )
