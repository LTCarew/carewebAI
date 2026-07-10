"""
Test-specific settings.

Extends the main settings but swaps out ManifestStaticFilesStorage
(which requires collectstatic + a staticfiles.json manifest) for the
plain StaticFilesStorage that works without any pre-build step.

Usage:
    python manage.py test --settings=config.test_settings <app> ...
"""
from config.settings import *  # noqa: F401, F403

# ── Static files ───────────────────────────────────────────────────────────────
# Settings uses the Django 4.2+ STORAGES dict with WhiteNoise's
# CompressedManifestStaticFilesStorage, which requires collectstatic.
# Override the staticfiles backend to the plain StaticFilesStorage so
# {% static %} tags resolve without a manifest in tests.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# ── Email ──────────────────────────────────────────────────────────────────────
# Use the in-memory email backend so tests can inspect sent mail
# without configuring an SMTP server.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ── OpenAI ─────────────────────────────────────────────────────────────────────
# Disable OpenAI calls in all tests by default.
# Individual test classes can re-enable it with @override_settings.
OPENAI_MATCH_ENABLED = False
OPENAI_API_KEY = ""
