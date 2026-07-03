OptimizerZero v0.1.0

What this is
- A local, safety-first compression optimizer.
- Works on ZIP, CBZ, EPUB, DOCX, PPTX, XLSX, images, and optional PDFs.
- Preserves originals by default.
- Keeps output only when it verifies and is smaller.

How to run
1. Unzip the release folder.
2. Open OptimizerZero.exe.
3. Add files or a folder.
4. Use Analyze to preview file types and total size.
5. Pick Loss, Quality, Target, Max size, and Min savings as needed.
6. Start with Dry Run.
7. Use the safe profile first.

Safety notes
- The lightweight Windows build does not bundle PDF cleanup support.
- Use the Python package with "pip install .[pdf]" for PDF cleanup.
- Loss none keeps images visually unchanged.
- Higher loss budgets should be checked before replacing originals.
- Avoid running in-place unless you already have backups.

Verify download
- Compare the release zip SHA256 with the .sha256 file.
