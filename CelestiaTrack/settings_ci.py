from .settings import *
import os

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
