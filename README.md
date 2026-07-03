# OptimizerZero Web Lite

Static browser version for Netlify-style sharing.

## What Works

- ZIP/CBZ/EPUB/DOCX/PPTX/XLSX recompression with JSZip
- PNG/JPG/WEBP browser-side image recompression
- Loss budget and quality control for standalone image conversion
- Purpose presets for archive, sharing, messenger, email, and quality-first use
- PWA cache for reopening after the first visit
- Download optimized copies
- Download all optimized outputs as one ZIP
- Download JSON report
- Rejected-file feedback and total saved percentage
- No server upload

## Limits

- Large files depend on browser memory.
- PDF cleanup is desktop/Python only.
- Encrypted archives are not supported.
- Browser image conversion uses WebP output for standalone images.
- Archive entries keep their original file names and formats.

## Deploy

Upload this `web/` folder to Netlify, or set Netlify publish directory to `web`.
