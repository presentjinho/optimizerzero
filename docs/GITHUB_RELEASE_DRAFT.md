# OptimizerZero v0.1.0 Release Draft

## Title

OptimizerZero v0.1.0 - user-controlled safe compression

## Body

OptimizerZero is a local compression tool focused on preserving originals and letting users decide the tradeoff.

Highlights:

- ZIP, CBZ, EPUB, DOCX, PPTX, XLSX container recompression
- optional image optimization for standalone images and image archives
- user-controlled loss budget, direct image quality, and target output size
- analyze mode for type/size/validity summaries
- duplicate finder for byte-identical supported files
- max-size and minimum-saving guards for large batches
- dry-run mode and JSON reports
- verify mode for checking outputs without optimizing
- originals preserved by default
- output kept only after verification and smaller-size check
- unsafe ZIP paths and encrypted entries rejected
- lightweight Windows GUI build included
- Netlify-ready Web Lite app with result ZIP download
- cleanup script for local cache/demo/build artifacts

Download:

- `OptimizerZero-0.1.0-windows-lite.zip`
- `OptimizerZero-0.1.0-web-lite.zip`

Proof:

- `python -m compileall src gui_entry.py`
- `python -m unittest discover -s tests -v`
- `python -m optimizerzero doctor`
- `.\package-release.ps1`
- `.\verify-release.ps1`
