"""
Settings for automated tests — Django unit tests and the Playwright E2E suite.

    DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test
"""

from .base import *

DEBUG = False

SECRET_KEY = SECRET_KEY or "django-insecure-test-only"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

# In-memory database: fast, and impossible to confuse with the dev database.
# The Playwright suite overrides NAME with a disposable file, because its
# server runs in a separate process that cannot share an in-memory database.
DATABASES["default"]["NAME"] = ":memory:"

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
