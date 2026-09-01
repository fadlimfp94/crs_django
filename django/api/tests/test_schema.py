"""
The OpenAPI schema and its Swagger UI must be served (PLAN.md's Phase 5
done-when). The custom {"rule", "detail"} error envelope from
api.exceptions.crs_exception_handler is not annotated in the generated
schema — drf-spectacular has no visibility into a custom EXCEPTION_HANDLER
without per-action @extend_schema(responses=...) hints, which is out of
scope for this phase. Not asserted here; see PLAN.md's Deviations note.
"""

from django.test import TestCase
from django.urls import reverse

from registration.tests.factories import make_student


class SchemaTests(TestCase):
    def setUp(self):
        self.client.force_login(make_student().user)

    def test_schema_is_served(self):
        response = self.client.get(reverse("api:schema"))
        self.assertEqual(response.status_code, 200)

    def test_docs_are_served(self):
        response = self.client.get(reverse("api:docs"))
        self.assertEqual(response.status_code, 200)
