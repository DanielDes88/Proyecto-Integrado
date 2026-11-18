import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .settings import *


LOAD_TEST_DATABASE = os.environ.get("LOAD_TEST_DATABASE")
if not LOAD_TEST_DATABASE:
    raise ImproperlyConfigured("Set LOAD_TEST_DATABASE to an isolated local SQLite file.")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(LOAD_TEST_DATABASE),
        "OPTIONS": {"timeout": 20},
    }
}
