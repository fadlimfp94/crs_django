"""
Tests for the registration rule engine.

One test class per rule (R1-R7), each with a passing and a failing case, plus
the boundaries PLAN.md calls out explicitly. Then drop/promotion behaviour,
including the skip-and-continue promotion re-check the user chose over
unconditional promotion.
"""

from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import StudentStatus
from registration.models import Enrollment, EnrollmentStatus
from registration.services import RegistrationError, drop, promote_from_waitlist, register

from .factories import (
    make_course,
    make_department,
    make_meeting,
    make_prerequisite,
    make_section,
    make_student,
    make_term,
)


class RegistrationTestCase(TestCase):
    """Shared fixture: one department, one open term, one prerequisite-free course."""

    @classmethod
    def setUpTestData(cls):
        cls.department = make_department()
        cls.term = make_term()
        cls.course = make_course(cls.department, "CS101")
        cls.section = make_section(cls.course, cls.term)
        make_meeting(cls.section)
        cls.student = make_student()


# --------------------------------------------------------------------------- #
# R1 — registration window
# --------------------------------------------------------------------------- #


class RegistrationWindowTests(RegistrationTestCase):
    def test_open_window_allows_registration(self):
        enrollment = register(self.student, self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)

    def test_window_not_yet_open_is_rejected(self):
        term = make_term("2026-SPRING", opens_days=+1, closes_days=+30)
        section = make_section(self.course, term)
        with self.assertRaises(RegistrationError) as ctx:
            register(self.student, section)
        self.assertEqual(ctx.exception.rule, "R1")

    def test_window_closed_a_second_ago_is_rejected(self):
        """The boundary PLAN.md names explicitly: closing is exact to the second."""
        term = make_term("2026-WINTER", opens_days=-10, closes_days=-1)
        term.registration_closes_at = timezone.now() - timedelta(seconds=1)
        term.save(update_fields=["registration_closes_at"])
        section = make_section(self.course, term)
        with self.assertRaises(RegistrationError) as ctx:
            register(self.student, section)
        self.assertEqual(ctx.exception.rule, "R1")

    def test_window_closing_in_a_few_seconds_is_still_open(self):
        term = make_term("2026-SUMMER", opens_days=-2, closes_days=-1)
        term.registration_closes_at = timezone.now() + timedelta(seconds=5)
        term.save(update_fields=["registration_closes_at"])
        section = make_section(self.course, term)
        enrollment = register(self.student, section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)


# --------------------------------------------------------------------------- #
# R2 — no double registration
# --------------------------------------------------------------------------- #


class NoDoubleRegistrationTests(RegistrationTestCase):
    def test_registering_twice_for_the_same_section_is_rejected(self):
        register(self.student, self.section)
        with self.assertRaises(RegistrationError) as ctx:
            register(self.student, self.section)
        self.assertEqual(ctx.exception.rule, "R2")

    def test_registering_for_another_section_of_the_same_course_is_rejected(self):
        other_section = make_section(self.course, self.term, section_code="02")
        make_meeting(other_section, start=time(14, 0), end=time(15, 0))
        register(self.student, self.section)
        with self.assertRaises(RegistrationError) as ctx:
            register(self.student, other_section)
        self.assertEqual(ctx.exception.rule, "R2")

    def test_registering_again_after_dropping_is_allowed(self):
        register(self.student, self.section)
        drop(self.student, self.section)
        enrollment = register(self.student, self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)


# --------------------------------------------------------------------------- #
# R3 — prerequisites
# --------------------------------------------------------------------------- #


class PrerequisiteTests(RegistrationTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.advanced = make_course(cls.department, "CS201")
        make_prerequisite(cls.advanced, cls.course, minimum_grade="C")
        cls.advanced_section = make_section(cls.advanced, cls.term)
        make_meeting(cls.advanced_section, start=time(14, 0), end=time(15, 0))

    def _complete_prerequisite(self, grade):
        Enrollment.objects.create(
            student=self.student,
            section=self.section,
            status=EnrollmentStatus.COMPLETED,
            grade=grade,
            registered_at=timezone.now(),
        )

    def test_missing_prerequisite_is_rejected(self):
        with self.assertRaises(RegistrationError) as ctx:
            register(self.student, self.advanced_section)
        self.assertEqual(ctx.exception.rule, "R3")

    def test_prerequisite_exactly_at_the_minimum_grade_is_accepted(self):
        self._complete_prerequisite("C")
        enrollment = register(self.student, self.advanced_section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)

    def test_prerequisite_one_step_under_the_minimum_grade_is_rejected(self):
        self._complete_prerequisite("C-")
        with self.assertRaises(RegistrationError) as ctx:
            register(self.student, self.advanced_section)
        self.assertEqual(ctx.exception.rule, "R3")

    def test_prerequisite_above_the_minimum_grade_is_accepted(self):
        self._complete_prerequisite("B")
        enrollment = register(self.student, self.advanced_section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)


# --------------------------------------------------------------------------- #
# R4 — credit limit
# --------------------------------------------------------------------------- #


class CreditLimitTests(RegistrationTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = make_department()
        cls.term = make_term(max_credits=8)
        cls.course_a = make_course(cls.department, "CS110", credits=4)
        cls.course_b = make_course(cls.department, "CS120", credits=4)
        cls.course_c = make_course(cls.department, "CS130", credits=1)
        cls.section_a = make_section(cls.course_a, cls.term)
        make_meeting(cls.section_a, start=time(9, 0), end=time(10, 0))
        cls.section_b = make_section(cls.course_b, cls.term)
        make_meeting(cls.section_b, start=time(11, 0), end=time(12, 0))
        cls.section_c = make_section(cls.course_c, cls.term)
        make_meeting(cls.section_c, start=time(13, 0), end=time(14, 0))
        cls.student = make_student()

    def test_credits_exactly_at_the_ceiling_are_accepted(self):
        register(self.student, self.section_a)
        enrollment = register(self.student, self.section_b)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)

    def test_credits_one_over_the_ceiling_are_rejected(self):
        register(self.student, self.section_a)
        register(self.student, self.section_b)
        with self.assertRaises(RegistrationError) as ctx:
            register(self.student, self.section_c)
        self.assertEqual(ctx.exception.rule, "R4")


# --------------------------------------------------------------------------- #
# R5 — timetable clash
# --------------------------------------------------------------------------- #


class TimetableClashTests(RegistrationTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.overlapping = make_course(cls.department, "CS150")
        cls.overlapping_section = make_section(cls.overlapping, cls.term)
        make_meeting(cls.overlapping_section, start=time(10, 30), end=time(11, 30))

        cls.back_to_back = make_course(cls.department, "CS160")
        cls.back_to_back_section = make_section(cls.back_to_back, cls.term)
        make_meeting(cls.back_to_back_section, start=time(11, 0), end=time(12, 0))

    def test_genuinely_overlapping_meetings_are_rejected(self):
        register(self.student, self.section)  # Monday 10:00-11:00
        with self.assertRaises(RegistrationError) as ctx:
            register(self.student, self.overlapping_section)
        self.assertEqual(ctx.exception.rule, "R5")

    def test_back_to_back_meetings_are_accepted(self):
        """PLAN.md calls this out explicitly: 10-11 and 11-12 must not clash."""
        register(self.student, self.section)  # Monday 10:00-11:00
        enrollment = register(self.student, self.back_to_back_section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)


# --------------------------------------------------------------------------- #
# R6 — seat outcome / waitlisting
# --------------------------------------------------------------------------- #


class SeatOutcomeTests(RegistrationTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = make_department()
        cls.term = make_term()
        cls.course = make_course(cls.department, "CS101")
        cls.section = make_section(cls.course, cls.term, capacity=1)
        make_meeting(cls.section)
        cls.first_student = make_student()
        cls.second_student = make_student()
        cls.third_student = make_student()

    def test_last_seat_is_taken_by_the_first_registrant(self):
        enrollment = register(self.first_student, self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)

    def test_the_next_registrant_after_the_last_seat_is_waitlisted(self):
        register(self.first_student, self.section)
        enrollment = register(self.second_student, self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.WAITLISTED)
        self.assertEqual(enrollment.waitlist_position, 1)

    def test_waitlist_positions_are_assigned_in_order(self):
        register(self.first_student, self.section)
        register(self.second_student, self.section)
        third = register(self.third_student, self.section)
        self.assertEqual(third.status, EnrollmentStatus.WAITLISTED)
        self.assertEqual(third.waitlist_position, 2)


# --------------------------------------------------------------------------- #
# R7 — academic standing
# --------------------------------------------------------------------------- #


class GoodStandingTests(RegistrationTestCase):
    def test_active_student_may_register(self):
        enrollment = register(self.student, self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)

    def test_suspended_student_is_rejected(self):
        suspended = make_student(status=StudentStatus.SUSPENDED)
        with self.assertRaises(RegistrationError) as ctx:
            register(suspended, self.section)
        self.assertEqual(ctx.exception.rule, "R7")

    def test_probation_student_is_rejected(self):
        on_probation = make_student(status=StudentStatus.PROBATION)
        with self.assertRaises(RegistrationError) as ctx:
            register(on_probation, self.section)
        self.assertEqual(ctx.exception.rule, "R7")


# --------------------------------------------------------------------------- #
# drop() and promote_from_waitlist()
# --------------------------------------------------------------------------- #


class DropAndPromotionTests(RegistrationTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = make_department()
        cls.term = make_term()
        cls.course = make_course(cls.department, "CS101")
        cls.section = make_section(cls.course, cls.term, capacity=1)
        make_meeting(cls.section)
        cls.first_student = make_student()
        cls.second_student = make_student()
        cls.third_student = make_student()

    def test_dropping_a_section_never_registered_for_is_rejected(self):
        with self.assertRaises(RegistrationError) as ctx:
            drop(self.first_student, self.section)
        self.assertIsNone(ctx.exception.rule)

    def test_dropping_the_enrolled_student_promotes_the_head_of_the_waitlist(self):
        register(self.first_student, self.section)
        register(self.second_student, self.section)

        dropped = drop(self.first_student, self.section)
        self.assertEqual(dropped.status, EnrollmentStatus.DROPPED)

        promoted = Enrollment.objects.get(student=self.second_student, section=self.section)
        self.assertEqual(promoted.status, EnrollmentStatus.ENROLLED)
        self.assertIsNone(promoted.waitlist_position)

    def test_dropping_a_waitlisted_student_renumbers_but_does_not_promote(self):
        register(self.first_student, self.section)
        register(self.second_student, self.section)
        register(self.third_student, self.section)

        drop(self.second_student, self.section)

        still_enrolled = Enrollment.objects.get(student=self.first_student, section=self.section)
        self.assertEqual(still_enrolled.status, EnrollmentStatus.ENROLLED)

        third = Enrollment.objects.get(student=self.third_student, section=self.section)
        self.assertEqual(third.status, EnrollmentStatus.WAITLISTED)
        self.assertEqual(third.waitlist_position, 1)

    def test_promotion_skips_a_candidate_who_now_fails_a_rule(self):
        """
        The user's explicit choice: a promotion candidate who would now fail
        R4/R5/R7 is skipped, not dropped, and the next candidate is tried.
        """
        clashing_course = make_course(self.department, "CS999")
        clashing_section = make_section(clashing_course, self.term)
        make_meeting(clashing_section, start=time(10, 0), end=time(11, 0))

        register(self.first_student, self.section)
        register(self.second_student, self.section)  # waitlist position 1
        register(self.third_student, self.section)  # waitlist position 2

        # second_student now has a clashing commitment that will block their
        # promotion when a seat opens.
        register(self.second_student, clashing_section)

        drop(self.first_student, self.section)

        second = Enrollment.objects.get(student=self.second_student, section=self.section)
        self.assertEqual(second.status, EnrollmentStatus.WAITLISTED)
        self.assertEqual(second.waitlist_position, 1)

        third = Enrollment.objects.get(student=self.third_student, section=self.section)
        self.assertEqual(third.status, EnrollmentStatus.ENROLLED)

    def test_promote_from_waitlist_returns_none_when_seat_is_still_full(self):
        register(self.first_student, self.section)
        register(self.second_student, self.section)
        self.assertIsNone(promote_from_waitlist(self.section))

    def test_promote_from_waitlist_returns_none_when_waitlist_is_empty(self):
        register(self.first_student, self.section)
        self.assertIsNone(promote_from_waitlist(self.section))

    def test_reregistering_the_same_section_reuses_the_same_row(self):
        first = register(self.first_student, self.section)
        drop(self.first_student, self.section)
        second = register(self.first_student, self.section)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Enrollment.objects.filter(student=self.first_student).count(), 1)
