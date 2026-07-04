param(
  [switch]$IncludePdf
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

foreach ($path in @("build", "dist", "releases", "OptimizerZero.spec")) {
  $full = Join-Path $PSScriptRoot $path
  if (Test-Path -LiteralPath $full) {
    Remove-Item -LiteralPath $full -Recurse -Force
  }
}

if ($IncludePdf) {
  & (Join-Path $PSScriptRoot "build-windows.ps1") -IncludePdf
}
else {
  & (Join-Path $PSScriptRoot "build-windows.ps1")
}

$releaseDir = Join-Path $PSScriptRoot "releases"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$zipName = if ($IncludePdf) { "OptimizerZero-0.1.0-windows-pdf.zip" } else { "OptimizerZero-0.1.0-windows-lite.zip" }
$zipPath = Join-Path $releaseDir $zipName
Compress-Archive -LiteralPath (Join-Path $PSScriptRoot "dist\OptimizerZero") -DestinationPath $zipPath -Force

& (Join-Path $PSScriptRoot "package-web.ps1")

$webZipPath = Join-Path $releaseDir "OptimizerZero-0.1.0-web-lite.zip"
& (Join-Path $PSScriptRoot "verify-release.ps1") -ReleaseZip $zipPath -WebZip $webZipPath

Write-Host "Packaged: $zipPath"
Write-Host "Packaged: $webZipPath"
