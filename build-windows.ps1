param(
  [switch]$IncludePdf
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pyinstaller
if ($IncludePdf) {
  python -m pip install ".[pdf]"
}

$hiddenImports = @("PIL._tkinter_finder")
if ($IncludePdf) {
  $hiddenImports += "fitz"
}

$args = @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--name", "OptimizerZero",
  "--paths", (Join-Path $PSScriptRoot "src"),
  "gui_entry.py"
)
foreach ($hiddenImport in $hiddenImports) {
  $args = @("--hidden-import", $hiddenImport) + $args
}
foreach ($excluded in @("torch", "tensorflow", "pandas", "scipy", "matplotlib", "sklearn", "IPython", "jupyter")) {
  $args = @("--exclude-module", $excluded) + $args
}

python -m PyInstaller @args

$dist = Join-Path $PSScriptRoot "dist\OptimizerZero"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "LICENSE") -Destination (Join-Path $dist "LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "docs\DIST_README.txt") -Destination (Join-Path $dist "README.txt") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "docs\GITHUB_RELEASE_DRAFT.md") -Destination (Join-Path $dist "RELEASE_NOTES.md") -Force

Write-Host "Built: $(Join-Path $dist 'OptimizerZero.exe')"
if (-not $IncludePdf) {
  Write-Host "Note: lightweight build excludes bundled PyMuPDF; run with -IncludePdf for PDF cleanup support."
}
