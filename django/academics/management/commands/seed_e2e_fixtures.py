"""
Layer deterministic, hard-to-reach fixtures on top of ``seed_demo_data`` for the
Playwright suite only.

    python manage.py seed_e2e_fixtures

Must run *after* ``seed_demo_data`` — it looks up the active Fall term, the
lecturer ``L-1001``, and re-derives its own program from a dedicated ``E2E``
department rather than duplicating the realistic catalogue.

``seed_demo_data``'s 7 students and 25-60-seat sections are realistic, which
is exactly why they can't cheaply reach a full section, a timetable clash, or
a credit-limit breach without inventing dozens of throwaway registrations.
This command adds a handful of narrow, purpose-built rows instead:

* a capacity=1 section for the waitlist suite (``e2e-wl-1``/``e2e-wl-2``);
* a same-time section pair for rule R5 (``e2e-clash``), pre-registered into
  the first so the Playwright test only has to attempt the second;
* two 12-credit sections plus a third small one for rule R4
  (``e2e-overload``) — ``Course.credits`` is capped at 12
  (``MaxValueValidator(12)``), so no single course can exceed the term's
  24-credit cap alone; two pre-registered 12-credit sections put the student
  exactly at the cap, and the Playwright test's attempt at the third tips it
  over;
* one pre-registered, ungraded enrollment for the lecturer suite
  (``e2e-grademe``).

Rules R1 (closed window), R2 (duplicate), R3 (prerequisite), and R7
(standing) need no new fixtures — they're already reachable from
``seed_demo_data``'s own terms, prerequisite graph, and student standings.

This is never run against the dev database or during ``manage.py test`` —
only by the Playwright server bootstrap (``playwright/utils/global-setup.ts``)
against a disposable, temp-file SQLite database. Like ``seed_demo_data``, it
refuses to run outside ``DEBUG`` unless ``--force`` is passed, and every row
is upserted on its natural key so re-running converges rather than
duplicating.
"""

from datetime import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academics.models import (
    Course,
    DayOfWeek,
    DegreeLevel,
    Department,
    Meeting,
    Program,
    Section,
    Term,
)
from accounts.management.commands.create_test_users import DEFAULT_PASSWORD
from accounts.models import LecturerProfile, Role, StudentProfile, StudentStatus, User
from registration.models import Enrollment
from registration.services import register

DEPARTMENT = ("E2E", "E2E Fixtures")
PROGRAM = ("E2E-BSC", "E2E Fixture Program", "E2E", DegreeLevel.BACHELOR, 144)

# (code, title, credits)
COURSES = [
    ("E2E101", "Waitlist Fixture", 3),
    ("E2E102", "Clash Fixture A", 3),
    ("E2E103", "Clash Fixture B", 3),
    ("E2E104", "Overload Fixture A", 12),
    ("E2E105", "Overload Fixture B", 12),
    ("E2E106", "Overload Fixture C", 3),
    ("E2E107", "Grademe Fixture", 3),
]

# (course code, capacity, day of week) — every meeting runs 07:00-07:40, an
# hour before seed_demo_data's earliest slot, so these can never clash with
# (or be blocked by) any real seeded section or lecturer.
SECTIONS = [
    ("E2E101", 1, DayOfWeek.MONDAY),
    ("E2E102", 30, DayOfWeek.TUESDAY),
    ("E2E103", 30, DayOfWeek.TUESDAY),  # same day/time as E2E102 — the R5 clash pair
    ("E2E104", 30, DayOfWeek.WEDNESDAY),
    ("E2E105", 30, DayOfWeek.THURSDAY),
    ("E2E106", 30, DayOfWeek.FRIDAY),
    ("E2E107", 30, DayOfWeek.MONDAY),
]

MEETING_START = time(7, 0)
MEETING_END = time(7, 40)

# (username, first, last, email) — all E2E-BSC, ACTIVE, enrolled 2026.
STUDENTS = [
    ("e2e-wl-1", "E2E", "WaitlistOne", "e2e-wl-1@crs.test"),
    ("e2e-wl-2", "E2E", "WaitlistTwo", "e2e-wl-2@crs.test"),
    ("e2e-clash", "E2E", "Clash", "e2e-clash@crs.test"),
    ("e2e-overload", "E2E", "Overload", "e2e-overload@crs.test"),
    ("e2e-grademe", "E2E", "Grademe", "e2e-grademe@crs.test"),
]


class Command(BaseCommand):
    help = "Layer E2E-only registration fixtures on top of seed_demo_data, for Playwright only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Password for every seeded account (default: {DEFAULT_PASSWORD!r}).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow seeding when DEBUG is False. Never do this on a real deployment.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed accounts with well-known passwords while DEBUG is False. "
                "Pass --force only if you are certain this is not a real deployment."
            )

        try:
            term = Term.objects.get(code="2026-FALL")
            lecturer = LecturerProfile.objects.get(staff_number="L-1001")
        except (Term.DoesNotExist, LecturerProfile.DoesNotExist) as exc:
            raise CommandError(
                "seed_e2e_fixtures must run after seed_demo_data — the Fall term and "
                "lecturer L-1001 don't exist yet."
            ) from exc

        password = options["password"]

        department = self._seed_department()
        program = self._seed_program(department)
        courses = self._seed_courses(department)
        sections = self._seed_sections(courses, term, lecturer)
        students = self._seed_students(program, password)

        self._preregister(students, sections)

        self.stdout.write(self.style.MIGRATE_HEADING("E2E fixtures"))
        self.stdout.write(f"  {len(courses):>4}  courses")
        self.stdout.write(f"  {len(sections):>4}  sections")
        self.stdout.write(f"  {len(students):>4}  students")

    def _seed_department(self) -> Department:
        code, name = DEPARTMENT
        department, _created = Department.objects.update_or_create(
            code=code, defaults={"name": name}
        )
        return department

    def _seed_program(self, department: Department) -> Program:
        code, name, _dept_code, level, credits_required = PROGRAM
        program, _created = Program.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "department": department,
                "degree_level": level,
                "credits_required": credits_required,
            },
        )
        return program

    def _seed_courses(self, department: Department) -> dict[str, Course]:
        result = {}
        for code, title, credits in COURSES:
            result[code], _created = Course.objects.update_or_create(
                code=code,
                defaults={
                    "title": title,
                    "credits": credits,
                    "level": 100,
                    "department": department,
                    "is_active": True,
                    "description": f"{title}. A Playwright-only fixture, worth {credits} credits.",
                },
            )
        return result

    def _seed_sections(
        self, courses: dict[str, Course], term: Term, lecturer: LecturerProfile
    ) -> dict[str, Section]:
        result = {}
        for course_code, capacity, day in SECTIONS:
            section, _created = Section.objects.update_or_create(
                course=courses[course_code],
                term=term,
                section_code="01",
                defaults={"lecturer": lecturer, "capacity": capacity},
            )
            Meeting.objects.update_or_create(
                section=section,
                day_of_week=day,
                start_time=MEETING_START,
                defaults={"end_time": MEETING_END, "room": f"E2E-{course_code}"},
            )
            result[course_code] = section
        return result

    def _seed_students(self, program: Program, password: str) -> dict[str, StudentProfile]:
        result = {}
        for username, first, last, email in STUDENTS:
            user, _created = User.objects.update_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "role": Role.STUDENT,
                    "is_active": True,
                },
            )
            user.set_password(password)
            user.save(update_fields=["password"])
            result[username], _created = StudentProfile.objects.update_or_create(
                user=user,
                defaults={
                    "student_number": username,
                    "enrollment_year": 2026,
                    "status": StudentStatus.ACTIVE,
                    "program": program,
                },
            )
        return result

    def _preregister(
        self, students: dict[str, StudentProfile], sections: dict[str, Section]
    ) -> None:
        """
        Put each dedicated student into the state its suite needs *before* the
        Playwright test runs, so the test only has to perform the one action
        under test rather than rebuild the precondition through the UI too.
        """
        preconditions = [
            ("e2e-clash", "E2E102"),
            ("e2e-overload", "E2E104"),
            ("e2e-overload", "E2E105"),
            ("e2e-grademe", "E2E107"),
        ]
        for username, course_code in preconditions:
            student = students[username]
            section = sections[course_code]
            if Enrollment.objects.filter(student=student, section=section).exists():
                continue
            register(student, section)
