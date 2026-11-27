import unittest

from tests.unit import _stubs  # noqa: F401
import contextlib
import io
import os
import re
import tempfile

from libgrabsite.main import main, replace_2arg, load_resume_state, write_control_files


class Replace2ArgTests(unittest.TestCase):
    def test_replaces_pair_with_replacement(self):
        args = ["a", "--x", "1", "b"]
        replace_2arg(args, "--x", ["--y", "2"])
        self.assertEqual(args, ["a", "--y", "2", "b"])

    def test_empty_replacement_removes_pair(self):
        args = ["a", "--x", "1", "b"]
        replace_2arg(args, "--x", [])
        self.assertEqual(args, ["a", "b"])

    def test_pair_at_end(self):
        args = ["a", "--x", "1"]
        replace_2arg(args, "--x", ["--z", "9"])
        self.assertEqual(args, ["a", "--z", "9"])

    def test_only_first_occurrence(self):
        args = ["--x", "1", "--x", "2"]
        replace_2arg(args, "--x", [])
        self.assertEqual(args, ["--x", "2"])

    def test_missing_argument_is_a_noop(self):
        args = ["a", "b"]
        replace_2arg(args, "--x", [])
        self.assertEqual(args, ["a", "b"])

    def test_missing_argument_does_not_insert_replacement(self):
        args = ["a", "b"]
        replace_2arg(args, "--x", ["--y", "2"])
        self.assertEqual(args, ["a", "b"])

    def test_missing_argument_in_empty_list(self):
        args = []
        replace_2arg(args, "--x", ["--y", "2"])
        self.assertEqual(args, [])

    def test_similar_argument_is_not_matched(self):
        # Only an exact token match counts, not a prefix or a value.
        args = ["--xy", "1", "a"]
        replace_2arg(args, "--x", ["--z", "9"])
        self.assertEqual(args, ["--xy", "1", "a"])


class ResumeStateTests(unittest.TestCase):
    def make_dir(self, tmp, **kw):
        write_control_files(
            tmp, None, False, "abc123", "http://a.test/", ("http://a.test/",),
            kw.get("warc_name", "a.test-2026-01-01-abc123"), 2, -1, "", False,
            True, False, None, "0",
        )
        open(os.path.join(tmp, "wpull.db"), "w").close()

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_dir(tmp)
            st = load_resume_state(tmp)
            self.assertEqual(st["id"], "abc123")
            self.assertEqual(st["warc_name"], "a.test-2026-01-01-abc123")
            self.assertEqual(st["all_start_urls"], ["http://a.test/"])

    def test_warc_name_falls_back_to_cdx(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_dir(tmp)
            os.remove(os.path.join(tmp, "warc_name"))
            open(os.path.join(tmp, "old-name.cdx"), "w").close()
            self.assertEqual(load_resume_state(tmp)["warc_name"], "old-name")

    def test_missing_database_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_dir(tmp)
            os.remove(os.path.join(tmp, "wpull.db"))
            with self.assertRaises(SystemExit):
                load_resume_state(tmp)


def run_main(**overrides):
    """Call main() with its defaults; returns (stdout, exit code or None)."""
    kwargs = dict(
        concurrency=2, concurrent=-1, delay="0", recursive=True, offsite_links=True,
        igsets="", ignore_sets="", no_global_igset=False, import_ignores=None,
        igon=False, debug=False, video=True, level="inf", page_requisites_level="5",
        max_content_length=-1, sitemaps=True, dupespotter=True,
        warc_max_size=5368709120, ua="ua", input_file=None, wpull_args="",
        start_url=(), id=None, dir=None, resume=False, finished_warc_dir=None,
        permanent_error_status_codes="404", which_wpull_args_partial=False,
        which_wpull_command=False,
    )
    kwargs.update(overrides)
    fn = getattr(main, "callback", main)
    out = io.StringIO()
    code = None
    with contextlib.redirect_stdout(out):
        try:
            fn(**kwargs)
        except SystemExit as e:
            code = e.code
    return out.getvalue(), code


class ResumeMainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = os.path.join(self._tmp.name, "crawl")

    def start_crawl(self, **kw):
        out, code = run_main(
            start_url=("http://a.test/",), dir=self.dir, which_wpull_command=True, **kw
        )
        self.assertIsNone(code)
        open(os.path.join(self.dir, "wpull.db"), "w").close()
        return out

    def read(self, name):
        with open(os.path.join(self.dir, name)) as f:
            return f.read()

    def test_new_crawl_records_warc_name(self):
        out = self.start_crawl()
        self.assertTrue(self.read("warc_name").startswith("a.test-"))
        self.assertNotIn("--warc-append", out)

    def test_resume_requires_dir(self):
        _, code = run_main(resume=True)
        self.assertEqual(code, 1)

    def test_resume_rejects_start_url_input_file_and_id(self):
        self.start_crawl()
        for extra in ({"start_url": ("http://b.test/",)}, {"input_file": "f"}, {"id": "x"}):
            _, code = run_main(resume=True, dir=self.dir, which_wpull_command=True, **extra)
            self.assertEqual(code, 1, extra)

    def test_resume_missing_dir_exits(self):
        _, code = run_main(resume=True, dir=self.dir)
        self.assertEqual(code, 1)

    def test_resume_reuses_state_and_appends_warcs(self):
        self.start_crawl()
        warc_name = self.read("warc_name")
        crawl_id = self.read("id")
        out, code = run_main(resume=True, dir=self.dir, which_wpull_command=True)
        self.assertIsNone(code)
        self.assertIn("--warc-append", out)
        self.assertIn("http://a.test/", out)
        self.assertIn(os.path.join(self.dir, warc_name), out)
        self.assertEqual(self.read("id"), crawl_id)

    def test_resume_does_not_overwrite_control_files(self):
        self.start_crawl()
        with open(os.path.join(self.dir, "ignores"), "w") as f:
            f.write("edited")
        with open(os.path.join(self.dir, "delay"), "w") as f:
            f.write("500")
        run_main(resume=True, dir=self.dir, which_wpull_command=True)
        self.assertEqual(self.read("ignores"), "edited")
        self.assertEqual(self.read("delay"), "500")

    def test_resume_clears_temp_dir(self):
        self.start_crawl()
        stale = os.path.join(self.dir, "temp", "stale")
        open(stale, "w").close()
        run_main(resume=True, dir=self.dir, which_wpull_command=True)
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.isdir(os.path.join(self.dir, "temp")))

    def test_resume_clears_stop_file(self):
        # Ctrl-C and `touch DIR/stop` both create DIR/stop. Without removing it,
        # the first response on resume sees it and the crawl stops immediately.
        self.start_crawl()
        stop = os.path.join(self.dir, "stop")
        open(stop, "w").close()
        run_main(resume=True, dir=self.dir, which_wpull_command=True)
        self.assertFalse(os.path.exists(stop))

    def test_resume_without_stop_file_still_works(self):
        self.start_crawl()
        out, code = run_main(resume=True, dir=self.dir, which_wpull_command=True)
        self.assertIsNone(code)
        self.assertIn("--warc-append", out)

    def test_which_wpull_args_dry_run_keeps_stop_file(self):
        # The dry run prints the command and exits without starting a crawl, so
        # it must not change the crawl directory.
        self.start_crawl()
        stop = os.path.join(self.dir, "stop")
        open(stop, "w").close()
        run_main(resume=True, dir=self.dir, which_wpull_args_partial=True)
        self.assertTrue(os.path.exists(stop))

    def test_resume_input_file_crawl_uses_stored_input_file(self):
        src = os.path.join(self._tmp.name, "urls.txt")
        with open(src, "w") as f:
            f.write("http://a.test/1\n")
        out, code = run_main(input_file=src, dir=self.dir, which_wpull_command=True)
        self.assertIsNone(code)
        open(os.path.join(self.dir, "wpull.db"), "w").close()
        out, code = run_main(resume=True, dir=self.dir, which_wpull_command=True)
        self.assertIsNone(code)
        self.assertIn("--input-file " + os.path.join(self.dir, "input_file"), out)


class WarcNameTests(unittest.TestCase):
    """The WARC and default DIR names are derived from the start URL.

    They should only contain characters that need no quoting in a shell or
    cmd.exe: letters, digits, and -_.,+ .
    """

    SAFE = re.compile(r"^[-_a-zA-Z0-9.,+]+$")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self.addCleanup(os.chdir, self.cwd)

    def warc_name_for(self, url):
        out, code = run_main(start_url=(url,), which_wpull_command=True)
        self.assertIsNone(code)
        name = None
        for line in out.splitlines():
            if "--warc-file" in line:
                name = line.split("--warc-file ", 1)[1].split()[0]
        return name

    def test_url_with_shell_special_characters_is_sanitized(self):
        name = self.warc_name_for("http://a.test/x;y%20z@q=1&r=2")
        base = os.path.basename(name)
        self.assertRegex(base, self.SAFE)
        for ch in ";%@=":
            self.assertNotIn(ch, base)

    def test_safe_characters_are_kept(self):
        name = self.warc_name_for("http://a.test/v1.2,b+c")
        self.assertIn("a.test-v1.2,b+c-", os.path.basename(name))

    def test_default_dir_is_named_after_warc(self):
        out, code = run_main(
            start_url=("http://a.test/;evil",), which_wpull_command=True
        )
        self.assertIsNone(code)
        dirs = [d for d in os.listdir(self._tmp.name) if os.path.isdir(d)]
        self.assertEqual(len(dirs), 1)
        self.assertRegex(dirs[0], self.SAFE)


class RemoteInputFileTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self, data):
            self._buf = io.BytesIO(data)
            self.closed = False

        def read(self, n=-1):
            return self._buf.read(n)

        def close(self):
            self.closed = True

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()
            return False

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def fetch(self, response):
        from unittest import mock

        with mock.patch(
            "libgrabsite.main.urllib.request.urlopen", return_value=response
        ) as opener:
            write_control_files(
                self._tmp.name,
                "http://a.test/list.txt",
                True,
                "abc123",
                "http://a.test/",
                ("http://a.test/",),
                "w",
                2,
                -1,
                "",
                False,
                True,
                False,
                None,
                "0",
            )
        return opener

    def test_download_uses_a_timeout(self):
        opener = self.fetch(self.FakeResponse(b"http://a.test/1\n"))
        self.assertIsNotNone(opener.call_args.kwargs.get("timeout"))

    def test_response_is_closed_after_download(self):
        response = self.FakeResponse(b"http://a.test/1\n")
        self.fetch(response)
        self.assertTrue(response.closed)

    def test_contents_are_written(self):
        self.fetch(self.FakeResponse(b"http://a.test/1\n"))
        with open(os.path.join(self._tmp.name, "input_file"), "rb") as f:
            self.assertEqual(f.read(), b"http://a.test/1\n")


class IgsetOptionTests(unittest.TestCase):
    """Bad --igsets names exit before anything is created on disk."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = os.path.join(self._tmp.name, "crawl")

    def assert_rejected(self, igsets):
        _, code = run_main(igsets=igsets, start_url=("http://a.test/",), dir=self.dir)
        self.assertEqual(code, 1, igsets)
        self.assertFalse(os.path.exists(self.dir), igsets)

    def test_traversal_name_rejected(self):
        self.assert_rejected("../../../../etc/hostname")

    def test_unknown_set_rejected(self):
        self.assert_rejected("no-such-set")

    def test_non_plain_name_rejected(self):
        self.assert_rejected("blogs.txt")

    def test_known_set_accepted(self):
        _, code = run_main(
            igsets="blogs, twitter,", start_url=("http://a.test/",),
            dir=self.dir, which_wpull_command=True,
        )
        self.assertIsNone(code)


if __name__ == "__main__":
    unittest.main()
