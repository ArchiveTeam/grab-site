"""
Static checks on dashboard.html. The page's JavaScript cannot run under the
unit-test runner, so these tests extract the URL check and inspect the sinks
that take message data.
"""

import os
import re
import unittest

from tests.unit import _stubs  # noqa: F401

HTML_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "src", "libgrabsite", "dashboard.html"
)


def read_html():
    with open(HTML_PATH, encoding="utf-8") as f:
        return f.read()


def extract_safe_href_regex():
    """Pull the regex literal out of the safeHref function in dashboard.html."""
    m = re.search(
        r"var safeHref = function\(url\) \{\s*return typeof url == \"string\" && "
        r"(/.+?/i)\.test\(url\)",
        read_html(),
    )
    if m is None:
        raise AssertionError("safeHref not found in dashboard.html")
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
        self.html = read_html()

    def test_no_html_injection_sinks(self):
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML"):
            with self.subTest(sink=sink):
                self.assertNotIn(sink, self.html)

    def test_href_assignments_are_guarded(self):
        # The only direct .href assignment allowed is the guarded one in href().
        values = [v.strip() for v in re.findall(r"\.href\s*=\s*([^;]+);", self.html)]
        self.assertEqual([v for v in values if v != "safe"], [])
        self.assertEqual(values, ["safe"])

    def test_href_attributes_use_safe_href(self):
        attrs = re.findall(r"[\"']href[\"']\s*:\s*([^,}\)]+)", self.html)
        self.assertTrue(attrs, "expected href attributes in dashboard.html")
        for value in attrs:
            with self.subTest(value=value.strip()):
                self.assertTrue(
                    value.strip().startswith("safeHref(") or value.strip() == "safe",
                    f"unguarded href value: {value.strip()}",
                )

    def test_null_attributes_are_skipped_by_h(self):
        self.assertIn("if(attrs[attr] == null)", self.html)


if __name__ == "__main__":
    unittest.main()
