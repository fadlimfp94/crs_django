"""
Tests for the grade scale.

Small module, disproportionate importance: rule R3 ("prerequisites satisfied")
is a grade comparison, and the obvious implementation — comparing the letters as
strings — is wrong in a way that looks right most of the time.
"""

from django.test import SimpleTestCase

from academics.grades import (
    GRADE_POINTS,
    PASSING_GRADE,
    Grade,
    grade_points,
    is_passing,
    meets_minimum,
)


class GradePointsTests(SimpleTestCase):
    def test_every_grade_has_points(self):
        for grade in Grade:
            with self.subTest(grade=grade):
                self.assertIn(grade, GRADE_POINTS)

    def test_scale_is_strictly_descending(self):
        points = [GRADE_POINTS[grade] for grade in Grade]
        self.assertEqual(points, sorted(points, reverse=True))
        self.assertEqual(len(set(points)), len(points))

    def test_a_is_four_and_f_is_zero(self):
        self.assertEqual(grade_points(Grade.A), 4.0)
        self.assertEqual(grade_points(Grade.F), 0.0)

    def test_missing_or_unknown_grade_scores_zero(self):
        self.assertEqual(grade_points(None), 0.0)
        self.assertEqual(grade_points(""), 0.0)
        self.assertEqual(grade_points("Z+"), 0.0)


class StringComparisonTrapTests(SimpleTestCase):
    """
    The reason this module exists rather than inlining `>=` on the letters.

    ``"B-" > "B+"`` is true as a string comparison and false as a grade
    comparison. If R3 ever compares letters directly, a student who scraped a
    B− will be let into a course demanding a B+.
    """

    def test_string_comparison_would_be_wrong(self):
        self.assertTrue("B-" > "B+")  # the trap
        self.assertFalse(meets_minimum(Grade.B_MINUS, Grade.B_PLUS))  # the truth

    def test_grade_points_orders_modifiers_correctly(self):
        self.assertGreater(grade_points(Grade.B_PLUS), grade_points(Grade.B))
        self.assertGreater(grade_points(Grade.B), grade_points(Grade.B_MINUS))
        self.assertGreater(grade_points(Grade.B_MINUS), grade_points(Grade.C_PLUS))


class IsPassingTests(SimpleTestCase):
    def test_d_is_the_lowest_pass(self):
        self.assertEqual(PASSING_GRADE, Grade.D)
        self.assertTrue(is_passing(Grade.D))

    def test_f_fails(self):
        self.assertFalse(is_passing(Grade.F))

    def test_no_grade_fails(self):
        self.assertFalse(is_passing(None))

    def test_every_grade_above_d_passes(self):
        for grade in Grade:
            if grade == Grade.F:
                continue
            with self.subTest(grade=grade):
                self.assertTrue(is_passing(grade))


class MeetsMinimumTests(SimpleTestCase):
    """Boundary cases for R3: exactly at the bar, one step under, one step over."""

    def test_exactly_the_minimum_qualifies(self):
        self.assertTrue(meets_minimum(Grade.C, Grade.C))

    def test_one_step_below_the_minimum_fails(self):
        self.assertFalse(meets_minimum(Grade.C_MINUS, Grade.C))

    def test_one_step_above_the_minimum_qualifies(self):
        self.assertTrue(meets_minimum(Grade.C_PLUS, Grade.C))

    def test_no_minimum_falls_back_to_a_bare_pass(self):
        self.assertTrue(meets_minimum(Grade.D, None))
        self.assertFalse(meets_minimum(Grade.F, None))

    def test_missing_grade_never_qualifies(self):
        self.assertFalse(meets_minimum(None, Grade.D))
        self.assertFalse(meets_minimum(None, None))
