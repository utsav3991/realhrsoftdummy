"""RealHRSoft dummy settings.

This project plays RealHRSoft for the Marketplace: it owns the directory (clients,
companies, employees), signs employee tokens and sync deliveries with RS256 keys,
publishes its public keys, pushes snapshot events and serves the snapshot API that
Marketplace reconciliation reads. See README.md for the Marketplace .env values.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "dev-only-realhrsoftdummy-secret-change-me"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    ISSUER=(str, "http://localhost:8100"),
    MARKETPLACE_URL=(str, "http://localhost:8000"),
    MARKETPLACE_AUDIENCE=(str, "realhrsoft-marketplace"),
    MARKETPLACE_SYNC_AUDIENCE=(str, "realhrsoft-marketplace-sync"),
    SNAPSHOT_API_TOKEN=(str, ""),
    SYNC_DELIVER_ON_COMMIT=(bool, True),
)
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env("DEBUG")
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
# Behind a proxy or load balancer (Docker, a deployed domain): the browser's origin,
# for example https://realhrsoft.example.com, so the login and admin forms pass CSRF.
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "directory",
    "signing",
    "sync",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files (admin, the employee screens) without a web server.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    # The delivery thread, request threads and `deliver_events` share the file. IMMEDIATE
    # takes the write lock up front, so two writers queue (up to the timeout) instead of
    # deadlocking on a read-to-write upgrade ("database is locked").
    DATABASES["default"].setdefault("OPTIONS", {}).update(
        timeout=20, transaction_mode="IMMEDIATE"
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # No hashed names: the employee screens are found through Vite's own manifest.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "portal-home"
LOGOUT_REDIRECT_URL = "login"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

# --- Marketplace integration ------------------------------------------------------
# ISSUER is the token `iss`; the Marketplace's REALHRSOFT_ISSUER must equal it.
ISSUER = env("ISSUER")
# Base URL of the Marketplace backend (no trailing /api).
MARKETPLACE_URL = env("MARKETPLACE_URL").rstrip("/")
MARKETPLACE_AUDIENCE = env("MARKETPLACE_AUDIENCE")
MARKETPLACE_SYNC_AUDIENCE = env("MARKETPLACE_SYNC_AUDIENCE")
# Accepted defaults (plan D4): 60 s employee tokens.
EMPLOYEE_TOKEN_LIFETIME = timedelta(seconds=60)
# A retired key stays in the JWKS this long: past the longest token (60 s), the
# delivery window (300 s) and the Marketplace's key set cache (300 s).
RETIRED_KEY_GRACE = timedelta(minutes=10)
# Bearer token the Marketplace sends to the snapshot API (its REALHRSOFT_API_TOKEN).
# Empty disables the snapshot API.
SNAPSHOT_API_TOKEN = env("SNAPSHOT_API_TOKEN")
# Deliver new events from a background thread right after commit. The
# `deliver_events --loop` command delivers retries and anything a thread missed.
SYNC_DELIVER_ON_COMMIT = env("SYNC_DELIVER_ON_COMMIT")
SYNC_MAX_ATTEMPTS = 20
SYNC_TIMEOUT = 10
# Marketplace path of the event endpoint; the signature binds it exactly.
SYNC_EVENTS_PATH = "/api/v1/integrations/realhrsoft/events"
PROXY_TIMEOUT = 20

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "sync": {"handlers": ["console"], "level": "INFO"},
        "portal": {"handlers": ["console"], "level": "INFO"},
    },
}
