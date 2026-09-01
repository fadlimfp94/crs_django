"""
Tests for the ``Enrollment`` model's database-level guarantees.

These are the last line of defence when a service-layer check is missed, so
each constraint gets its own test, matching the convention set in
``academics.tests.test_models``.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from registration.models import Enrollment, EnrollmentStatus

from .factories import make_course, make_department, make_section, make_student, make_term


class EnrollmentTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = make_department()
        cls.course = make_course(cls.department, "CS101")
        cls.term = make_term()
        cls.section = make_section(cls.course, cls.term)
        cls.student = make_student()


class UniqueConstraintTests(EnrollmentTestCase):
    def test_one_row_per_student_and_section(self):
        Enrollment.objects.create(
            student=self.student,
            section=self.section,
            status=EnrollmentStatus.ENROLLED,
            registered_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    student=self.student,
                    section=self.section,
                    status=EnrollmentStatus.DROPPED,
                    dropped_at=timezone.now(),
                    registered_at=timezone.now(),
                )


class WaitlistPositionConstraintTests(EnrollmentTestCase):
    def test_waitlisted_without_a_position_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    student=self.student,
                    section=self.section,
                    status=EnrollmentStatus.WAITLISTED,
                    waitlist_position=None,
                    registered_at=timezone.now(),
                )

    def test_enrolled_with_a_position_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    student=self.student,
                    section=self.section,
                    status=EnrollmentStatus.ENROLLED,
                    waitlist_position=1,
                    registered_at=timezone.now(),
                )

    def test_waitlisted_with_a_position_is_accepted(self):
        enrollment = Enrollment.objects.create(
            student=self.student,
            section=self.section,
            status=EnrollmentStatus.WAITLISTED,
            waitlist_position=1,
            registered_at=timezone.now(),
        )
        self.assertEqual(enrollment.waitlist_position, 1)


class GradeConstraintTests(EnrollmentTestCase):
    def test_grade_without_completed_status_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    student=self.student,
                    section=self.section,
                    status=EnrollmentStatus.ENROLLED,
                    grade="A",
                    registered_at=timezone.now(),
                )

    def test_completed_with_a_grade_is_accepted(self):
        enrollment = Enrollment.objects.create(
            student=self.student,
            section=self.section,
            status=EnrollmentStatus.COMPLETED,
            grade="A",
            registered_at=timezone.now(),
        )
        self.assertEqual(enrollment.grade, "A")

    def test_completed_without_a_grade_is_accepted(self):
        """Not every historical record need carry a grade (e.g. audited)."""
        enrollment = Enrollment.objects.create(
            student=self.student,
            section=self.section,
            status=EnrollmentStatus.COMPLETED,
            registered_at=timezone.now(),
        )
        self.assertEqual(enrollment.grade, "")


class ProtectedForeignKeyTests(EnrollmentTestCase):
    def test_deleting_a_student_with_enrollments_is_protected(self):
        Enrollment.objects.create(
            student=self.student,
            section=self.section,
            status=EnrollmentStatus.ENROLLED,
            registered_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError):
            self.student.delete()

    def test_deleting_a_section_with_enrollments_is_protected(self):
        Enrollment.objects.create(
            student=self.student,
            section=self.section,
            status=EnrollmentStatus.ENROLLED,
            registered_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError):
            self.section.delete()


class StrTests(EnrollmentTestCase):
    def test_str_shows_student_section_and_status(self):
        enrollment = Enrollment.objects.create(
            student=self.student,
            section=self.section,
            status=EnrollmentStatus.ENROLLED,
            registered_at=timezone.now(),
        )
        text = str(enrollment)
        self.assertIn(str(self.student), text)
        self.assertIn(str(self.section), text)
        self.assertIn("Enrolled", text)
