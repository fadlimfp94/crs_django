"""
Tests for ``seed_demo_data``.

Phase 2's "done when" is that the command populates a browsable catalogue from a
clean database *and* is idempotent, so both halves are asserted here. The
invariant tests matter beyond the seed itself: a lecturer or room booked twice at
once would make the Phase 6 timetable assertions meaningless.
"""

from collections import Counter, defaultdict
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from academics.grades import Grade
from academics.management.commands.seed_demo_data import (
    CLASS_SLOTS,
    COURSES,
    DEPARTMENTS,
    LECTURERS,
    PREREQUISITES,
    PROGRAMS,
    STUDENTS,
    WEEKDAYS,
)
from academics.models import (
    Course,
    Department,
    Meeting,
    PrerequisiteRule,
    Program,
    Section,
    Term,
)
from accounts.models import LecturerProfile, StudentProfile, StudentStatus, User


def seed(**options) -> str:
    """
    Run the command and return its output.

    ``force=True`` by default: Django forces ``DEBUG=False`` for the duration of
    a test run whatever the settings module says, so the command's own
    well-known-password guard would otherwise refuse every call. The guard
    itself is tested explicitly in ``SafetyGuardTests``.
    """
    options.setdefault("force", True)
    out = StringIO()
    call_command("seed_demo_data", stdout=out, **options)
    return out.getvalue()


class SeedFromCleanDatabaseTests(TestCase):
    """One seeding run, many assertions — the command is slow to run per test."""

    @classmethod
    def setUpTestData(cls):
        cls.output = seed()

    def test_the_declared_dataset_is_what_lands(self):
        self.assertEqual(Department.objects.count(), len(DEPARTMENTS))
        self.assertEqual(Program.objects.count(), len(PROGRAMS))
        self.assertEqual(Course.objects.count(), len(COURSES))
        self.assertEqual(PrerequisiteRule.objects.count(), len(PREREQUISITES))
        self.assertEqual(Term.objects.count(), 2)

    def test_the_plan_calls_for_four_departments_and_thirty_courses(self):
        self.assertEqual(Department.objects.count(), 4)
        self.assertEqual(Course.objects.count(), 30)

    def test_about_fifty_sections_exist(self):
        self.assertGreaterEqual(Section.objects.count(), 45)

    def test_every_section_has_at_least_one_meeting(self):
        without = [str(s) for s in Section.objects.filter(meetings__isnull=True)]
        self.assertEqual(without, [])

    def test_exactly_one_term_is_open_and_one_is_closed(self):
        statuses = Counter(str(term.registration_status) for term in Term.objects.all())
        self.assertEqual(statuses["Open"], 1)
        self.assertEqual(statuses["Closed"], 1)

    def test_exactly_one_term_is_current(self):
        self.assertEqual(Term.objects.filter(is_active=True).count(), 1)
        self.assertEqual(Term.objects.get(is_active=True).code, "2026-FALL")

    def test_people_are_created_with_profiles(self):
        self.assertEqual(LecturerProfile.objects.count(), len(LECTURERS))
        self.assertEqual(StudentProfile.objects.count(), len(STUDENTS))

    def test_every_lecturer_has_a_department_and_every_student_a_program(self):
        self.assertFalse(LecturerProfile.objects.filter(department__isnull=True).exists())
        self.assertFalse(StudentProfile.objects.filter(program__isnull=True).exists())

    def test_students_span_several_academic_standings(self):
        """Rule R7 needs someone to reject, not just someone to accept."""
        standings = set(StudentProfile.objects.values_list("status", flat=True))
        self.assertIn(StudentStatus.ACTIVE, standings)
        self.assertGreater(len(standings), 1)
        self.assertTrue(
            StudentProfile.objects.exclude(status=StudentStatus.ACTIVE).exists(),
            "no student exists that R7 would turn away",
        )

    def test_the_baseline_test_accounts_still_exist(self):
        for username in ("2026001", "L-1001", "admin"):
            with self.subTest(username=username):
                self.assertTrue(User.objects.filter(username=username).exists())

    def test_the_administrator_can_reach_the_admin_site(self):
        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_staff)

    def test_seeded_accounts_can_log_in(self):
        self.assertTrue(
            self.client.login(username="2026001", password="crs-dev-password"),
        )

    def test_output_reports_what_it_did(self):
        self.assertIn("Catalogue ready", self.output)
        self.assertIn("30 courses", self.output)


class PrerequisiteGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def test_the_chain_is_at_least_three_levels_deep(self):
        """PLAN.md Phase 2 asks for depth; R3's recursion is only exercised by it."""
        memo: dict[int, int] = {}

        def depth(course: Course) -> int:
            if course.pk in memo:
                return memo[course.pk]
            parents = [rule.prerequisite for rule in course.prerequisite_rules.all()]
            memo[course.pk] = 1 if not parents else 1 + max(depth(p) for p in parents)
            return memo[course.pk]

        deepest = max(depth(course) for course in Course.objects.all())
        self.assertGreaterEqual(deepest, 4)

    def test_the_named_chain_exists_end_to_end(self):
        for course_code, prereq_code in (
            ("CS201", "CS101"),
            ("CS301", "CS201"),
            ("CS401", "CS301"),
        ):
            with self.subTest(course=course_code):
                self.assertTrue(
                    PrerequisiteRule.objects.filter(
                        course__code=course_code, prerequisite__code=prereq_code
                    ).exists()
                )

    def test_some_rules_demand_better_than_a_bare_pass(self):
        """Otherwise R3's grade comparison is never really tested."""
        self.assertTrue(PrerequisiteRule.objects.exclude(minimum_grade=Grade.D).exists())

    def test_the_graph_is_acyclic(self):
        edges = defaultdict(list)
        for rule in PrerequisiteRule.objects.all():
            edges[rule.course_id].append(rule.prerequisite_id)

        WHITE, GREY, BLACK = 0, 1, 2
        colour: dict[int, int] = defaultdict(int)

        def visit(node: int) -> None:
            colour[node] = GREY
            for child in edges[node]:
                if colour[child] == GREY:
                    self.fail(f"prerequisite cycle reaching course id {child}")
                if colour[child] == WHITE:
                    visit(child)
            colour[node] = BLACK

        for course_id in list(edges):
            if colour[course_id] == WHITE:
                visit(course_id)


class TimetableInvariantTests(TestCase):
    """
    Nobody and nowhere is booked twice.

    The generated timetable is only useful to later phases if it is physically
    possible, and a greedy assignment is exactly the kind of code that silently
    stops being correct when the dataset grows.
    """

    @classmethod
    def setUpTestData(cls):
        seed()

    def test_no_lecturer_teaches_two_sections_at_once(self):
        for term in Term.objects.all():
            bookings = defaultdict(list)
            for meeting in Meeting.objects.filter(section__term=term).select_related("section"):
                if meeting.section.lecturer_id:
                    key = (meeting.section.lecturer_id, meeting.day_of_week, meeting.start_time)
                    bookings[key].append(str(meeting.section))

            doubled = {key: value for key, value in bookings.items() if len(value) > 1}
            self.assertEqual(doubled, {}, f"lecturer double-booked in {term.code}")

    def test_no_room_hosts_two_sections_at_once(self):
        for term in Term.objects.all():
            bookings = defaultdict(list)
            for meeting in Meeting.objects.filter(section__term=term).exclude(room=""):
                key = (meeting.room, meeting.day_of_week, meeting.start_time)
                bookings[key].append(str(meeting.section))

            doubled = {key: value for key, value in bookings.items() if len(value) > 1}
            self.assertEqual(doubled, {}, f"room double-booked in {term.code}")

    def test_no_section_meets_twice_at_the_same_time(self):
        for section in Section.objects.prefetch_related("meetings"):
            meetings = list(section.meetings.all())
            for index, first in enumerate(meetings):
                for second in meetings[index + 1 :]:
                    with self.subTest(section=str(section)):
                        self.assertFalse(first.overlaps(second))

    def test_every_meeting_sits_on_the_published_grid(self):
        valid_times = set(CLASS_SLOTS)
        valid_days = set(WEEKDAYS)
        for meeting in Meeting.objects.all():
            with self.subTest(meeting=str(meeting)):
                self.assertIn((meeting.start_time, meeting.end_time), valid_times)
                self.assertIn(meeting.day_of_week, valid_days)

    def test_four_credit_courses_meet_twice_a_week(self):
        for section in Section.objects.select_related("course").prefetch_related("meetings"):
            expected = 2 if section.course.credits >= 4 else 1
            with self.subTest(section=str(section)):
                self.assertEqual(section.meetings.count(), expected)


class IdempotencyTests(TestCase):
    def test_running_twice_changes_nothing(self):
        seed()
        before = self._snapshot()

        second_run = seed()

        self.assertEqual(self._snapshot(), before)
        self.assertIn("0  meetings created", second_run)

    def test_running_three_times_still_changes_nothing(self):
        seed()
        seed()
        before = self._snapshot()
        seed()
        self.assertEqual(self._snapshot(), before)

    def test_a_hand_edited_timetable_survives_a_re_run(self):
        """Idempotent must not mean destructive — admin edits are kept."""
        seed()
        meeting = Meeting.objects.first()
        meeting.room = "HAND-EDITED"
        meeting.save(update_fields=["room"])

        seed()

        meeting.refresh_from_db()
        self.assertEqual(meeting.room, "HAND-EDITED")

    def test_a_deleted_section_is_recreated(self):
        seed()
        Section.objects.get(
            course__code="CS101", section_code="01", term__code="2026-FALL"
        ).delete()

        seed()

        section = Section.objects.get(
            course__code="CS101", section_code="01", term__code="2026-FALL"
        )
        self.assertTrue(section.meetings.exists())

    @staticmethod
    def _snapshot() -> dict[str, int]:
        return {
            model.__name__: model.objects.count()
            for model in (
                Department,
                Program,
                Course,
                PrerequisiteRule,
                Term,
                Section,
                Meeting,
                User,
                StudentProfile,
                LecturerProfile,
            )
        }


class SafetyGuardTests(TestCase):
    """
    Note the asymmetry: these call ``call_command`` directly rather than the
    ``seed`` helper, because the helper's ``force=True`` is exactly what is under
    test here.
    """

    @override_settings(DEBUG=False)
    def test_it_refuses_to_run_outside_debug(self):
        with self.assertRaises(CommandError) as caught:
            call_command("seed_demo_data", stdout=StringIO())
        self.assertIn("well-known passwords", str(caught.exception))
        self.assertEqual(Course.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_it_runs_without_force_when_debug_is_on(self):
        call_command("seed_demo_data", stdout=StringIO())
        self.assertEqual(Course.objects.count(), len(COURSES))

    @override_settings(DEBUG=False)
    def test_force_overrides_the_guard(self):
        call_command("seed_demo_data", force=True, stdout=StringIO())
        self.assertEqual(Course.objects.count(), len(COURSES))

    def test_a_custom_password_is_honoured(self):
        seed(password="something-else")
        self.assertTrue(self.client.login(username="2026001", password="something-else"))
