import os
import re
import unittest

from tests.unit import _stubs  # noqa: F401

from libgrabsite import dashboard_assets

PACKAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src", "libgrabsite")


class LookupTests(unittest.TestCase):
    def test_serves_listed_paths(self):
        self.assertEqual(dashboard_assets.lookup("/").file, "dashboard.html")
        self.assertEqual(dashboard_assets.lookup("/dashboard/app.js").file, "dashboard/app.js")

    def test_rejects_unlisted_and_traversal_paths(self):
        for path in (
            "/server.py",
            "/dashboard/../server.py",
            "/../libgrabsite/server.py",
            "/dashboard/app.js/",
            "/dashboard/missing.js",
            "/dashboard",
            "",
        ):
            with self.subTest(path=path):
                self.assertIsNone(dashboard_assets.lookup(path))

    def test_every_asset_file_exists(self):
        for path, asset in dashboard_assets.ASSETS.items():
            with self.subTest(path=path):
                self.assertTrue(os.path.isfile(os.path.join(PACKAGE_DIR, asset.file)))

    def test_modules_have_javascript_content_type(self):
        for path, asset in dashboard_assets.ASSETS.items():
            if asset.file.endswith(".js"):
                with self.subTest(path=path):
                    self.assertEqual(asset.content_type, dashboard_assets.JS)


class HtmlReferenceTests(unittest.TestCase):
    """Every local script and stylesheet the page loads must be served."""

    def test_page_references_are_all_served(self):
        with open(os.path.join(PACKAGE_DIR, "dashboard.html"), encoding="utf-8") as f:
            html = f.read()
        refs = re.findall(r'(?:src|href)="(dashboard/[^"]+)"', html)
        self.assertTrue(refs, "expected the page to reference its assets")
        served = {asset.file for asset in dashboard_assets.ASSETS.values()}
        for ref in refs:
            with self.subTest(ref=ref):
                self.assertIn(ref, served)

    def test_module_imports_are_all_served(self):
        served = {asset.file for asset in dashboard_assets.ASSETS.values()}
        for asset in dashboard_assets.ASSETS.values():
            if not asset.file.endswith(".js"):
                continue
            with open(os.path.join(PACKAGE_DIR, asset.file), encoding="utf-8") as f:
                source = f.read()
            for target in re.findall(r'from "\./([^"]+)";', source):
                with self.subTest(module=asset.file, target=target):
                    self.assertIn("dashboard/" + target, served)


if __name__ == "__main__":
    unittest.main()
