"""
Plain constructors for the objects registration tests build repeatedly.

Not a fixture framework — just functions, so each test can compose exactly
the scenario it needs (a clashing meeting, a tiny capacity, a closed window)
without dragging in a shared class hierarchy. Mirrors the ``make_term`` helper
in ``academics.tests.test_models``.
"""

import itertools
from datetime import date, time, timedelta

from django.utils import timezone

from academics.models import Course, DayOfWeek, Department, Meeting, PrerequisiteRule, Section, Term
from accounts.models import StudentStatus, User

_usernames = itertools.count(1)


def make_department(code="CS", name="Computer Science") -> Department:
    return Department.objects.create(code=code, name=name)


def make_course(department, code, *, credits=4, **extra) -> Course:
    return Course.objects.create(
        code=code, title=code, credits=credits, department=department, **extra
    )


def make_prerequisite(course, prerequisite, *, minimum_grade="D") -> PrerequisiteRule:
    return PrerequisiteRule.objects.create(
        course=course, prerequisite=prerequisite, minimum_grade=minimum_grade
    )


def make_term(code="2026-FALL", *, opens_days=-1, closes_days=+7, max_credits=24, **extra) -> Term:
    now = timezone.now()
    defaults = {
        "name": code,
        "start_date": date(2026, 9, 7),
        "end_date": date(2027, 1, 15),
        "registration_opens_at": now + timedelta(days=opens_days),
        "registration_closes_at": now + timedelta(days=closes_days),
        "max_credits_per_student": max_credits,
    }
    defaults.update(extra)
    return Term.objects.create(code=code, **defaults)


def make_section(course, term, *, section_code="01", capacity=30, **extra) -> Section:
    return Section.objects.create(
        course=course, term=term, section_code=section_code, capacity=capacity, **extra
    )


def make_meeting(
    section, *, day=DayOfWeek.MONDAY, start=time(10, 0), end=time(11, 0), **extra
) -> Meeting:
    return Meeting.objects.create(
        section=section, day_of_week=day, start_time=start, end_time=end, **extra
    )


def make_student(*, status=StudentStatus.ACTIVE, **extra):
    username = f"student{next(_usernames)}"
    user = User.objects.create_student(
        username, f"{username}@example.com", "pw-not-checked-here", status=status, **extra
    )
    return user.student_profile
