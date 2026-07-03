param(
  [string]$ReleaseZip = "releases\OptimizerZero-0.1.0-windows-lite.zip",
  [string]$WebZip = "releases\OptimizerZero-0.1.0-web-lite.zip"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
python -m compileall src gui_entry.py
python -m unittest discover -s tests -v
& (Join-Path $PSScriptRoot "verify-web.ps1")

if (Test-Path -LiteralPath $ReleaseZip) {
  $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $ReleaseZip
  "$($hash.Hash)  $(Split-Path -Leaf $ReleaseZip)" | Set-Content -LiteralPath "$ReleaseZip.sha256" -Encoding ASCII
  Write-Host "Release verified: $ReleaseZip"
  Write-Host "SHA256: $($hash.Hash)"
}
else {
  Write-Host "Release zip not found, tests only."
}

if (Test-Path -LiteralPath $WebZip) {
  $requiredWebEntries = @(
    "index.html",
    "app.js",
    "PRIVACY.md",
    "styles.css",
    "service-worker.js",
    "manifest.webmanifest",
    "icon.svg",
    "robots.txt",
    "_headers",
    "vendor/jszip.min.js",
    "vendor/JSZIP_LICENSE.markdown"
  )
  $entries = (tar -tf $WebZip) | ForEach-Object { $_.TrimStart("./") }
  foreach ($entry in $requiredWebEntries) {
    if ($entries -notcontains $entry) {
      throw "Web release zip missing: $entry"
    }
  }
  $webHash = Get-FileHash -Algorithm SHA256 -LiteralPath $WebZip
  "$($webHash.Hash)  $(Split-Path -Leaf $WebZip)" | Set-Content -LiteralPath "$WebZip.sha256" -Encoding ASCII
  Write-Host "Web release verified: $WebZip"
  Write-Host "Web SHA256: $($webHash.Hash)"
}
