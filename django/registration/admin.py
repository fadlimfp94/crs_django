"""
Django admin for registration.

Phase 3 has no purpose-built administration screens — those belong to
Phase 4 — so this is registered properly enough to inspect and correct
enrollments by hand in the meantime.
"""

from django.contrib import admin

from .models import Enrollment


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "section", "status", "waitlist_position", "grade", "registered_at")
    list_filter = ("status", "section__term")
    search_fields = (
        "student__student_number",
        "student__user__first_name",
        "student__user__last_name",
        "section__course__code",
        "section__course__title",
    )
    list_select_related = ("student__user", "section__course", "section__term")
    autocomplete_fields = ("student", "section")
