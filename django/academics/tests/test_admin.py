"""
Tests for the catalogue admin.

Phase 2's deliverable is a *browsable* catalogue, and until Phase 4 the admin is
the only thing browsing it — so every registered screen is loaded here. These are
cheap smoke tests, but they catch the two mistakes that are easy to make and
invisible until someone clicks: an ``autocomplete_fields`` entry pointing at a
model whose admin has no ``search_fields``, and a ``list_display`` method that
blows up on a row with nothing in it.
"""

from datetime import date, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import (
    Course,
    DayOfWeek,
    Department,
    Meeting,
    PrerequisiteRule,
    Program,
    Section,
    Term,
)
from accounts.models import User


class AdminScreenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser("admin", "a@crs.test", "pw")

        cls.department = Department.objects.create(code="CS", name="Computer Science")
        cls.program = Program.objects.create(
            code="CS-BSC", name="Bachelor of Computer Science", department=cls.department
        )
        cls.intro = Course.objects.create(
            code="CS101", title="Introduction to Programming", credits=4, department=cls.department
        )
        cls.advanced = Course.objects.create(
            code="CS201", title="Data Structures", credits=4, level=200, department=cls.department
        )
        cls.rule = PrerequisiteRule.objects.create(course=cls.advanced, prerequisite=cls.intro)

        now = timezone.now()
        cls.term = Term.objects.create(
            code="2026-FALL",
            name="Fall 2026",
            start_date=date(2026, 9, 7),
            end_date=date(2027, 1, 15),
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=20),
            is_active=True,
        )
        cls.lecturer = User.objects.create_lecturer(
            "L-1001",
            "l@crs.test",
            "pw",
            first_name="Budi",
            last_name="Santoso",
            department=cls.department,
        ).lecturer_profile
        cls.section = Section.objects.create(
            course=cls.intro,
            term=cls.term,
            section_code="01",
            capacity=40,
            lecturer=cls.lecturer,
        )
        cls.meeting = Meeting.objects.create(
            section=cls.section,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 40),
            room="IT-101",
        )

        cls.objects = {
            "department": cls.department,
            "program": cls.program,
            "course": cls.intro,
            "prerequisiterule": cls.rule,
            "term": cls.term,
            "section": cls.section,
            "meeting": cls.meeting,
        }

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_every_changelist_renders(self):
        for model in self.objects:
            with self.subTest(model=model):
                url = reverse(f"admin:academics_{model}_changelist")
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_every_change_page_renders(self):
        for model, instance in self.objects.items():
            with self.subTest(model=model):
                url = reverse(f"admin:academics_{model}_change", args=[instance.pk])
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_every_add_page_renders(self):
        for model in self.objects:
            with self.subTest(model=model):
                url = reverse(f"admin:academics_{model}_add")
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_section_page_offers_the_meetings_inline(self):
        response = self.client.get(
            reverse("admin:academics_section_change", args=[self.section.pk])
        )
        self.assertContains(response, "meetings-0-start_time")

    def test_course_page_offers_the_prerequisites_inline(self):
        response = self.client.get(reverse("admin:academics_course_change", args=[self.intro.pk]))
        self.assertContains(response, "prerequisite_rules-0-prerequisite")

    def test_term_changelist_shows_the_window_state(self):
        response = self.client.get(reverse("admin:academics_term_changelist"))
        self.assertContains(response, "Open")

    def test_section_changelist_shows_the_schedule(self):
        response = self.client.get(reverse("admin:academics_section_changelist"))
        self.assertContains(response, "IT-101")

    def test_section_changelist_copes_with_a_section_that_has_no_meetings(self):
        Section.objects.create(course=self.advanced, term=self.term, section_code="01", capacity=30)
        response = self.client.get(reverse("admin:academics_section_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_autocomplete_endpoints_return_matches(self):
        """
        Guards every ``autocomplete_fields`` entry across both apps.

        Django's system checks catch a target admin with no ``search_fields``,
        but not a ``search_fields`` list that cannot actually find the thing a
        user would type — so each case searches for a real code and asserts a
        result comes back. The parameters name the *source* model and field; the
        view derives the target from the relation.
        """
        cases = [
            ("academics", "program", "department", "CS", "Computer Science"),
            ("academics", "course", "department", "CS", "Computer Science"),
            ("academics", "prerequisiterule", "prerequisite", "CS101", "CS101"),
            ("academics", "section", "course", "CS101", "CS101"),
            ("academics", "section", "term", "2026", "Fall 2026"),
            ("academics", "section", "lecturer", "L-1001", "Santoso"),
            ("academics", "meeting", "section", "CS101", "CS101-01"),
            ("accounts", "studentprofile", "program", "CS-BSC", "CS-BSC"),
            ("accounts", "lecturerprofile", "department", "CS", "Computer Science"),
        ]
        for app_label, model_name, field_name, query, expected in cases:
            with self.subTest(source=f"{model_name}.{field_name}"):
                response = self.client.get(
                    reverse("admin:autocomplete"),
                    {
                        "app_label": app_label,
                        "model_name": model_name,
                        "field_name": field_name,
                        "term": query,
                    },
                )
                self.assertEqual(response.status_code, 200)
                results = response.json()["results"]
                self.assertTrue(results, f"{query!r} matched nothing")
                self.assertTrue(
                    any(expected in item["text"] for item in results),
                    f"{query!r} did not surface {expected!r}: {results}",
                )

    def test_annotated_changelists_are_ordered(self):
        """
        Regression: an aggregate annotation clears ``Meta.ordering``, so the
        department and term changelists were paginating unordered querysets —
        which Django only surfaces as a warning, not an error.
        """
        for model in ("department", "term"):
            with self.subTest(model=model):
                response = self.client.get(reverse(f"admin:academics_{model}_changelist"))
                self.assertTrue(response.context["cl"].queryset.ordered)

    def test_department_changelist_counts_programs_and_courses(self):
        response = self.client.get(reverse("admin:academics_department_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Computer Science")


class ProfileAdminTests(TestCase):
    """The Phase 1 accounts admin, re-checked now that the FKs are wired up."""

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser("admin", "a@crs.test", "pw")
        cls.department = Department.objects.create(code="CS", name="Computer Science")
        cls.program = Program.objects.create(
            code="CS-BSC", name="Bachelor of Computer Science", department=cls.department
        )
        cls.student = User.objects.create_student(
            "2026001", "s@crs.test", "pw", program=cls.program
        )
        cls.lecturer = User.objects.create_lecturer(
            "L-1001", "l@crs.test", "pw", department=cls.department
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_student_change_page_offers_the_program_field(self):
        response = self.client.get(reverse("admin:accounts_user_change", args=[self.student.pk]))
        self.assertContains(response, "student_profile-0-program")

    def test_lecturer_change_page_offers_the_department_field(self):
        response = self.client.get(reverse("admin:accounts_user_change", args=[self.lecturer.pk]))
        self.assertContains(response, "lecturer_profile-0-department")

    def test_profile_changelists_render_with_the_new_columns(self):
        for url_name in (
            "admin:accounts_studentprofile_changelist",
            "admin:accounts_lecturerprofile_changelist",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "CS")
