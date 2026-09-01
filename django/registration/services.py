"""
The registration rule engine — PLAN.md §5, rules R1 through R7.

Each rule is one small function that raises ``RegistrationError`` on failure.
``register()`` runs them in the literal R1→R7 order from the plan. Keeping
each rule in its own function means each has exactly one implementation,
shared between a fresh registration and a waitlist promotion recheck.
"""

import time
from functools import wraps

from django.db import OperationalError, transaction
from django.utils import timezone

from academics.grades import meets_minimum
from academics.models import Section

from .models import ACTIVE_STATUSES, Enrollment, EnrollmentStatus

_LOCK_RETRY_ATTEMPTS = 5
_LOCK_RETRY_DELAY_SECONDS = 0.05


def _retry_on_lock(func):
    """
    Retry on SQLite's "database table is locked".

    In shared-cache mode SQLite deliberately does *not* invoke the busy
    handler for this error, to avoid a possible deadlock between two
    connections in the same process (documented SQLite behaviour) — so the
    ~20s busy timeout in settings/base.py never kicks in here. The caller has
    to retry itself. A real writer conflict resolves in microseconds, so a
    handful of short retries is enough; on PostgreSQL this never triggers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            try:
                return func(*args, **kwargs)
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == _LOCK_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(_LOCK_RETRY_DELAY_SECONDS)

    return wrapper


class RegistrationError(Exception):
    """
    A registration or drop request was refused.

    ``rule`` is ``"R1"``–``"R7"`` when a numbered rule failed, or ``None`` for
    a non-rule failure (e.g. dropping a section you're not in). Callers such
    as Phase 5's API can build ``{"rule": rule, "detail": message}`` directly
    from this without parsing the message text.
    """

    def __init__(self, message: str, *, rule: str | None = None):
        super().__init__(message)
        self.rule = rule


def _check_registration_window(term) -> None:
    """R1: the term's registration window must be open right now."""
    if not term.registration_is_open:
        raise RegistrationError(f"Registration for {term} is not currently open.", rule="R1")


def _check_not_already_registered(student, section) -> None:
    """R2: no active enrollment in another section of the same course this term."""
    if Enrollment.objects.filter(
        student=student,
        section__course=section.course,
        section__term=section.term,
        status__in=ACTIVE_STATUSES,
    ).exists():
        raise RegistrationError(
            f"You are already registered or waitlisted for {section.course.code} this term.",
            rule="R2",
        )


def _check_prerequisites(student, course) -> None:
    """R3: every prerequisite rule for ``course`` must be satisfied."""
    for rule in course.prerequisite_rules.select_related("prerequisite"):
        best_grade = (
            Enrollment.objects.filter(
                student=student,
                section__course=rule.prerequisite,
                status=EnrollmentStatus.COMPLETED,
            )
            .exclude(grade="")
            .values_list("grade", flat=True)
        )
        if not any(meets_minimum(grade, rule.minimum_grade) for grade in best_grade):
            raise RegistrationError(
                f"{course.code} requires {rule.prerequisite.code} "
                f"with a minimum grade of {rule.minimum_grade}.",
                rule="R3",
            )


def _check_credit_limit(student, section, term) -> None:
    """
    R4: active credits this term, plus this section, must not exceed the ceiling.

    Excludes ``section`` itself from the "current" sum — during a waitlist
    promotion recheck, the candidate's own row is still WAITLISTED (an active
    status) for this very section, and counting it twice would double-charge
    the credits it's already accounted for.
    """
    current_credits = sum(
        enrollment.section.credits
        for enrollment in Enrollment.objects.filter(
            student=student, section__term=term, status__in=ACTIVE_STATUSES
        )
        .exclude(section=section)
        .select_related("section__course")
    )
    if current_credits + section.credits > term.max_credits_per_student:
        raise RegistrationError(
            f"Adding {section} would exceed the {term.max_credits_per_student}-credit "
            f"limit for {term}.",
            rule="R4",
        )


def _check_no_clash(student, section) -> None:
    """R5: no timetable clash with a section the student is currently enrolled in."""
    enrolled_sections = Section.objects.filter(
        enrollments__student=student,
        enrollments__status=EnrollmentStatus.ENROLLED,
        term=section.term,
    ).prefetch_related("meetings")
    for other in enrolled_sections:
        if section.clashes_with(other):
            raise RegistrationError(f"{section} clashes with {other} on your timetable.", rule="R5")


def _determine_seat_outcome(section) -> tuple[str, int | None]:
    """R6: a full section waitlists rather than refuses. Never raises."""
    if _seats_taken(section) < section.capacity:
        return EnrollmentStatus.ENROLLED, None
    return EnrollmentStatus.WAITLISTED, _next_waitlist_position(section)


def _check_good_standing(student) -> None:
    """R7: only students in good academic standing may register."""
    if not student.may_register:
        raise RegistrationError("Your academic standing does not permit registration.", rule="R7")


def _seats_taken(section) -> int:
    return Enrollment.objects.filter(section=section, status=EnrollmentStatus.ENROLLED).count()


def _next_waitlist_position(section) -> int:
    last = (
        Enrollment.objects.filter(section=section, status=EnrollmentStatus.WAITLISTED)
        .order_by("-waitlist_position")
        .values_list("waitlist_position", flat=True)
        .first()
    )
    return (last or 0) + 1


def _renumber_waitlist(section) -> None:
    """Close gaps left by a drop or promotion so positions stay 1, 2, 3, ..."""
    waitlisted = Enrollment.objects.filter(
        section=section, status=EnrollmentStatus.WAITLISTED
    ).order_by("waitlist_position")
    for position, enrollment in enumerate(waitlisted, start=1):
        if enrollment.waitlist_position != position:
            enrollment.waitlist_position = position
            enrollment.save(update_fields=["waitlist_position"])


def _promotion_blocked(student, section) -> bool:
    """Re-run the rules that can change between joining a waitlist and a seat opening."""
    try:
        _check_credit_limit(student, section, section.term)
        _check_no_clash(student, section)
        _check_good_standing(student)
    except RegistrationError:
        return True
    return False


@_retry_on_lock
@transaction.atomic
def register(student, section) -> Enrollment:
    """Attempt to register ``student`` for ``section``, applying rules R1–R7 in order."""
    section = (
        Section.objects.select_for_update().select_related("term", "course").get(pk=section.pk)
    )
    term = section.term

    _check_registration_window(term)  # R1
    _check_not_already_registered(student, section)  # R2
    _check_prerequisites(student, section.course)  # R3
    _check_credit_limit(student, section, term)  # R4
    _check_no_clash(student, section)  # R5
    status, waitlist_position = _determine_seat_outcome(section)  # R6
    _check_good_standing(student)  # R7

    enrollment, _created = Enrollment.objects.update_or_create(
        student=student,
        section=section,
        defaults={
            "status": status,
            "waitlist_position": waitlist_position,
            "registered_at": timezone.now(),
            "dropped_at": None,
        },
    )
    return enrollment


@_retry_on_lock
@transaction.atomic
def drop(student, section) -> Enrollment:
    """Drop ``student`` from ``section``, promoting a waitlisted student if a seat frees up."""
    try:
        enrollment = Enrollment.objects.select_for_update().get(
            student=student, section=section, status__in=ACTIVE_STATUSES
        )
    except Enrollment.DoesNotExist:
        raise RegistrationError("You are not registered for this section.") from None

    was_enrolled = enrollment.status == EnrollmentStatus.ENROLLED
    enrollment.status = EnrollmentStatus.DROPPED
    enrollment.dropped_at = timezone.now()
    enrollment.waitlist_position = None
    enrollment.save(update_fields=["status", "dropped_at", "waitlist_position"])

    _renumber_waitlist(section)
    if was_enrolled:
        promote_from_waitlist(section)
    return enrollment


@_retry_on_lock
@transaction.atomic
def promote_from_waitlist(section) -> Enrollment | None:
    """
    Promote the next eligible waitlisted student into a free seat, if any.

    Candidates are re-checked against R4, R5 and R7 before promotion — a
    candidate who now fails one of these is skipped (left WAITLISTED at their
    existing position, not dropped) and the next in line is tried, since
    whatever blocked them might resolve itself before the next seat opens.
    """
    section = Section.objects.select_for_update().select_related("term").get(pk=section.pk)
    skipped_ids: set[int] = set()

    while True:
        if _seats_taken(section) >= section.capacity:
            return None

        candidate = (
            Enrollment.objects.select_for_update()
            .filter(section=section, status=EnrollmentStatus.WAITLISTED)
            .exclude(pk__in=skipped_ids)
            .order_by("waitlist_position")
            .select_related("student")
            .first()
        )
        if candidate is None:
            return None

        if _promotion_blocked(candidate.student, section):
            skipped_ids.add(candidate.pk)
            continue

        candidate.status = EnrollmentStatus.ENROLLED
        candidate.waitlist_position = None
        candidate.registered_at = timezone.now()
        candidate.save(update_fields=["status", "waitlist_position", "registered_at"])
        _renumber_waitlist(section)
        return candidate
