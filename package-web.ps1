param(
  [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$releaseDir = Join-Path $PSScriptRoot "releases"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$webZipPath = Join-Path $releaseDir "OptimizerZero-$Version-web-lite.zip"
$tempWebZipPath = Join-Path $releaseDir ("OptimizerZero-$Version-web-lite.tmp-{0}.zip" -f ([guid]::NewGuid().ToString("N")))

& (Join-Path $PSScriptRoot "verify-web.ps1")

try {
  $webFiles = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "web") -Force
  Compress-Archive -Path $webFiles.FullName -DestinationPath $tempWebZipPath -Force

  $requiredWebEntries = @(
    "index.html",
    "app.js",
    "optimize-core.js",
    "worker.js",
    "avif-jxl-worker.js",
    "PRIVACY.md",
    "styles.css",
    "service-worker.js",
    "manifest.webmanifest",
    "icon.svg",
    "robots.txt",
    "_headers",
    "vendor/jszip.min.js",
    "vendor/JSZIP_LICENSE.markdown",
    "vendor/pdf-lib.min.js",
    "vendor/PDF_LIB_LICENSE.md",
    "vendor/JSQUASH_LICENSE.md",
    "vendor/jsquash-avif/encode.js",
    "vendor/jsquash-avif/meta.js",
    "vendor/jsquash-avif/utils.js",
    "vendor/jsquash-avif/avif_enc.js",
    "vendor/jsquash-avif/avif_enc.wasm",
    "vendor/jsquash-jxl/encode.js",
    "vendor/jsquash-jxl/meta.js",
    "vendor/jsquash-jxl/utils.js",
    "vendor/jsquash-jxl/jxl_enc.js",
    "vendor/jsquash-jxl/jxl_enc.wasm"
  )
  $entries = (tar -tf $tempWebZipPath) | ForEach-Object { $_.TrimStart("./") }
  foreach ($entry in $requiredWebEntries) {
    if ($entries -notcontains $entry) {
      throw "Web package missing: $entry"
    }
  }
  if (Test-Path -LiteralPath $webZipPath) {
    Remove-Item -LiteralPath $webZipPath -Force
  }
  Move-Item -LiteralPath $tempWebZipPath -Destination $webZipPath
} finally {
  if (Test-Path -LiteralPath $tempWebZipPath) {
    Remove-Item -LiteralPath $tempWebZipPath -Force -ErrorAction SilentlyContinue
  }
}

$webHash = Get-FileHash -Algorithm SHA256 -LiteralPath $webZipPath
"$($webHash.Hash)  $(Split-Path -Leaf $webZipPath)" | Set-Content -LiteralPath "$webZipPath.sha256" -Encoding ASCII

Write-Host "Packaged: $webZipPath"
Write-Host "SHA256: $($webHash.Hash)"
