"""
Enrollment scoping and the drop/grade/override actions — including the
explicit authorisation requirement that student A cannot read or modify
student B's enrollments.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import LecturerTitle, StudentStatus, User
from registration.models import Enrollment, EnrollmentStatus
from registration.tests.factories import (
    make_course,
    make_department,
    make_section,
    make_student,
    make_term,
)

PASSWORD = "test-password"


class EnrollmentTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = make_department()
        cls.term = make_term(is_active=True)
        cls.course = make_course(cls.department, "CS101")
        cls.lecturer_user = User.objects.create_lecturer(
            "L-1001", "lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )
        cls.section = make_section(
            cls.course, cls.term, capacity=1, lecturer=cls.lecturer_user.lecturer_profile
        )
        cls.other_lecturer_user = User.objects.create_lecturer(
            "L-1002", "other-lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )
        cls.admin = User.objects.create_superuser("admin", "admin@crs.test", PASSWORD)
        cls.student = make_student()
        cls.other_student = make_student()


class EnrollmentScopingTests(EnrollmentTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.enrollment = Enrollment.objects.get(student=self.student, section=self.section)

    def test_student_sees_only_their_own_enrollments(self):
        response = self.client.get(reverse("api:enrollment-list"))
        ids = {e["id"] for e in response.json()["results"]}
        self.assertEqual(ids, {self.enrollment.id})

    def test_student_a_cannot_read_student_bs_enrollment(self):
        self.client.force_login(self.other_student.user)
        response = self.client.get(reverse("api:enrollment-detail", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 404)

    def test_student_a_cannot_drop_student_bs_enrollment(self):
        self.client.force_login(self.other_student.user)
        response = self.client.post(reverse("api:enrollment-drop", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 404)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, EnrollmentStatus.ENROLLED)

    def test_lecturer_sees_no_enrollments_via_this_endpoint(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.get(reverse("api:enrollment-list"))
        self.assertEqual(response.json()["results"], [])

    def test_administrator_sees_every_enrollment(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("api:enrollment-list"))
        ids = {e["id"] for e in response.json()["results"]}
        self.assertEqual(ids, {self.enrollment.id})


class EnrollmentDropTests(EnrollmentTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.enrollment = Enrollment.objects.get(student=self.student, section=self.section)

    def test_drop_promotes_the_next_waitlisted_student(self):
        self.client.force_login(self.other_student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))
        waitlisted = Enrollment.objects.get(student=self.other_student, section=self.section)
        self.assertEqual(waitlisted.status, EnrollmentStatus.WAITLISTED)

        self.client.force_login(self.student.user)
        response = self.client.post(reverse("api:enrollment-drop", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 200)

        waitlisted.refresh_from_db()
        self.assertEqual(waitlisted.status, EnrollmentStatus.ENROLLED)


class EnrollmentGradeTests(EnrollmentTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))
        self.enrollment = Enrollment.objects.get(student=self.student, section=self.section)

    def test_lecturer_can_grade_an_enrolled_student(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.post(
            reverse("api:enrollment-grade", args=[self.enrollment.pk]), {"grade": "A"}
        )
        self.assertEqual(response.status_code, 200)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, EnrollmentStatus.COMPLETED)
        self.assertEqual(self.enrollment.grade, "A")

    def test_grading_a_waitlisted_enrollment_is_rejected(self):
        self.client.force_login(self.other_student.user)
        self.client.post(reverse("api:section-register", args=[self.section.pk]))
        waitlisted = Enrollment.objects.get(student=self.other_student, section=self.section)

        self.client.force_login(self.lecturer_user)
        response = self.client.post(
            reverse("api:enrollment-grade", args=[waitlisted.pk]), {"grade": "A"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["rule"], None)

    def test_a_different_lecturer_gets_not_found(self):
        self.client.force_login(self.other_lecturer_user)
        response = self.client.post(
            reverse("api:enrollment-grade", args=[self.enrollment.pk]), {"grade": "A"}
        )
        self.assertEqual(response.status_code, 404)


class EnrollmentOverrideTests(EnrollmentTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_can_override_a_students_bad_standing(self):
        suspended_student = make_student(status=StudentStatus.SUSPENDED)
        response = self.client.post(
            reverse("api:enrollment-override"),
            {"student": suspended_student.pk, "section": self.section.pk},
        )
        self.assertEqual(response.status_code, 201)
        enrollment = Enrollment.objects.get(student=suspended_student, section=self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)

    def test_override_still_waitlists_once_the_section_is_full(self):
        self.client.post(
            reverse("api:enrollment-override"),
            {"student": self.student.pk, "section": self.section.pk},
        )
        response = self.client.post(
            reverse("api:enrollment-override"),
            {"student": self.other_student.pk, "section": self.section.pk},
        )
        self.assertEqual(response.json()["status"], EnrollmentStatus.WAITLISTED)

    def test_student_cannot_reach_the_override_action(self):
        self.client.force_login(self.student.user)
        response = self.client.post(
            reverse("api:enrollment-override"),
            {"student": self.student.pk, "section": self.section.pk},
        )
        self.assertEqual(response.status_code, 403)
