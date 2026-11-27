import unittest

from tests.unit import _stubs  # noqa: F401
from libgrabsite.main import replace_2arg


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


if __name__ == "__main__":
    unittest.main()
