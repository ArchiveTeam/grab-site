"""
Static checks on the dashboard's JavaScript modules. The page cannot run under
the unit-test runner, so these tests extract the URL check and inspect the sinks
that take message data.
"""

import os
import re
import unittest

from tests.unit import _stubs  # noqa: F401

from libgrabsite import dashboard_assets

PACKAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src", "libgrabsite")


def read_js():
    """All dashboard JavaScript, concatenated. Every module is checked, not just one."""
    sources = []
    for path, asset in sorted(dashboard_assets.ASSETS.items()):
        if asset.content_type.startswith("text/javascript"):
            with open(os.path.join(PACKAGE_DIR, asset.file), encoding="utf-8") as f:
                sources.append(f.read())
    return "\n".join(sources)


def extract_safe_href_regex():
    """Pull the regex literal out of the safeHref function."""
    m = re.search(
        r"const safeHref = \(url\) => \(typeof url === \"string\" && "
        r"(/.+?/i)\.test\(url\)",
        read_js(),
    )
    if m is None:
        raise AssertionError("safeHref not found in the dashboard JavaScript")
    # Strip the surrounding slashes and the trailing flag.
    return re.compile(m.group(1)[1:-2], re.IGNORECASE)


class SafeHrefTests(unittest.TestCase):
    def setUp(self):
        self.pattern = extract_safe_href_regex()

    def accepts(self, url):
        return bool(self.pattern.match(url))

    def test_accepts_http_https_ftp(self):
        for url in (
            "http://example.com/",
            "https://example.com/a?b=c",
            "ftp://files.example.com/x",
            "HTTPS://EXAMPLE.COM/",
        ):
            with self.subTest(url=url):
                self.assertTrue(self.accepts(url))

    def test_rejects_script_and_data_schemes(self):
        for url in (
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "  javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox",
            "file:///etc/passwd",
        ):
            with self.subTest(url=url):
                self.assertFalse(self.accepts(url))

    def test_rejects_relative_and_empty(self):
        for url in ("", "/relative", "example.com", "//example.com/x", "https:/x"):
            with self.subTest(url=url):
                self.assertFalse(self.accepts(url))


class SinkTests(unittest.TestCase):
    """Every link built from message data goes through safeHref, and nothing uses innerHTML."""

    def setUp(self):
        self.html = read_js()

    def test_no_html_injection_sinks(self):
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML"):
            with self.subTest(sink=sink):
                self.assertNotIn(sink, self.html)

    def test_href_assignments_are_guarded(self):
        # Any direct .href assignment must go through the guarded safe value.
        values = [v.strip() for v in re.findall(r"\.href\s*=\s*([^;]+);", self.html)]
        self.assertEqual([v for v in values if v != "safe"], [])

    def test_href_attributes_use_safe_href(self):
        attrs = re.findall(r"[\"']?\bhref[\"']?\s*:\s*([^,}\)]+)", self.html)
        self.assertTrue(attrs, "expected href attributes in the dashboard JavaScript")
        for value in attrs:
            with self.subTest(value=value.strip()):
                self.assertTrue(
                    value.strip().startswith("safeHref(") or value.strip() == "safe",
                    f"unguarded href value: {value.strip()}",
                )

    def test_null_attributes_are_skipped_by_el(self):
        self.assertIn("if (value == null)", self.html)


if __name__ == "__main__":
    unittest.main()
