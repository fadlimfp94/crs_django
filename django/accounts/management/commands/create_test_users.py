"""
Create one account per role for local development and the E2E suite.

    python manage.py create_test_users

Idempotent: re-running updates the existing accounts instead of failing, so it
is safe to call from test setup and from the Phase 2 seed command.

These accounts have well-known passwords, so the command refuses to run outside
DEBUG unless --force is passed.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import LecturerProfile, LecturerTitle, Role, StudentProfile, User

# Deliberately well-known. The DEBUG guard in handle() is what keeps this safe.
DEFAULT_PASSWORD = "crs-dev-password"

TEST_USERS = [
    {
        "username": "2026001",
        "email": "student@crs.test",
        "first_name": "Sinta",
        "last_name": "Wijaya",
        "role": Role.STUDENT,
    },
    {
        "username": "L-1001",
        "email": "lecturer@crs.test",
        "first_name": "Budi",
        "last_name": "Santoso",
        "role": Role.LECTURER,
    },
    {
        "username": "admin",
        "email": "admin@crs.test",
        "first_name": "Registrar",
        "last_name": "Office",
        "role": Role.ADMIN,
    },
]


class Command(BaseCommand):
    help = "Create or refresh one test account per role (student, lecturer, administrator)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Password for every test account (default: {DEFAULT_PASSWORD!r}).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow creation when DEBUG is False. Never do this on a real deployment.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to create accounts with well-known passwords while DEBUG is False. "
                "Pass --force only if you are certain this is not a real deployment."
            )

        password = options["password"]

        for spec in TEST_USERS:
            user, created = User.objects.update_or_create(
                username=spec["username"],
                defaults={
                    "email": spec["email"],
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "role": spec["role"],
                    "is_active": True,
                    # The administrator needs the Django admin site in Phase 1,
                    # since no purpose-built admin screens exist yet.
                    "is_staff": spec["role"] == Role.ADMIN,
                    "is_superuser": spec["role"] == Role.ADMIN,
                },
            )
            user.set_password(password)
            user.save(update_fields=["password"])

            self._ensure_profile(user)

            verb = "created" if created else "updated"
            style = self.style.SUCCESS if created else self.style.WARNING
            self.stdout.write(
                style(f"  {verb}: {user.username:<10} {user.get_role_display():<14} {user.email}")
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"{len(TEST_USERS)} test accounts ready."))
        self.stdout.write(f"Password for all of them: {password}")

    @staticmethod
    def _ensure_profile(user: User) -> None:
        """Create the profile the user's role implies, if it is missing."""
        if user.is_student:
            StudentProfile.objects.get_or_create(
                user=user,
                defaults={"student_number": user.username, "enrollment_year": 2026},
            )
        elif user.is_lecturer:
            LecturerProfile.objects.get_or_create(
                user=user,
                defaults={
                    "staff_number": user.username,
                    "title": LecturerTitle.ASSOCIATE_PROFESSOR,
                },
            )
