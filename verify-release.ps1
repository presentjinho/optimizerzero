param(
  [string]$ReleaseZip = "releases\OptimizerZero-0.1.0-windows-lite.zip",
  [string]$WebZip = "releases\OptimizerZero-0.1.0-web-lite.zip"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
python -m compileall src gui_entry.py
python -m unittest discover -s tests -v
node --check web\app.js
node --check web\service-worker.js

function Assert-TextContains {
  param(
    [string]$Path,
    [string]$Needle
  )
  $content = Get-Content -Raw -LiteralPath $Path
  if (-not $content.Contains($Needle)) {
    throw "Missing '$Needle' in $Path"
  }
}

Assert-TextContains -Path "web\index.html" -Needle "noindex,nofollow,noarchive"
Assert-TextContains -Path "web\robots.txt" -Needle "Disallow: /"
Assert-TextContains -Path "web\_headers" -Needle "X-Robots-Tag: noindex"
Assert-TextContains -Path "web\service-worker.js" -Needle "Promise.allSettled"

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
    "styles.css",
    "service-worker.js",
    "manifest.webmanifest",
    "icon.svg",
    "robots.txt",
    "_headers"
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
