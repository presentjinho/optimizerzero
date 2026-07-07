# OptimizerZero

OptimizerZero is a safety-first compression and archive optimizer for local files.

It is user-centered: start with one practical goal, then tune limits only when needed.

- ZIP, CBZ, EPUB, DOCX, PPTX, XLSX, ODT, ODS, ODP, JAR: safe container recompression
- TAR, TGZ, TAR.GZ, TAR.BZ2, TAR.XZ: safe archive recompression
- PDF: lossless cleanup with PyMuPDF and pikepdf when available
- JPG, JPEG, PNG, WEBP, BMP, TIFF: optional image recompression
- HEIC/HEIF: optional image recompression on desktop with `pillow-heif` installed (`pip install "optimizerzero[heic]"`); the Web Lite browser app cannot decode HEIC (no browser support), so HEIC files there fall back to the generic ZIP wrapper
- ZIP/CBZ/EPUB/Office/OpenDocument containers: format-preserving image entry optimization when useful
- Generic files: verified `.ozero.zip` fallback when no format-specific optimizer exists
- Analyze folders by type, size, and optional validity
- Find byte-identical duplicate files before optimizing
- Simple goals for Smart, Quality, or Smallest output
- Local worker parallelism for multi-file desktop jobs
- Batch limits for huge files, minimum saving percentage, and target size
- Original files are preserved by default
- Output is accepted only when it verifies and is smaller

## Quick Start

```powershell
python -m optimizerzero scan "D:\Files"
python -m optimizerzero analyze "D:\Files" --recursive --verify
python -m optimizerzero duplicates "D:\Files" --recursive
python -m optimizerzero verify "D:\Files" --recursive
python -m optimizerzero optimize "D:\Files\book.cbz"
python -m optimizerzero optimize "D:\Files" --recursive --goal smart
python -m optimizerzero optimize "D:\Photos" --recursive --goal quality
python -m optimizerzero optimize "D:\Photos" --recursive --goal smallest --target-size 5MB
python -m optimizerzero optimize "D:\Files" --recursive --max-size 150MB --dry-run --report report.json
python -m optimizerzero gui
```

Windows shortcut style:

```powershell
.\run-gui.cmd
.\run-safe-scan.cmd "D:\Files" -r
.\build-windows.ps1
.\package-release.ps1
.\package-web.ps1
.\deploy-cloudflare.ps1
.\verify-release.ps1
.\verify-web.ps1
.\cleanup.ps1 -DemoOutputs
```

`verify-release.ps1` writes `releases/OptimizerZero-release-manifest.json` with artifact names, roles, sizes, and SHA256 hashes for sharing checks.

## User-Controlled Compression

Use goals first:

- `--goal smart`: recommended default; good savings with low visual risk.
- `--goal quality`: preserve quality; skip tiny wins.
- `--goal smallest`: stronger compression; review outputs before replacing originals.

Tune only when needed:

- `--loss-budget none`: do not use lossy image recompression.
- `--loss-budget low`: near-original image quality.
- `--loss-budget medium`: smaller files with visible-quality tradeoff.
- `--loss-budget high`: size first; check results before replacing originals.
- `--quality 1-100`: direct JPEG/WEBP quality control.
- `--target-size 5MB`: keep only outputs that fit the target. When one quality attempt misses, OptimizerZero automatically retries down a quality ladder, then a resize ladder, until the target is hit or both run out.
- `--max-dimension 1600`: cap an image's longest edge in pixels; applies unconditionally, independent of `--target-size`.
- `--min-savings-percent 1`: skip tiny wins.
- `--max-size 150MB`: avoid heavy files in mixed folders.
- `--workers 4`: use local CPU workers for multi-file jobs. Omit it for the safe automatic default.
- `--supported-only`: skip generic `.ozero.zip` fallback.

OptimizerZero preserves image file formats in archives. The Web Lite app converts standalone images to WebP only when lossy compression is allowed.

## Profiles

- `safe`: container/PDF cleanup and lossless image cleanup only.
- `balanced`: conservative image recompression.
- `strong`: stronger image recompression. Use after checking visual quality. PNGs also get palette quantization here (256 colors, more if a target size needs it) -- a big win on screenshots/illustrations, visibly lossy on photos.

Most users should use goals instead of profiles.

## Web Lite

`web/` contains a Netlify-ready browser app for people who do not want to install anything.

- files stay in the browser
- PWA cache lets visitors reopen the app after the first visit, including offline AVIF/JXL encoding
- JSZip and pdf-lib are bundled locally, so deployed Web Lite does not depend on an external CDN
- one strength slider (7 steps, nano to max) sets quality/target-size/limit together; advanced settings expose target size, minimum savings, max input size, image codec (WebP/AVIF/JPEG XL), and worker concurrency for finer control
- when a target size is set, a miss retries down a quality ladder and then a resize ladder before giving up, same as the desktop app
- multiple files compress in parallel across a Web Worker pool sized to the machine's CPU cores, with a live ETA during the run
- queue rows can be removed one by one before rerunning
- ZIP/CBZ/EPUB/Office containers can recompress JPG/JPEG/WEBP/BMP/GIF entries in the browser when visual loss is allowed
- damaged or unsupported image entries inside containers are kept original instead of failing the whole job
- PDF pages are rewritten with pdf-lib (cleanup + object streams), and embedded JPEG images are recompressed too when the loss budget allows it
- good for ZIP/CBZ/EPUB/Office containers, standalone images, and PDFs; very large folders are still better handled by the desktop app

Deploy with `netlify.toml` or set the publish directory to `web`.
Cloudflare Pages can also read `wrangler.toml`, which points Pages at `./web`.

See `docs/STRATEGY_KO.md` for positioning and sharing strategy.
See `docs/DEPLOY_FREE_KO.md` for free hosting and domain options.
See `docs/PRIVATE_DEPLOY_KO.md` for private-first deployment.
See `docs/LOCAL_FIRST_ARCHITECTURE_KO.md` for the no-server-data architecture decision.
See `docs/GITHUB_SECRETS_CLOUDFLARE_KO.md` for GitHub Actions Cloudflare secret setup.
See `docs/PRIVACY_KO.md` for the local-processing/privacy note.
Use `docs/CLOUDFLARE_PRIVATE_CHECKLIST_KO.md` when creating the private Cloudflare Pages app.

## Safety Model

- no original deletion by default
- no blind in-place overwrite
- no archive extraction into user folders
- no path traversal writes
- encrypted ZIP entries are rejected
- EPUB `mimetype` entry is preserved
- output is verified before it is kept
- larger outputs are skipped unless explicitly allowed
- CLI refuses `--in-place` unless `--yes` is provided
