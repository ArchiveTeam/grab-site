import unittest

from tests.unit import _stubs  # noqa: F401
from libgrabsite.dupes import DupesInMemory


class DupesInMemoryTests(unittest.TestCase):
    def test_unknown_digest_returns_none(self):
        self.assertIsNone(DupesInMemory().get_old_url(b"abc"))

    def test_set_then_get(self):
        db = DupesInMemory()
        db.set_old_url(b"abc", "http://example.com/a")
        self.assertEqual(db.get_old_url(b"abc"), "http://example.com/a")

    def test_overwrite(self):
        db = DupesInMemory()
        db.set_old_url(b"abc", "http://example.com/a")
        db.set_old_url(b"abc", "http://example.com/b")
        self.assertEqual(db.get_old_url(b"abc"), "http://example.com/b")

    def test_digests_are_independent(self):
        db = DupesInMemory()
        db.set_old_url(b"a", "u1")
        db.set_old_url(b"b", "u2")
        self.assertEqual(db.get_old_url(b"a"), "u1")
        self.assertEqual(db.get_old_url(b"b"), "u2")


try:
    import lmdb  # noqa: F401
except ImportError:
    lmdb = None


@unittest.skipIf(lmdb is None, "lmdb not installed")
class DupesOnDiskTests(unittest.TestCase):
    def test_roundtrip(self):
        import tempfile
        from libgrabsite.dupes import DupesOnDisk

        with tempfile.TemporaryDirectory() as d:
            db = DupesOnDisk(d)
            self.assertIsNone(db.get_old_url(b"k"))
            db.set_old_url(b"k", "http://example.com/é")
            self.assertEqual(db.get_old_url(b"k"), "http://example.com/é")

    def test_existing_file_path_opens_as_single_file_env(self):
        import os
        import tempfile
        from libgrabsite.dupes import DupesOnDisk

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dupes.lmdb")
            db = DupesOnDisk(path)  # path does not exist yet: directory env
            db.set_old_url(b"k", "u")
            db._env.close()

            file_path = os.path.join(d, "single.lmdb")
            import lmdb as _lmdb

            _lmdb.open(file_path, subdir=False).close()
            self.assertTrue(os.path.isfile(file_path))
            db2 = DupesOnDisk(file_path)
            db2.set_old_url(b"a", "http://x")
            self.assertEqual(db2.get_old_url(b"a"), "http://x")

    def test_reopen_existing_directory_keeps_data(self):
        import tempfile
        from libgrabsite.dupes import DupesOnDisk

        with tempfile.TemporaryDirectory() as d:
            db = DupesOnDisk(d)
            db.set_old_url(b"k", "u")
            db._env.close()
            self.assertEqual(DupesOnDisk(d).get_old_url(b"k"), "u")


if __name__ == "__main__":
    unittest.main()
