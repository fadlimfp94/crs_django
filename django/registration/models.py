"""
Who is enrolled in what.

The academic catalogue (``academics``) describes what could be registered
for; this app records what actually was, and — in ``services.py`` — owns the
rule engine that decides whether a registration is allowed (PLAN.md §5).

One ``Enrollment`` row exists per (student, section) pair for the entire life
of that relationship. Dropping and re-registering for the same section
updates the existing row rather than creating a new one — a student retaking
a course does so through a *different* ``Section`` (a later term's offering),
so this needs no special-casing.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from academics.grades import Grade


class EnrollmentStatus(models.TextChoices):
    ENROLLED = "ENROLLED", _("Enrolled")
    WAITLISTED = "WAITLISTED", _("Waitlisted")
    DROPPED = "DROPPED", _("Dropped")
    COMPLETED = "COMPLETED", _("Completed")


#: Statuses that occupy a place in the student's schedule for this term —
#: shared by rule R2 (no double-registration) and R4 (credit limit).
ACTIVE_STATUSES = (EnrollmentStatus.ENROLLED, EnrollmentStatus.WAITLISTED)


class Enrollment(models.Model):
    """A student's registration in one section, and its history."""

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.PROTECT, related_name="enrollments"
    )
    section = models.ForeignKey(
        "academics.Section", on_delete=models.PROTECT, related_name="enrollments"
    )
    status = models.CharField(
        _("status"), max_length=10, choices=EnrollmentStatus.choices, db_index=True
    )
    waitlist_position = models.PositiveSmallIntegerField(
        _("waitlist position"),
        null=True,
        blank=True,
        help_text=_("1 is next in line. Set only while status is WAITLISTED."),
    )
    grade = models.CharField(
        _("grade"),
        max_length=2,
        choices=Grade.choices,
        blank=True,
        default="",
        help_text=_("Recorded once status is COMPLETED."),
    )
    registered_at = models.DateTimeField(_("registered at"))
    dropped_at = models.DateTimeField(_("dropped at"), null=True, blank=True)

    class Meta:
        ordering = ["-registered_at"]
        verbose_name = _("enrollment")
        verbose_name_plural = _("enrollments")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "section"], name="registration_enrollment_unique"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=EnrollmentStatus.WAITLISTED, waitlist_position__isnull=False)
                    | (
                        ~models.Q(status=EnrollmentStatus.WAITLISTED)
                        & models.Q(waitlist_position__isnull=True)
                    )
                ),
                name="registration_enrollment_waitlist_position_consistency",
            ),
            models.CheckConstraint(
                condition=(models.Q(status=EnrollmentStatus.COMPLETED) | models.Q(grade="")),
                name="registration_enrollment_grade_requires_completed",
            ),
        ]
        indexes = [
            models.Index(fields=["section", "status"], name="registration_section_status"),
            models.Index(fields=["student", "status"], name="registration_student_status"),
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.section} ({self.get_status_display()})"
