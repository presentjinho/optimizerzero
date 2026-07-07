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
                self.assertNotIn("?/span", text, path.name)
                self.assertNotIn("?/button", text, path.name)

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

    def test_mobile_layout_and_file_picker_are_supported(self):
        html = self.read("index.html")
        css = self.read("styles.css")
        app = self.read("app.js")

        self.assertIn('class="drop-zone" id="dropZone" tabindex="0" for="fileInput"', html)
        self.assertIn('class="visually-hidden" type="file" multiple', html)
        self.assertIn("@media (max-width: 560px)", css)
        self.assertIn("min-height: 100dvh", css)
        self.assertIn("-webkit-text-size-adjust: 100%", css)
        self.assertIn('"Noto Sans KR", "Malgun Gothic"', css)
        self.assertIn("font-size: 16px", css)
        self.assertNotIn('el.dropZone.addEventListener("click"', app)

    def test_strength_slider_has_seven_levels(self):
        html = self.read("index.html")
        app = self.read("app.js")

        self.assertIn('id="strength" type="range" min="1" max="7" step="1" value="4"', html)
        ticks_block = html.split('class="strength-ticks"', 1)[1].split("</div>", 1)[0]
        self.assertEqual(ticks_block.count("<span>"), 7)
        self.assertIn("const STRENGTH_LEVELS = [", app)
        self.assertEqual(app.count("label:"), 7)
        self.assertIn("\ub098\ub178 \uc555\ucd95", app)
        self.assertIn("\ucd5c\ub300 \uc555\ucd95", app)
        self.assertIn('el.strength.addEventListener("input", applyStrength)', app)

    def test_nano_level_actually_recompresses_instead_of_a_no_op(self):
        # Level 1 (나노 압축) used to set lossBudget "none", which makes
        # optimizeImageFile() skip recompression outright -- a loose image file at
        # the gentlest setting produced zero savings, which reads as "broken" to a
        # user moving the slider off its default. It must still touch pixels, just
        # at a very high quality floor.
        app = self.read("app.js")
        levels_block = app.split("const STRENGTH_LEVELS = [", 1)[1].split("];", 1)[0]
        first_level = levels_block.strip().splitlines()[0]
        self.assertNotIn('lossBudget: "none"', first_level)
        self.assertIn('quality: 97', first_level)

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
            "./vendor/pdf-lib.min.js",
            "./optimize-core.js",
            "./worker.js",
            "./avif-jxl-worker.js",
            "./vendor/jsquash-avif/avif_enc.wasm",
            "./vendor/jsquash-avif/encode.js",
            "./vendor/jsquash-jxl/jxl_enc.wasm",
            "./vendor/jsquash-jxl/encode.js",
        ):
            self.assertIn(asset, worker)
        self.assertIn('caches.match("./index.html")', worker)
        self.assertIn('optimizerzero-web-lite-v12', worker)

    def test_static_headers_force_utf8_for_korean_text(self):
        headers = self.read("_headers")

        self.assertIn("Content-Type: text/html; charset=utf-8", headers)
        self.assertIn("Content-Type: text/css; charset=utf-8", headers)
        self.assertIn("Content-Type: application/javascript; charset=utf-8", headers)
        self.assertIn("/vendor/jszip.min.js", headers)
        self.assertIn("/vendor/pdf-lib.min.js", headers)
        self.assertIn("Content-Type: text/markdown; charset=utf-8", headers)

    def test_web_uses_local_vendor_files(self):
        html = self.read("index.html")
        worker = self.read("service-worker.js")

        self.assertIn("./vendor/jszip.min.js", html)
        self.assertIn("./vendor/pdf-lib.min.js", html)
        self.assertIn("./vendor/jszip.min.js", worker)
        self.assertIn("./vendor/pdf-lib.min.js", worker)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("cdn.jsdelivr.net", worker)
        self.assertTrue((WEB / "vendor" / "JSZIP_LICENSE.markdown").exists())
        self.assertTrue((WEB / "vendor" / "PDF_LIB_LICENSE.md").exists())

    def test_privacy_note_matches_local_first_claims(self):
        privacy = self.read("PRIVACY.md")

        self.assertIn("not uploaded", privacy)
        self.assertIn("does not include analytics", privacy)
        self.assertIn("JSZip and pdf-lib are bundled", privacy)

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
        self.assertIn("vendor/pdf-lib.min.js", script)
        self.assertIn("vendor/PDF_LIB_LICENSE.md", script)
        self.assertIn("Move-Item -LiteralPath $tempWebZipPath -Destination $webZipPath", script)
        self.assertIn("finally", script)

    def test_release_package_reuses_web_package_script(self):
        script = (ROOT / "package-release.ps1").read_text(encoding="utf-8")
        build = (ROOT / "build-windows.ps1").read_text(encoding="utf-8")
        verify = (ROOT / "verify-release.ps1").read_text(encoding="utf-8")

        self.assertIn('"package-web.ps1"', script)
        self.assertNotIn("Compress-Archive -Path $webFiles.FullName", script)
        self.assertIn("[switch]$Lite", script)
        self.assertIn("windows-pdf.zip", script)
        self.assertIn("python -m pip install \".[pdf]\"", build)
        self.assertIn('"pikepdf"', build)
        self.assertIn("windows-pdf.zip", verify)

    def test_release_verify_writes_artifact_manifest(self):
        script = (ROOT / "verify-release.ps1").read_text(encoding="utf-8")

        self.assertIn("OptimizerZero-release-manifest.json", script)
        self.assertIn("Add-ManifestItem", script)
        self.assertIn('-Role "web-lite"', script)
        self.assertIn('-Role "windows-app"', script)
        self.assertIn("sha256 = $Sha256", script)
        self.assertIn("function Test-Manifest", script)
        self.assertIn("vendor/pdf-lib.min.js", script)
        self.assertIn("vendor/PDF_LIB_LICENSE.md", script)
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

    def test_ci_workflow_is_manual_to_avoid_failure_mail_noise(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn(".\\verify-web.ps1", workflow)

    def test_private_preview_auth_uses_cloudflare_secret(self):
        middleware = (ROOT / "functions" / "_middleware.js").read_text(encoding="utf-8")

        self.assertIn("OPTIMIZERZERO_PASSWORD", middleware)
        self.assertIn("OPTIMIZERZERO_USER", middleware)
        self.assertIn("WWW-Authenticate", middleware)
        self.assertIn("context.next()", middleware)
        self.assertIn('guarded.headers.set("Cache-Control", "no-store")', middleware)
        self.assertIn('guarded.headers.set("Vary", "Authorization")', middleware)
        self.assertNotIn("password123", middleware.lower())

    def test_cloudflare_secrets_docs_exist(self):
        doc = (ROOT / "docs" / "GITHUB_SECRETS_CLOUDFLARE_KO.md").read_text(encoding="utf-8")

        self.assertIn("CLOUDFLARE_API_TOKEN", doc)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID", doc)
        self.assertIn("GitHub repository secret", doc)
        self.assertIn("token은 README, issue, commit, 채팅에 붙여넣지 않는다", doc)

    def test_app_reports_archive_dependency_status(self):
        app = self.read("app.js")
        core = self.read("optimize-core.js")

        self.assertIn("dependencyStatus", app)
        self.assertIn("압축 엔진 준비됨", app)
        self.assertIn("PDF 엔진 준비됨", app)
        self.assertIn("압축 엔진을 불러오지 못했습니다.", core)
        self.assertIn("PDF 엔진을 불러오지 못했습니다.", core)

    def test_web_recompresses_images_inside_supported_containers(self):
        core = self.read("optimize-core.js")

        self.assertIn('const imageOptimizableArchiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx", "odt", "ods", "odp", "jar"])', core)
        self.assertIn("imageOptimizableArchiveExts.has(fileExt)", core)
        self.assertIn('const archiveImageExts = new Set(["jpg", "jpeg", "webp", "bmp", "gif", "png"])', core)

    def test_web_keeps_archive_entry_when_image_recompression_fails(self):
        core = self.read("optimize-core.js")

        self.assertIn("try {", core)
        self.assertIn("({ blob: optimized } = await recompressImage(data, mimeType, opts.quality, opts.maxDimension))", core)
        self.assertIn("return { blob: data, changed: false, skipped: true }", core)
        self.assertIn("imageEntriesSkipped", core)
        self.assertIn("이미지 ${imageEntriesSkipped}개는 원본 유지", core)

    def test_web_skips_recompression_for_animated_images(self):
        core = self.read("optimize-core.js")

        self.assertIn("async function isAnimatedGif(blob)", core)
        self.assertIn("async function isAnimatedWebp(blob)", core)
        self.assertIn("async function isAnimatedPng(blob)", core)
        self.assertIn("async function isUnsafeToRecompress(ext, blob)", core)
        self.assertIn("움직이는 이미지라 프레임 보존을 위해 원본 유지", core)

    def test_web_has_generic_zip_fallback(self):
        core = self.read("optimize-core.js")
        readme = self.read("README.md")

        self.assertIn("async function optimizeGenericFile(file, opts)", core)
        self.assertIn("일반 ZIP 압축", core)
        self.assertIn(".ozero.zip", core)
        self.assertIn("Generic-file `.ozero.zip` fallback", readme)

    def test_web_pdf_mode_is_explicit(self):
        html = self.read("index.html")
        core = self.read("optimize-core.js")
        readme = self.read("README.md")

        self.assertIn("pdf", html)
        self.assertIn('const pdfExts = new Set(["pdf"])', core)
        self.assertIn("async function optimizePdfFile(file, opts)", core)
        self.assertIn("PDFLib.PDFDocument.load", core)
        self.assertIn("useObjectStreams: true", core)
        self.assertIn(".ozero.pdf", core)
        self.assertNotIn("PDF web safe ZIP", core)
        self.assertIn("PDF browser-side rewrite", readme)

    def test_web_uses_worker_pool_for_multiple_files(self):
        app = self.read("app.js")
        worker = self.read("worker.js")

        self.assertIn("navigator.hardwareConcurrency", app)
        self.assertIn("function runWithWorkerPool(files, opts, onDone, workerScript = \"./worker.js\", workerOptions, onFailure)", app)
        self.assertIn("new Worker(workerScript, workerOptions)", app)
        self.assertIn("function runSequentialFallback(files, opts, onDone)", app)
        self.assertIn("importScripts(", worker)
        self.assertIn("optimizeFile(file, opts)", worker)

    def test_web_routes_avif_jxl_codecs_to_module_worker(self):
        app = self.read("app.js")
        core = self.read("optimize-core.js")
        html = self.read("index.html")
        avif_jxl_worker = self.read("avif-jxl-worker.js")

        self.assertIn("function runWithCodecRouting(files, opts, onDone)", app)
        self.assertIn('"./avif-jxl-worker.js", { type: "module" }', app)
        self.assertIn("codec: selectedCodec()", app)
        # "auto" (the default codec) must run the AVIF engine but fall a
        # single file back to WebP on a hard encode failure rather than
        # recording it as an error.
        self.assertIn('opts.codec === "auto"', app)
        self.assertIn('optimizeFile(file, { ...opts, codec: "webp" })', app)
        self.assertIn('<option value="auto" selected>', html)
        self.assertIn("self.onmessage = async (event)", avif_jxl_worker)
        self.assertIn('import("./vendor/jsquash-avif/encode.js")', avif_jxl_worker)
        self.assertIn('import("./vendor/jsquash-jxl/encode.js")', avif_jxl_worker)
        # PDFs/archives can't carry AVIF/JXL streams (PDF spec only allows
        # DCTDecode/JPXDecode image filters) -- optimize-core.js's PDF/archive
        # paths must stay untouched by the AVIF/JXL codec picker.
        self.assertNotIn("avif", core.lower())
        self.assertNotIn("jxl", core.lower())

    def test_web_javascript_syntax(self):
        for script in ("app.js", "optimize-core.js", "worker.js", "service-worker.js"):
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
