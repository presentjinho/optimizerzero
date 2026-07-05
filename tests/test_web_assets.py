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

    def test_web_rows_can_be_removed_individually(self):
        html = self.read("index.html")
        app = self.read("app.js")
        css = self.read("styles.css")

        self.assertIn('class="remove-button"', html)
        self.assertIn("function fileKey(file)", app)
        self.assertIn("function removeFile(key)", app)
        self.assertIn("function resultForKey(key)", app)
        self.assertIn("function configureDownloadButton(button, blob, name)", app)
        self.assertIn('row.dataset.key = key', app)
        self.assertIn('row.querySelector(".remove-button").addEventListener("click", () => removeFile(key))', app)
        self.assertIn("const result = resultForKey(key)", app)
        self.assertIn("if (result.blob) configureDownloadButton", app)
        self.assertIn('state.results = state.results.filter((result) => result.key !== key)', app)
        self.assertIn(".remove-button", css)

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

    def test_local_first_architecture_doc_matches_no_server_data_decision(self):
        doc = (ROOT / "docs" / "LOCAL_FIRST_ARCHITECTURE_KO.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("서버 저장 없는 정적 웹앱", doc)
        self.assertIn("Cloudflare Pages", doc)
        self.assertIn("파일 처리: 브라우저 내부", doc)
        self.assertIn("중앙 DB: 사용하지 않는다", doc)
        self.assertIn("서버 업로드 압축: 사용하지 않는다", doc)
        self.assertIn("docs/LOCAL_FIRST_ARCHITECTURE_KO.md", readme)

    def test_cloudflare_pages_config_points_to_web(self):
        wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")

        self.assertIn('name = "optimizerzero"', wrangler)
        self.assertIn('pages_build_output_dir = "./web"', wrangler)
        self.assertNotIn("api", wrangler.lower())
        self.assertNotIn("token", wrangler.lower())

    def test_cloudflare_deploy_script_is_explicit(self):
        script = (ROOT / "deploy-cloudflare.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$Deploy", script)
        self.assertIn("Dry run only", script)
        self.assertIn("wrangler@latest", script)
        self.assertIn("--project-name", script)
        self.assertIn("optimizerzero", script)

    def test_web_package_uses_temporary_zip_before_replace(self):
        script = (ROOT / "package-web.ps1").read_text(encoding="utf-8")

        self.assertIn("$tempWebZipPath", script)
        self.assertIn("Compress-Archive -Path $webFiles.FullName -DestinationPath $tempWebZipPath", script)
        self.assertIn("tar -tf $tempWebZipPath", script)
        self.assertIn("Move-Item -LiteralPath $tempWebZipPath -Destination $webZipPath", script)
        self.assertIn("finally", script)

    def test_release_package_reuses_web_package_script(self):
        script = (ROOT / "package-release.ps1").read_text(encoding="utf-8")

        self.assertIn('"package-web.ps1"', script)
        self.assertNotIn("Compress-Archive -Path $webFiles.FullName", script)

    def test_release_verify_writes_artifact_manifest(self):
        script = (ROOT / "verify-release.ps1").read_text(encoding="utf-8")

        self.assertIn("OptimizerZero-release-manifest.json", script)
        self.assertIn("Add-ManifestItem", script)
        self.assertIn('-Role "web-lite"', script)
        self.assertIn('-Role "windows-app"', script)
        self.assertIn("sha256 = $Sha256", script)
        self.assertIn("function Test-Manifest", script)
        self.assertIn("Manifest SHA256 mismatch", script)
        self.assertIn("Test-Manifest -ManifestPath $manifestPath", script)

    def test_cloudflare_deploy_workflow_is_manual(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy-cloudflare.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertIn("CLOUDFLARE_API_TOKEN", workflow)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID", workflow)
        self.assertIn("cloudflare/wrangler-action@v3", workflow)
        self.assertIn("pages deploy web --project-name optimizerzero", workflow)

    def test_cloudflare_secrets_docs_exist(self):
        doc = (ROOT / "docs" / "GITHUB_SECRETS_CLOUDFLARE_KO.md").read_text(encoding="utf-8")

        self.assertIn("CLOUDFLARE_API_TOKEN", doc)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID", doc)
        self.assertIn("GitHub repository secret", doc)
        self.assertIn("token은 README, issue, commit, 채팅에 붙여넣지 않는다", doc)

    def test_app_reports_archive_dependency_status(self):
        app = self.read("app.js")

        self.assertIn("dependencyStatus", app)
        self.assertIn("archive engine ready", app)
        self.assertIn("image-only / archive engine unavailable", app)
        self.assertIn("Archive engine unavailable. Standalone images still work.", app)

    def test_web_recompresses_images_inside_supported_containers(self):
        app = self.read("app.js")

        self.assertIn('const imageOptimizableArchiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx"])', app)
        self.assertIn("imageOptimizableArchiveExts.has(fileExt)", app)
        self.assertIn('const archiveImageExts = new Set(["jpg", "jpeg", "webp"])', app)

    def test_web_keeps_archive_entry_when_image_recompression_fails(self):
        app = self.read("app.js")

        self.assertIn("try {", app)
        self.assertIn("optimized = await recompressImage(data, mimeType)", app)
        self.assertIn("return { blob: data, changed: false, skipped: true }", app)
        self.assertIn("imageEntriesSkipped", app)
        self.assertIn("image entries kept original", app)

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
