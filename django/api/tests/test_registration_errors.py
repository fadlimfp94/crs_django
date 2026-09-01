"""
One round-trip test per registration rule, asserting the exact
``{"rule": "R<n>", "detail": "..."}`` error envelope, plus one test for the
``rule=None`` case (a non-rule-coded failure).
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import StudentStatus
from registration.tests.factories import (
    make_course,
    make_department,
    make_meeting,
    make_prerequisite,
    make_section,
    make_student,
    make_term,
)


class RegistrationErrorTests(TestCase):
    def setUp(self):
        self.department = make_department()
        self.term = make_term(is_active=True)
        self.course = make_course(self.department, "CS101")
        self.section = make_section(self.course, self.term, capacity=5)
        make_meeting(self.section)
        self.student = make_student()
        self.client.force_login(self.student.user)

    def _register(self, section):
        return self.client.post(reverse("api:section-register", args=[section.pk]))

    def test_r1_registration_window_closed(self):
        term = make_term("2025-FALL", opens_days=-10, closes_days=-5)
        section = make_section(self.course, term)
        response = self._register(section)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["rule"], "R1")

    def test_r2_already_registered_for_the_course(self):
        self._register(self.section)
        response = self._register(self.section)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["rule"], "R2")

    def test_r3_prerequisite_not_met(self):
        prerequisite = make_course(self.department, "CS100")
        advanced = make_course(self.department, "CS201")
        make_prerequisite(advanced, prerequisite)
        section = make_section(advanced, self.term, section_code="02")

        response = self._register(section)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["rule"], "R3")

    def test_r4_credit_limit_exceeded(self):
        term = make_term("2026-SPRING", max_credits=3)
        section = make_section(self.course, term, section_code="03")  # course has 4 credits

        response = self._register(section)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["rule"], "R4")

    def test_r5_timetable_clash(self):
        self._register(self.section)
        other_course = make_course(self.department, "CS102")
        clashing_section = make_section(other_course, self.term, section_code="02", capacity=5)
        make_meeting(clashing_section)  # same day/time as self.section by factory default

        response = self._register(clashing_section)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["rule"], "R5")

    def test_r7_academic_standing(self):
        self.client.force_login(make_student(status=StudentStatus.SUSPENDED).user)
        response = self._register(self.section)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["rule"], "R7")

    def test_non_rule_error_serializes_rule_as_null(self):
        self._register(self.section)
        from registration.models import Enrollment

        enrollment = Enrollment.objects.get(student=self.student, section=self.section)
        self.client.post(reverse("api:enrollment-drop", args=[enrollment.pk]))  # first drop

        response = self.client.post(reverse("api:enrollment-drop", args=[enrollment.pk]))
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("rule", body)
        self.assertIsNone(body["rule"])
