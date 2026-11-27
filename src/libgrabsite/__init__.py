import logging
import os

__version__ = "2.2.7"


def parse_ports(value=None):
    """Parse GRAB_SITE_PORT, a port or a comma-separated list of ports (default 29000)."""
    if value is None:
        value = os.environ.get("GRAB_SITE_PORT", "29000")
    ports = [int(p) for p in value.split(",") if p.strip()]
    if not ports:
        raise ValueError(f"No ports in GRAB_SITE_PORT={value!r}")
    return ports


def log_level():
    """Return the level named by GRAB_SITE_LOG_LEVEL (default INFO); unknown names fall back to INFO."""
    name = os.environ.get("GRAB_SITE_LOG_LEVEL", "INFO").upper()
    return logging.getLevelNamesMapping().get(name, logging.INFO)
