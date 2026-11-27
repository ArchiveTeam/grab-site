import logging
import os
import re

_DIGITS = re.compile(r"[0-9]+")

__version__ = "2.2.7"


def parse_ports(value=None):
    """Parse GRAB_SITE_PORT, a port or a comma-separated list of ports (default 29000)."""
    if value is None:
        value = os.environ.get("GRAB_SITE_PORT", "29000")
    ports = []
    for part in value.split(","):
        if not part.strip():
            continue
        try:
            ports.append(int(part))
        except ValueError:
            raise ValueError(
                f"GRAB_SITE_PORT={value!r} is not a port number or a "
                "comma-separated list of port numbers"
            ) from None
    if not ports:
        raise ValueError(f"No ports in GRAB_SITE_PORT={value!r}")
    return ports


def parse_delay(value):
    """Parse a delay in milliseconds, "NUM" or "MIN-MAX", into (min, max).

    Used by both the --delay option and the DIR/delay control file, so the two
    accept exactly the same values.
    """
    parts = value.split("-")
    if len(parts) > 2:
        raise ValueError(f"delay {value!r} has too many '-' separators")
    numbers = []
    for part in parts:
        part = part.strip()
        if not _DIGITS.fullmatch(part):
            raise ValueError(f"delay {value!r} must be NUM or MIN-MAX, non-negative")
        numbers.append(int(part))
    low = numbers[0]
    high = numbers[-1]
    if low > high:
        raise ValueError(f"delay {value!r} has MIN greater than MAX")
    return low, high


def parse_non_negative_or_inf(value):
    """Validate a count such as --level: a non-negative integer, or "inf"."""
    text = value.strip()
    if text == "inf":
        return value
    if not _DIGITS.fullmatch(text):
        raise ValueError(f"{value!r} must be a non-negative integer or 'inf'")
    return value


def log_level():
    """Return the level named by GRAB_SITE_LOG_LEVEL (default INFO); unknown names fall back to INFO."""
    name = os.environ.get("GRAB_SITE_LOG_LEVEL", "INFO").upper()
    return logging.getLevelNamesMapping().get(name, logging.INFO)
