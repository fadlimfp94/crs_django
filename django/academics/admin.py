"""
Django admin for the academic catalogue.

Phase 4 builds purpose-made administrator screens for the things that need
care (registration windows, enrollment overrides). Until then this *is* the
catalogue management interface, and Phase 2's "done when" is that a seeded
catalogue is browsable here — so it is configured properly rather than
registered bare.

Two deliberate choices:

* ``MeetingInline`` sits on ``Section``, not the other way round. A meeting is
  meaningless without its section, and editing a section's timetable in one
  screen is what an administrator actually wants to do.
* Forms go through ``full_clean`` (the admin's default), so ``Meeting.clean``
  and ``PrerequisiteRule.clean`` run here. That is where the cycle and
  self-clash checks live, and the admin is exactly where a human is most
  likely to trip them.
"""

from django.contrib import admin
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from .models import (
    Course,
    Department,
    Meeting,
    PrerequisiteRule,
    Program,
    Section,
    Term,
)


class ProgramInline(admin.TabularInline):
    model = Program
    fields = ("code", "name", "degree_level", "credits_required")
    extra = 0
    show_change_link = True


class PrerequisiteRuleInline(admin.TabularInline):
    """The rules for taking *this* course — not the courses this one unlocks."""

    model = PrerequisiteRule
    fk_name = "course"
    fields = ("prerequisite", "minimum_grade")
    autocomplete_fields = ("prerequisite",)
    extra = 1
    verbose_name = _("prerequisite")
    verbose_name_plural = _("prerequisites for this course")


class SectionInline(admin.TabularInline):
    model = Section
    fields = ("term", "section_code", "lecturer", "capacity")
    autocomplete_fields = ("term", "lecturer")
    extra = 0
    show_change_link = True


class MeetingInline(admin.TabularInline):
    model = Meeting
    fields = ("day_of_week", "start_time", "end_time", "room")
    extra = 1


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "program_count", "course_count")
    search_fields = ("code", "name")
    inlines = (ProgramInline,)
    # An aggregate annotation clears Meta.ordering, which leaves the changelist
    # paginating an unordered queryset. State the ordering explicitly.
    ordering = ("code",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_programs=Count("programs", distinct=True))
            .annotate(_courses=Count("courses", distinct=True))
        )

    @admin.display(description=_("programs"), ordering="_programs")
    def program_count(self, obj: Department) -> int:
        return obj._programs

    @admin.display(description=_("courses"), ordering="_courses")
    def course_count(self, obj: Department) -> int:
        return obj._courses


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "department", "degree_level", "credits_required")
    list_filter = ("degree_level", "department")
    search_fields = ("code", "name")
    list_select_related = ("department",)
    autocomplete_fields = ("department",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "department", "level", "credits", "is_active")
    list_filter = ("is_active", "department", "level", "credits")
    search_fields = ("code", "title", "description")
    list_select_related = ("department",)
    autocomplete_fields = ("department",)
    list_editable = ("is_active",)
    inlines = (PrerequisiteRuleInline, SectionInline)
    fieldsets = (
        (None, {"fields": ("code", "title", "description")}),
        (_("Classification"), {"fields": ("department", "level", "credits", "is_active")}),
    )


@admin.register(PrerequisiteRule)
class PrerequisiteRuleAdmin(admin.ModelAdmin):
    """
    Editable standalone as well as inline, so the whole prerequisite graph can
    be reviewed in one list rather than course by course.
    """

    list_display = ("course", "prerequisite", "minimum_grade")
    list_filter = ("minimum_grade", "course__department")
    search_fields = ("course__code", "course__title", "prerequisite__code", "prerequisite__title")
    list_select_related = ("course", "prerequisite")
    autocomplete_fields = ("course", "prerequisite")


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "start_date",
        "end_date",
        "window",
        "is_active",
        "max_credits_per_student",
        "section_count",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("-start_date",)  # see DepartmentAdmin.ordering
    fieldsets = (
        (None, {"fields": ("code", "name", "is_active")}),
        (_("Term dates"), {"fields": ("start_date", "end_date")}),
        (
            _("Registration"),
            {
                "fields": (
                    "registration_opens_at",
                    "registration_closes_at",
                    "max_credits_per_student",
                ),
                "description": _(
                    "The window backs rule R1 and the ceiling backs rule R4. "
                    "Changing these changes what students can do right now."
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_sections=Count("sections"))

    @admin.display(description=_("registration"))
    def window(self, obj: Term) -> str:
        return obj.registration_status

    @admin.display(description=_("sections"), ordering="_sections")
    def section_count(self, obj: Term) -> int:
        return obj._sections


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "course", "term", "section_code", "lecturer", "capacity", "schedule")
    list_filter = ("term", "course__department", "course__level")
    search_fields = (
        "course__code",
        "course__title",
        "section_code",
        "lecturer__staff_number",
        "lecturer__user__first_name",
        "lecturer__user__last_name",
    )
    list_select_related = ("course", "term", "lecturer__user")
    autocomplete_fields = ("course", "term", "lecturer")
    inlines = (MeetingInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("meetings")

    @admin.display(description=_("schedule"))
    def schedule(self, obj: Section) -> str:
        meetings = obj.meetings.all()
        if not meetings:
            return "—"
        return "; ".join(str(meeting) for meeting in meetings)


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    """
    Normally edited inline on a section. Registered standalone as well so
    room and time clashes can be reviewed across the whole timetable.
    """

    list_display = ("section", "day_of_week", "start_time", "end_time", "room")
    list_filter = ("day_of_week", "section__term", "room")
    search_fields = ("section__course__code", "section__course__title", "room")
    list_select_related = ("section__course", "section__term")
    autocomplete_fields = ("section",)
