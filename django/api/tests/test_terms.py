"""Term read visibility and admin-only registration-window updates."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import LecturerTitle, User
from registration.tests.factories import make_student, make_term

PASSWORD = "test-password"


class TermTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.term = make_term(is_active=True)
        cls.student = make_student()
        cls.lecturer = User.objects.create_lecturer(
            "L-1001", "lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )
        cls.admin = User.objects.create_superuser("admin", "admin@crs.test", PASSWORD)


class TermReadTests(TermTestCase):
    def test_student_can_read_term_window_data(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("api:term-detail", args=[self.term.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("registration_opens_at", body)
        self.assertIn("registration_closes_at", body)
        self.assertIn("registration_status", body)

    def test_every_role_can_list_terms(self):
        for user in (self.student.user, self.lecturer, self.admin):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("api:term-list"))
                self.assertEqual(response.status_code, 200)


class TermUpdateTests(TermTestCase):
    def test_admin_can_patch_the_registration_window(self):
        self.client.force_login(self.admin)
        response = self.client.patch(
            reverse("api:term-detail", args=[self.term.pk]),
            {"max_credits_per_student": 18},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.term.refresh_from_db()
        self.assertEqual(self.term.max_credits_per_student, 18)

    def test_non_admin_cannot_patch(self):
        for user in (self.student.user, self.lecturer):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.patch(
                    reverse("api:term-detail", args=[self.term.pk]),
                    {"max_credits_per_student": 18},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 403)

    def test_invalid_window_is_rejected_on_a_full_update(self):
        self.client.force_login(self.admin)
        response = self.client.put(
            reverse("api:term-detail", args=[self.term.pk]),
            {
                "registration_opens_at": "2026-12-31T00:00:00Z",
                "registration_closes_at": "2026-01-01T00:00:00Z",
                "max_credits_per_student": 18,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_window_is_rejected_on_a_partial_update(self):
        self.client.force_login(self.admin)
        response = self.client.patch(
            reverse("api:term-detail", args=[self.term.pk]),
            {"registration_closes_at": "1999-01-01T00:00:00Z"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
