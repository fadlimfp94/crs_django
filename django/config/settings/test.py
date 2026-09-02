"""
Settings for automated tests — Django unit tests and the Playwright E2E suite.

    DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test
"""

import os

from .base import *

DEBUG = False

SECRET_KEY = SECRET_KEY or "django-insecure-test-only"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

# In-memory by default: fast, and impossible to confuse with the dev database.
# The Playwright suite sets CRS_E2E_DB_PATH to a disposable file instead,
# because its runserver process can't share an in-memory database with the
# process that seeds it.
DATABASES["default"]["NAME"] = os.environ.get("CRS_E2E_DB_PATH", ":memory:")

# Hashing dominates test runtime with the real hasher; this cuts it sharply.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

AUTH_PASSWORD_VALIDATORS: list[dict] = []

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Keep test output readable — only surface real problems.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "ERROR"},
}
