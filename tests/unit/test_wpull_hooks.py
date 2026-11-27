import re
import types
import unittest

from tests.unit import _stubs  # noqa: F401
from libgrabsite import wpull_hooks as wh


class FakeFields:
    def __init__(self, pairs):
        self.pairs = pairs

    def get_all(self):
        return list(self.pairs)


class FakeResponse:
    def __init__(self, pairs=()):
        self.fields = FakeFields(pairs)


_REAL_RE2 = hasattr(__import__("re2"), "_re2")


class IgnoreLineTests(unittest.TestCase):
    def test_comment_and_blank_excluded(self):
        self.assertFalse(wh.include_ignore_line("# comment"))
        self.assertFalse(wh.include_ignore_line(""))

    def test_pattern_included(self):
        self.assertTrue(wh.include_ignore_line(r"\.jpg$"))


class CombinedRegexpTests(unittest.TestCase):
    def test_no_patterns_ignores_nothing(self):
        rx = wh.compile_combined_regexp([])
        self.assertIsNone(rx.search("http://example.com/"))

    def test_matches_any_pattern(self):
        rx = wh.compile_combined_regexp([r"\.jpg$", r"/logout"])
        self.assertTrue(rx.search("http://a/x.jpg"))
        self.assertTrue(rx.search("http://a/logout?x=1"))
        self.assertIsNone(rx.search("http://a/page.html"))

    def test_alternation_inside_pattern_is_grouped(self):
        # Each pattern is wrapped in a group so "a|b" can't leak into others.
        rx = wh.compile_combined_regexp([r"^x$", r"foo|bar"])
        self.assertIsNone(rx.search("zzz"))
        self.assertTrue(rx.search("xbar"))

    def test_invalid_regexp_raises(self):
        with self.assertRaises(re.error):
            wh.re_compile("(")

    @unittest.skipUnless(_REAL_RE2, "needs the real google-re2 package")
    def test_lookaround_falls_back_to_re(self):
        # google-re2 raises re2.error, which is not a subclass of re.error, so
        # re_compile must catch both to fall back to `re`.
        rx = wh.re_compile(r"foo(?=bar)")
        self.assertTrue(rx.search("foobar"))
        self.assertIsNone(rx.search("foobaz"))


class IgnoreSetTests(unittest.TestCase):
    def test_global_set_loads(self):
        patterns = wh.get_patterns_for_ignore_set("global")
        self.assertTrue(any(wh.include_ignore_line(p) for p in patterns))

    def test_every_shipped_set_compiles(self):
        import os

        for name in sorted(os.listdir(wh.ignore_sets_path)):
            with self.subTest(igset=name):
                for p in wh.get_patterns_for_ignore_set(name):
                    if wh.include_ignore_line(p):
                        # netloc placeholder is substituted at runtime
                        wh.re_compile(p.replace("{any_start_netloc}", "example\\.com"))

    def test_meetupeverywhere_compiles(self):
        for p in wh.get_patterns_for_ignore_set("meetupeverywhere"):
            if wh.include_ignore_line(p):
                wh.re_compile(p)

    def test_empty_name_rejected(self):
        with self.assertRaises(AssertionError):
            wh.get_patterns_for_ignore_set("")

    def test_unknown_set_raises(self):
        with self.assertRaises(FileNotFoundError):
            wh.get_patterns_for_ignore_set("no-such-set")


class ResponseHelperTests(unittest.TestCase):
    def test_content_length(self):
        r = FakeResponse([("Content-Length", "123")])
        self.assertEqual(wh.get_content_length(r), 123)

    def test_content_length_missing_or_invalid(self):
        self.assertEqual(wh.get_content_length(FakeResponse()), -1)
        self.assertEqual(
            wh.get_content_length(FakeResponse([("Content-Length", "x")])), -1
        )

    def test_content_type_video(self):
        self.assertTrue(
            wh.has_content_type_video(FakeResponse([("Content-Type", "Video/MP4")]))
        )
        self.assertFalse(
            wh.has_content_type_video(FakeResponse([("Content-Type", "text/html")]))
        )
        self.assertFalse(wh.has_content_type_video(FakeResponse()))

    def test_content_length_header_name_case_insensitive(self):
        self.assertEqual(
            wh.get_content_length(FakeResponse([("content-length", "5")])), 5
        )

    def test_content_type_header_name_case_insensitive(self):
        self.assertTrue(
            wh.has_content_type_video(FakeResponse([("content-type", "video/mp4")]))
        )

    def test_status_code_http(self):
        class R:
            status_code = 404

        self.assertEqual(wh.response_status_code(R()), 404)

    def test_status_code_ftp(self):
        class Reply:
            code = 226

        class R:
            reply = Reply()

        self.assertEqual(wh.response_status_code(R()), 226)

    def test_status_code_unknown(self):
        self.assertEqual(wh.response_status_code(object()), 0)


class VideoExtTests(unittest.TestCase):
    def test_known_extensions(self):
        for u in ("http://a/v.mp4", "http://a/v.WEBM", "http://a/x.y.mkv"):
            self.assertTrue(wh.has_video_ext(u), u)

    def test_non_video(self):
        for u in ("http://a/page.html", "http://a/img.png", "http://a/mp4"):
            self.assertFalse(wh.has_video_ext(u), u)

    def test_extension_followed_by_query(self):
        self.assertTrue(wh.has_video_ext("http://a/v.mp4?token=1"))
        self.assertTrue(wh.has_video_ext("http://a/v.webm?x=1&y=2"))

    def test_extension_followed_by_fragment(self):
        self.assertTrue(wh.has_video_ext("http://a/v.mp4#t=10"))
        self.assertTrue(wh.has_video_ext("http://a/v.mkv?x=1#t=10"))

    def test_extension_in_query_only(self):
        self.assertFalse(wh.has_video_ext("http://a/page.php?file=x.mp4"))
        self.assertFalse(wh.has_video_ext("http://example.com/a.php?f=x.mp4"))
        self.assertFalse(wh.has_video_ext("http://a/page?f=x.mp4#y.webm"))

    def test_dot_in_host_or_directory_ignored(self):
        self.assertFalse(wh.has_video_ext("http://x.mp4/page"))
        self.assertFalse(wh.has_video_ext("http://a/clip.mp4/page"))
        self.assertFalse(wh.has_video_ext("http://a/dir.mp4/index.html"))

    def test_no_extension_with_dotted_directory(self):
        self.assertFalse(wh.has_video_ext("http://a/dir.webm/file"))

    def test_uppercase_extension_in_path(self):
        self.assertTrue(wh.has_video_ext("http://a/V.MP4?x=1"))

    def test_url_without_path(self):
        self.assertFalse(wh.has_video_ext("http://a"))
        self.assertFalse(wh.has_video_ext("http://a?f=x.mp4"))


class IcyPatternTests(unittest.TestCase):
    def test_icy_fields_match(self):
        for f in ("icy-name", "ICY-Genre", "x-audiocast-name", "ice-audio-info"):
            self.assertTrue(wh.ICY_FIELD_PATTERN.match(f), f)

    def test_normal_fields_do_not_match(self):
        for f in ("Content-Type", "Server", "Date"):
            self.assertFalse(wh.ICY_FIELD_PATTERN.match(f), f)

    def test_server_value(self):
        self.assertTrue(wh.ICY_VALUE_PATTERN.match("Icecast 2.4"))
        self.assertFalse(wh.ICY_VALUE_PATTERN.match("nginx"))

    def test_field_pattern_is_anchored_for_every_alternative(self):
        # Without a group, ^ only applied to "icy-"; search() then matched
        # "ice-" / "x-audiocast-" anywhere in a header name.
        for f in ("service-id", "device-type", "office-x", "xx-audiocast-y"):
            self.assertIsNone(wh.ICY_FIELD_PATTERN.search(f), f)


class FindIcyReasonTests(unittest.TestCase):
    @staticmethod
    def response(pairs=(), version="HTTP/1.1"):
        r = FakeResponse(pairs)
        r.version = version
        return r

    def test_icy_version(self):
        self.assertEqual(
            wh.find_icy_reason(self.response(version="ICY")), "[icy version]"
        )

    def test_icy_field(self):
        for name in ("icy-name", "ICY-Genre", "x-audiocast-name", "ice-audio-info"):
            r = self.response([(name, "x")])
            self.assertEqual(wh.find_icy_reason(r), "[icy field]", name)

    def test_lookalike_headers_are_not_icy(self):
        for name in ("service-id", "device-type", "office-x", "X-Device-Id"):
            r = self.response([(name, "1")])
            self.assertIsNone(wh.find_icy_reason(r), name)

    def test_icecast_server_header(self):
        r = self.response([("Server", "Icecast 2.4.4")])
        self.assertEqual(wh.find_icy_reason(r), "[icy server]")

    def test_server_header_name_is_case_insensitive(self):
        for name in ("server", "SERVER"):
            r = self.response([(name, "Icecast 2.4.4")])
            self.assertEqual(wh.find_icy_reason(r), "[icy server]", name)

    def test_non_icecast_server_header(self):
        for name in ("Server", "server"):
            r = self.response([(name, "nginx")])
            self.assertIsNone(wh.find_icy_reason(r), name)

    def test_ordinary_response(self):
        r = self.response([("Content-Type", "text/html"), ("Server", "nginx")])
        self.assertIsNone(wh.find_icy_reason(r))


class CachingDecoratorTests(unittest.TestCase):
    def test_caches_within_window(self):
        calls = []

        @wh.caching_decorator
        def f(path):
            calls.append(path)
            return len(calls)

        self.assertEqual(f("p"), 1)
        self.assertEqual(f("p"), 1)
        self.assertEqual(calls, ["p"])

    def test_separate_paths_cached_separately(self):
        @wh.caching_decorator
        def f(path):
            return path.upper()

        self.assertEqual(f("a"), "A")
        self.assertEqual(f("b"), "B")

    def test_expires(self):
        from unittest import mock

        calls = []

        @wh.caching_decorator
        def f(path):
            calls.append(1)
            return len(calls)

        with mock.patch.object(
            wh.time, "monotonic", side_effect=[100.0, 100.0, 200.0, 200.0]
        ):
            self.assertEqual(f("p"), 1)
            self.assertEqual(f("p"), 2)


class FileChangedWatcherTests(unittest.TestCase):
    def test_changed_then_unchanged_then_changed(self):
        from unittest import mock

        w = wh.FileChangedWatcher("/some/file")
        with (
            mock.patch.object(wh, "mtime_with_cache", side_effect=[10, 10, 11]),
            mock.patch("builtins.print"),
        ):
            self.assertTrue(w.has_changed())
            self.assertFalse(w.has_changed())
            self.assertTrue(w.has_changed())


class SwallowExceptionTests(unittest.TestCase):
    def test_returns_value(self):
        @wh.swallow_exception
        def f(x):
            return x + 1

        self.assertEqual(f(1), 2)

    def test_swallows_exceptions(self):
        from unittest import mock

        @wh.swallow_exception
        def f():
            raise ValueError("boom")

        with mock.patch.object(wh.traceback, "print_exc"):
            self.assertIsNone(f())


class PluginLogicTests(unittest.TestCase):
    """Exercise plugin methods that don't need a running wpull."""

    def make_plugin(self, netlocs=("example.com",)):
        p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        p.all_start_netlocs = set(netlocs)
        return p

    def test_pattern_without_placeholder(self):
        p = self.make_plugin()
        self.assertEqual(p.ignore_pattern_to_regexp_strings(r"\.jpg$"), [r"\.jpg$"])

    def test_netloc_placeholder_expanded_and_escaped(self):
        p = self.make_plugin(["a.example.com", "b.org"])
        out = sorted(
            p.ignore_pattern_to_regexp_strings("^https?://{any_start_netloc}/x")
        )
        self.assertEqual(
            out,
            [
                "^https?://" + re.escape("a.example.com") + "/x",
                "^https?://" + re.escape("b.org") + "/x",
            ],
        )

    def test_get_specific_ignore_pattern(self):
        p = self.make_plugin()
        p.compiled_ignores = [(ig, wh.re_compile(ig)) for ig in (r"\.jpg$", r"/logout")]
        self.assertEqual(p.get_specific_ignore_pattern("http://a/logout"), "/logout")
        self.assertIsNone(p.get_specific_ignore_pattern("http://a/ok"))

    def test_get_urls_twitter_orig(self):
        p = self.make_plugin()
        item = _item("https://pbs.twimg.com/media/abc.jpg:large")
        extra = p.get_urls(item)
        self.assertEqual(extra[0]["url"], "https://pbs.twimg.com/media/abc.jpg:orig")

    def test_get_urls_quora(self):
        p = self.make_plugin()
        extra = p.get_urls(_item("https://www.quora.com/Some-Question"))
        self.assertEqual(extra[0]["url"], "https://www.quora.com/Some-Question?share=1")
        self.assertIsNone(p.get_urls(_item("https://www.quora.com/Q?share=1")))

    def test_get_urls_other(self):
        self.assertIsNone(self.make_plugin().get_urls(_item("http://example.com/")))

    def test_accept_url_drops_data_urls_and_applies_ignores(self):
        p = self.make_plugin()
        p.update_ignores = lambda: None
        p.all_start_urls = ["http://example.com/"]
        p.job_data = {"suppress_ignore_reports": True}
        p.combined_ignore_regexp = wh.compile_combined_regexp([r"\.jpg$"])
        p.compiled_ignores = []

        self.assertFalse(p.accept_url(_item("data:text/plain,hi"), True, {}))
        self.assertFalse(p.accept_url(_item("http://example.com/x.jpg"), True, {}))
        self.assertTrue(p.accept_url(_item("http://example.com/x.html"), True, {}))
        self.assertFalse(p.accept_url(_item("http://example.com/x.html"), False, {}))

    def test_start_urls_are_never_ignored(self):
        p = self.make_plugin()
        p.update_ignores = lambda: None
        p.all_start_urls = ["http://example.com/x.jpg"]
        p.job_data = {"suppress_ignore_reports": True}
        p.combined_ignore_regexp = wh.compile_combined_regexp([r"\.jpg$"])
        self.assertTrue(p.accept_url(_item("http://example.com/x.jpg"), True, {}))
        self.assertFalse(p.accept_url(_item("http://example.com/x.jpg"), False, {}))


def _item(url):
    class UrlInfo:
        raw = url

    class Request:
        url_info = UrlInfo()

    class Item:
        request = Request()
        url_record = None

    return Item()


class _FakeLoop:
    def __init__(self, raises=None):
        self.handlers = {}
        self._raises = raises

    def add_signal_handler(self, sig, callback):
        if self._raises is not None:
            raise self._raises
        self.handlers[sig] = callback


def _fake_self(loop):
    return types.SimpleNamespace(
        loop=loop,
        graceful_stop_callback=lambda: None,
        forceful_stop_callback=lambda: None,
    )


class AddSignalHandlersTests(unittest.TestCase):
    def test_registers_sigint_and_sigterm(self):
        import signal

        loop = _FakeLoop()
        wh.GrabSitePlugin.add_signal_handlers(_fake_self(loop))
        self.assertEqual(set(loop.handlers), {signal.SIGINT, signal.SIGTERM})

    def test_not_implemented_is_tolerated(self):
        # Windows event loops raise NotImplementedError here; startup must
        # continue without stop-signal handlers instead of crashing.
        loop = _FakeLoop(raises=NotImplementedError())
        wh.GrabSitePlugin.add_signal_handlers(_fake_self(loop))
        self.assertEqual(loop.handlers, {})

    def test_other_errors_propagate(self):
        loop = _FakeLoop(raises=RuntimeError("loop closed"))
        with self.assertRaises(RuntimeError):
            wh.GrabSitePlugin.add_signal_handlers(_fake_self(loop))


if __name__ == "__main__":
    unittest.main()
