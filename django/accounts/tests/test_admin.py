"""
Tests for the accounts admin.

Phase 1 has no purpose-built administration screens, so the admin site is the
only way to manage accounts — its behaviour is worth pinning down.
"""

from django.contrib.admin.sites import site
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.admin import LecturerProfileInline, StudentProfileInline, UserAdmin
from accounts.models import User


class UserAdminInlineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_student("2026001", "s@crs.test", "pw")
        cls.lecturer = User.objects.create_lecturer("L-1001", "l@crs.test", "pw")
        cls.admin_user = User.objects.create_superuser("admin", "a@crs.test", "pw")

    def setUp(self):
        self.model_admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        self.request.user = self.admin_user

    def test_student_gets_only_the_student_inline(self):
        self.assertEqual(
            self.model_admin.get_inlines(self.request, self.student), (StudentProfileInline,)
        )

    def test_lecturer_gets_only_the_lecturer_inline(self):
        self.assertEqual(
            self.model_admin.get_inlines(self.request, self.lecturer), (LecturerProfileInline,)
        )

    def test_administrator_gets_no_profile_inline(self):
        self.assertEqual(self.model_admin.get_inlines(self.request, self.admin_user), ())

    def test_add_form_shows_no_inlines(self):
        """Creation is two-step; the profile appears only after the first save."""
        self.assertEqual(self.model_admin.get_inlines(self.request, None), ())

    def test_only_one_profile_form_is_offered(self):
        """A user has at most one profile — max_num must prevent spare forms."""
        formset_class = StudentProfileInline(User, site).get_formset(self.request, self.student)
        formset = formset_class(instance=self.student)

        self.assertEqual(formset.max_num, 1)
        self.assertEqual(len(formset.forms), 1)

    def test_profile_form_offered_when_profile_is_missing(self):
        """A student without a profile row must still get a form to create one."""
        self.student.student_profile.delete()
        self.student.refresh_from_db()

        formset_class = StudentProfileInline(User, site).get_formset(self.request, self.student)
        formset = formset_class(instance=self.student)

        self.assertEqual(len(formset.forms), 1)


class UserAdminViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_student("2026001", "s@crs.test", "pw")
        cls.admin_user = User.objects.create_superuser("admin", "a@crs.test", "pw")

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_changelist_renders_and_lists_users(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026001")

    def test_change_page_renders_the_student_inline(self):
        response = self.client.get(reverse("admin:accounts_user_change", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student_profile")
        self.assertNotContains(response, "lecturer_profile")

    def test_add_page_requires_role(self):
        response = self.client.get(reverse("admin:accounts_user_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="role"')

    def test_profile_changelists_render(self):
        for url_name in (
            "admin:accounts_studentprofile_changelist",
            "admin:accounts_lecturerprofile_changelist",
        ):
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

    def test_non_staff_user_cannot_reach_the_admin_site(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("admin:accounts_user_changelist"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
