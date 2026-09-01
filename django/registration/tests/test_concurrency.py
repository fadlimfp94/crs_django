"""
PLAN.md's "concurrent double-registration attempt" for the last seat.

Real threads racing ``register()`` for a capacity-1 section, asserting
exactly one lands ENROLLED and the other WAITLISTED. Needs
``TransactionTestCase`` (not ``TestCase``) so each thread's writes are
actually committed and visible to the other — ``TestCase`` wraps every test
in a transaction that never commits, which would make this race pointless.

Correctness here comes from ``transaction_mode="IMMEDIATE"`` in
``settings/base.py``: whichever thread's transaction reaches the database
first takes the write lock immediately, and the other blocks until it
commits — not from SQLite row-level locking, which doesn't exist.
"""

import threading

from django.db import connections
from django.test import TransactionTestCase

from registration.models import Enrollment, EnrollmentStatus
from registration.services import register

from .factories import (
    make_course,
    make_department,
    make_meeting,
    make_section,
    make_student,
    make_term,
)


class ConcurrentRegistrationTests(TransactionTestCase):
    def setUp(self):
        self.department = make_department()
        self.term = make_term()
        self.course = make_course(self.department, "CS310")
        self.section = make_section(self.course, self.term, section_code="02", capacity=1)
        make_meeting(self.section)
        self.first_student = make_student()
        self.second_student = make_student()

    def test_only_one_of_two_simultaneous_registrants_gets_the_seat(self):
        results = {}
        errors = {}
        barrier = threading.Barrier(2)

        def attempt(name, student):
            try:
                barrier.wait()
                enrollment = register(student, self.section)
                results[name] = enrollment.status
            except Exception as exc:
                errors[name] = exc
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=("first", self.first_student)),
            threading.Thread(target=attempt, args=("second", self.second_student)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, {}, f"registration raised unexpectedly: {errors}")
        self.assertEqual(
            sorted(results.values()),
            sorted([EnrollmentStatus.ENROLLED, EnrollmentStatus.WAITLISTED]),
        )
        self.assertEqual(
            Enrollment.objects.filter(
                section=self.section, status=EnrollmentStatus.ENROLLED
            ).count(),
            1,
        )
