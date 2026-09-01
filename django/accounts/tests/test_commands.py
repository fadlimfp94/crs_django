"""Tests for the create_test_users management command."""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from accounts.models import LecturerProfile, Role, StudentProfile, User


class CreateTestUsersTests(TestCase):
    @staticmethod
    def run_command(**kwargs):
        out = StringIO()
        call_command("create_test_users", stdout=out, **kwargs)
        return out.getvalue()

    @override_settings(DEBUG=True)
    def test_creates_one_user_per_role_with_profiles(self):
        self.run_command()

        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(
            set(User.objects.values_list("role", flat=True)),
            {Role.STUDENT, Role.LECTURER, Role.ADMIN},
        )
        self.assertEqual(StudentProfile.objects.count(), 1)
        self.assertEqual(LecturerProfile.objects.count(), 1)

    @override_settings(DEBUG=True)
    def test_is_idempotent(self):
        self.run_command()
        self.run_command()

        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(StudentProfile.objects.count(), 1)
        self.assertEqual(LecturerProfile.objects.count(), 1)

    @override_settings(DEBUG=True)
    def test_accounts_can_actually_log_in(self):
        self.run_command(password="known-password")

        for username in ("2026001", "L-1001", "admin"):
            with self.subTest(username=username):
                self.assertTrue(self.client.login(username=username, password="known-password"))
                self.client.logout()

    @override_settings(DEBUG=True)
    def test_administrator_can_reach_the_django_admin_site(self):
        self.run_command(password="known-password")

        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_staff)

        self.client.force_login(admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    @override_settings(DEBUG=True)
    def test_rerun_resets_the_password(self):
        self.run_command(password="first-password")
        self.run_command(password="second-password")

        self.assertFalse(self.client.login(username="2026001", password="first-password"))
        self.assertTrue(self.client.login(username="2026001", password="second-password"))

    @override_settings(DEBUG=False)
    def test_refuses_to_run_when_debug_is_off(self):
        with self.assertRaises(CommandError):
            self.run_command()

        self.assertEqual(User.objects.count(), 0)

    @override_settings(DEBUG=False)
    def test_force_overrides_the_debug_guard(self):
        self.run_command(force=True)
        self.assertEqual(User.objects.count(), 3)
