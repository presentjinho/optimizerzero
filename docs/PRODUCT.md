# OptimizerZero Product Notes

## Positioning

OptimizerZero is a local-first compression assistant.

- broader input scope: archives, document containers, OpenDocument/JAR, TAR/TGZ, PDFs, images, generic files
- safety-first defaults: preserve originals, verify outputs, skip larger results
- practical preflight: analyze folders, find duplicates, cap huge files before processing
- user-controlled compression: simple goals first, advanced target size and minimum savings when needed
- public-ready wording: no piracy/downloader framing

## Current Engine

- ZIP/CBZ: recompress entries; image entries keep their original format
- EPUB: preserve `mimetype` as first stored entry; validate required EPUB structure
- DOCX/PPTX/XLSX/ODT/ODS/ODP/JAR: ZIP container recompression
- TAR/TGZ/TAR.GZ/TAR.BZ2/TAR.XZ: TAR container recompression with path-safety validation
- PDF: PyMuPDF + pikepdf lossless cleanup, deflate, object streams, page-count verification
- Images: PNG lossless optimization; JPEG/WEBP quality control when lossy compression is allowed
- Generic files: fallback to verified `.ozero.zip` when no format-specific optimizer exists
- Multi-file jobs: use local CPU workers for parallel desktop processing
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
- PyMuPDF and pikepdf PDF support in the default Windows build, with a lite build option
- output-name collision avoidance
- Netlify-ready Web Lite app
- PWA cache and installable Web Lite shell
- simplified goals: smart, quality, smallest
- `analyze` and `duplicates` CLI commands
- smart defaults plus target-size, min-saving, max-size, and worker controls
- GUI analysis, simplified goals, and local multi-worker compression
- cleanup script for Python caches, demo outputs, and optional build artifacts
