"""Tests for authentication, role routing, and access control."""

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from accounts.models import LecturerTitle, User

PASSWORD = "test-password"


class AuthTestCase(TestCase):
    """Shared fixtures: one user per role."""

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_student(
            "2026001", "student@crs.test", PASSWORD, first_name="Sinta", last_name="Wijaya"
        )
        # Title is set explicitly, and to something other than the model default,
        # so asserting on it proves the profile value is what gets rendered.
        cls.lecturer = User.objects.create_lecturer(
            "L-1001",
            "lecturer@crs.test",
            PASSWORD,
            first_name="Budi",
            last_name="Santoso",
            title=LecturerTitle.ASSOCIATE_PROFESSOR,
        )
        cls.admin = User.objects.create_superuser("admin", "admin@crs.test", PASSWORD)


class LoginTests(AuthTestCase):
    def test_login_page_renders(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")
        self.assertContains(response, "Student / staff number")

    def test_each_role_lands_on_its_own_dashboard(self):
        cases = [
            (self.student, "accounts:student_dashboard"),
            (self.lecturer, "accounts:lecturer_dashboard"),
            (self.admin, "accounts:admin_dashboard"),
        ]
        for user, expected_url_name in cases:
            with self.subTest(role=user.role):
                self.client.logout()
                response = self.client.post(
                    reverse("accounts:login"),
                    {"username": user.username, "password": PASSWORD},
                )
                self.assertRedirects(response, reverse(expected_url_name))

    def test_wrong_password_shows_error_and_does_not_authenticate(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.student.username, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No account matches")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_unknown_username_shows_same_generic_error(self):
        """The message must not reveal whether the account exists."""
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "no-such-user", "password": PASSWORD},
        )
        self.assertContains(response, "No account matches")

    def test_inactive_user_cannot_log_in(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.student.username, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_next_parameter_is_honoured(self):
        target = reverse("accounts:profile")
        response = self.client.post(
            f"{reverse('accounts:login')}?next={target}",
            {"username": self.student.username, "password": PASSWORD},
        )
        self.assertRedirects(response, target)

    def test_authenticated_user_is_bounced_off_the_login_page(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:login"))
        self.assertRedirects(response, reverse("accounts:student_dashboard"))


class LogoutTests(AuthTestCase):
    def test_logout_via_post_redirects_to_login(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))

    def test_logout_ends_the_session(self):
        self.client.force_login(self.student)
        self.client.post(reverse("accounts:logout"))

        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_logout_rejects_get(self):
        """Django requires POST for logout; a GET must not end the session."""
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)

        self.assertEqual(self.client.get(reverse("accounts:student_dashboard")).status_code, 200)


class DashboardRoutingTests(AuthTestCase):
    def test_root_url_redirects_to_the_users_dashboard(self):
        self.client.force_login(self.lecturer)
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/lecturer_dashboard.html")

    def test_dashboard_entry_point_dispatches_by_role(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertRedirects(response, reverse("accounts:student_dashboard"))

    def test_anonymous_user_is_sent_to_login_with_next(self):
        target = reverse("accounts:student_dashboard")
        response = self.client.get(target)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={target}")


class RoleAccessControlTests(AuthTestCase):
    def test_student_cannot_reach_lecturer_or_admin_dashboards(self):
        self.client.force_login(self.student)

        for url_name in ("accounts:lecturer_dashboard", "accounts:admin_dashboard"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse("accounts:student_dashboard"))

    def test_lecturer_cannot_reach_student_or_admin_dashboards(self):
        self.client.force_login(self.lecturer)

        for url_name in ("accounts:student_dashboard", "accounts:admin_dashboard"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse("accounts:lecturer_dashboard"))

    def test_wrong_role_gets_an_explanatory_message(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:lecturer_dashboard"), follow=True)

        texts = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("That page is only available to lecturers.", texts)

    def test_each_role_can_reach_its_own_dashboard(self):
        cases = [
            (self.student, "accounts:student_dashboard", "accounts/student_dashboard.html"),
            (self.lecturer, "accounts:lecturer_dashboard", "accounts/lecturer_dashboard.html"),
            (self.admin, "accounts:admin_dashboard", "accounts/admin_dashboard.html"),
        ]
        for user, url_name, template in cases:
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)


class ProfileTests(AuthTestCase):
    def test_profile_shows_student_details(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sinta Wijaya")
        self.assertContains(response, "student@crs.test")
        self.assertContains(response, self.student.student_profile.student_number)

    def test_profile_shows_lecturer_details(self):
        self.client.force_login(self.lecturer)
        response = self.client.get(reverse("accounts:profile"))

        self.assertContains(response, self.lecturer.lecturer_profile.staff_number)
        self.assertContains(response, "Associate Professor")

    def test_profile_renders_for_admin_without_a_profile_row(self):
        """An ADMIN has neither profile model; the page must still render."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["profile"])

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)


class PasswordChangeTests(AuthTestCase):
    def test_password_change_succeeds_and_new_password_works(self):
        self.client.force_login(self.student)
        new_password = "a-brand-new-password"

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": PASSWORD,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertRedirects(response, reverse("accounts:password_change_done"))

        self.client.logout()
        self.assertTrue(self.client.login(username=self.student.username, password=new_password))

    def test_wrong_old_password_is_rejected(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "not-the-old-password",
                "new_password1": "some-new-password",
                "new_password2": "some-new-password",
            },
        )
        self.assertEqual(response.status_code, 200)

        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(PASSWORD))

    def test_mismatched_confirmation_is_rejected(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": PASSWORD,
                "new_password1": "password-one",
                "new_password2": "password-two",
            },
        )
        self.assertEqual(response.status_code, 200)

        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(PASSWORD))

    def test_password_change_requires_login(self):
        response = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(response.status_code, 302)
