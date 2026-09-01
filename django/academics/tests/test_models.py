"""
Tests for the catalogue models.

Focus on the two things Phase 3 will lean on and Phase 2 must therefore get
right: the database-level constraints (which are the last line of defence when a
service-layer check is missed) and the clash-detection helpers behind rule R5.
"""

from datetime import date, time, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from academics.grades import Grade
from academics.models import (
    Course,
    DayOfWeek,
    Department,
    Meeting,
    PrerequisiteRule,
    Program,
    Section,
    Term,
    time_ranges_overlap,
)
from accounts.models import LecturerTitle, StudentStatus, User


def make_term(code="2026-FALL", *, opens_days=-1, closes_days=+1, **extra) -> Term:
    now = timezone.now()
    defaults = {
        "name": code,
        "start_date": date(2026, 9, 7),
        "end_date": date(2027, 1, 15),
        "registration_opens_at": now + timedelta(days=opens_days),
        "registration_closes_at": now + timedelta(days=closes_days),
    }
    defaults.update(extra)
    return Term.objects.create(code=code, **defaults)


class CatalogueTestCase(TestCase):
    """Shared fixture: one department, one program, two courses, one term."""

    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(code="CS", name="Computer Science")
        cls.program = Program.objects.create(
            code="CS-BSC", name="Bachelor of Computer Science", department=cls.department
        )
        cls.intro = Course.objects.create(
            code="CS101", title="Introduction to Programming", credits=4, department=cls.department
        )
        cls.data_structures = Course.objects.create(
            code="CS201",
            title="Data Structures",
            credits=4,
            level=200,
            department=cls.department,
        )
        cls.term = make_term()


# --------------------------------------------------------------------------- #
# Overlap arithmetic — the core of R5
# --------------------------------------------------------------------------- #


class TimeRangeOverlapTests(SimpleTestCase):
    def test_back_to_back_ranges_do_not_overlap(self):
        """PLAN.md Phase 3 calls this out explicitly: 10–11 and 11–12 must not clash."""
        self.assertFalse(time_ranges_overlap(time(10, 0), time(11, 0), time(11, 0), time(12, 0)))

    def test_genuine_overlap_is_detected(self):
        self.assertTrue(time_ranges_overlap(time(10, 0), time(11, 30), time(11, 0), time(12, 0)))

    def test_identical_ranges_overlap(self):
        self.assertTrue(time_ranges_overlap(time(10, 0), time(11, 0), time(10, 0), time(11, 0)))

    def test_containment_overlaps_in_both_directions(self):
        self.assertTrue(time_ranges_overlap(time(9, 0), time(13, 0), time(10, 0), time(11, 0)))
        self.assertTrue(time_ranges_overlap(time(10, 0), time(11, 0), time(9, 0), time(13, 0)))

    def test_disjoint_ranges_do_not_overlap(self):
        self.assertFalse(time_ranges_overlap(time(8, 0), time(9, 0), time(10, 0), time(11, 0)))

    def test_one_minute_of_overlap_counts(self):
        self.assertTrue(time_ranges_overlap(time(10, 0), time(11, 1), time(11, 0), time(12, 0)))


# --------------------------------------------------------------------------- #
# Department, Program, Course
# --------------------------------------------------------------------------- #


class DepartmentTests(CatalogueTestCase):
    def test_code_is_unique(self):
        with self.assertRaises(IntegrityError):
            Department.objects.create(code="CS", name="Something Else")

    def test_str_shows_code_and_name(self):
        self.assertEqual(str(self.department), "CS — Computer Science")

    def test_lowercase_code_is_rejected_by_validation(self):
        with self.assertRaises(ValidationError):
            Department(code="cs", name="Lowercase").full_clean()


class CourseTests(CatalogueTestCase):
    def test_code_is_unique(self):
        with self.assertRaises(IntegrityError):
            Course.objects.create(
                code="CS101", title="Duplicate", credits=3, department=self.department
            )

    def test_zero_credits_is_rejected_by_the_database(self):
        """`validators` are form-level; the CheckConstraint is what actually holds."""
        with self.assertRaises(IntegrityError):
            Course.objects.create(code="CS000", title="Zero", credits=0, department=self.department)

    def test_label_is_dense_and_readable(self):
        self.assertEqual(self.data_structures.label, "CS201 Data Structures (4 cr)")

    def test_department_cannot_be_deleted_while_courses_reference_it(self):
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.department.delete()


# --------------------------------------------------------------------------- #
# PrerequisiteRule
# --------------------------------------------------------------------------- #


class PrerequisiteRuleTests(CatalogueTestCase):
    def test_rule_links_courses_through_the_m2m(self):
        PrerequisiteRule.objects.create(
            course=self.data_structures, prerequisite=self.intro, minimum_grade=Grade.C
        )
        self.assertIn(self.intro, self.data_structures.prerequisites.all())
        self.assertIn(self.data_structures, self.intro.required_for.all())

    def test_the_same_pair_cannot_be_added_twice(self):
        PrerequisiteRule.objects.create(course=self.data_structures, prerequisite=self.intro)
        with self.assertRaises(IntegrityError):
            PrerequisiteRule.objects.create(course=self.data_structures, prerequisite=self.intro)

    def test_self_reference_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError):
            PrerequisiteRule.objects.create(course=self.intro, prerequisite=self.intro)

    def test_self_reference_is_rejected_by_clean_with_a_readable_message(self):
        rule = PrerequisiteRule(course=self.intro, prerequisite=self.intro)
        with self.assertRaises(ValidationError) as caught:
            rule.clean()
        self.assertIn("own prerequisite", str(caught.exception))

    def test_a_two_step_cycle_is_rejected(self):
        PrerequisiteRule.objects.create(course=self.data_structures, prerequisite=self.intro)

        rule = PrerequisiteRule(course=self.intro, prerequisite=self.data_structures)
        with self.assertRaises(ValidationError) as caught:
            rule.clean()
        self.assertIn("cycle", str(caught.exception))

    def test_a_long_cycle_is_rejected(self):
        """CS101 → CS201 → CS301; closing CS301 → CS101 must fail."""
        third = Course.objects.create(
            code="CS301", title="Databases", credits=4, level=300, department=self.department
        )
        PrerequisiteRule.objects.create(course=self.data_structures, prerequisite=self.intro)
        PrerequisiteRule.objects.create(course=third, prerequisite=self.data_structures)

        rule = PrerequisiteRule(course=self.intro, prerequisite=third)
        with self.assertRaises(ValidationError):
            rule.clean()

    def test_a_diamond_is_not_a_cycle(self):
        """Two courses sharing a prerequisite is legitimate and must be allowed."""
        other = Course.objects.create(
            code="CS210", title="OO Design", credits=3, level=200, department=self.department
        )
        PrerequisiteRule.objects.create(course=self.data_structures, prerequisite=self.intro)

        rule = PrerequisiteRule(course=other, prerequisite=self.intro)
        rule.clean()  # must not raise

    def test_deleting_a_course_that_is_a_prerequisite_is_blocked(self):
        from django.db.models import ProtectedError

        PrerequisiteRule.objects.create(course=self.data_structures, prerequisite=self.intro)
        with self.assertRaises(ProtectedError):
            self.intro.delete()

    def test_deleting_a_course_removes_its_own_rules(self):
        PrerequisiteRule.objects.create(course=self.data_structures, prerequisite=self.intro)
        self.data_structures.delete()
        self.assertEqual(PrerequisiteRule.objects.count(), 0)


# --------------------------------------------------------------------------- #
# Term
# --------------------------------------------------------------------------- #


class TermWindowTests(TestCase):
    def test_window_is_open_between_the_two_timestamps(self):
        term = make_term(opens_days=-1, closes_days=+1)
        self.assertTrue(term.registration_is_open)
        self.assertFalse(term.registration_has_closed)
        self.assertEqual(str(term.registration_status), "Open")

    def test_window_not_yet_open(self):
        term = make_term(opens_days=+1, closes_days=+2)
        self.assertFalse(term.registration_is_open)
        self.assertFalse(term.registration_has_closed)
        self.assertEqual(str(term.registration_status), "Not yet open")

    def test_window_already_closed(self):
        term = make_term(opens_days=-2, closes_days=-1)
        self.assertFalse(term.registration_is_open)
        self.assertTrue(term.registration_has_closed)
        self.assertEqual(str(term.registration_status), "Closed")

    def test_the_instant_the_window_opens_counts_as_open(self):
        """R1 is inclusive at both ends; Phase 3 tests the boundary to the second."""
        now = timezone.now()
        term = make_term()
        term.registration_opens_at = now
        term.registration_closes_at = now + timedelta(days=1)
        self.assertTrue(term.registration_is_open)


class TermConstraintTests(TestCase):
    def test_end_date_must_follow_start_date(self):
        with self.assertRaises(IntegrityError):
            make_term(end_date=date(2026, 1, 1))

    def test_registration_must_close_after_it_opens(self):
        with self.assertRaises(IntegrityError):
            make_term(opens_days=+5, closes_days=+1)

    def test_only_one_term_may_be_current(self):
        make_term("2026-SPRING", is_active=True)
        with self.assertRaises(IntegrityError):
            make_term("2026-FALL", is_active=True)

    def test_many_terms_may_be_non_current(self):
        make_term("2026-SPRING", is_active=False)
        make_term("2026-FALL", is_active=False)
        self.assertEqual(Term.objects.filter(is_active=False).count(), 2)

    def test_code_is_unique(self):
        make_term("2026-FALL")
        with self.assertRaises(IntegrityError):
            make_term("2026-FALL")


# --------------------------------------------------------------------------- #
# Section
# --------------------------------------------------------------------------- #


class SectionTests(CatalogueTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.lecturer_user = User.objects.create_lecturer(
            "L-1001",
            "l@crs.test",
            "pw",
            first_name="Budi",
            last_name="Santoso",
            title=LecturerTitle.PROFESSOR,
        )
        cls.lecturer = cls.lecturer_user.lecturer_profile

    def test_str_identifies_course_section_and_term(self):
        section = Section.objects.create(
            course=self.intro, term=self.term, section_code="01", capacity=40
        )
        self.assertEqual(str(section), "CS101-01 (2026-FALL)")

    def test_section_code_is_unique_within_a_course_and_term(self):
        Section.objects.create(course=self.intro, term=self.term, section_code="01", capacity=40)
        with self.assertRaises(IntegrityError):
            Section.objects.create(
                course=self.intro, term=self.term, section_code="01", capacity=30
            )

    def test_the_same_section_code_is_fine_in_a_different_term(self):
        other_term = make_term("2027-SPRING")
        Section.objects.create(course=self.intro, term=self.term, section_code="01", capacity=40)
        Section.objects.create(course=self.intro, term=other_term, section_code="01", capacity=40)
        self.assertEqual(Section.objects.filter(section_code="01").count(), 2)

    def test_zero_capacity_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError):
            Section.objects.create(course=self.intro, term=self.term, section_code="01", capacity=0)

    def test_credits_come_from_the_course(self):
        section = Section.objects.create(
            course=self.intro, term=self.term, section_code="01", capacity=40
        )
        self.assertEqual(section.credits, self.intro.credits)

    def test_lecturer_name_falls_back_when_unassigned(self):
        section = Section.objects.create(
            course=self.intro, term=self.term, section_code="01", capacity=40
        )
        self.assertEqual(str(section.lecturer_name), "To be announced")

    def test_lecturer_name_uses_the_display_name(self):
        section = Section.objects.create(
            course=self.intro,
            term=self.term,
            section_code="01",
            capacity=40,
            lecturer=self.lecturer,
        )
        self.assertEqual(section.lecturer_name, "Budi Santoso")

    def test_deleting_a_lecturer_leaves_the_section_as_to_be_announced(self):
        """SET_NULL, not CASCADE — a staff departure must not delete teaching."""
        section = Section.objects.create(
            course=self.intro,
            term=self.term,
            section_code="01",
            capacity=40,
            lecturer=self.lecturer,
        )
        self.lecturer_user.delete()
        section.refresh_from_db()
        self.assertIsNone(section.lecturer)


class SectionClashTests(CatalogueTestCase):
    def setUp(self):
        self.a = Section.objects.create(
            course=self.intro, term=self.term, section_code="01", capacity=40
        )
        self.b = Section.objects.create(
            course=self.data_structures, term=self.term, section_code="01", capacity=40
        )

    def test_sections_meeting_at_the_same_time_clash(self):
        Meeting.objects.create(
            section=self.a,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        Meeting.objects.create(
            section=self.b,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(11, 0),
            end_time=time(12, 40),
        )
        self.assertTrue(self.a.clashes_with(self.b))
        self.assertTrue(self.b.clashes_with(self.a))

    def test_back_to_back_sections_do_not_clash(self):
        Meeting.objects.create(
            section=self.a,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        Meeting.objects.create(
            section=self.b,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        self.assertFalse(self.a.clashes_with(self.b))

    def test_the_same_time_on_different_days_does_not_clash(self):
        Meeting.objects.create(
            section=self.a,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        Meeting.objects.create(
            section=self.b,
            day_of_week=DayOfWeek.TUESDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        self.assertFalse(self.a.clashes_with(self.b))

    def test_a_clash_on_only_the_second_meeting_is_still_a_clash(self):
        """The helper must check every pair, not just the first."""
        for day in (DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY):
            Meeting.objects.create(
                section=self.a, day_of_week=day, start_time=time(8, 0), end_time=time(9, 40)
            )
        Meeting.objects.create(
            section=self.b,
            day_of_week=DayOfWeek.WEDNESDAY,
            start_time=time(9, 0),
            end_time=time(10, 40),
        )
        self.assertTrue(self.a.clashes_with(self.b))

    def test_a_section_without_meetings_clashes_with_nothing(self):
        Meeting.objects.create(
            section=self.b,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        self.assertFalse(self.a.clashes_with(self.b))


# --------------------------------------------------------------------------- #
# Meeting
# --------------------------------------------------------------------------- #


class MeetingTests(CatalogueTestCase):
    def setUp(self):
        self.section = Section.objects.create(
            course=self.intro, term=self.term, section_code="01", capacity=40
        )

    def test_str_reads_like_a_timetable_entry(self):
        meeting = Meeting.objects.create(
            section=self.section,
            day_of_week=DayOfWeek.WEDNESDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
            room="IT-101",
        )
        self.assertEqual(str(meeting), "Wednesday 10:00–11:40 in IT-101")

    def test_str_omits_a_blank_room(self):
        meeting = Meeting.objects.create(
            section=self.section,
            day_of_week=DayOfWeek.WEDNESDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        self.assertEqual(str(meeting), "Wednesday 10:00–11:40")

    def test_monday_is_zero_matching_python_weekday(self):
        """Phase 4's weekly grid indexes by this, so the convention must hold."""
        self.assertEqual(DayOfWeek.MONDAY, date(2026, 9, 7).weekday())

    def test_end_before_start_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError):
            Meeting.objects.create(
                section=self.section,
                day_of_week=DayOfWeek.MONDAY,
                start_time=time(11, 0),
                end_time=time(10, 0),
            )

    def test_end_equal_to_start_is_rejected(self):
        with self.assertRaises(IntegrityError):
            Meeting.objects.create(
                section=self.section,
                day_of_week=DayOfWeek.MONDAY,
                start_time=time(10, 0),
                end_time=time(10, 0),
            )

    def test_end_before_start_is_rejected_by_clean(self):
        meeting = Meeting(
            section=self.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(11, 0),
            end_time=time(10, 0),
        )
        with self.assertRaises(ValidationError) as caught:
            meeting.clean()
        self.assertIn("end_time", caught.exception.message_dict)

    def test_the_same_slot_cannot_be_recorded_twice_for_one_section(self):
        Meeting.objects.create(
            section=self.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        with self.assertRaises(IntegrityError):
            Meeting.objects.create(
                section=self.section,
                day_of_week=DayOfWeek.MONDAY,
                start_time=time(10, 0),
                end_time=time(12, 0),
            )

    def test_a_section_cannot_meet_twice_at_overlapping_times(self):
        """Not expressible as a constraint, so clean() carries it."""
        Meeting.objects.create(
            section=self.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        clashing = Meeting(
            section=self.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(11, 0),
            end_time=time(12, 40),
        )
        with self.assertRaises(ValidationError):
            clashing.clean()

    def test_a_section_may_meet_back_to_back_on_the_same_day(self):
        Meeting.objects.create(
            section=self.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        adjacent = Meeting(
            section=self.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        adjacent.clean()  # must not raise

    def test_editing_a_meeting_does_not_clash_with_itself(self):
        meeting = Meeting.objects.create(
            section=self.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        meeting.end_time = time(12, 0)
        meeting.clean()  # must not raise

    def test_deleting_a_section_deletes_its_meetings(self):
        Meeting.objects.create(
            section=self.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
        )
        self.section.delete()
        self.assertEqual(Meeting.objects.count(), 0)


# --------------------------------------------------------------------------- #
# The FKs deferred out of Phase 1
# --------------------------------------------------------------------------- #


class DeferredProfileForeignKeyTests(CatalogueTestCase):
    def test_a_student_can_be_placed_on_a_program(self):
        user = User.objects.create_student(
            "2026001", "s@crs.test", "pw", program=self.program, status=StudentStatus.ACTIVE
        )
        self.assertEqual(user.student_profile.program, self.program)
        self.assertIn(user.student_profile, self.program.students.all())

    def test_a_lecturer_can_be_placed_in_a_department(self):
        user = User.objects.create_lecturer(
            "L-1001", "l@crs.test", "pw", department=self.department
        )
        self.assertEqual(user.lecturer_profile.department, self.department)
        self.assertIn(user.lecturer_profile, self.department.lecturers.all())

    def test_both_are_optional(self):
        student = User.objects.create_student("2026002", "s2@crs.test", "pw")
        lecturer = User.objects.create_lecturer("L-1002", "l2@crs.test", "pw")
        self.assertIsNone(student.student_profile.program)
        self.assertIsNone(lecturer.lecturer_profile.department)

    def test_a_program_with_students_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        User.objects.create_student("2026003", "s3@crs.test", "pw", program=self.program)
        with transaction.atomic(), self.assertRaises(ProtectedError):
            self.program.delete()
