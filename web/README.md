# OptimizerZero Web Lite

Static browser version for Netlify-style sharing.

## What Works

- ZIP/CBZ/EPUB/DOCX/PPTX/XLSX recompression with JSZip
- JPG/JPEG/WEBP recompression inside ZIP/CBZ when visual loss is allowed
- PNG/JPG/WEBP browser-side image recompression
- Loss budget and quality control for standalone image conversion
- Per-file target size and minimum-savings controls
- Purpose presets for archive, sharing, messenger, email, and quality-first use
- PWA cache for reopening after the first visit
- Download optimized copies
- Download all optimized outputs as one ZIP
- Download JSON report
- Rejected-file feedback and total saved percentage
- No server upload
- JSZip is vendored locally under `vendor/`, so the app does not need an external CDN after deploy

See `PRIVACY.md` for the local-processing/privacy note.

## Limits

- Large files depend on browser memory.
- PDF cleanup is desktop/Python only.
- Encrypted archives are not supported.
- Browser image conversion uses WebP output for standalone images.
- Archive image recompression is limited to ZIP/CBZ JPG/JPEG/WEBP entries.
- EPUB and Office files use safe container recompression only.

## Deploy

Upload this `web/` folder to Netlify, or set Netlify publish directory to `web`.

For a shareable zip of only the static web app, run:

```powershell
.\package-web.ps1
```
