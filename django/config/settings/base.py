"""
Settings shared by every environment.

Never used directly — always import one of the concrete modules:

    config.settings.dev     local development (default)
    config.settings.test    automated tests
    config.settings.prod    deployment

Select one with DJANGO_SETTINGS_MODULE, e.g.

    DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy
"""

import os
from pathlib import Path

# django/  — the directory containing manage.py
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Supplied by the environment. dev/test fall back to an insecure value;
# prod refuses to start without it.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")

DEBUG = False
ALLOWED_HOSTS: list[str] = []

# ─── Applications ─────────────────────────────────────────────────────────────

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: list[str] = [
    # Phase 5: "rest_framework", "rest_framework.authtoken", "drf_spectacular"
]

LOCAL_APPS = [
    "accounts",
    "academics",
    "registration",
    # Phase 5: "api"
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ─── Database ─────────────────────────────────────────────────────────────────
# SQLite serialises writes at the database level, which is exactly the wrong
# shape for registration-day contention. WAL mode plus a busy timeout lets
# readers proceed during a write and makes writers wait rather than fail
# immediately with "database is locked". See PLAN.md §8.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,  # seconds a writer waits for the lock
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;",
            "transaction_mode": "IMMEDIATE",  # take the write lock up front
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Authentication ───────────────────────────────────────────────────────────

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# ─── Internationalisation ─────────────────────────────────────────────────────
# Timestamps are stored in UTC; TIME_ZONE controls how they are rendered and
# how naive input is interpreted. Registration windows depend on this being
# correct for the institution.

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Asia/Jakarta")
USE_I18N = True
USE_TZ = True

# ─── Static files ─────────────────────────────────────────────────────────────

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ─── Messages ─────────────────────────────────────────────────────────────────
# Bootstrap-compatible tag names so templates can use them directly.

from django.contrib.messages import constants as messages  # noqa: E402

MESSAGE_TAGS = {messages.ERROR: "danger"}
