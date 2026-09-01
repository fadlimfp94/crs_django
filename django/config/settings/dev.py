"""Local development settings. The default when DJANGO_SETTINGS_MODULE is unset."""

from .base import *

DEBUG = True

# Fine for local work; prod.py rejects this value.
SECRET_KEY = SECRET_KEY or "django-insecure-dev-only-do-not-use-in-production"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

# An Android emulator reaches the host machine at 10.0.2.2 (see README).
ALLOWED_HOSTS += ["10.0.2.2"]

# Print emails to the console instead of sending them.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Relaxed so throwaway local accounts are quick to create.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # Uncomment to see every SQL statement.
        # "django.db.backends": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
    },
}
