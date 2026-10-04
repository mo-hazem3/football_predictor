"""Django settings.

Two databases:
  default   Django's own tables (auth, sessions, admin log): backend/db.sqlite3
  pipeline  the data pipeline's SQLite file, read through unmanaged models (see pipeline_data).
            Django never migrates it; the pipeline's own CLIs write to it.

Configuration comes from environment variables so the same code runs locally and deployed.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set DJANGO_SECRET_KEY (or DJANGO_DEBUG=1 for local development).")
    SECRET_KEY = "insecure-development-key-do-not-use-in-production"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "pipeline_data",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
            ],
        },
    },
]

PIPELINE_DB_PATH = Path(os.environ.get("FOOTBALL_DB", REPO_ROOT / "data" / "db" / "football.sqlite"))

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"},
    "pipeline": {"ENGINE": "django.db.backends.sqlite3", "NAME": PIPELINE_DB_PATH},
}
DATABASE_ROUTERS = ["pipeline_data.routers.PipelineRouter"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------- API
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # read-only public API: no auth, but a modest per-client rate limit
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": os.environ.get("API_THROTTLE_ANON", "120/min")},
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Football player comps and trajectory API",
    "DESCRIPTION": (
        "Find statistically similar football players (controlled for position, age and league quality) and "
        "project what comparable players went on to become, as probabilities with ranges. Read-only. "
        "See the repository README for how the numbers are produced and how well they validate."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# Separate frontend origin (Vite dev server by default); set CORS_ALLOWED_ORIGINS in production.
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CORS_ALLOW_METHODS = ["GET", "HEAD", "OPTIONS"]

# ---------------------------------------------------------------- forecasting service
# Bootstrap fits behind the forecast ranges (model uncertainty); the pickle is built by
# `manage.py build_forecast_cache` and reused until the pipeline database changes.
FORECAST_BOOTSTRAPS = int(os.environ.get("FORECAST_BOOTSTRAPS", "30"))
FORECAST_CACHE_PATH = Path(os.environ.get("FORECAST_CACHE", REPO_ROOT / "data" / "cache" / "forecaster.pkl"))
PRELOAD_MODELS = env_bool("PRELOAD_MODELS", False)  # build/load the models at server start instead of first request
