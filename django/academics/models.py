"""
The academic catalogue: who teaches what, when, and with what prerequisites.

This is reference data. It describes what *could* be registered for; the
``registration`` app (Phase 3) records what actually was, and owns the rule
engine. Keeping the two apart means the catalogue can be edited by
administrators without touching enrollment logic.

The shapes here are driven by the registration rules in PLAN.md §5:

* ``Meeting`` exists as discrete rows rather than a free-text schedule string
  so timetable clashes (R5) can be detected reliably.
* ``PrerequisiteRule`` is an explicit through-model rather than a plain M2M so
  a rule can demand better than a bare pass (R3).
* ``Term`` carries the registration window (R1) and the credit ceiling (R4).
"""

from datetime import time

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .grades import DEFAULT_PREREQUISITE_GRADE, Grade

code_validator = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9\-]*$",
    message=_("Use upper-case letters, digits and hyphens only."),
)


def time_ranges_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """
    Whether two time ranges genuinely overlap.

    Half-open comparison, so ranges that merely touch do not overlap:
    10:00–11:00 and 11:00–12:00 are back-to-back classes, not a clash. This is
    the core of rule R5 and the single most likely place for an off-by-one
    error, so it lives in one function with its own tests.
    """
    return a_start < b_end and b_start < a_end


class DayOfWeek(models.IntegerChoices):
    """Matches ``datetime.date.weekday()`` — Monday is 0."""

    MONDAY = 0, _("Monday")
    TUESDAY = 1, _("Tuesday")
    WEDNESDAY = 2, _("Wednesday")
    THURSDAY = 3, _("Thursday")
    FRIDAY = 4, _("Friday")
    SATURDAY = 5, _("Saturday")
    SUNDAY = 6, _("Sunday")


class DegreeLevel(models.TextChoices):
    BACHELOR = "BACHELOR", _("Bachelor's")
    MASTER = "MASTER", _("Master's")
    DOCTORATE = "DOCTORATE", _("Doctorate")


class Department(models.Model):
    """An academic department. Owns courses and programs."""

    code = models.CharField(_("code"), max_length=10, unique=True, validators=[code_validator])
    name = models.CharField(_("name"), max_length=120)

    class Meta:
        ordering = ["code"]
        verbose_name = _("department")
        verbose_name_plural = _("departments")

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Program(models.Model):
    """A degree program a student is enrolled in."""

    code = models.CharField(_("code"), max_length=20, unique=True, validators=[code_validator])
    name = models.CharField(_("name"), max_length=150)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programs")
    degree_level = models.CharField(
        _("degree level"),
        max_length=10,
        choices=DegreeLevel.choices,
        default=DegreeLevel.BACHELOR,
    )
    credits_required = models.PositiveSmallIntegerField(
        _("credits required to graduate"),
        default=144,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
    )

    class Meta:
        ordering = ["code"]
        verbose_name = _("program")
        verbose_name_plural = _("programs")

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Course(models.Model):
    """
    A course in the catalogue.

    A ``Course`` is the syllabus; a ``Section`` is a specific offering of it in
    a term. Students register for sections, not courses.
    """

    code = models.CharField(_("code"), max_length=12, unique=True, validators=[code_validator])
    title = models.CharField(_("title"), max_length=150)
    description = models.TextField(_("description"), blank=True)
    credits = models.PositiveSmallIntegerField(
        _("credits"), validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="courses")
    level = models.PositiveSmallIntegerField(
        _("level"),
        default=100,
        help_text=_("Nominal year of study: 100, 200, 300, 400."),
        db_index=True,
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Inactive courses stay on record but cannot be offered."),
    )

    prerequisites = models.ManyToManyField(
        "self",
        through="PrerequisiteRule",
        through_fields=("course", "prerequisite"),
        symmetrical=False,
        related_name="required_for",
        blank=True,
    )

    class Meta:
        ordering = ["code"]
        verbose_name = _("course")
        verbose_name_plural = _("courses")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(credits__gte=1), name="academics_course_credits_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"

    @property
    def label(self) -> str:
        """Short form for dense listings: ``CS201 Data Structures (4 cr)``."""
        return f"{self.code} {self.title} ({self.credits} cr)"


class PrerequisiteRule(models.Model):
    """
    "To take ``course``, you must first have passed ``prerequisite``."

    An explicit through-model rather than a plain M2M, because a rule can
    demand better than a bare pass — see ``minimum_grade``.
    """

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="prerequisite_rules")
    prerequisite = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name="prerequisite_for_rules"
    )
    minimum_grade = models.CharField(
        _("minimum grade"),
        max_length=2,
        choices=Grade.choices,
        default=DEFAULT_PREREQUISITE_GRADE,
        help_text=_("The lowest grade in the prerequisite that satisfies this rule."),
    )

    class Meta:
        ordering = ["course__code", "prerequisite__code"]
        verbose_name = _("prerequisite rule")
        verbose_name_plural = _("prerequisite rules")
        constraints = [
            models.UniqueConstraint(
                fields=["course", "prerequisite"], name="academics_prerequisite_unique"
            ),
            # A course cannot require itself. Deeper cycles are not expressible
            # as a database constraint and are caught in clean() instead.
            models.CheckConstraint(
                condition=~models.Q(course=models.F("prerequisite")),
                name="academics_prerequisite_not_self",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.course.code} requires {self.prerequisite.code} (min {self.minimum_grade})"

    def clean(self):
        """
        Reject cycles.

        A prerequisite cycle makes a course permanently unregisterable, and the
        check in R3 would recurse forever. The database can only catch the
        self-reference case, so walk the graph here.
        """
        super().clean()
        if not self.course_id or not self.prerequisite_id:
            return

        if self.course_id == self.prerequisite_id:
            raise ValidationError({"prerequisite": _("A course cannot be its own prerequisite.")})

        # Would adding this rule make `course` reachable from `prerequisite`?
        seen: set[int] = set()
        frontier = [self.prerequisite_id]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            if current == self.course_id:
                raise ValidationError(
                    {
                        "prerequisite": _(
                            "This would create a prerequisite cycle: %(prereq)s already "
                            "depends on %(course)s."
                        )
                        % {
                            "prereq": self.prerequisite.code,
                            "course": self.course.code,
                        }
                    }
                )
            frontier.extend(
                PrerequisiteRule.objects.filter(course_id=current).values_list(
                    "prerequisite_id", flat=True
                )
            )


class Term(models.Model):
    """
    An academic term, and the registration window that governs it.

    The window backs rule R1 and ``max_credits_per_student`` backs R4. Both are
    per-term rather than global so the institution can run a shorter window or
    a lower ceiling for a summer term without code changes.
    """

    code = models.CharField(
        _("code"),
        max_length=20,
        unique=True,
        validators=[code_validator],
        help_text=_("e.g. 2026-FALL"),
    )
    name = models.CharField(_("name"), max_length=60, help_text=_("e.g. Fall 2026"))

    start_date = models.DateField(_("term starts"))
    end_date = models.DateField(_("term ends"))

    registration_opens_at = models.DateTimeField(_("registration opens"))
    registration_closes_at = models.DateTimeField(_("registration closes"))

    is_active = models.BooleanField(
        _("current term"),
        default=False,
        help_text=_("The term CRS treats as current. Only one term may be current."),
    )
    max_credits_per_student = models.PositiveSmallIntegerField(
        _("credit ceiling per student"),
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )

    class Meta:
        ordering = ["-start_date"]
        verbose_name = _("term")
        verbose_name_plural = _("terms")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="academics_term_ends_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(registration_closes_at__gt=models.F("registration_opens_at")),
                name="academics_term_registration_window_ordered",
            ),
            # A partial unique index: at most one row may have is_active=True.
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="academics_term_single_active",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def registration_is_open(self) -> bool:
        """Rule R1: is the registration window open right now?"""
        return self.registration_opens_at <= timezone.now() <= self.registration_closes_at

    @property
    def registration_has_closed(self) -> bool:
        return timezone.now() > self.registration_closes_at

    @property
    def registration_status(self) -> str:
        """Human-readable window state, for listings and the admin."""
        now = timezone.now()
        if now < self.registration_opens_at:
            return _("Not yet open")
        if now > self.registration_closes_at:
            return _("Closed")
        return _("Open")


class Section(models.Model):
    """
    A specific offering of a course in a term — what students register for.

    Seat counts are deliberately *not* stored here. Phase 3 derives them by
    counting ``Enrollment`` rows inside a transaction, so a cached counter
    cannot drift from reality under concurrent registration (PLAN.md §8).
    """

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="sections")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="sections")
    section_code = models.CharField(
        _("section"), max_length=5, validators=[code_validator], help_text=_("e.g. 01")
    )
    lecturer = models.ForeignKey(
        "accounts.LecturerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sections",
        help_text=_("Leave blank for a section whose lecturer is still to be announced."),
    )
    capacity = models.PositiveSmallIntegerField(
        _("capacity"),
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
        help_text=_("Number of seats. Backs rule R6."),
    )

    class Meta:
        ordering = ["term", "course__code", "section_code"]
        verbose_name = _("section")
        verbose_name_plural = _("sections")
        constraints = [
            models.UniqueConstraint(
                fields=["course", "term", "section_code"], name="academics_section_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(capacity__gte=1), name="academics_section_capacity_positive"
            ),
        ]
        indexes = [models.Index(fields=["term", "course"], name="academics_section_term_course")]

    def __str__(self) -> str:
        return f"{self.course.code}-{self.section_code} ({self.term.code})"

    @property
    def credits(self) -> int:
        """Convenience passthrough — R4 sums credits over sections."""
        return self.course.credits

    @property
    def lecturer_name(self) -> str:
        return self.lecturer.user.display_name if self.lecturer else str(_("To be announced"))

    def clashes_with(self, other: "Section") -> bool:
        """
        Whether any meeting of this section overlaps any meeting of ``other``.

        The building block of rule R5. Callers that check many sections should
        prefetch ``meetings`` — this walks both sets.
        """
        return any(
            mine.overlaps(theirs) for mine in self.meetings.all() for theirs in other.meetings.all()
        )


class Meeting(models.Model):
    """
    One weekly time slot for a section.

    Discrete rows, rather than a "Mon/Wed 10-12" string, so overlaps are
    computable. A section that meets twice a week has two rows.
    """

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="meetings")
    day_of_week = models.PositiveSmallIntegerField(_("day"), choices=DayOfWeek.choices)
    start_time = models.TimeField(_("starts"))
    end_time = models.TimeField(_("ends"))
    room = models.CharField(_("room"), max_length=40, blank=True)

    class Meta:
        ordering = ["day_of_week", "start_time"]
        verbose_name = _("meeting")
        verbose_name_plural = _("meetings")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="academics_meeting_ends_after_start",
            ),
            models.UniqueConstraint(
                fields=["section", "day_of_week", "start_time"],
                name="academics_meeting_unique_slot",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.get_day_of_week_display()} "
            f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
            f"{f' in {self.room}' if self.room else ''}"
        )

    def overlaps(self, other: "Meeting") -> bool:
        """Whether this meeting and ``other`` collide on the timetable."""
        if self.day_of_week != other.day_of_week:
            return False
        return time_ranges_overlap(self.start_time, self.end_time, other.start_time, other.end_time)

    def clean(self):
        """A section cannot meet in two places at once."""
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": _("The end time must be after the start time.")})

        if not self.section_id:
            return

        siblings = self.section.meetings.exclude(pk=self.pk)
        for sibling in siblings:
            if self.overlaps(sibling):
                raise ValidationError(
                    _("This clashes with another meeting of the same section: %(other)s.")
                    % {"other": sibling}
                )
