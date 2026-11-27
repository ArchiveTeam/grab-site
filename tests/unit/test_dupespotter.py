import unittest

from tests.unit import _stubs  # noqa: F401
from libgrabsite import dupespotter


class LowerEscapesTests(unittest.TestCase):
    def test_no_percent_unchanged(self):
        self.assertEqual(dupespotter.lower_escapes(b"abc"), b"abc")

    def test_lowercases_only_escapes(self):
        self.assertEqual(dupespotter.lower_escapes(b"A%2FB%3A"), b"A%2fB%3a")

    def test_requires_bytes(self):
        with self.assertRaises(AssertionError):
            dupespotter.lower_escapes("str")


class KillPathTests(unittest.TestCase):
    def test_removes_plain_path(self):
        self.assertEqual(dupespotter.kill_path("foo/bar", b"x foo/bar y"), b"x  y")

    def test_removes_escaped_slash_variant(self):
        self.assertNotIn(b"foo", dupespotter.kill_path("foo/bar", b'{"u":"foo\\/bar"}'))

    def test_removes_quote_plus_variant(self):
        self.assertNotIn(b"foo", dupespotter.kill_path("foo/bar", b"u=foo%2Fbar"))


class ProcessBodyTests(unittest.TestCase):
    URL = "http://example.com/some/long/path"

    def test_requires_bytes(self):
        with self.assertRaises(AssertionError):
            dupespotter.process_body("text", self.URL)

    def test_plain_body_unchanged(self):
        self.assertEqual(
            dupespotter.process_body(b"<p>hello world</p>", self.URL),
            b"<p>hello world</p>",
        )

    def test_html_comments_stripped(self):
        a = dupespotter.process_body(b"<p>x</p><!-- generated in 0.12s -->", self.URL)
        b = dupespotter.process_body(b"<p>x</p><!-- generated in 0.98s -->", self.URL)
        self.assertEqual(a, b)

    def test_long_hex_tokens_stripped(self):
        a = dupespotter.process_body(b"<p>x</p> 1234567890abcdef", self.URL)
        b = dupespotter.process_body(b"<p>x</p> fedcba0987654321", self.URL)
        self.assertEqual(a, b)

    def test_hidden_inputs_stripped(self):
        a = dupespotter.process_body(
            b'<input type="hidden" name="t" value="1">hi', self.URL
        )
        b = dupespotter.process_body(
            b'<input type="hidden" name="t" value="2">hi', self.URL
        )
        self.assertEqual(a, b)

    def test_own_url_path_removed(self):
        a = dupespotter.process_body(b"<a href='/some/long/path'>x</a>", self.URL)
        self.assertNotIn(b"some/long/path", a)

    def test_different_content_stays_different(self):
        a = dupespotter.process_body(b"<p>first page</p>", self.URL)
        b = dupespotter.process_body(b"<p>second page</p>", self.URL)
        self.assertNotEqual(a, b)

    def test_drupal_settings_stripped(self):
        body = b'Drupal jQuery.extend(Drupal.settings, {"a":"%s"});<p>x</p>'
        a = dupespotter.process_body(body % b"one", self.URL)
        b = dupespotter.process_body(body % b"two", self.URL)
        self.assertEqual(a, b)

    def test_canonical_link_stripped(self):
        a = dupespotter.process_body(
            b'<link rel="canonical" href="http://a/1" />x', self.URL
        )
        b = dupespotter.process_body(
            b'<link rel="canonical" href="http://a/2" />x', self.URL
        )
        self.assertEqual(a, b)


class Md5UrlTests(unittest.TestCase):
    def test_known_value(self):
        self.assertEqual(dupespotter.md5_url("a"), "0cc175b9c0f1b6a831c399e269772661")


if __name__ == "__main__":
    unittest.main()
