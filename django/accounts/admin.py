"""
Django admin for accounts.

Phase 1 has no purpose-built administration screens, so the admin site is the
real management interface for accounts. It is worth configuring properly:
searchable, filterable, and showing the profile inline that matches the user's
role rather than both at once.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .forms import CRSUserChangeForm, CRSUserCreationForm
from .models import LecturerProfile, Role, StudentProfile, User


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    can_delete = False
    verbose_name_plural = _("Student profile")
    fields = ("student_number", "program", "enrollment_year", "status")
    autocomplete_fields = ("program",)
    # A user has at most one profile, so cap the formset at one form. Without
    # this the admin offers spare "add another" forms that can never be valid.
    max_num = 1


class LecturerProfileInline(admin.StackedInline):
    model = LecturerProfile
    can_delete = False
    verbose_name_plural = _("Lecturer profile")
    fields = ("staff_number", "title", "department")
    autocomplete_fields = ("department",)
    max_num = 1


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = CRSUserChangeForm
    add_form = CRSUserCreationForm

    list_display = ("username", "display_name", "email", "role", "is_active", "last_login")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (
            _("CRS role"),
            {
                "fields": ("role",),
                "description": _(
                    "Selects the dashboard and permissions. Independent of "
                    "&ldquo;Staff status&rdquo;, which grants access to this admin site."
                ),
            },
        ),
        (
            _("Permissions"),
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
                "classes": ("collapse",),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined"), "classes": ("collapse",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "first_name", "last_name", "role"),
                "description": _(
                    "Save to continue — the role-specific profile can be filled in "
                    "on the next screen."
                ),
            },
        ),
        (_("Password"), {"classes": ("wide",), "fields": ("password1", "password2")}),
    )

    @admin.display(description=_("name"), ordering="first_name")
    def display_name(self, obj: User) -> str:
        return obj.display_name

    def get_inlines(self, request, obj=None):
        """Show only the profile inline matching this user's role."""
        if obj is None:
            return ()  # Creation is two-step; the profile appears after the first save.
        if obj.role == Role.STUDENT:
            return (StudentProfileInline,)
        if obj.role == Role.LECTURER:
            return (LecturerProfileInline,)
        return ()


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("student_number", "user", "program", "status", "enrollment_year")
    list_filter = ("status", "enrollment_year", "program__department", "program")
    search_fields = ("student_number", "user__username", "user__first_name", "user__last_name")
    list_select_related = ("user", "program")
    autocomplete_fields = ("user", "program")


@admin.register(LecturerProfile)
class LecturerProfileAdmin(admin.ModelAdmin):
    list_display = ("staff_number", "user", "title", "department")
    list_filter = ("title", "department")
    search_fields = ("staff_number", "user__username", "user__first_name", "user__last_name")
    list_select_related = ("user", "department")
    autocomplete_fields = ("user", "department")
