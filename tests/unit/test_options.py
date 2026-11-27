import os
import tempfile
import unittest

from tests.unit import _stubs  # noqa: F401
import click.testing

import libgrabsite
from libgrabsite.main import main


class ParseDelayTests(unittest.TestCase):
    def test_single_value(self):
        self.assertEqual(libgrabsite.parse_delay("0"), (0, 0))
        self.assertEqual(libgrabsite.parse_delay("500"), (500, 500))

    def test_range(self):
        self.assertEqual(libgrabsite.parse_delay("100-200"), (100, 200))
        self.assertEqual(libgrabsite.parse_delay("7-7"), (7, 7))

    def test_whitespace_is_allowed(self):
        self.assertEqual(libgrabsite.parse_delay(" 1 - 2 \n"), (1, 2))

    def test_invalid_values_are_rejected(self):
        for bad in ["abc", "1-2-3", "5-", "-5", "", "-", "1.5", "1--2", "2-1"]:
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    libgrabsite.parse_delay(bad)


class ParseNonNegativeOrInfTests(unittest.TestCase):
    def test_accepted(self):
        for good in ["inf", "0", "5", " 3 "]:
            with self.subTest(value=good):
                libgrabsite.parse_non_negative_or_inf(good)

    def test_rejected(self):
        for bad in ["-1", "abc", "", "1.5", "infinity"]:
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    libgrabsite.parse_non_negative_or_inf(bad)


class CliValidationTests(unittest.TestCase):
    """Bad options must fail at the command line, before DIR is created."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = os.path.join(self._tmp.name, "crawl")

    def invoke(self, *args):
        result = click.testing.CliRunner().invoke(
            main, [*args, "--dir", self.dir, "http://a.test/"]
        )
        self.assertFalse(os.path.exists(self.dir), "DIR must not be created")
        return result

    def test_bad_delay_is_a_usage_error(self):
        for bad in ["abc", "1-2-3", "2-1"]:
            with self.subTest(value=bad):
                result = self.invoke("--delay", bad)
                self.assertEqual(result.exit_code, 2)
                self.assertIn("--delay", result.output)

    def test_bad_level_is_a_usage_error(self):
        result = self.invoke("--level", "-1")
        self.assertEqual(result.exit_code, 2)
        self.assertIn("--level", result.output)

    def test_bad_page_requisites_level_is_a_usage_error(self):
        result = self.invoke("--page-requisites-level", "abc")
        self.assertEqual(result.exit_code, 2)
        self.assertIn("--page-requisites-level", result.output)


if __name__ == "__main__":
    unittest.main()
