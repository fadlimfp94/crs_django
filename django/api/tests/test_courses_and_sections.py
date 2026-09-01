"""Tests for the read-only course/section endpoints and the register/roster actions."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import LecturerTitle, User
from registration.models import Enrollment, EnrollmentStatus
from registration.tests.factories import (
    make_course,
    make_department,
    make_meeting,
    make_section,
    make_student,
    make_term,
)

PASSWORD = "test-password"


class ApiTestCase(TestCase):
    """Shared fixture: one active term, one department, three sections, every role."""

    @classmethod
    def setUpTestData(cls):
        cls.department = make_department("CS", "Computer Science")
        other_department = make_department("MATH", "Mathematics")

        cls.term = make_term("2026-FALL", is_active=True)
        cls.other_term = make_term("2027-SPRING", opens_days=+30, closes_days=+60)

        cls.course = make_course(cls.department, "CS101", credits=4)
        cls.other_course = make_course(other_department, "MATH200", credits=3)

        cls.lecturer_user = User.objects.create_lecturer(
            "L-1001", "lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )
        cls.other_lecturer_user = User.objects.create_lecturer(
            "L-1002", "other-lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )
        cls.admin = User.objects.create_superuser("admin", "admin@crs.test", PASSWORD)

        cls.section = make_section(
            cls.course, cls.term, capacity=2, lecturer=cls.lecturer_user.lecturer_profile
        )
        make_meeting(cls.section)
        cls.other_section = make_section(cls.other_course, cls.term, section_code="01", capacity=30)
        cls.other_term_section = make_section(cls.course, cls.other_term, section_code="02")

        cls.student = make_student()
        cls.second_student = make_student()
        cls.third_student = make_student()


class AuthenticationTests(ApiTestCase):
    def test_anonymous_request_is_rejected(self):
        response = self.client.get(reverse("api:section-list"))
        self.assertEqual(response.status_code, 401)


class CourseListTests(ApiTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)

    def test_lists_every_course(self):
        response = self.client.get(reverse("api:course-list"))
        self.assertEqual(response.status_code, 200)
        codes = {c["code"] for c in response.json()["results"]}
        self.assertEqual(codes, {"CS101", "MATH200"})

    def test_filter_by_department(self):
        response = self.client.get(reverse("api:course-list"), {"department": "CS"})
        codes = {c["code"] for c in response.json()["results"]}
        self.assertEqual(codes, {"CS101"})

    def test_free_text_search(self):
        response = self.client.get(reverse("api:course-list"), {"q": "CS101"})
        codes = {c["code"] for c in response.json()["results"]}
        self.assertEqual(codes, {"CS101"})

    def test_filter_by_is_active(self):
        self.other_course.is_active = False
        self.other_course.save(update_fields=["is_active"])
        response = self.client.get(reverse("api:course-list"), {"is_active": "false"})
        codes = {c["code"] for c in response.json()["results"]}
        self.assertEqual(codes, {"MATH200"})


class SectionListTests(ApiTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)

    def test_no_query_defaults_to_the_active_term(self):
        response = self.client.get(reverse("api:section-list"))
        ids = {s["id"] for s in response.json()["results"]}
        self.assertIn(self.section.id, ids)
        self.assertIn(self.other_section.id, ids)
        self.assertNotIn(self.other_term_section.id, ids)

    def test_explicit_any_term_shows_every_term(self):
        response = self.client.get(reverse("api:section-list"), {"term": ""})
        ids = {s["id"] for s in response.json()["results"]}
        self.assertIn(self.other_term_section.id, ids)

    def test_filter_by_term_code(self):
        response = self.client.get(reverse("api:section-list"), {"term": self.other_term.code})
        ids = {s["id"] for s in response.json()["results"]}
        self.assertEqual(ids, {self.other_term_section.id})

    def test_pagination_page_size_is_twenty(self):
        for index in range(25):
            make_section(self.course, self.term, section_code=f"P{index:02d}")
        response = self.client.get(reverse("api:section-list"))
        body = response.json()
        self.assertEqual(len(body["results"]), 20)
        self.assertIsNotNone(body["next"])

    def test_availability_open_excludes_a_full_section(self):
        self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.client.force_login(self.second_student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))  # now full

        response = self.client.get(reverse("api:section-list"), {"availability": "open"})
        ids = {s["id"] for s in response.json()["results"]}
        self.assertNotIn(self.section.id, ids)
        self.assertIn(self.other_section.id, ids)

    def test_availability_waitlist_only_returns_the_full_section(self):
        self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.client.force_login(self.second_student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))

        response = self.client.get(reverse("api:section-list"), {"availability": "waitlist"})
        ids = {s["id"] for s in response.json()["results"]}
        self.assertEqual(ids, {self.section.id})

    def test_mine_scopes_a_lecturer_to_their_own_sections(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.get(reverse("api:section-list"), {"mine": "true"})
        ids = {s["id"] for s in response.json()["results"]}
        self.assertEqual(ids, {self.section.id})

    def test_mine_is_a_silent_no_op_for_a_student(self):
        response = self.client.get(reverse("api:section-list"), {"mine": "true"})
        ids = {s["id"] for s in response.json()["results"]}
        self.assertIn(self.other_section.id, ids)


class SectionRegisterTests(ApiTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)

    def test_registers_the_student(self):
        response = self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], EnrollmentStatus.ENROLLED)
        self.assertTrue(
            Enrollment.objects.filter(student=self.student, section=self.section).exists()
        )

    def test_waitlists_once_the_section_is_full(self):
        self.client.post(reverse("api:section-register", args=[self.section.pk]))  # capacity=2
        self.client.force_login(self.second_student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))

        self.client.force_login(self.third_student.user)
        response = self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.assertEqual(response.json()["status"], EnrollmentStatus.WAITLISTED)
        self.assertEqual(response.json()["waitlist_position"], 1)

    def test_lecturer_cannot_register(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.assertEqual(response.status_code, 403)


class SectionRosterTests(ApiTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))  # capacity=2
        self.client.force_login(self.second_student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.client.force_login(self.third_student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))  # waitlisted

    def test_owning_lecturer_sees_enrolled_and_waitlisted(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.get(reverse("api:section-roster", args=[self.section.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["enrolled"]), 2)
        self.assertEqual(len(body["waitlisted"]), 1)

    def test_a_different_lecturer_gets_not_found(self):
        self.client.force_login(self.other_lecturer_user)
        response = self.client.get(reverse("api:section-roster", args=[self.section.pk]))
        self.assertEqual(response.status_code, 404)

    def test_a_student_cannot_reach_the_roster(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("api:section-roster", args=[self.section.pk]))
        self.assertEqual(response.status_code, 403)
