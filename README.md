# OptimizerZero

OptimizerZero is a safety-first compression and archive optimizer for local files.

It is user-centered: choose how much space to save, how much visual quality to trade, and when to skip files.

- ZIP, CBZ, EPUB, DOCX, PPTX, XLSX: safe container recompression
- PDF: lossless cleanup with PyMuPDF when available
- JPG, JPEG, PNG, WEBP, BMP, TIFF: optional image recompression
- Image archives: format-preserving image optimization when useful
- Analyze folders by type, size, and optional validity
- Find byte-identical duplicate files before optimizing
- Batch limits for huge files, minimum saving percentage, target size, quality, and loss budget
- Original files are preserved by default
- Output is accepted only when it verifies and is smaller

## Quick Start

```powershell
python -m optimizerzero scan "D:\Files"
python -m optimizerzero analyze "D:\Files" --recursive --verify
python -m optimizerzero duplicates "D:\Files" --recursive
python -m optimizerzero verify "D:\Files" --recursive
python -m optimizerzero optimize "D:\Files\book.cbz"
python -m optimizerzero optimize "D:\Files" --recursive --profile balanced --min-savings-percent 1
python -m optimizerzero optimize "D:\Photos" --recursive --loss-budget low --quality 88
python -m optimizerzero optimize "D:\Photos" --recursive --loss-budget high --target-size 5MB
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
.\verify-release.ps1
.\verify-web.ps1
.\cleanup.ps1 -DemoOutputs
```

## User-Controlled Compression

- `--loss-budget none`: do not use lossy image recompression.
- `--loss-budget low`: near-original image quality.
- `--loss-budget medium`: smaller files with visible-quality tradeoff.
- `--loss-budget high`: size first; check results before replacing originals.
- `--quality 1-100`: direct JPEG/WEBP quality control.
- `--target-size 5MB`: keep only outputs that fit the target.
- `--min-savings-percent 1`: skip tiny wins.
- `--max-size 150MB`: avoid heavy files in mixed folders.

OptimizerZero preserves image file formats in archives. The Web Lite app converts standalone images to WebP only when lossy compression is allowed.

## Profiles

- `safe`: container/PDF cleanup and lossless image cleanup only.
- `balanced`: conservative image recompression.
- `strong`: stronger image recompression. Use after checking visual quality.

## Web Lite

`web/` contains a Netlify-ready browser app for people who do not want to install anything.

- files stay in the browser
- PWA cache lets visitors reopen the app after the first visit
- JSZip is included locally, so deployed Web Lite does not depend on an external CDN
- intent presets choose practical defaults for archive, sharing, messenger, email, and quality-first use
- ZIP/CBZ can recompress JPG/JPEG/WEBP entries in the browser when visual loss is allowed
- good for small ZIP/CBZ/EPUB/Office containers and standalone images
- not meant for heavy PDF cleanup or very large folders

Deploy with `netlify.toml` or set the publish directory to `web`.
Cloudflare Pages can also read `wrangler.toml`, which points Pages at `./web`.

See `docs/STRATEGY_KO.md` for positioning and sharing strategy.
See `docs/DEPLOY_FREE_KO.md` for free hosting and domain options.
See `docs/PRIVATE_DEPLOY_KO.md` for private-first deployment.
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
