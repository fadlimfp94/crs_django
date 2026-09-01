"""
Tests for register/drop, timetable, enrollment history, lecturer roster and
grading, and administrative override — the end-to-end journey through the
browser that PLAN.md's Phase 4 done-when describes.

The rule engine itself (R1-R7) already has full coverage in
``test_services.py``; these tests exercise the views that call it, plus the
role-gating and data-isolation each screen adds on top.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import LecturerTitle, StudentStatus, User
from registration.models import Enrollment, EnrollmentStatus
from registration.tests.factories import (
    make_course,
    make_department,
    make_meeting,
    make_section,
    make_student,
    make_term,
)

PASSWORD = "test-password"


class RegistrationViewTestCase(TestCase):
    """Shared fixture: one open term, one section, one student, one lecturer."""

    @classmethod
    def setUpTestData(cls):
        cls.department = make_department()
        cls.term = make_term(is_active=True)
        cls.course = make_course(cls.department, "CS101")
        cls.section = make_section(cls.course, cls.term, capacity=1)
        make_meeting(cls.section)

        cls.lecturer_user = User.objects.create_lecturer(
            "L-1001", "lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )
        cls.section.lecturer = cls.lecturer_user.lecturer_profile
        cls.section.save(update_fields=["lecturer"])

        cls.other_lecturer_user = User.objects.create_lecturer(
            "L-1002", "other-lecturer@crs.test", PASSWORD, title=LecturerTitle.LECTURER
        )

        cls.admin = User.objects.create_superuser("admin", "admin@crs.test", PASSWORD)

        cls.student = make_student()
        cls.second_student = make_student()


class RegisterViewTests(RegistrationViewTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)

    def test_get_renders_the_confirmation_page(self):
        response = self.client.get(reverse("registration:register", args=[self.section.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/register_confirm.html")

    def test_get_with_an_existing_active_enrollment_redirects_to_section_detail(self):
        self.client.post(reverse("registration:register", args=[self.section.pk]))
        response = self.client.get(reverse("registration:register", args=[self.section.pk]))
        self.assertRedirects(response, reverse("academics:section_detail", args=[self.section.pk]))

    def test_post_enrolls_the_student(self):
        response = self.client.post(reverse("registration:register", args=[self.section.pk]))
        self.assertRedirects(response, reverse("academics:section_detail", args=[self.section.pk]))
        enrollment = Enrollment.objects.get(student=self.student, section=self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)

    def test_post_waitlists_once_the_section_is_full(self):
        self.client.post(reverse("registration:register", args=[self.section.pk]))  # takes the seat

        self.client.force_login(self.second_student.user)
        response = self.client.post(reverse("registration:register", args=[self.section.pk]))
        self.assertRedirects(response, reverse("academics:section_detail", args=[self.section.pk]))

        enrollment = Enrollment.objects.get(student=self.second_student, section=self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.WAITLISTED)
        self.assertEqual(enrollment.waitlist_position, 1)

    def test_post_rejection_re_renders_the_confirm_page_with_the_specific_reason(self):
        """A timetable clash (R5) is surfaced inline, not as a generic failure."""
        other_course = make_course(self.department, "CS102")
        clashing_section = make_section(other_course, self.term, section_code="02", capacity=5)
        make_meeting(clashing_section)  # same day/time as self.section by factory default

        self.client.post(reverse("registration:register", args=[self.section.pk]))
        response = self.client.post(reverse("registration:register", args=[clashing_section.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/register_confirm.html")
        self.assertContains(response, 'data-testid="registration-error"')
        self.assertContains(response, "clashes with")

    def test_lecturer_cannot_reach_register(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.get(reverse("registration:register", args=[self.section.pk]))
        self.assertRedirects(response, reverse("accounts:lecturer_dashboard"))


class DropViewTests(RegistrationViewTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("registration:register", args=[self.section.pk]))
        self.enrollment = Enrollment.objects.get(student=self.student, section=self.section)

    def test_get_renders_the_confirmation_page(self):
        response = self.client.get(reverse("registration:drop", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/drop_confirm.html")

    def test_post_drops_and_redirects_to_enrollment_history(self):
        response = self.client.post(reverse("registration:drop", args=[self.enrollment.pk]))
        self.assertRedirects(response, reverse("registration:enrollment_history"))

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, EnrollmentStatus.DROPPED)

    def test_dropping_someone_elses_enrollment_is_not_found(self):
        self.client.force_login(self.second_student.user)
        response = self.client.get(reverse("registration:drop", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 404)

    def test_drop_promotes_the_next_waitlisted_student(self):
        self.client.force_login(self.second_student.user)
        self.client.post(reverse("registration:register", args=[self.section.pk]))
        waitlisted = Enrollment.objects.get(student=self.second_student, section=self.section)
        self.assertEqual(waitlisted.status, EnrollmentStatus.WAITLISTED)

        self.client.force_login(self.student.user)
        self.client.post(reverse("registration:drop", args=[self.enrollment.pk]))

        waitlisted.refresh_from_db()
        self.assertEqual(waitlisted.status, EnrollmentStatus.ENROLLED)


class MyTimetableViewTests(RegistrationViewTestCase):
    def test_empty_state_with_no_enrollments(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("registration:my_timetable"))
        self.assertContains(response, 'data-testid="timetable-empty"')

    def test_an_enrolled_section_produces_one_timetable_block(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("registration:register", args=[self.section.pk]))

        response = self.client.get(reverse("registration:my_timetable"))
        self.assertContains(response, 'data-testid="timetable-block"')
        self.assertEqual(len(response.context["blocks"]), 1)

    def test_lecturer_cannot_reach_my_timetable(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.get(reverse("registration:my_timetable"))
        self.assertRedirects(response, reverse("accounts:lecturer_dashboard"))


class EnrollmentHistoryViewTests(RegistrationViewTestCase):
    def test_empty_state_with_no_enrollments(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("registration:enrollment_history"))
        self.assertContains(response, 'data-testid="enrollment-history-empty"')

    def test_shows_every_enrollment_with_a_drop_link_while_active(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("registration:register", args=[self.section.pk]))

        response = self.client.get(reverse("registration:enrollment_history"))
        self.assertContains(response, 'data-testid="enrollment-history-row"')
        self.assertContains(response, 'data-testid="enrollment-history-drop"')


class LecturerSectionListViewTests(RegistrationViewTestCase):
    def test_shows_the_lecturers_assigned_sections(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.get(reverse("registration:lecturer_sections"))
        self.assertContains(response, 'data-testid="lecturer-sections-row"')

    def test_a_lecturer_with_no_sections_sees_the_empty_state(self):
        self.client.force_login(self.other_lecturer_user)
        response = self.client.get(reverse("registration:lecturer_sections"))
        self.assertContains(response, 'data-testid="lecturer-sections-empty"')

    def test_student_cannot_reach_lecturer_sections(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("registration:lecturer_sections"))
        self.assertRedirects(response, reverse("accounts:student_dashboard"))


class SectionRosterViewTests(RegistrationViewTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("registration:register", args=[self.section.pk]))
        self.client.force_login(self.second_student.user)
        self.client.post(reverse("registration:register", args=[self.section.pk]))  # waitlisted

    def test_owning_lecturer_sees_enrolled_and_waitlisted_students(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.get(reverse("registration:roster", args=[self.section.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="roster-enrolled-row"')
        self.assertContains(response, 'data-testid="roster-waitlist-row"')

    def test_a_different_lecturer_gets_not_found(self):
        self.client.force_login(self.other_lecturer_user)
        response = self.client.get(reverse("registration:roster", args=[self.section.pk]))
        self.assertEqual(response.status_code, 404)


class GradeEntryViewTests(RegistrationViewTestCase):
    def setUp(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("registration:register", args=[self.section.pk]))
        self.enrollment = Enrollment.objects.get(student=self.student, section=self.section)

    def test_lecturer_can_grade_an_enrolled_student(self):
        self.client.force_login(self.lecturer_user)
        response = self.client.post(
            reverse("registration:grade_entry", args=[self.enrollment.pk]), {"grade": "A"}
        )
        self.assertRedirects(response, reverse("registration:roster", args=[self.section.pk]))

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, EnrollmentStatus.COMPLETED)
        self.assertEqual(self.enrollment.grade, "A")

    def test_grading_a_waitlisted_enrollment_is_rejected(self):
        self.client.force_login(self.second_student.user)
        self.client.post(reverse("registration:register", args=[self.section.pk]))
        waitlisted = Enrollment.objects.get(student=self.second_student, section=self.section)

        self.client.force_login(self.lecturer_user)
        self.client.post(reverse("registration:grade_entry", args=[waitlisted.pk]), {"grade": "A"})

        waitlisted.refresh_from_db()
        self.assertEqual(waitlisted.status, EnrollmentStatus.WAITLISTED)

    def test_a_different_lecturer_gets_not_found(self):
        self.client.force_login(self.other_lecturer_user)
        response = self.client.post(
            reverse("registration:grade_entry", args=[self.enrollment.pk]), {"grade": "A"}
        )
        self.assertEqual(response.status_code, 404)


class EnrollmentOverrideViewTests(RegistrationViewTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_can_override_a_students_bad_standing(self):
        suspended_student = make_student(status=StudentStatus.SUSPENDED)
        other_section = make_section(
            make_course(self.department, "CS999"), self.term, section_code="09", capacity=5
        )

        response = self.client.post(
            reverse("registration:admin_override"),
            {"student": suspended_student.pk, "section": other_section.pk},
        )
        self.assertEqual(response.status_code, 200)

        enrollment = Enrollment.objects.get(student=suspended_student, section=other_section)
        self.assertEqual(enrollment.status, EnrollmentStatus.ENROLLED)

    def test_override_still_waitlists_once_the_section_is_full(self):
        self.client.post(
            reverse("registration:admin_override"),
            {"student": self.student.pk, "section": self.section.pk},
        )
        self.client.post(
            reverse("registration:admin_override"),
            {"student": self.second_student.pk, "section": self.section.pk},
        )

        enrollment = Enrollment.objects.get(student=self.second_student, section=self.section)
        self.assertEqual(enrollment.status, EnrollmentStatus.WAITLISTED)

    def test_student_cannot_reach_the_override_tool(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("registration:admin_override"))
        self.assertRedirects(response, reverse("accounts:student_dashboard"))
