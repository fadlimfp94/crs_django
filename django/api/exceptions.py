"""
Turns a ``RegistrationError`` into the structured error shape PLAN.md asks
for: ``{"rule": "R5", "detail": "..."}``. ``rule`` is ``None`` for the couple
of non-rule-coded errors (e.g. dropping a section you're not in) — the key is
always present, only the value is sometimes null.

This is the one place ``RegistrationError`` becomes an HTTP response, so every
view/action that calls into ``registration.services`` gets a structured error
for free without its own ``try/except``.
"""

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from registration.services import RegistrationError


def crs_exception_handler(exc, context):
    if isinstance(exc, RegistrationError):
        return Response({"rule": exc.rule, "detail": str(exc)}, status=400)
    return drf_exception_handler(exc, context)
