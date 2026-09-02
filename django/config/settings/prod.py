"""
Deployment settings.

Required environment variables:
    DJANGO_SECRET_KEY     long random string, never committed
    DJANGO_ALLOWED_HOSTS  comma-separated hostnames

Optional:
    DJANGO_TIME_ZONE          default "Asia/Jakarta"
    DJANGO_SECURE_SSL         "0" to disable HTTPS redirect (default on)
    DJANGO_DB_PATH            absolute path to the SQLite file

Verify before deploying:
    DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set in production. Generate one with:\n"
        "  python -c 'from django.core.management.utils import get_random_secret_key;"
        " print(get_random_secret_key())'"
    )

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list at least one hostname in production."
    )

_ssl = os.environ.get("DJANGO_SECURE_SSL", "1") != "0"
_scheme = "https" if _ssl else "http"
CSRF_TRUSTED_ORIGINS = [f"{_scheme}://{h}" for h in ALLOWED_HOSTS if not h.startswith(".")]

# ─── Database ─────────────────────────────────────────────────────────────────
# Keep the SQLite file outside the source tree so a redeploy cannot clobber it.

if db_path := os.environ.get("DJANGO_DB_PATH"):
    DATABASES["default"]["NAME"] = db_path

# ─── Security ─────────────────────────────────────────────────────────────────

SECURE_SSL_REDIRECT = _ssl
SESSION_COOKIE_SECURE = _ssl
CSRF_COOKIE_SECURE = _ssl

SECURE_HSTS_SECONDS = 31_536_000 if _ssl else 0  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = _ssl
SECURE_HSTS_PRELOAD = _ssl

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Behind a reverse proxy that terminates TLS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours

# ─── Static files ─────────────────────────────────────────────────────────────
# Hashed filenames so clients can cache aggressively.

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}

# ─── Logging ──────────────────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {process:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # Registration outcomes are the audit trail that matters most.
        "registration": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
