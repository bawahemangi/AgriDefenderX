"""
Django settings for the Crop Health System (SIH Problem Statement 26131).

Defaults to SQLite so the project runs with zero external setup:
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py runserver

For a real deployment, set DATABASE_URL (or the individual POSTGRES_*
env vars below) to point at PostgreSQL -- recommended once you have real
farmer/report volume, and PostGIS if you want true spatial queries
(nearest-hotspot, radius search) instead of the simple lat/lng distance
math used in reports/geo.py.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "accounts",
    "farms",
    "reports",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("en", "English"),
    ("mr", "Marathi"),
    ("hi", "Hindi"),
]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
}

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/farmer/"

# -- Crop Health System specific settings -----------------------------------

# OpenWeatherMap API key. If unset, weather.services falls back to
# season-representative synthetic weather so the pipeline still runs.
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

# Anthropic API key, used only by ml/advisory_rag/generate.py for
# translation + tone polishing of advisories that are already grounded in
# the retrieved knowledge base. Optional -- template mode works without it.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Below this image-classifier confidence, a report is auto-flagged for
# expert review instead of being shown to the farmer as a confirmed diagnosis.
#
# NOTE ON CALIBRATION: 0.20 is tuned for the DEMO HEURISTIC classifier
# (ml/disease_classifier/features.py + demo_feature_model.pkl), whose
# confidence is structurally lower -- it genuinely can't distinguish, say,
# Tomato Early Blight from Potato Early Blight on color statistics alone,
# so probability mass legitimately splits across visually-similar classes.
# Once you deploy the real trained CNN (ml/disease_classifier/model.py +
# train.py), which produces much sharper, well-separated softmax
# confidences, raise this back up to ~0.6 via the env var.
LOW_CONFIDENCE_THRESHOLD = float(os.environ.get("LOW_CONFIDENCE_THRESHOLD", "0.20"))
