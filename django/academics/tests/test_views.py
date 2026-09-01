"""
Tests for catalogue browsing and registration-window administration views.

Register/drop/timetable/roster screens are tested in
``registration/tests/test_views.py`` instead — they belong to that app.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import LecturerTitle, User
from registration.models import EnrollmentStatus
from registration.services import register
from registration.tests.factories import (
    make_course,
    make_department,
    make_meeting,
    make_section,
    make_student,
    make_term,
)

PASSWORD = "test-password"


class CatalogueTestCase(TestCase):
    """Shared fixture: one active term, one department, three sections."""

    @classmethod
    def setUpTestData(cls):
        cls.department = make_department("CS", "Computer Science")
        other_department = make_department("MATH", "Mathematics")

        cls.term = make_term("2026-FALL", is_active=True)
        cls.other_term = make_term("2027-SPRING", opens_days=+30, closes_days=+60)

        cls.course = make_course(cls.department, "CS101", credits=4)
        other_course = make_course(other_department, "MATH200", credits=3)

        cls.section = make_section(cls.course, cls.term, capacity=2)
        make_meeting(cls.section)
        cls.other_section = make_section(other_course, cls.term, section_code="01", capacity=30)
        cls.other_term_section = make_section(cls.course, cls.other_term, section_code="02")

        cls.student = make_student()
        cls.lecturer = User.objects.create_lecturer(
            "L-1001", "lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )
        cls.admin = User.objects.create_superuser("admin", "admin@crs.test", PASSWORD)


class CatalogueAccessTests(CatalogueTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("academics:catalogue"))
        self.assertEqual(response.status_code, 302)

    def test_every_role_can_browse_the_catalogue(self):
        for user in (self.student.user, self.lecturer, self.admin):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("academics:catalogue"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "academics/catalogue.html")


class CatalogueFilterTests(CatalogueTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)

    def test_no_query_defaults_to_the_active_term(self):
        response = self.client.get(reverse("academics:catalogue"))
        sections = list(response.context["sections"])
        self.assertIn(self.section, sections)
        self.assertIn(self.other_section, sections)
        self.assertNotIn(self.other_term_section, sections)

    def test_explicit_any_term_shows_every_term(self):
        response = self.client.get(reverse("academics:catalogue"), {"term": ""})
        sections = list(response.context["sections"])
        self.assertIn(self.other_term_section, sections)

    def test_filter_by_department(self):
        response = self.client.get(
            reverse("academics:catalogue"), {"department": self.department.pk}
        )
        sections = list(response.context["sections"])
        self.assertIn(self.section, sections)
        self.assertNotIn(self.other_section, sections)

    def test_filter_by_term(self):
        response = self.client.get(reverse("academics:catalogue"), {"term": self.other_term.pk})
        sections = list(response.context["sections"])
        self.assertEqual(sections, [self.other_term_section])

    def test_free_text_search_matches_course_code_or_title(self):
        response = self.client.get(reverse("academics:catalogue"), {"q": "CS101"})
        sections = list(response.context["sections"])
        self.assertIn(self.section, sections)
        self.assertNotIn(self.other_section, sections)

    def test_min_credits_excludes_lighter_courses(self):
        response = self.client.get(reverse("academics:catalogue"), {"min_credits": 4})
        sections = list(response.context["sections"])
        self.assertIn(self.section, sections)
        self.assertNotIn(self.other_section, sections)

    def test_max_credits_excludes_heavier_courses(self):
        response = self.client.get(reverse("academics:catalogue"), {"max_credits": 3})
        sections = list(response.context["sections"])
        self.assertNotIn(self.section, sections)
        self.assertIn(self.other_section, sections)

    def test_availability_open_excludes_a_full_section(self):
        register(self.student, self.section)
        second_student = make_student()
        register(second_student, self.section)  # capacity=2, now full

        response = self.client.get(reverse("academics:catalogue"), {"availability": "open"})
        sections = list(response.context["sections"])
        self.assertNotIn(self.section, sections)
        self.assertIn(self.other_section, sections)

    def test_availability_waitlist_only_returns_the_full_section(self):
        register(self.student, self.section)
        second_student = make_student()
        register(second_student, self.section)

        response = self.client.get(reverse("academics:catalogue"), {"availability": "waitlist"})
        sections = list(response.context["sections"])
        self.assertEqual(sections, [self.section])


class CataloguePaginationTests(CatalogueTestCase):
    def test_more_than_twenty_sections_are_paginated(self):
        for index in range(25):
            make_section(self.course, self.term, section_code=f"P{index:02d}")

        self.client.force_login(self.student.user)
        response = self.client.get(reverse("academics:catalogue"))
        self.assertTrue(response.context["page_obj"].has_other_pages())
        self.assertEqual(len(response.context["sections"]), 20)

        second_page = self.client.get(reverse("academics:catalogue"), {"page": 2})
        self.assertEqual(second_page.status_code, 200)


class SectionDetailTests(CatalogueTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("academics:section_detail", args=[self.section.pk]))
        self.assertEqual(response.status_code, 302)

    def test_unenrolled_student_sees_a_register_link(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("academics:section_detail", args=[self.section.pk]))
        self.assertContains(response, 'data-testid="section-register-link"')

    def test_enrolled_student_sees_a_drop_link(self):
        register(self.student, self.section)
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("academics:section_detail", args=[self.section.pk]))
        self.assertContains(response, 'data-testid="section-drop-link"')
        self.assertNotContains(response, 'data-testid="section-register-link"')

    def test_waitlisted_student_sees_their_position(self):
        register(self.student, self.section)  # capacity=2
        second_student = make_student()
        register(second_student, self.section)
        third_student = make_student()
        enrollment = register(third_student, self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.WAITLISTED)

        self.client.force_login(third_student.user)
        response = self.client.get(reverse("academics:section_detail", args=[self.section.pk]))
        self.assertContains(response, "position 1")

    def test_lecturer_sees_no_registration_card(self):
        self.client.force_login(self.lecturer)
        response = self.client.get(reverse("academics:section_detail", args=[self.section.pk]))
        self.assertNotContains(response, 'data-testid="section-register-link"')
        self.assertNotContains(response, 'data-testid="section-drop-link"')

    def test_seats_remaining_is_shown(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("academics:section_detail", args=[self.section.pk]))
        self.assertEqual(response.context["seats_remaining"], 2)


class TermWindowAccessTests(CatalogueTestCase):
    def test_admin_can_reach_the_term_list(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("academics:admin_term_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "academics/term_window_list.html")

    def test_student_is_redirected_to_their_own_dashboard(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("academics:admin_term_list"))
        self.assertRedirects(response, reverse("accounts:student_dashboard"))

    def test_lecturer_is_redirected_to_their_own_dashboard(self):
        self.client.force_login(self.lecturer)
        response = self.client.get(reverse("academics:admin_term_list"))
        self.assertRedirects(response, reverse("accounts:lecturer_dashboard"))

    def test_non_admin_cannot_reach_the_update_form(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("academics:admin_term_update", args=[self.term.pk]))
        self.assertRedirects(response, reverse("accounts:student_dashboard"))


class TermWindowUpdateTests(CatalogueTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_can_update_the_registration_window(self):
        response = self.client.post(
            reverse("academics:admin_term_update", args=[self.term.pk]),
            {
                "registration_opens_at": "2026-01-01T00:00",
                "registration_closes_at": "2026-12-31T00:00",
                "max_credits_per_student": 18,
            },
        )
        self.assertRedirects(response, reverse("academics:admin_term_list"))

        self.term.refresh_from_db()
        self.assertEqual(self.term.max_credits_per_student, 18)

    def test_invalid_window_is_rejected(self):
        response = self.client.post(
            reverse("academics:admin_term_update", args=[self.term.pk]),
            {
                "registration_opens_at": "2026-12-31T00:00",
                "registration_closes_at": "2026-01-01T00:00",
                "max_credits_per_student": 18,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.term.refresh_from_db()
        self.assertNotEqual(self.term.max_credits_per_student, 18)
