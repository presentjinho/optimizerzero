import re
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.options = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "option":
            self.options.append(values)


class WebAssetTests(unittest.TestCase):
    def read(self, relative):
        return (WEB / relative).read_text(encoding="utf-8")

    def test_web_assets_are_valid_utf8_without_mojibake(self):
        bad_markers = (
            "\ufffd",
            "\u8e42",
            "\u6028",
            "\uf9ce",
            "\u91c9",
            "\ub6af",
            "\uc495",
            "\ub369",
        )
        for path in WEB.glob("*"):
            if path.suffix.lower() in {".html", ".js", ".css", ".json", ".webmanifest", ".md"} or path.name in {"_headers", "robots.txt"}:
                text = path.read_text(encoding="utf-8")
                self.assertFalse(any(marker in text for marker in bad_markers), path.name)

    def test_app_references_existing_html_ids(self):
        parser = IdParser()
        parser.feed(self.read("index.html"))
        app = self.read("app.js")
        referenced_ids = set(re.findall(r'document\.querySelector\("#([^"]+)"\)', app))

        self.assertIn("targetSize", parser.ids)
        self.assertIn("minSavings", parser.ids)
        self.assertLessEqual(referenced_ids, parser.ids)

    def test_intent_options_have_korean_recommendations(self):
        parser = IdParser()
        parser.feed(self.read("index.html"))

        intent_options = [option for option in parser.options if option.get("value") in {"archive", "share", "messenger", "email", "quality"}]
        self.assertEqual(len(intent_options), 5)
        for option in intent_options:
            message = option.get("data-message", "")
            self.assertIn("\ucd94\ucc9c", message)

    def test_service_worker_caches_required_assets(self):
        worker = self.read("service-worker.js")
        for asset in (
            "./index.html",
            "./styles.css",
            "./app.js",
            "./PRIVACY.md",
            "./manifest.webmanifest",
            "./icon.svg",
            "./vendor/jszip.min.js",
        ):
            self.assertIn(asset, worker)
        self.assertIn('caches.match("./index.html")', worker)

    def test_web_uses_local_jszip_vendor_file(self):
        html = self.read("index.html")
        worker = self.read("service-worker.js")

        self.assertIn("./vendor/jszip.min.js", html)
        self.assertIn("./vendor/jszip.min.js", worker)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("cdn.jsdelivr.net", worker)
        self.assertTrue((WEB / "vendor" / "JSZIP_LICENSE.markdown").exists())

    def test_privacy_note_matches_local_first_claims(self):
        privacy = self.read("PRIVACY.md")

        self.assertIn("not uploaded", privacy)
        self.assertIn("does not include analytics", privacy)
        self.assertIn("JSZip is bundled", privacy)

    def test_cloudflare_pages_config_points_to_web(self):
        wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")

        self.assertIn('name = "optimizerzero"', wrangler)
        self.assertIn('pages_build_output_dir = "./web"', wrangler)
        self.assertNotIn("api", wrangler.lower())
        self.assertNotIn("token", wrangler.lower())

    def test_app_reports_archive_dependency_status(self):
        app = self.read("app.js")

        self.assertIn("dependencyStatus", app)
        self.assertIn("archive engine ready", app)
        self.assertIn("image-only / archive engine unavailable", app)
        self.assertIn("Archive engine unavailable. Standalone images still work.", app)

    def test_web_javascript_syntax(self):
        for script in ("app.js", "service-worker.js"):
            with self.subTest(script=script):
                try:
                    completed = subprocess.run(
                        ["node", "--check", str(WEB / script)],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                except FileNotFoundError:
                    self.skipTest("node is not installed")
                self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
