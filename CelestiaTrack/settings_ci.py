from pathlib import Path
from .settings import *  # noqa:  F401,F403

# Define BASE_DIR explicitly since star import might miss it contextually in linting
BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------------------------------------
# Database Configuration: Force SQLite for CI
# -----------------------------------------------------------
# This ensures that CI tests run quickly and reliably on a local file database
# instead of trying to connect to the non-existent 'postgres' service.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Ensure DEBUG is True for CI environment checks
DEBUG = True

# Disable security features that interfere with CI/test runners
ALLOWED_HOSTS = ['*']
CSRF_TRUSTED_ORIGINS = []

# Force simple static storage for CI so templates can load 'styles.css' without collectstatic
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# If you want to be extra explicit, also disable any “manifest” toggles used by base settings
USE_MANIFEST_STATIC = False
