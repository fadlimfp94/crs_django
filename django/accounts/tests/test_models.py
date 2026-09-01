"""Tests for the user and profile models."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import (
    LecturerProfile,
    LecturerTitle,
    Role,
    StudentProfile,
    StudentStatus,
    User,
)


class UserModelTests(TestCase):
    def test_role_helpers_are_mutually_exclusive(self):
        student = User.objects.create_user("s1", "s1@crs.test", "pw", role=Role.STUDENT)
        lecturer = User.objects.create_user("l1", "l1@crs.test", "pw", role=Role.LECTURER)
        admin = User.objects.create_user("a1", "a1@crs.test", "pw", role=Role.ADMIN)

        self.assertEqual(
            (student.is_student, student.is_lecturer, student.is_administrator),
            (True, False, False),
        )
        self.assertEqual(
            (lecturer.is_student, lecturer.is_lecturer, lecturer.is_administrator),
            (False, True, False),
        )
        self.assertEqual(
            (admin.is_student, admin.is_lecturer, admin.is_administrator),
            (False, False, True),
        )

    def test_role_based_admin_is_independent_of_staff_flag(self):
        """A CRS administrator is not automatically a Django admin-site user."""
        admin = User.objects.create_user("a2", "a2@crs.test", "pw", role=Role.ADMIN)
        self.assertTrue(admin.is_administrator)
        self.assertFalse(admin.is_staff)

    def test_display_name_prefers_full_name(self):
        user = User.objects.create_user(
            "s2", "s2@crs.test", "pw", role=Role.STUDENT, first_name="Sinta", last_name="Wijaya"
        )
        self.assertEqual(user.display_name, "Sinta Wijaya")

    def test_display_name_falls_back_to_username(self):
        user = User.objects.create_user("s3", "s3@crs.test", "pw", role=Role.STUDENT)
        self.assertEqual(user.display_name, "s3")

    def test_email_must_be_unique(self):
        User.objects.create_user("s4", "dupe@crs.test", "pw", role=Role.STUDENT)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("s5", "dupe@crs.test", "pw", role=Role.STUDENT)

    def test_invalid_role_rejected_by_database_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("s6", "s6@crs.test", "pw", role="WIZARD")

    def test_dashboard_url_name_matches_role(self):
        cases = {
            Role.STUDENT: "accounts:student_dashboard",
            Role.LECTURER: "accounts:lecturer_dashboard",
            Role.ADMIN: "accounts:admin_dashboard",
        }
        for index, (role, expected) in enumerate(cases.items()):
            with self.subTest(role=role):
                user = User.objects.create_user(f"u{index}", f"u{index}@crs.test", "pw", role=role)
                self.assertEqual(user.dashboard_url_name, expected)

    def test_create_superuser_defaults_to_admin_role(self):
        root = User.objects.create_superuser("root", "root@crs.test", "pw")
        self.assertEqual(root.role, Role.ADMIN)
        self.assertTrue(root.is_staff)
        self.assertTrue(root.is_superuser)


class ManagerHelperTests(TestCase):
    def test_create_student_also_creates_profile(self):
        user = User.objects.create_student("2026099", "x@crs.test", "pw", enrollment_year=2025)

        self.assertEqual(user.role, Role.STUDENT)
        self.assertEqual(user.student_profile.student_number, "2026099")
        self.assertEqual(user.student_profile.enrollment_year, 2025)
        self.assertEqual(user.student_profile.status, StudentStatus.ACTIVE)

    def test_create_lecturer_also_creates_profile(self):
        user = User.objects.create_lecturer(
            "L-9", "y@crs.test", "pw", title=LecturerTitle.PROFESSOR
        )

        self.assertEqual(user.role, Role.LECTURER)
        self.assertEqual(user.lecturer_profile.staff_number, "L-9")
        self.assertEqual(user.lecturer_profile.title, LecturerTitle.PROFESSOR)

    def test_student_number_defaults_to_username(self):
        user = User.objects.create_student("2026100", "z@crs.test", "pw")
        self.assertEqual(user.student_profile.student_number, "2026100")

    def test_profile_creation_is_atomic(self):
        """A duplicate student number must not leave an orphaned user behind."""
        User.objects.create_student("2026101", "a@crs.test", "pw")

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_student(
                "different-username", "b@crs.test", "pw", student_number="2026101"
            )

        self.assertFalse(User.objects.filter(username="different-username").exists())


class StudentProfileTests(TestCase):
    def test_only_active_students_may_register(self):
        """Backs rule R7 (PLAN.md §5)."""
        user = User.objects.create_student("2026102", "c@crs.test", "pw")
        profile = user.student_profile

        self.assertTrue(profile.may_register)

        for blocked in (
            StudentStatus.PROBATION,
            StudentStatus.SUSPENDED,
            StudentStatus.GRADUATED,
            StudentStatus.WITHDRAWN,
        ):
            with self.subTest(status=blocked):
                profile.status = blocked
                self.assertFalse(profile.may_register)

    def test_profile_deleted_with_user(self):
        user = User.objects.create_student("2026103", "d@crs.test", "pw")
        user.delete()
        self.assertFalse(StudentProfile.objects.filter(student_number="2026103").exists())

    def test_lecturer_profile_deleted_with_user(self):
        user = User.objects.create_lecturer("L-10", "e@crs.test", "pw")
        user.delete()
        self.assertFalse(LecturerProfile.objects.filter(staff_number="L-10").exists())
