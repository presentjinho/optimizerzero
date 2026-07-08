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
        self.assertIn("function configureDownloadButton(button, url, name)", app)
        self.assertIn('row.dataset.key = key', app)
        self.assertIn('row.querySelector(".remove-button").addEventListener("click", () => removeFile(key))', app)
        self.assertIn("const result = resultForKey(key)", app)
        self.assertIn("if (result.blobUrl) configureDownloadButton", app)
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

    def test_folder_input_and_type_grouping(self):
        # Dropping a folder (or a mixed pile of files) groups the queue by
        # type and the results ZIP mirrors those groups as folders.
        html = self.read("index.html")
        app = self.read("app.js")
        css = self.read("styles.css")

        self.assertIn('id="folderInput" class="visually-hidden" type="file" webkitdirectory multiple', html)
        self.assertIn('id="folderButton"', html)
        self.assertIn("function fileCategory(file)", app)
        self.assertIn("async function filesFromDataTransfer(dataTransfer)", app)
        # entries must be captured before the first await or the
        # DataTransferItemList is already gone
        self.assertIn("webkitGetAsEntry", app)
        self.assertIn("file-group-header", app)
        self.assertIn(".file-group-header", css)
        # results ZIP: folder per category only when the batch mixes types
        self.assertIn("categories.size > 1 ? `${result.category ||", app)

    def test_skip_messages_explain_why_and_what_to_try(self):
        # A bare "기준 미달" skip sends users off to ask a human what it
        # means. Skips must carry the reason and the next thing to try.
        core = self.read("optimize-core.js")
        self.assertIn("ALREADY_COMPRESSED_EXTS", core)
        self.assertIn("전용 인코더", core)
        self.assertIn("강력/최대 레벨은 페이지를 이미지로 재구성", core)
        self.assertIn("오히려 커집니다(텍스트 위주 PDF)", core)
        self.assertIn("데스크탑 앱이 더 안정적입니다", core)
        self.assertIn("내용: ${topEntries}", core)

    def test_worker_script_urls_are_version_busted_in_sync(self):
        # Worker importScripts and Worker() spawn URLs carry a ?vNN buster:
        # without it, a worker created before the service worker takes
        # control (or with no SW at all) loads whatever stale bytes the
        # browser HTTP cache still holds -- which shipped as "rasterize
        # silently never runs in the pool". The buster must stay in lockstep
        # with CACHE_NAME or it stops doing anything.
        sw = self.read("service-worker.js")
        worker = self.read("worker.js")
        app = self.read("app.js")
        version = re.search(r'optimizerzero-web-lite-(v\d+)', sw).group(1)
        self.assertGreaterEqual(worker.count(f"?{version}"), 5)
        self.assertGreaterEqual(app.count(f"?{version}"), 3)
        for text, name in ((worker, "worker.js"), (app, "app.js")):
            stray = set(re.findall(r"\?v\d+", text)) - {f"?{version}"}
            self.assertFalse(stray, f"{name} has mismatched versions: {stray}")
        self.assertIn("ignoreSearch: true", sw)
        self.assertIn(f'const APP_VERSION = "{version}";', app)

    def test_strength_curve_is_wide_and_monotonic(self):
        # The slider promises a spectrum: 나노 ~ visually original, 최대 ~
        # as small as usable. Every knob must move monotonically along it or
        # some level is pointless (a stronger level compressing less than a
        # weaker one shipped once as the 25MB-limit inversion).
        app = self.read("app.js")
        levels_block = app.split("const STRENGTH_LEVELS = [", 1)[1].split("];", 1)[0]
        qualities = [int(m) for m in re.findall(r"quality: (\d+)", levels_block)]
        self.assertEqual(len(qualities), 7)
        self.assertEqual(qualities, sorted(qualities, reverse=True))
        self.assertGreaterEqual(qualities[0], 95)
        self.assertLessEqual(qualities[-1], 50)
        dims = [int(m) for m in re.findall(r"maxDimension: (\d+)", levels_block)]
        set_dims = [d for d in dims if d]
        self.assertEqual(set_dims, sorted(set_dims, reverse=True))

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
        self.assertIn('optimizerzero-web-lite-v24', worker)

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

        self.assertIn("const result = await recompressImageWithLadder(data, opts, mimeType)", core)
        self.assertIn("if (!result || !result.blob) return { blob: data, changed: false, skipped: true }", core)
        self.assertIn("imageEntriesSkipped", core)
        self.assertIn("이미지 ${imageEntriesSkipped}개는 원본 유지", core)

    def test_web_chases_target_size_with_quality_ladder(self):
        core = self.read("optimize-core.js")

        self.assertIn("function qualityLadder(opts)", core)
        self.assertIn("async function recompressImageWithLadder(blob, opts, mimeType)", core)
        # no target size -> single predictable rung, same as before this feature
        self.assertIn("if (!opts.targetSizeBytes || opts.targetSizeBytes <= 0) return [chosen];", core)
        # every recompression path (standalone images, archive entries, PDF
        # embedded images) must go through the shared ladder, not a lone shot
        self.assertIn("await recompressImageWithLadder(file, opts,", core)
        self.assertIn("await recompressImageWithLadder(data, opts, mimeType)", core)
        self.assertIn("await recompressImageWithLadder(\n      new Blob([sourceBytes]", core)

    def test_web_falls_back_to_resizing_when_quality_alone_cannot_hit_a_target(self):
        core = self.read("optimize-core.js")
        worker = self.read("avif-jxl-worker.js")

        for source in (core, worker):
            self.assertIn("function dimensionLadder(opts)", source)
            # no target size -> single predictable cap, same as before this feature
            self.assertIn("if (!opts.targetSizeBytes || opts.targetSizeBytes <= 0", source)
        # WebP path nests the dimension ladder around the quality ladder
        self.assertIn("for (const maxDimension of dimensionLadder(opts)) {", core)
        self.assertIn("for (const quality of qualityLadder(opts)) {", core)
        # AVIF/JXL module worker mirrors the same two-lever retry
        self.assertIn("for (const maxDimension of dimensionLadder(opts)) {", worker)
        self.assertIn("for (const quality of qualityLadder(opts)) {", worker)

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

    def test_large_input_options_exist_for_capable_machines(self):
        # The 150MB ceiling was only ever a dropdown default, not an
        # engineering limit -- capable desktop browsers handle 300-500MB.
        # GB-range files stay desktop-app territory (whole-file-in-RAM
        # engines), which the option labels should not promise.
        html = self.read("index.html")
        self.assertIn('<option value="300">', html)
        self.assertIn('<option value="500">', html)
        self.assertIn('<option value="75" selected>', html)

    def test_web_pdf_scan_reconstruction_via_pdfjs(self):
        # Losslessly-stored (FlateDecode) page scans are what actually make
        # PDFs big, and stream replacement can't reach them in the browser.
        # pdf.js renders each page and the file is rebuilt as JPEG pages --
        # gated on the "high" loss budget (text stops being selectable) and
        # only kept when genuinely smaller.
        core = self.read("optimize-core.js")
        html = self.read("index.html")
        worker = self.read("worker.js")
        sw = self.read("service-worker.js")

        self.assertTrue((WEB / "vendor" / "pdfjs" / "pdf.min.js").exists())
        self.assertTrue((WEB / "vendor" / "pdfjs" / "pdf.worker.min.js").exists())
        self.assertTrue((WEB / "vendor" / "pdfjs" / "PDFJS_LICENSE").exists())
        self.assertIn("async function rasterizePdfDocument(", core)
        self.assertIn('opts.lossBudget === "high"', core)
        self.assertIn("스캔형 재구성", core)
        self.assertIn('"./vendor/pdfjs/pdf.min.js"', html.replace("'", '"'))
        # workers can't spawn pdf.js's nested worker and its fake-worker path
        # needs `document` -- unless pdf.worker.min.js is imported into the
        # same scope first. Its load-time handshake postMessage must be
        # swallowed or it leaks junk into the pool protocol.
        self.assertIn("./vendor/pdfjs/pdf.worker.min.js", worker)
        self.assertIn("self.postMessage = () => {};", worker)
        # pdf.js render needs a canvas factory in workers -- its default one
        # calls document.createElement for temp canvases (patterns/masks) and
        # only SOME content triggers that path, so the breakage was
        # intermittent: simple pages rendered, alpha-heavy pages failed.
        self.assertIn("class OffscreenCanvasFactory", core)
        self.assertIn("viewport, canvasFactory", core)
        self.assertIn("./vendor/pdfjs/pdf.min.js", sw)
        self.assertIn("./vendor/pdfjs/pdf.worker.min.js", sw)
        # a new SW version must not re-cache stale bytes from the HTTP cache
        self.assertIn('new Request(url, { cache: "reload" })', sw)

    def test_web_pdf_recompresses_common_real_world_image_variants(self):
        # Filter-array spelling and ICCBased-wrapped colorspaces are how most
        # real exporters mark embedded JPEGs. Only accepting the bare
        # /DCTDecode + /DeviceRGB shape left big PDFs effectively untouched.
        core = self.read("optimize-core.js")
        app = self.read("app.js")

        self.assertIn("function pdfFilterIsDct(", core)
        self.assertIn("function pdfColorSpaceIsRecompressable(", core)
        self.assertIn('PDFName.of("ICCBased")', core)
        # Canvas re-encode always outputs 8-bit RGB -- the dict must be
        # rewritten to match or gray/ICC sources render wrong after replace.
        self.assertIn('dict.set(PDFName.of("ColorSpace"), PDFName.of("DeviceRGB"))', core)
        self.assertIn('dict.delete(PDFName.of("DecodeParms"))', core)
        # Stronger presets should not reject files the default preset accepts.
        self.assertNotIn("limit: 25,", app)

    def test_web_uses_worker_pool_for_multiple_files(self):
        app = self.read("app.js")
        worker = self.read("worker.js")

        self.assertIn("navigator.hardwareConcurrency", app)
        self.assertIn("function runWithWorkerPool(files, opts, onDone, workerScript = \"./worker.js?", app)
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
        self.assertIn('"./avif-jxl-worker.js?v', app)
        self.assertIn("codec: selectedCodec()", app)
        # "auto" (the default codec) must run the AVIF engine but fall a
        # single file back to WebP on a hard encode failure rather than
        # recording it as an error.
        self.assertIn('opts.codec === "auto"', app)
        self.assertIn('optimizeFile(file, { ...opts, codec: "webp" })', app)
        self.assertIn('<option value="webp" selected>', html)
        self.assertIn('<option value="auto">', html)
        self.assertIn("self.onmessage = async (event)", avif_jxl_worker)
        self.assertIn('import("./vendor/jsquash-avif/encode.js")', avif_jxl_worker)
        self.assertIn('import("./vendor/jsquash-jxl/encode.js")', avif_jxl_worker)
        # PDFs/archives can't carry AVIF/JXL streams (PDF spec only allows
        # DCTDecode/JPXDecode image filters) -- optimize-core.js's PDF/archive
        # paths must stay untouched by the AVIF/JXL codec picker.
        self.assertNotIn("avif", core.lower())
        self.assertNotIn("jxl", core.lower())

    def test_web_falls_back_to_webp_pool_when_avif_worker_unsupported(self):
        app = self.read("app.js")

        self.assertIn(
            'const SUPPORTS_AVIF_JXL_WORKER = typeof OffscreenCanvas !== "undefined" && typeof Worker !== "undefined";',
            app,
        )
        self.assertIn('if (opts.codec === "webp" || !SUPPORTS_AVIF_JXL_WORKER) {', app)

    def test_web_scales_default_concurrency_to_device(self):
        app = self.read("app.js")

        self.assertIn("function detectAutoPoolSize()", app)
        self.assertIn('window.matchMedia("(pointer: coarse)").matches', app)
        self.assertIn("navigator.deviceMemory", app)
        self.assertIn("const AUTO_POOL_SIZE = detectAutoPoolSize();", app)

    def test_web_locks_clear_and_file_input_while_running(self):
        app = self.read("app.js")

        self.assertIn("function setRunning(running)", app)
        self.assertIn("el.clearButton.disabled = running", app)
        self.assertIn("el.fileInput.disabled = running", app)
        self.assertIn("if (!state.files.length || state.running) return;", app)
        self.assertIn("if (state.running) return;", app)

    def test_web_revokes_blob_urls_between_runs(self):
        app = self.read("app.js")

        self.assertIn("function revokeTrackedBlobUrls()", app)
        self.assertIn("URL.revokeObjectURL(url)", app)
        # must be called both when a run restarts and when the queue is cleared,
        # otherwise every re-render after a run leaks one Object URL per row.
        occurrences = app.count("revokeTrackedBlobUrls();")
        self.assertGreaterEqual(occurrences, 2)

    def test_web_before_after_preview_slider(self):
        app = self.read("app.js")
        html = self.read("index.html")
        css = self.read("styles.css")

        self.assertIn("function openPreview(file, result)", app)
        self.assertIn("function closePreview()", app)
        # only offer the preview for image results, and only once optimized
        self.assertIn("result.status === \"optimized\" && result.blobUrl && imageExts.has(extOf(file))", app)
        # the modal must be closed before URLs it references get revoked, or
        # a mid-preview run/clear would leave it pointing at a dead blob URL
        self.assertIn("closePreview();\n  revokeTrackedBlobUrls();", app)
        self.assertIn('id="previewModal"', html)
        self.assertIn('id="previewHandle"', html)
        # any class setting its own display beats the UA's [hidden] rule
        # (author rules always win) -- this bug shipped twice, once as an
        # always-visible preview modal and once as an empty-state box shown
        # next to real file rows. The global override kills the whole class.
        self.assertIn("[hidden] { display: none !important; }", css)

    def test_web_image_only_zip_becomes_cbz(self):
        core = self.read("optimize-core.js")

        self.assertIn("function isImageOnlyZipEntries(files)", core)
        # only a plain .zip gets relabeled -- .cbz/.epub/office formats are
        # already their own specific type and must not be touched
        self.assertIn('fileExt === "zip" && isImageOnlyZipEntries(source.files)', core)
        self.assertIn('.replace(/\\.[^.]+$/, ".ozero.cbz")', core)
        # OS junk files (Thumbs.db etc.) alongside images shouldn't block detection
        self.assertIn("IGNORABLE_ZIP_ENTRY_NAMES", core)

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
