param(
  [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$releaseDir = Join-Path $PSScriptRoot "releases"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$webZipPath = Join-Path $releaseDir "OptimizerZero-$Version-web-lite.zip"
if (Test-Path -LiteralPath $webZipPath) {
  Remove-Item -LiteralPath $webZipPath -Force
}

& (Join-Path $PSScriptRoot "verify-web.ps1")

$webFiles = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "web") -Force
Compress-Archive -Path $webFiles.FullName -DestinationPath $webZipPath -Force

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
$entries = (tar -tf $webZipPath) | ForEach-Object { $_.TrimStart("./") }
foreach ($entry in $requiredWebEntries) {
  if ($entries -notcontains $entry) {
    throw "Web package missing: $entry"
  }
}
$webHash = Get-FileHash -Algorithm SHA256 -LiteralPath $webZipPath
"$($webHash.Hash)  $(Split-Path -Leaf $webZipPath)" | Set-Content -LiteralPath "$webZipPath.sha256" -Encoding ASCII

Write-Host "Packaged: $webZipPath"
Write-Host "SHA256: $($webHash.Hash)"
