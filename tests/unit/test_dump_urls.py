import contextlib
import io
import os
import sqlite3
import tempfile
import unittest

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


if __name__ == "__main__":
	unittest.main()
