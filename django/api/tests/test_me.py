"""Shape of GET /api/v1/me/ for each role."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import LecturerTitle, User
from registration.tests.factories import make_student

PASSWORD = "test-password"


class MeViewTests(TestCase):
    def test_student_profile_fields(self):
        student = make_student()
        self.client.force_login(student.user)
        response = self.client.get(reverse("api:me"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["role"], "STUDENT")
        self.assertEqual(body["student"]["student_number"], student.student_number)
        self.assertIn("may_register", body["student"])

    def test_lecturer_profile_fields(self):
        lecturer = User.objects.create_lecturer(
            "L-1001", "lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )
        self.client.force_login(lecturer)
        response = self.client.get(reverse("api:me"))
        body = response.json()
        self.assertEqual(body["role"], "LECTURER")
        self.assertEqual(body["lecturer"]["staff_number"], lecturer.lecturer_profile.staff_number)

    def test_administrator_has_no_profile_block(self):
        admin = User.objects.create_superuser("admin", "admin@crs.test", PASSWORD)
        self.client.force_login(admin)
        response = self.client.get(reverse("api:me"))
        body = response.json()
        self.assertEqual(body["role"], "ADMIN")
        self.assertNotIn("student", body)
        self.assertNotIn("lecturer", body)
