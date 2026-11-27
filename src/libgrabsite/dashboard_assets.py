"""
The files gs-server will send to a browser, keyed by the request path.

Only paths listed here are served, so a request can never reach an arbitrary
file under this package. The dashboard's own JavaScript is split into ES
modules under dashboard/; each one must be listed so the browser can load it.
"""

from typing import NamedTuple, Optional


class Asset(NamedTuple):
    file: str  # path relative to this package directory
    content_type: str


HTML = "text/html; charset=UTF-8"
CSS = "text/css; charset=UTF-8"
JS = "text/javascript; charset=UTF-8"

ASSETS = {
    "/": Asset("dashboard.html", HTML),
    "/favicon.ico": Asset("favicon.ico", "image/x-icon"),
    "/dashboard/dashboard.css": Asset("dashboard/dashboard.css", CSS),
    "/dashboard/app.js": Asset("dashboard/app.js", JS),
    "/dashboard/context-menu.js": Asset("dashboard/context-menu.js", JS),
    "/dashboard/jobs.js": Asset("dashboard/jobs.js", JS),
    "/dashboard/queue.js": Asset("dashboard/queue.js", JS),
    "/dashboard/renderer.js": Asset("dashboard/renderer.js", JS),
    "/dashboard/theme.js": Asset("dashboard/theme.js", JS),
    "/dashboard/util.js": Asset("dashboard/util.js", JS),
}

NOT_FOUND_PAGE = "404.html"


def lookup(request_path: str) -> Optional[Asset]:
    """Returns the asset for an exact request path, or None if it is not served."""
    return ASSETS.get(request_path)
