"""Token obtain endpoint, and its throttle."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from registration.tests.factories import make_student

STUDENT_PASSWORD = "pw-not-checked-here"


class TokenObtainTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = make_student()

    def test_valid_credentials_return_a_token(self):
        response = self.client.post(
            reverse("api:token-obtain"),
            {"username": self.student.user.username, "password": STUDENT_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("token", body)
        self.assertEqual(body["role"], "STUDENT")
        self.assertEqual(body["display_name"], self.student.user.display_name)

    def test_invalid_credentials_are_rejected(self):
        response = self.client.post(
            reverse("api:token-obtain"),
            {"username": self.student.user.username, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 400)

    def test_the_auth_scope_is_throttled(self):
        for _ in range(10):
            response = self.client.post(
                reverse("api:token-obtain"),
                {"username": self.student.user.username, "password": "wrong-password"},
            )
            self.assertNotEqual(response.status_code, 429)

        response = self.client.post(
            reverse("api:token-obtain"),
            {"username": self.student.user.username, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 429)
