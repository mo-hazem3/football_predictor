"""Test settings: no real secrets, no throttling, an in-memory pipeline database."""
import os

os.environ.setdefault("DJANGO_DEBUG", "1")

from .settings import *  # noqa: E402,F401,F403

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405
PRELOAD_MODELS = False
FORECAST_BOOTSTRAPS = 3
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AGING_MIN_OBS = 4  # the synthetic world is small
