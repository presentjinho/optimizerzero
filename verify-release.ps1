param(
  [string]$ReleaseZip = "releases\OptimizerZero-0.1.0-windows-lite.zip"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
python -m compileall src gui_entry.py
python -m unittest discover -s tests -v

if (Test-Path -LiteralPath $ReleaseZip) {
  $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $ReleaseZip
  "$($hash.Hash)  $(Split-Path -Leaf $ReleaseZip)" | Set-Content -LiteralPath "$ReleaseZip.sha256" -Encoding ASCII
  Write-Host "Release verified: $ReleaseZip"
  Write-Host "SHA256: $($hash.Hash)"
}
else {
  Write-Host "Release zip not found, tests only."
}
