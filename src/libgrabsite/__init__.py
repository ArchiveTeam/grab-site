import logging
import os

__version__ = "2.2.7"


def log_level():
    """Return the level named by GRAB_SITE_LOG_LEVEL (default INFO); unknown names fall back to INFO."""
    name = os.environ.get("GRAB_SITE_LOG_LEVEL", "INFO").upper()
    return logging.getLevelNamesMapping().get(name, logging.INFO)
