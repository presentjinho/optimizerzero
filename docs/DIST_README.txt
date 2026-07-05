OptimizerZero v0.1.0

What this is
- A local, safety-first compression optimizer.
- Works on ZIP, CBZ, EPUB, DOCX, PPTX, XLSX, PDFs, images, and generic files.
- Preserves originals by default.
- Keeps output only when it verifies and is smaller.

How to run
1. Unzip the release folder.
2. Open OptimizerZero.exe.
3. Add files or a folder.
4. Use Analyze to preview file types and total size.
5. Pick a Goal. Smart is the recommended default.
6. Start with Dry Run.
7. Use Workers "auto" to let the PC process multiple files at once.

Safety notes
- The default Windows build bundles PDF cleanup support.
- The lite Windows build excludes PDF cleanup support.
- Loss none keeps images visually unchanged.
- Higher loss budgets should be checked before replacing originals.
- Avoid running in-place unless you already have backups.

Verify download
- Compare the release zip SHA256 with the .sha256 file.
