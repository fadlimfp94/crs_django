"""
The institution's grade scale.

Lives in ``academics`` rather than ``registration`` because it is reference
data: prerequisite rules reference it (a rule may demand better than a bare
pass), and Phase 3 enrollments record it.

Grades are compared by grade point, never as strings — ``"C+" > "C-"``
happens to be true lexicographically but ``"B-" > "B+"`` is not, so string
comparison silently produces wrong answers for rule R3.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Grade(models.TextChoices):
    # Label and value are deliberately identical, hyphen and all. A typographic
    # minus sign in the label would read better but would stop the label from
    # matching the stored value, which is a trap for anyone comparing the two.
    A = "A", _("A")
    A_MINUS = "A-", _("A-")
    B_PLUS = "B+", _("B+")
    B = "B", _("B")
    B_MINUS = "B-", _("B-")
    C_PLUS = "C+", _("C+")
    C = "C", _("C")
    C_MINUS = "C-", _("C-")
    D = "D", _("D")
    F = "F", _("F")


#: Grade points on a 4.0 scale.
GRADE_POINTS: dict[str, float] = {
    Grade.A: 4.0,
    Grade.A_MINUS: 3.7,
    Grade.B_PLUS: 3.3,
    Grade.B: 3.0,
    Grade.B_MINUS: 2.7,
    Grade.C_PLUS: 2.3,
    Grade.C: 2.0,
    Grade.C_MINUS: 1.7,
    Grade.D: 1.0,
    Grade.F: 0.0,
}

#: The lowest grade that earns credit for a course.
PASSING_GRADE = Grade.D

#: Default minimum grade a prerequisite must have been passed with.
DEFAULT_PREREQUISITE_GRADE = Grade.D


def grade_points(grade: str | None) -> float:
    """Grade points for ``grade``. An unknown or missing grade scores 0.0."""
    if not grade:
        return 0.0
    return GRADE_POINTS.get(grade, 0.0)


def is_passing(grade: str | None) -> bool:
    """Whether ``grade`` earns credit for the course."""
    return grade_points(grade) >= grade_points(PASSING_GRADE)


def meets_minimum(earned: str | None, minimum: str | None) -> bool:
    """
    Whether ``earned`` satisfies a requirement of at least ``minimum``.

    Backs registration rule R3. With no minimum specified, any passing grade
    will do.
    """
    if not minimum:
        return is_passing(earned)
    return grade_points(earned) >= grade_points(minimum)
