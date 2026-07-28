from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")

DEBUG = os.getenv("DEBUG", "False") == "True"

# In production (Cloud Run), set ALLOWED_HOSTS as a comma-separated env var:
#   e.g. ALLOWED_HOSTS=careweb-xyz-uc.a.run.app,carewebai.org
_allowed_hosts_env = os.getenv("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(",") if h.strip()] or (
    ["localhost", "127.0.0.1"] if DEBUG else []
)

# Trust the HTTPS termination proxy in Cloud Run
CSRF_TRUSTED_ORIGINS = [
    f"https://{host}"
    for host in ALLOWED_HOSTS
    if not host.startswith("localhost") and not host.startswith("127.")
]

# ─────────────────────────────────────────────────────────────
# APPLICATION DEFINITION
# ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Project apps
    "accounts",
    "organizations",
    "registry",
    "matching",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise must come right after SecurityMiddleware
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ─────────────────────────────────────────────────────────────
# DATABASE
# DEBUG=True  → SQLite (local dev, zero config)
# DEBUG=False → PostgreSQL (production via Cloud SQL)
# ─────────────────────────────────────────────────────────────
if DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME':     os.getenv('POSTGRES_DB',       'careweb'),
            'USER':     os.getenv('POSTGRES_USER',     'careweb_user'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST':     os.getenv('POSTGRES_HOST',     '127.0.0.1'),
            'PORT':     os.getenv('POSTGRES_PORT',     '5432'),
            'OPTIONS': {
                # Cloud SQL Auth Proxy (unix socket) for Cloud Run.
                # When POSTGRES_HOST starts with '/' it is treated as a socket path.
                # For direct TCP (e.g. local staging), leave POSTGRES_HOST as an IP.
            },
        }
    }

# ─────────────────────────────────────────────────────────────
# PASSWORD VALIDATION
# ─────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─────────────────────────────────────────────────────────────
# INTERNATIONALIZATION
# ─────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────────────────────
# STATIC FILES
# WhiteNoise serves compressed/cached static files from STATIC_ROOT
# ─────────────────────────────────────────────────────────────
STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# collectstatic writes here; WhiteNoise serves from here in production
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ─────────────────────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────────────────────
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard_redirect"
LOGOUT_REDIRECT_URL = "/"

# ─────────────────────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'false').lower() == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'CareWeb <noreply@carewebai.org>')

# Site URL for invitation links
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

# ─────────────────────────────────────────────────────────────
# OPENAI / AI MATCHING
# ─────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MATCH_MODEL = os.getenv("OPENAI_MATCH_MODEL", "gpt-4o-mini")
OPENAI_MATCH_TIMEOUT = int(os.getenv("OPENAI_MATCH_TIMEOUT", "15"))
OPENAI_MATCH_ENABLED = os.getenv("OPENAI_MATCH_ENABLED", "true").lower() == "true"
