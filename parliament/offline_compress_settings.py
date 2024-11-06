# A hack used to coax django-compressor to properly generate bundles
# pylint: disable-next=wildcard-import,unused-wildcard-import
from .default_settings import * # noqa: F401,F403

DEBUG = False
COMPRESS_ENABLED = True
COMPRESS_OFFLINE = True

SECRET_KEY = 'compression!'
