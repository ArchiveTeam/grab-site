import unittest
from unittest import mock

from tests.unit import _stubs  # noqa: F401
from libgrabsite import wpull_tweaks as wt

LIMIT = 30 * 1024 * 1024


class FakeBody:
    def __init__(self, data=b"<html>hi</html>", size_error=None):
        self._data = data
        self._size_error = size_error
        self.content_calls = 0

    def size(self):
        if self._size_error is not None:
            raise self._size_error
        return len(self._data)

    def content(self):
        self.content_calls += 1
        return self._data


class FakeResponse:
    def __init__(self, body):
        self.body = body


class FakeRequest:
    class url_info:
        raw = "http://example.com/page"


class FakeItemSession:
    def __init__(self, body):
        self.response = FakeResponse(body)
        self.request = FakeRequest()


class FakeDupesDB:
    def __init__(self):
        self.seen = {}
        self.get_calls = 0
        self.set_calls = 0

    def get_old_url(self, digest):
        self.get_calls += 1
        return self.seen.get(digest)

    def set_old_url(self, digest, url):
        self.set_calls += 1
        self.seen[digest] = url


class ResponseBodySizeTests(unittest.TestCase):
    def test_returns_size_when_available(self):
        resp = FakeResponse(FakeBody(b"abc"))
        self.assertEqual(wt.response_body_size(resp), 3)

    def test_failed_size_lookup_is_reported_as_unknown(self):
        # A failed lookup must not look like a 0-byte (small) body.
        resp = FakeResponse(FakeBody(size_error=OSError("no fstat")))
        self.assertIsNone(wt.response_body_size(resp))


class ScrapeDocumentTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(wt.ProcessingRule, "scrape_document")
        self.super_scrape = patcher.start()
        self.addCleanup(patcher.stop)
        html = mock.patch.object(wt.HTMLReader, "is_response", return_value=False)
        html.start()
        self.addCleanup(html.stop)

    def make_rule(self, db):
        return wt.DupeSpottingProcessingRule(fetch_rule=None, dupes_db=db)

    def test_dupes_db_is_required(self):
        with self.assertRaises(KeyError):
            wt.DupeSpottingProcessingRule(fetch_rule=None)

    def test_small_body_is_read_and_deduplicated(self):
        db = FakeDupesDB()
        rule = self.make_rule(db)
        body = FakeBody(b"same page")
        rule.scrape_document(FakeItemSession(body))
        self.assertEqual(body.content_calls, 1)
        self.assertEqual(self.super_scrape.call_count, 1)

    def test_duplicate_small_body_skips_link_extraction(self):
        db = FakeDupesDB()
        rule = self.make_rule(db)
        rule.scrape_document(FakeItemSession(FakeBody(b"same page")))
        rule.scrape_document(FakeItemSession(FakeBody(b"same page")))
        # Only the first copy reaches link extraction.
        self.assertEqual(self.super_scrape.call_count, 1)

    def test_oversized_body_is_not_read_and_links_still_extracted(self):
        db = FakeDupesDB()
        rule = self.make_rule(db)
        body = FakeBody(b"x" * (LIMIT + 1))
        with mock.patch.object(FakeBody, "size", return_value=LIMIT + 1):
            rule.scrape_document(FakeItemSession(body))
        self.assertEqual(body.content_calls, 0)
        self.assertEqual(db.get_calls, 0)
        self.assertEqual(self.super_scrape.call_count, 1)

    def test_unknown_size_does_not_read_body(self):
        # Regression: when size() fails, the body must not be read in full.
        db = FakeDupesDB()
        rule = self.make_rule(db)
        body = FakeBody(size_error=OSError("Unsupported operation."))
        rule.scrape_document(FakeItemSession(body))
        self.assertEqual(body.content_calls, 0)

    def test_unknown_size_still_extracts_links(self):
        rule = self.make_rule(FakeDupesDB())
        body = FakeBody(size_error=OSError("Unsupported operation."))
        rule.scrape_document(FakeItemSession(body))
        self.assertEqual(self.super_scrape.call_count, 1)


if __name__ == "__main__":
    unittest.main()
