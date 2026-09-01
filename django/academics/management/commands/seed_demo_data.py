"""
Populate a realistic academic catalogue for development, demos, and the E2E suite.

    python manage.py seed_demo_data

Idempotent: every row is keyed on its natural key and upserted, so re-running
converges on the same dataset rather than duplicating or failing. It is
non-destructive — nothing is deleted, and sections that already have meetings
keep them, so hand edits made in the admin survive a re-run.

The dataset (PLAN.md Phase 2):

* 4 departments, 5 degree programs
* 30 courses with a prerequisite chain 4 levels deep
  (CS101 → CS201 → CS301 → CS401)
* 2 terms — Spring 2026 with its registration window closed, Fall 2026 with
  its window open
* ~56 sections with non-overlapping weekly meetings, no lecturer or room
  double-booked
* 9 lecturers and 7 students, the students spanning several academic standings
  so rule R7 has something to reject

These accounts have well-known passwords, so like ``create_test_users`` the
command refuses to run outside DEBUG unless ``--force`` is passed.

**One deliberate non-determinism:** the registration *windows* are computed
relative to ``timezone.now()`` — that is the only way "one term open, one
closed" can stay true however long after seeding you run the app. Everything
else, including the term start and end dates, is fixed.
"""

from collections import defaultdict
from datetime import date, time, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.grades import Grade
from academics.models import (
    Course,
    DayOfWeek,
    DegreeLevel,
    Department,
    Meeting,
    PrerequisiteRule,
    Program,
    Section,
    Term,
)
from accounts.management.commands.create_test_users import DEFAULT_PASSWORD
from accounts.models import (
    LecturerProfile,
    LecturerTitle,
    Role,
    StudentProfile,
    StudentStatus,
    User,
)

# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #

DEPARTMENTS = [
    ("CS", "Computer Science"),
    ("MATH", "Mathematics"),
    ("EE", "Electrical Engineering"),
    ("BUS", "Business Administration"),
]

#: (code, name, department, degree level, credits to graduate)
PROGRAMS = [
    ("CS-BSC", "Bachelor of Computer Science", "CS", DegreeLevel.BACHELOR, 144),
    ("CS-MSC", "Master of Computer Science", "CS", DegreeLevel.MASTER, 40),
    ("MATH-BSC", "Bachelor of Mathematics", "MATH", DegreeLevel.BACHELOR, 144),
    ("EE-BSC", "Bachelor of Electrical Engineering", "EE", DegreeLevel.BACHELOR, 148),
    ("BUS-BBA", "Bachelor of Business Administration", "BUS", DegreeLevel.BACHELOR, 140),
]

#: (code, title, credits, level, department)
COURSES = [
    # Computer Science — 10
    ("CS101", "Introduction to Programming", 4, 100, "CS"),
    ("CS102", "Discrete Structures", 3, 100, "CS"),
    ("CS201", "Data Structures and Algorithms", 4, 200, "CS"),
    ("CS202", "Computer Organisation", 3, 200, "CS"),
    ("CS210", "Object-Oriented Design", 3, 200, "CS"),
    ("CS301", "Database Systems", 4, 300, "CS"),
    ("CS302", "Operating Systems", 4, 300, "CS"),
    ("CS310", "Web Application Development", 3, 300, "CS"),
    ("CS401", "Distributed Systems", 4, 400, "CS"),
    ("CS410", "Machine Learning", 4, 400, "CS"),
    # Mathematics — 7
    ("MATH101", "Calculus I", 4, 100, "MATH"),
    ("MATH102", "Linear Algebra", 3, 100, "MATH"),
    ("MATH201", "Calculus II", 4, 200, "MATH"),
    ("MATH202", "Probability and Statistics", 3, 200, "MATH"),
    ("MATH301", "Numerical Methods", 3, 300, "MATH"),
    ("MATH302", "Real Analysis", 4, 300, "MATH"),
    ("MATH401", "Optimisation", 3, 400, "MATH"),
    # Electrical Engineering — 7
    ("EE101", "Circuit Analysis", 4, 100, "EE"),
    ("EE102", "Digital Logic Design", 3, 100, "EE"),
    ("EE201", "Signals and Systems", 4, 200, "EE"),
    ("EE202", "Microcontroller Systems", 3, 200, "EE"),
    ("EE301", "Embedded Systems", 4, 300, "EE"),
    ("EE302", "Control Systems", 3, 300, "EE"),
    ("EE401", "Communication Systems", 4, 400, "EE"),
    # Business Administration — 6
    ("BUS101", "Principles of Management", 3, 100, "BUS"),
    ("BUS102", "Financial Accounting", 3, 100, "BUS"),
    ("BUS201", "Marketing Management", 3, 200, "BUS"),
    ("BUS202", "Business Statistics", 3, 200, "BUS"),
    ("BUS301", "Operations Management", 3, 300, "BUS"),
    ("BUS401", "Strategic Management", 3, 400, "BUS"),
]

#: (course, prerequisite, minimum grade).
#: The chain CS101 → CS201 → CS301 → CS401 is 4 levels deep, and several rules
#: demand better than a bare pass so rule R3's grade comparison is exercised.
PREREQUISITES = [
    ("CS201", "CS101", Grade.C),
    ("CS201", "CS102", Grade.D),
    ("CS202", "CS101", Grade.D),
    ("CS210", "CS101", Grade.C),
    ("CS301", "CS201", Grade.C),
    ("CS302", "CS201", Grade.D),
    ("CS302", "CS202", Grade.D),
    ("CS310", "CS210", Grade.D),
    ("CS401", "CS301", Grade.B),
    ("CS401", "CS302", Grade.D),
    ("CS410", "CS201", Grade.C),
    ("CS410", "MATH202", Grade.C),
    ("MATH201", "MATH101", Grade.C),
    ("MATH202", "MATH101", Grade.D),
    ("MATH301", "MATH201", Grade.D),
    ("MATH301", "MATH102", Grade.D),
    ("MATH302", "MATH201", Grade.B),
    ("MATH401", "MATH301", Grade.C),
    ("EE201", "EE101", Grade.C),
    ("EE201", "MATH101", Grade.D),
    ("EE202", "EE102", Grade.D),
    ("EE301", "EE202", Grade.C),
    ("EE302", "EE201", Grade.C),
    ("EE401", "EE201", Grade.B),
    ("BUS201", "BUS101", Grade.D),
    ("BUS202", "MATH101", Grade.D),
    ("BUS301", "BUS202", Grade.C),
    ("BUS401", "BUS201", Grade.D),
    ("BUS401", "BUS301", Grade.C),
]

#: (username, first, last, email, department, title)
#: L-1001 is also created by ``create_test_users``; listed here so it picks up a
#: department. The email must match, or the unique-email constraint bites.
LECTURERS = [
    ("L-1001", "Budi", "Santoso", "lecturer@crs.test", "CS", LecturerTitle.ASSOCIATE_PROFESSOR),
    ("L-1002", "Dewi", "Lestari", "dewi.lestari@crs.test", "CS", LecturerTitle.PROFESSOR),
    ("L-1003", "Agus", "Pratama", "agus.pratama@crs.test", "CS", LecturerTitle.ASSISTANT_PROFESSOR),
    ("L-1004", "Rina", "Kusuma", "rina.kusuma@crs.test", "MATH", LecturerTitle.PROFESSOR),
    ("L-1005", "Hendra", "Wibowo", "hendra.wibowo@crs.test", "MATH", LecturerTitle.LECTURER),
    ("L-1006", "Maya", "Sari", "maya.sari@crs.test", "EE", LecturerTitle.ASSOCIATE_PROFESSOR),
    ("L-1007", "Tono", "Nugroho", "tono.nugroho@crs.test", "EE", LecturerTitle.INSTRUCTOR),
    ("L-1008", "Fitri", "Handayani", "fitri.h@crs.test", "BUS", LecturerTitle.ASSOCIATE_PROFESSOR),
    ("L-1009", "Yudi", "Firmansyah", "yudi.f@crs.test", "BUS", LecturerTitle.LECTURER),
]

#: (username, first, last, email, program, enrollment year, standing)
#: The non-ACTIVE students exist so rule R7 has something to reject, and so the
#: Phase 6 suite can assert on the message rather than mutate a fixture.
STUDENTS = [
    ("2026001", "Sinta", "Wijaya", "student@crs.test", "CS-BSC", 2026, StudentStatus.ACTIVE),
    ("2026002", "Rizky", "Ananda", "rizky.ananda@crs.test", "CS-BSC", 2026, StudentStatus.ACTIVE),
    ("2025001", "Putri", "Maharani", "putri.m@crs.test", "CS-BSC", 2025, StudentStatus.ACTIVE),
    ("2025002", "Bayu", "Setiawan", "bayu.s@crs.test", "MATH-BSC", 2025, StudentStatus.PROBATION),
    ("2024001", "Nadia", "Rahmawati", "nadia.r@crs.test", "EE-BSC", 2024, StudentStatus.ACTIVE),
    ("2024002", "Iwan", "Kurniawan", "iwan.k@crs.test", "BUS-BBA", 2024, StudentStatus.SUSPENDED),
    ("2023001", "Lia", "Puspita", "lia.p@crs.test", "CS-BSC", 2023, StudentStatus.GRADUATED),
]

# --------------------------------------------------------------------------- #
# Timetable grid
# --------------------------------------------------------------------------- #

#: A uniform, strictly non-overlapping grid of teaching slots. Uniformity is
#: the point: because no two slots overlap, "is this lecturer free?" reduces to
#: a set lookup on (day, slot index) instead of interval arithmetic.
CLASS_SLOTS = [
    (time(8, 0), time(9, 40)),
    (time(10, 0), time(11, 40)),
    (time(13, 0), time(14, 40)),
    (time(15, 0), time(16, 40)),
]

SLOT_INDEX = {times: index for index, times in enumerate(CLASS_SLOTS)}

WEEKDAYS = [
    DayOfWeek.MONDAY,
    DayOfWeek.TUESDAY,
    DayOfWeek.WEDNESDAY,
    DayOfWeek.THURSDAY,
    DayOfWeek.FRIDAY,
]

#: Courses meeting twice a week use one of these day pairs, so the two sessions
#: land on different days rather than back to back.
PAIRED_DAYS = [
    (DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY),
    (DayOfWeek.TUESDAY, DayOfWeek.THURSDAY),
    (DayOfWeek.WEDNESDAY, DayOfWeek.FRIDAY),
    (DayOfWeek.MONDAY, DayOfWeek.THURSDAY),
    (DayOfWeek.TUESDAY, DayOfWeek.FRIDAY),
]

#: Each department teaches in its own building, so room clashes can only ever
#: occur within a department — which keeps the search space small.
BUILDINGS = {"CS": "IT", "MATH": "SCI", "EE": "ENG", "BUS": "BIZ"}
ROOMS_PER_BUILDING = 8

#: Seats fall as courses get more advanced.
CAPACITY_BY_LEVEL = {100: 60, 200: 40, 300: 30, 400: 25}

#: A 4-credit course meets twice a week, anything smaller once.
TWO_MEETING_THRESHOLD = 4


def _patterns(cells_needed: int) -> list[tuple[tuple[int, int], ...]]:
    """
    Candidate timetable patterns, each a tuple of ``(day, slot index)`` cells.

    Ordered slot-major so consecutive sections spread across days before
    reusing a time of day.
    """
    if cells_needed == 2:
        return [
            tuple((day, slot) for day in days)
            for slot in range(len(CLASS_SLOTS))
            for days in PAIRED_DAYS
        ]
    return [((day, slot),) for slot in range(len(CLASS_SLOTS)) for day in WEEKDAYS]


class Command(BaseCommand):
    help = "Populate departments, programs, courses, prerequisites, terms, sections and meetings."

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

        password = options["password"]

        self._heading("Baseline accounts")
        call_command(
            "create_test_users",
            password=password,
            force=options["force"],
            stdout=self.stdout,
        )

        self._heading("Catalogue")
        departments = self._seed_departments()
        programs = self._seed_programs(departments)
        courses = self._seed_courses(departments)
        rules = self._seed_prerequisites(courses)

        self._heading("People")
        lecturers = self._seed_lecturers(departments, password)
        students = self._seed_students(programs, password)

        self._heading("Terms and sections")
        terms = self._seed_terms()
        sections = self._seed_sections(courses, terms, lecturers)
        meetings = self._seed_meetings(terms)

        self._summary(
            departments, programs, courses, rules, terms, sections, meetings, lecturers, students
        )

    # ----------------------------------------------------------------- #
    # Catalogue
    # ----------------------------------------------------------------- #

    def _seed_departments(self) -> dict[str, Department]:
        result = {}
        for code, name in DEPARTMENTS:
            result[code], _created = Department.objects.update_or_create(
                code=code, defaults={"name": name}
            )
        self._report("departments", len(result))
        return result

    def _seed_programs(self, departments: dict[str, Department]) -> dict[str, Program]:
        result = {}
        for code, name, dept_code, level, credits_required in PROGRAMS:
            result[code], _created = Program.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "department": departments[dept_code],
                    "degree_level": level,
                    "credits_required": credits_required,
                },
            )
        self._report("programs", len(result))
        return result

    def _seed_courses(self, departments: dict[str, Department]) -> dict[str, Course]:
        result = {}
        for code, title, credits, level, dept_code in COURSES:
            result[code], _created = Course.objects.update_or_create(
                code=code,
                defaults={
                    "title": title,
                    "credits": credits,
                    "level": level,
                    "department": departments[dept_code],
                    "is_active": True,
                    "description": (
                        f"{title}. A level-{level} course offered by the "
                        f"{departments[dept_code].name} department, worth {credits} credits."
                    ),
                },
            )
        self._report("courses", len(result))
        return result

    def _seed_prerequisites(self, courses: dict[str, Course]) -> list[PrerequisiteRule]:
        result = []
        for course_code, prereq_code, minimum_grade in PREREQUISITES:
            rule, _created = PrerequisiteRule.objects.update_or_create(
                course=courses[course_code],
                prerequisite=courses[prereq_code],
                defaults={"minimum_grade": minimum_grade},
            )
            # Assert the seeded graph stays acyclic. Cheap here, and a cycle
            # would make its course permanently unregisterable.
            rule.clean()
            result.append(rule)
        self._report("prerequisite rules", len(result))
        return result

    # ----------------------------------------------------------------- #
    # People
    # ----------------------------------------------------------------- #

    def _seed_lecturers(
        self, departments: dict[str, Department], password: str
    ) -> dict[str, list[LecturerProfile]]:
        """Returns lecturers grouped by department code, in declaration order."""
        by_department: dict[str, list[LecturerProfile]] = defaultdict(list)
        for username, first, last, email, dept_code, title in LECTURERS:
            user = self._upsert_user(username, first, last, email, Role.LECTURER, password)
            profile, _created = LecturerProfile.objects.update_or_create(
                user=user,
                defaults={
                    "staff_number": username,
                    "title": title,
                    "department": departments[dept_code],
                },
            )
            by_department[dept_code].append(profile)
        self._report("lecturers", sum(len(v) for v in by_department.values()))
        return by_department

    def _seed_students(self, programs: dict[str, Program], password: str) -> list[StudentProfile]:
        result = []
        for username, first, last, email, program_code, year, status in STUDENTS:
            user = self._upsert_user(username, first, last, email, Role.STUDENT, password)
            profile, _created = StudentProfile.objects.update_or_create(
                user=user,
                defaults={
                    "student_number": username,
                    "enrollment_year": year,
                    "status": status,
                    "program": programs[program_code],
                },
            )
            result.append(profile)
        self._report("students", len(result))
        return result

    @staticmethod
    def _upsert_user(
        username: str, first: str, last: str, email: str, role: str, password: str
    ) -> User:
        user, _created = User.objects.update_or_create(
            username=username,
            defaults={
                "first_name": first,
                "last_name": last,
                "email": email,
                "role": role,
                "is_active": True,
            },
        )
        user.set_password(password)
        user.save(update_fields=["password"])
        return user

    # ----------------------------------------------------------------- #
    # Terms
    # ----------------------------------------------------------------- #

    def _seed_terms(self) -> dict[str, Term]:
        now = timezone.now()

        # Term dates are fixed; the registration windows are relative to now so
        # that "one open, one closed" holds however long after seeding you look.
        specs = [
            {
                "code": "2026-SPRING",
                "name": "Spring 2026",
                "start_date": date(2026, 2, 2),
                "end_date": date(2026, 6, 12),
                "registration_opens_at": now - timedelta(days=240),
                "registration_closes_at": now - timedelta(days=210),
                "is_active": False,
            },
            {
                "code": "2026-FALL",
                "name": "Fall 2026",
                "start_date": date(2026, 9, 7),
                "end_date": date(2027, 1, 15),
                "registration_opens_at": now - timedelta(days=7),
                "registration_closes_at": now + timedelta(days=21),
                "is_active": True,
            },
        ]

        result = {}
        # Order matters: the inactive term is written first, so a re-run never
        # holds two rows with is_active=True and trips the partial unique index.
        for spec in specs:
            code = spec.pop("code")
            spec["max_credits_per_student"] = 24
            result[code], _created = Term.objects.update_or_create(code=code, defaults=spec)

        self._report("terms", len(result))
        for term in result.values():
            self.stdout.write(f"      {term.code:<12} registration {term.registration_status}")
        return result

    # ----------------------------------------------------------------- #
    # Sections and meetings
    # ----------------------------------------------------------------- #

    def _section_specs(
        self, courses: dict[str, Course], terms: dict[str, Term]
    ) -> list[tuple[Term, Course, str, int]]:
        """
        Every (term, course, section code, capacity) to exist.

        Fall offers the whole catalogue; Spring offers only the first two years,
        which is both realistic and gives the rule engine a term whose window is
        shut but whose sections are real.
        """
        specs: list[tuple[Term, Course, str, int]] = []
        fall, spring = terms["2026-FALL"], terms["2026-SPRING"]

        for course in courses.values():
            specs.append((fall, course, "01", CAPACITY_BY_LEVEL[course.level]))
            # First-year courses are the crowded ones — give them a second section.
            if course.level == 100:
                specs.append((fall, course, "02", CAPACITY_BY_LEVEL[course.level]))
            if course.level in (100, 200):
                specs.append((spring, course, "01", CAPACITY_BY_LEVEL[course.level]))

        # A deliberately tiny section. Filling a 30-seat section to test rule R6
        # and the waitlist means inventing 30 students; two seats does the same
        # job in two clicks.
        specs.append((fall, courses["CS310"], "02", 2))

        return specs

    def _seed_sections(
        self,
        courses: dict[str, Course],
        terms: dict[str, Term],
        lecturers: dict[str, list[LecturerProfile]],
    ) -> list[Section]:
        # Round-robin a department's lecturers across its sections. Each keeps
        # its own counter so a department with two staff alternates cleanly.
        next_lecturer: dict[str, int] = defaultdict(int)
        result = []

        for term, course, section_code, capacity in self._section_specs(courses, terms):
            dept_code = course.department.code
            staff = lecturers[dept_code]

            # One section is left unassigned, so the "to be announced" path in
            # the UI has real data behind it.
            if course.code == "BUS401":
                lecturer = None
            else:
                lecturer = staff[next_lecturer[dept_code] % len(staff)]
                next_lecturer[dept_code] += 1

            section, _created = Section.objects.update_or_create(
                course=course,
                term=term,
                section_code=section_code,
                defaults={"lecturer": lecturer, "capacity": capacity},
            )
            result.append(section)

        self._report("sections", len(result))
        return result

    def _seed_meetings(self, terms: dict[str, Term]) -> list[Meeting]:
        """
        Give every section without meetings a slot, double-booking nobody.

        Sections that already have meetings are left alone, so a timetable
        adjusted by hand in the admin survives a re-run. Their slots are still
        read into the occupancy map, so new sections avoid clashing with them.
        """
        created: list[Meeting] = []

        for term in terms.values():
            # (day, slot index) -> the lecturers / rooms already teaching then.
            busy_lecturers: dict[tuple[int, int], set[int]] = defaultdict(set)
            busy_rooms: dict[tuple[int, int], set[str]] = defaultdict(set)

            sections = list(
                term.sections.select_related("course__department").prefetch_related("meetings")
            )

            for section in sections:
                for meeting in section.meetings.all():
                    slot = SLOT_INDEX.get((meeting.start_time, meeting.end_time))
                    if slot is None:
                        continue  # Hand-authored off-grid time; nothing to reserve.
                    cell = (meeting.day_of_week, slot)
                    if section.lecturer_id:
                        busy_lecturers[cell].add(section.lecturer_id)
                    if meeting.room:
                        busy_rooms[cell].add(meeting.room)

            for offset, section in enumerate(sections):
                if section.meetings.all():
                    continue

                cells_needed = 2 if section.course.credits >= TWO_MEETING_THRESHOLD else 1
                candidates = _patterns(cells_needed)
                rooms = self._room_pool(section.course.department.code)

                placement = self._find_placement(
                    section, candidates, rooms, offset, busy_lecturers, busy_rooms
                )
                if placement is None:
                    raise CommandError(
                        f"No free timetable slot for {section}. The seed dataset has "
                        f"outgrown the {len(WEEKDAYS) * len(CLASS_SLOTS)}-cell weekly grid — "
                        f"widen CLASS_SLOTS, add rooms, or add lecturers."
                    )

                pattern, room = placement
                for day, slot in pattern:
                    start, end = CLASS_SLOTS[slot]
                    created.append(
                        Meeting(
                            section=section,
                            day_of_week=day,
                            start_time=start,
                            end_time=end,
                            room=room,
                        )
                    )
                    if section.lecturer_id:
                        busy_lecturers[(day, slot)].add(section.lecturer_id)
                    busy_rooms[(day, slot)].add(room)

        Meeting.objects.bulk_create(created)
        self._report("meetings created", len(created))
        return created

    @staticmethod
    def _room_pool(department_code: str) -> list[str]:
        building = BUILDINGS[department_code]
        return [f"{building}-{101 + index}" for index in range(ROOMS_PER_BUILDING)]

    @staticmethod
    def _find_placement(
        section: Section,
        candidates: list[tuple[tuple[int, int], ...]],
        rooms: list[str],
        offset: int,
        busy_lecturers: dict[tuple[int, int], set[int]],
        busy_rooms: dict[tuple[int, int], set[str]],
    ) -> tuple[tuple[tuple[int, int], ...], str] | None:
        """
        First pattern whose cells are all free for this lecturer, plus a room
        free across every one of them.

        Starts the scan at ``offset`` so consecutive sections land on different
        days instead of stacking on Monday morning.
        """
        for step in range(len(candidates)):
            pattern = candidates[(offset + step) % len(candidates)]

            if section.lecturer_id and any(
                section.lecturer_id in busy_lecturers[cell] for cell in pattern
            ):
                continue

            for room in rooms:
                if all(room not in busy_rooms[cell] for cell in pattern):
                    return pattern, room

        return None

    # ----------------------------------------------------------------- #
    # Output
    # ----------------------------------------------------------------- #

    def _heading(self, text: str) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(text))

    def _report(self, label: str, count: int) -> None:
        self.stdout.write(f"  {count:>4}  {label}")

    def _summary(
        self, departments, programs, courses, rules, terms, sections, meetings, lecturers, students
    ) -> None:
        active = next((t for t in terms.values() if t.is_active), None)
        lecturer_count = sum(len(v) for v in lecturers.values())

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Catalogue ready: {len(departments)} departments, {len(programs)} programs, "
                f"{len(courses)} courses, {len(rules)} prerequisite rules, "
                f"{len(terms)} terms, {len(sections)} sections "
                f"({len(meetings)} new meetings), "
                f"{lecturer_count} lecturers, {len(students)} students."
            )
        )
        if active:
            self.stdout.write(
                f"Current term: {active.name} — registration {active.registration_status.lower()}, "
                f"closes {timezone.localtime(active.registration_closes_at):%Y-%m-%d %H:%M}."
            )
        self.stdout.write("Browse it at /admin/ once the server is running.")
