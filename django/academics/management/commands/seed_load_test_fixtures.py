"""
Layer fixtures for the registration-endpoint load sanity check on top of
``seed_demo_data`` only.

    python manage.py seed_load_test_fixtures

Must run *after* ``seed_demo_data`` — it looks up the active Fall term the
same way ``seed_e2e_fixtures`` does. Creates one small-capacity section and a
batch of dedicated, ACTIVE students, each minted a DRF auth token, so
``scripts/load_test_registration.py`` can fire real concurrent HTTP
registration requests without needing to log each one in through a form
first.

This is never run against the dev database or during ``manage.py test`` —
only by ``scripts/load_test_registration.py`` against a disposable, temp-file
SQLite database. Like the other seed commands, it refuses to run outside
``DEBUG`` unless ``--force`` is passed, and every row is upserted on its
natural key so re-running converges rather than duplicating.
"""

from datetime import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.authtoken.models import Token

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
from accounts.models import Role, StudentProfile, StudentStatus, User

DEPARTMENT = ("LOADTEST", "Load Test Fixtures")
PROGRAM = ("LOADTEST-BSC", "Load Test Fixture Program", "LOADTEST", DegreeLevel.BACHELOR, 144)
COURSE = ("LOAD101", "Load Test Fixture", 3)
SECTION_CAPACITY = 10
STUDENT_COUNT = 40

MEETING_START = time(6, 0)
MEETING_END = time(6, 40)


class Command(BaseCommand):
    help = "Layer registration load-test fixtures on top of seed_demo_data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Password for every seeded account (default: {DEFAULT_PASSWORD!r}).",
        )
        parser.add_argument(
            "--students",
            type=int,
            default=STUDENT_COUNT,
            help=f"Number of dedicated students to seed (default: {STUDENT_COUNT}).",
        )
        parser.add_argument(
            "--capacity",
            type=int,
            default=SECTION_CAPACITY,
            help=f"Capacity of the fixture section (default: {SECTION_CAPACITY}).",
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
        except Term.DoesNotExist as exc:
            raise CommandError(
                "seed_load_test_fixtures must run after seed_demo_data — "
                "the Fall term doesn't exist yet."
            ) from exc

        password = options["password"]
        student_count = options["students"]
        capacity = options["capacity"]

        department = self._seed_department()
        program = self._seed_program(department)
        section = self._seed_section(department, term, capacity)
        students = self._seed_students(program, password, student_count)
        tokens = self._seed_tokens(students)

        self.stdout.write(self.style.MIGRATE_HEADING("Load test fixtures"))
        self.stdout.write(f"  section {section}  capacity={capacity}")
        self.stdout.write(f"  {len(students):>4}  students, {len(tokens):>4} tokens")

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

    def _seed_section(self, department: Department, term: Term, capacity: int) -> Section:
        code, title, credits = COURSE
        course, _created = Course.objects.update_or_create(
            code=code,
            defaults={
                "title": title,
                "credits": credits,
                "level": 100,
                "department": department,
                "is_active": True,
                "description": f"{title}. A load-test-only fixture.",
            },
        )
        # No lecturer needed — nothing in the load test touches roster views.
        section, _created = Section.objects.update_or_create(
            course=course,
            term=term,
            section_code="01",
            defaults={"capacity": capacity},
        )
        Meeting.objects.update_or_create(
            section=section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=MEETING_START,
            defaults={"end_time": MEETING_END, "room": "LOAD-101"},
        )
        return section

    def _seed_students(self, program: Program, password: str, count: int) -> list[StudentProfile]:
        result = []
        for i in range(1, count + 1):
            username = f"load-{i:03d}"
            user, _created = User.objects.update_or_create(
                username=username,
                defaults={
                    "first_name": "Load",
                    "last_name": f"Test{i:03d}",
                    "email": f"{username}@crs.test",
                    "role": Role.STUDENT,
                    "is_active": True,
                },
            )
            user.set_password(password)
            user.save(update_fields=["password"])
            profile, _created = StudentProfile.objects.update_or_create(
                user=user,
                defaults={
                    "student_number": username,
                    "enrollment_year": 2026,
                    "status": StudentStatus.ACTIVE,
                    "program": program,
                },
            )
            result.append(profile)
        return result

    def _seed_tokens(self, students: list[StudentProfile]) -> list[str]:
        tokens = []
        for student in students:
            token, _created = Token.objects.get_or_create(user=student.user)
            tokens.append(token.key)
        return tokens
