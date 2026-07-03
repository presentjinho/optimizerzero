# OptimizerZero Product Notes

## Positioning

OptimizerZero is a local-first compression assistant.

- broader input scope: archives, document containers, PDFs, images
- safety-first defaults: preserve originals, verify outputs, skip larger results
- practical preflight: analyze folders, find duplicates, cap huge files before processing
- user-controlled compression: loss budget, image quality, target size, and minimum savings
- public-ready wording: no piracy/downloader framing

## Current Engine

- ZIP/CBZ: recompress entries; image entries keep their original format
- EPUB: preserve `mimetype` as first stored entry; validate required EPUB structure
- DOCX/PPTX/XLSX: ZIP container recompression only
- PDF: PyMuPDF lossless cleanup, deflate, garbage collection, page-count verification
- Images: PNG lossless optimization; JPEG/WEBP quality control when lossy compression is allowed
- Analyze: summarize supported files by kind, size, and optional validity
- Duplicates: SHA-256 identical-file grouping for supported file types

Acceptance gate:

1. candidate written to temp folder
2. format-specific verification
3. smaller-than-original check
4. optional target/min-saving checks
5. atomic move to final output
6. original preserved unless user explicitly uses `--in-place`

Implemented for v0.1.0:

- synthetic public demo assets
- release zip SHA256 generation
- release verification script
- optional PDF dependency split
- output-name collision avoidance
- Netlify-ready Web Lite app
- PWA cache and installable Web Lite shell
- purpose presets for archive/share/messenger/email/quality-first use
- `analyze` and `duplicates` CLI commands
- loss budget, quality, target-size, min-saving, and max-size controls
- GUI analysis and user-centered compression controls
- cleanup script for Python caches, demo outputs, and optional build artifacts
