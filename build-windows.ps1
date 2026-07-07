param(
  [switch]$Lite
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pyinstaller
if (-not $Lite) {
  python -m pip install ".[pdf]"
}

$hiddenImports = @("PIL._tkinter_finder")
if (-not $Lite) {
  $hiddenImports += "fitz"
  $hiddenImports += "pikepdf"
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
foreach ($excluded in @("torch", "tensorflow", "pandas", "scipy", "matplotlib", "sklearn", "IPython", "jupyter", "lxml")) {
  $args = @("--exclude-module", $excluded) + $args
}

python -m PyInstaller @args

$dist = Join-Path $PSScriptRoot "dist\OptimizerZero"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "LICENSE") -Destination (Join-Path $dist "LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "docs\DIST_README.txt") -Destination (Join-Path $dist "README.txt") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "docs\GITHUB_RELEASE_DRAFT.md") -Destination (Join-Path $dist "RELEASE_NOTES.md") -Force

Write-Host "Built: $(Join-Path $dist 'OptimizerZero.exe')"
if ($Lite) {
  Write-Host "Note: lite build excludes bundled PyMuPDF; use the default build for PDF cleanup support."
}
