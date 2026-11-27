import collections
import re
import types
import unittest
from unittest import mock

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
        with self.assertRaises(ValueError):
            wh.get_patterns_for_ignore_set("")

    def test_path_traversal_name_rejected(self):
        for name in ("../global", "a/b", "/etc/hostname", "..", "global.txt"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                wh.get_patterns_for_ignore_set(name)

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
    def test_changed_until_marked_seen(self):
        from unittest import mock

        w = wh.FileChangedWatcher("/some/file")
        with (
            mock.patch.object(wh, "mtime_with_cache", side_effect=[10, 10, 10, 11]),
            mock.patch("builtins.print"),
        ):
            self.assertTrue(w.has_changed())
            # Not marked seen (e.g. parse failed): still reported as changed.
            self.assertTrue(w.has_changed())
            w.mark_seen()
            self.assertFalse(w.has_changed())
            self.assertTrue(w.has_changed())

    def test_missing_file_is_unchanged_not_error(self):
        w = wh.FileChangedWatcher("/nonexistent/definitely/missing")
        wh.clear_file_caches()
        self.assertFalse(w.has_changed())
        w.mark_seen()  # no-op
        self.assertEqual(w.last_mtime, -1)


class FileCacheTests(unittest.TestCase):
    def setUp(self):
        wh.clear_file_caches()
        self.addCleanup(wh.clear_file_caches)

    def test_mtime_missing_file_returns_none(self):
        self.assertIsNone(wh.mtime_with_cache("/nonexistent/definitely/missing"))

    def test_cache_clear_forces_refresh(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "f")
            self.assertFalse(wh.path_exists_with_cache(path))
            open(path, "w").close()
            self.assertFalse(wh.path_exists_with_cache(path))  # cached
            wh.clear_file_caches()
            self.assertTrue(wh.path_exists_with_cache(path))

    def test_decorator_cache_clear(self):
        calls = []

        @wh.caching_decorator
        def f(path):
            calls.append(path)

        f("p")
        f.cache_clear()
        f("p")
        self.assertEqual(calls, ["p", "p"])


class UpdateRetryTests(unittest.TestCase):
    """A failed parse must not consume the change."""

    def setUp(self):
        import os
        import tempfile

        wh.clear_file_caches()
        self.addCleanup(wh.clear_file_caches)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "delay")
        self.p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        self.p.job_data = {}
        self.p.watchers = {"delay": wh.FileChangedWatcher(self.path)}

    def write(self, text):
        with open(self.path, "w") as f:
            f.write(text)
        wh.clear_file_caches()

    def test_delay_retried_after_bad_parse(self):
        from unittest import mock

        self.write("12-")  # half-written
        with mock.patch.object(wh.logger, "exception"):
            self.p.update_delay()
        self.assertNotIn("delay_min", self.p.job_data)

        # Rewritten (possibly with an identical mtime); must still be picked up.
        self.write("100-200")
        self.p.update_delay()
        self.assertEqual(self.p.job_data["delay_min"], 100)
        self.assertEqual(self.p.job_data["delay_max"], 200)

    def test_delay_not_reparsed_after_success(self):
        self.write("5")
        self.p.update_delay()
        self.p.job_data["delay_min"] = -1
        wh.clear_file_caches()
        self.p.update_delay()
        self.assertEqual(self.p.job_data["delay_min"], -1)

    def test_deleted_file_does_not_raise_or_log(self):
        import os
        from unittest import mock

        self.write("5")
        os.remove(self.path)
        wh.clear_file_caches()
        with mock.patch.object(wh.logger, "exception") as log_exc:
            self.p.update_delay()
        log_exc.assert_not_called()


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

        with mock.patch.object(wh.logger, "exception") as log_exc:
            self.assertIsNone(f())
        log_exc.assert_called_once()


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


class _SizeError:
    def size(self):
        raise OSError("fstat failed")


class _Body:
    def __init__(self, n):
        self._n = n

    def size(self):
        return self._n


class _Response:
    def __init__(self, body):
        self.body = body
        self.reason = "OK"


class _ItemSession:
    def __init__(self, response):
        self.response = response
        self.request = types.SimpleNamespace(
            url_info=types.SimpleNamespace(raw="http://example.com/x")
        )
        self.url_record = None


class HandleResultBytesTests(unittest.TestCase):
    """handle_result must tolerate a body size that cannot be determined."""

    def make_plugin(self):
        p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        p.job_data = collections.defaultdict(int)
        p.job_data["bytes_downloaded"] = 0
        p.update_igoff = mock.Mock()
        p.put_ws_queue = mock.Mock()
        p.should_stop = mock.Mock(return_value=False)
        return p

    def test_error_without_response_does_not_raise(self):
        # wpull calls handle_error before any response exists, so response
        # is None. Previously this raised TypeError (int += None).
        p = self.make_plugin()
        session = _ItemSession(response=None)
        result = p.handle_error(session, OSError("connection refused"))
        self.assertEqual(result, wh.Actions.NORMAL)
        self.assertEqual(p.job_data["bytes_downloaded"], 0)
        self.assertEqual(p.job_data["runk"], 1)

    def test_unknown_body_size_on_success_does_not_raise(self):
        p = self.make_plugin()
        resp = _Response(_SizeError())
        result = p.handle_result(
            types.SimpleNamespace(raw="http://example.com/x"), None, None, resp
        )
        self.assertEqual(result, wh.Actions.NORMAL)
        self.assertEqual(p.job_data["bytes_downloaded"], 0)

    def test_known_body_size_is_accumulated(self):
        p = self.make_plugin()
        p.job_data["bytes_downloaded"] = 10
        resp = _Response(_Body(25))
        p.handle_result(
            types.SimpleNamespace(raw="http://example.com/x"), None, None, resp
        )
        self.assertEqual(p.job_data["bytes_downloaded"], 35)

    def test_unknown_size_does_not_discard_running_total(self):
        p = self.make_plugin()
        p.job_data["bytes_downloaded"] = 10
        p.handle_error(_ItemSession(response=None), OSError("reset"))
        resp = _Response(_SizeError())
        p.handle_result(
            types.SimpleNamespace(raw="http://example.com/x"), None, None, resp
        )
        self.assertEqual(p.job_data["bytes_downloaded"], 10)


class PutWsQueueTests(unittest.TestCase):
    def test_queued_job_data_is_a_snapshot(self):
        # The sender serializes later, so the event must keep the counters it
        # had when it happened, not whatever job_data holds at send time.
        import asyncio

        p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        p.job_data = {"items_queued": 1}
        p.ws_queue = asyncio.Queue(maxsize=10)
        p.put_ws_queue({"type": "download", "job_data": p.job_data})
        p.job_data["items_queued"] = 99
        queued = p.ws_queue.get_nowait()
        self.assertEqual(queued["job_data"]["items_queued"], 1)


class CombinedRegexpRobustnessTests(unittest.TestCase):
    """One bad ignore pattern must not disable the rest."""

    def test_bad_pattern_rejected_others_still_match(self):
        rx = wh.compile_combined_regexp([r"\.jpg$", r"foo(?i)bar", r"/logout"])
        self.assertTrue(rx.search("http://a/x.jpg"))
        self.assertTrue(rx.search("http://a/logout"))
        self.assertIsNone(rx.search("http://a/page.html"))
        self.assertEqual([p for p, _ in rx.rejected], [r"foo(?i)bar"])
        self.assertEqual(rx.accepted, [r"\.jpg$", r"/logout"])

    def test_rejected_pattern_has_error_message(self):
        rx = wh.compile_combined_regexp(["("])
        self.assertEqual(len(rx.rejected), 1)
        self.assertTrue(rx.rejected[0][1])

    def test_leading_inline_flag_pattern_matches(self):
        # Valid alone, but "(?i)" is not allowed inside a larger alternation.
        rx = wh.compile_combined_regexp([r"(?i)FOO", r"\.jpg$"])
        self.assertTrue(rx.search("http://a/foo"))
        self.assertTrue(rx.search("http://a/x.jpg"))
        self.assertEqual(rx.rejected, [])

    def test_numbered_backref_alone_matches(self):
        # Wrapping used to make \1 refer to the wrapper group and fail to compile.
        rx = wh.compile_combined_regexp([r"^(a)\1$"])
        self.assertTrue(rx.search("aa"))
        self.assertIsNone(rx.search("ab"))

    def test_backref_in_later_pattern_binds_to_its_own_group(self):
        # Joining renumbers groups: \1 used to point at the first pattern's group.
        rx = wh.compile_combined_regexp([r"^b(x)$", r"^(a)\1$"])
        self.assertTrue(rx.search("aa"))
        self.assertTrue(rx.search("bx"))
        self.assertIsNone(rx.search("ax"))

    def test_capturing_group_pattern_still_matches(self):
        rx = wh.compile_combined_regexp([r"(foo|bar)baz", r"/logout"])
        self.assertTrue(rx.search("http://a/xbarbaz"))
        self.assertTrue(rx.search("http://a/logout"))
        self.assertIsNone(rx.search("http://a/foobar"))

    def test_search_returns_match_object(self):
        rx = wh.compile_combined_regexp([r"\.jpg$"])
        self.assertEqual(rx.search("http://a/x.jpg").group(0), ".jpg")


class DefaultIgnoreStateTests(unittest.TestCase):
    def test_accept_url_before_ignores_load_does_not_raise(self):
        # Regression: combined_ignore_regexp used to be unset until the first
        # successful update_ignores(), so accept_url raised AttributeError.
        p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        self.assertIsNone(p.should_ignore_url("http://a/x.jpg", None))
        self.assertEqual(p.compiled_ignores, [])


class UpdateIgnoresTests(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile
        from unittest import mock

        wh.clear_file_caches()
        self.addCleanup(wh.clear_file_caches)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(wh, "working_dir", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.igsets = os.path.join(self.tmp.name, "igsets")
        self.ignores = os.path.join(self.tmp.name, "ignores")
        self.p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        self.p.all_start_netlocs = set()
        self.p.print_to_terminal = lambda s: None
        self.p.watchers = {
            "igsets": wh.FileChangedWatcher(self.igsets),
            "ignores": wh.FileChangedWatcher(self.ignores),
        }

    def write(self, path, text):
        with open(path, "w") as f:
            f.write(text)
        wh.clear_file_caches()

    def test_bad_igset_name_skipped_and_logged_once(self):
        from unittest import mock

        self.write(self.igsets, "no-such-set,../../etc/hostname")
        self.write(self.ignores, r"\.jpg$")
        with (
            mock.patch.object(wh.logger, "error") as log_err,
            mock.patch.object(wh.logger, "exception") as log_exc,
        ):
            self.p.update_ignores()
            self.p.update_ignores()  # same files: must not re-run or re-log
        self.assertEqual(log_err.call_count, 2)  # one per bad name, once
        log_exc.assert_not_called()
        self.assertTrue(self.p.combined_ignore_regexp.search("http://a/x.jpg"))

    def test_bad_regex_skipped_others_still_apply_logged_once(self):
        from unittest import mock

        self.write(self.igsets, "")
        self.write(self.ignores, "foo(?i)bar\n\\.jpg$\n")
        with mock.patch.object(wh.logger, "error") as log_err:
            self.p.update_ignores()
            self.p.update_ignores()
        self.assertEqual(log_err.call_count, 1)
        self.assertTrue(self.p.combined_ignore_regexp.search("http://a/x.jpg"))
        self.assertIsNone(self.p.combined_ignore_regexp.search("http://a/page"))

    def test_unexpected_failure_keeps_previous_set_and_is_marked_seen(self):
        from unittest import mock

        self.write(self.igsets, "")
        self.write(self.ignores, r"\.jpg$")
        self.p.update_ignores()
        self.assertTrue(self.p.combined_ignore_regexp.search("http://a/x.jpg"))

        self.write(self.ignores, r"\.png$")
        with (
            mock.patch.object(
                self.p, "_rebuild_ignores", side_effect=RuntimeError("boom")
            ),
            mock.patch.object(wh.logger, "exception") as log_exc,
        ):
            self.p.update_ignores()
            self.p.update_ignores()  # already marked seen: no second attempt
        self.assertEqual(log_exc.call_count, 1)
        self.assertTrue(self.p.combined_ignore_regexp.search("http://a/x.jpg"))

    def test_missing_igsets_file_still_applies_ignores_logged_once(self):
        from unittest import mock

        self.write(self.ignores, r"\.jpg$")  # igsets file never written
        with (
            mock.patch.object(wh.logger, "error") as log_err,
            mock.patch.object(wh.logger, "exception") as log_exc,
        ):
            self.p.update_ignores()
            self.p.update_ignores()
        self.assertEqual(log_err.call_count, 1)
        log_exc.assert_not_called()
        self.assertTrue(self.p.combined_ignore_regexp.search("http://a/x.jpg"))


class StartUrlTests(unittest.TestCase):
    """Start URLs for START_URL and --input-file crawls."""

    def setUp(self):
        import os
        import tempfile
        from unittest import mock

        wh.clear_file_caches()
        self.addCleanup(wh.clear_file_caches)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(wh, "working_dir", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = self.tmp.name
        self.os = os

    def write(self, name, text):
        with open(self.os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_start_url_crawl_drops_blank_lines(self):
        self.write("all_start_urls", "http://a.test/\n\n")
        self.assertEqual(wh.read_start_urls(), ["http://a.test/"])

    def test_input_file_crawl_reads_urls_from_input_file(self):
        # --input-file crawls record no start URL, so all_start_urls is empty.
        self.write("all_start_urls", "")
        self.write("input_file", "http://a.test/1\n\n  http://b.test/2  \n\n")
        self.assertEqual(wh.read_start_urls(), ["http://a.test/1", "http://b.test/2"])

    def test_empty_crawl_has_no_start_urls(self):
        self.write("all_start_urls", "")
        self.assertEqual(wh.read_start_urls(), [])

    def test_no_empty_netloc_from_input_file_crawl(self):
        self.write("all_start_urls", "")
        self.write("input_file", "http://a.test/1\n")
        netlocs = wh.start_netlocs(wh.read_start_urls())
        self.assertEqual(netlocs, {"a.test"})
        self.assertNotIn("", netlocs)

    def test_any_start_netloc_expands_to_input_file_hosts_only(self):
        self.write("all_start_urls", "")
        self.write("input_file", "http://a.test/1\nhttp://b.test/2\n")
        p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        p.all_start_netlocs = wh.start_netlocs(wh.read_start_urls())
        out = p.ignore_pattern_to_regexp_strings(r"^https?://{any_start_netloc}/x")
        self.assertEqual(
            sorted(out),
            sorted(
                [
                    r"^https?://" + re.escape("a.test") + "/x",
                    r"^https?://" + re.escape("b.test") + "/x",
                ]
            ),
        )

    def test_input_file_start_url_is_exempt_from_ignores(self):
        self.write("all_start_urls", "")
        self.write("input_file", "http://a.test/x.jpg\n")
        p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        p.update_ignores = lambda: None
        p.all_start_urls = set(wh.read_start_urls())
        p.job_data = {"suppress_ignore_reports": True}
        p.combined_ignore_regexp = wh.compile_combined_regexp([r"\.jpg$"])
        p.compiled_ignores = []
        # Without the exemption this would be ignored (False).
        self.assertTrue(p.accept_url(_item("http://a.test/x.jpg"), True, {}))


if __name__ == "__main__":
    unittest.main()
