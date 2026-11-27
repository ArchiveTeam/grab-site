import contextlib
import io
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from tests.unit import _stubs  # noqa: F401
from libgrabsite import dump_urls

main = getattr(dump_urls.main, "callback", dump_urls.main)


class DumpUrlsTests(unittest.TestCase):
    def _dump(self, setup_sql, status):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "wpull.db")
            conn = sqlite3.connect(path)
            conn.executescript(setup_sql)
            conn.commit()
            conn.close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(path, status)
            return out.getvalue().splitlines()

    def test_wpull2_schema(self):
        sql = """
			CREATE TABLE url_strings (id INTEGER PRIMARY KEY, url TEXT);
			CREATE TABLE queued_urls (id INTEGER PRIMARY KEY, url_string_id INTEGER, status TEXT);
			INSERT INTO url_strings VALUES (1, 'http://a/'), (2, 'http://b/'), (3, 'http://c/');
			INSERT INTO queued_urls VALUES (1, 1, 'done'), (2, 2, 'todo'), (3, 3, 'done');
		"""
        self.assertEqual(self._dump(sql, "done"), ["http://a/", "http://c/"])
        self.assertEqual(self._dump(sql, "todo"), ["http://b/"])
        self.assertEqual(self._dump(sql, "error"), [])

    def test_wpull1_schema_fallback(self):
        sql = """
			CREATE TABLE url_strings (id INTEGER PRIMARY KEY, url TEXT);
			CREATE TABLE urls (id INTEGER PRIMARY KEY, url_str_id INTEGER, status TEXT);
			INSERT INTO url_strings VALUES (1, 'http://old/');
			INSERT INTO urls VALUES (1, 1, 'skipped');
		"""
        self.assertEqual(self._dump(sql, "skipped"), ["http://old/"])

    def _run_tracking_connections(self, path, status):
        # Wrap sqlite3.connect so the test can inspect the connection main() opened.
        real_connect = sqlite3.connect
        opened = []

        def connect(p, *args, **kwargs):
            conn = real_connect(p, *args, **kwargs)
            opened.append(conn)
            return conn

        out = io.StringIO()
        with mock.patch.object(dump_urls.sqlite3, "connect", side_effect=connect):
            with contextlib.redirect_stdout(out):
                try:
                    main(path, status)
                except sqlite3.OperationalError as e:
                    return opened, e
        return opened, None

    def _assert_closed(self, conn):
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_connection_closed_on_success(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "wpull.db")
            setup = sqlite3.connect(path)
            setup.executescript(
                "CREATE TABLE url_strings (id INTEGER PRIMARY KEY, url TEXT);"
                "CREATE TABLE queued_urls (id INTEGER PRIMARY KEY, url_string_id INTEGER, status TEXT);"
                "INSERT INTO url_strings VALUES (1, 'http://a/');"
                "INSERT INTO queued_urls VALUES (1, 1, 'done');"
            )
            setup.commit()
            setup.close()
            opened, err = self._run_tracking_connections(path, "done")
        self.assertIsNone(err)
        self.assertEqual(len(opened), 1)
        self._assert_closed(opened[0])

    def test_connection_closed_on_error(self):
        # Neither schema exists: the fallback query fails and the error propagates.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "wpull.db")
            sqlite3.connect(path).close()
            opened, err = self._run_tracking_connections(path, "done")
        self.assertIsNotNone(err)
        self.assertEqual(len(opened), 1)
        self._assert_closed(opened[0])

    def test_no_fallback_when_wpull2_schema_matches(self):
        # A 2.x/5.x database must never reach the 1.x query, even if it is empty.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "wpull.db")
            setup = sqlite3.connect(path)
            setup.executescript(
                "CREATE TABLE url_strings (id INTEGER PRIMARY KEY, url TEXT);"
                "CREATE TABLE queued_urls (id INTEGER PRIMARY KEY, url_string_id INTEGER, status TEXT);"
            )
            setup.commit()
            setup.close()
            opened, err = self._run_tracking_connections(path, "done")
        self.assertIsNone(err)
        self.assertEqual(len(opened), 1)


if __name__ == "__main__":
    unittest.main()
