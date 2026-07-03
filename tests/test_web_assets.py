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
        bad_markers = ("�", "蹂", "怨", "硫", "釉", "뚯", "쒕", "덉")
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
            self.assertIn("추천", message)

    def test_service_worker_caches_required_assets(self):
        worker = self.read("service-worker.js")
        for asset in ("./index.html", "./styles.css", "./app.js", "./manifest.webmanifest", "./icon.svg"):
            self.assertIn(asset, worker)

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
