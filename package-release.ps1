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
& (Join-Path $PSScriptRoot "verify-release.ps1") -ReleaseZip $zipPath

$webZipPath = Join-Path $releaseDir "OptimizerZero-0.1.0-web-lite.zip"
$webFiles = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "web") -Force
Compress-Archive -Path $webFiles.FullName -DestinationPath $webZipPath -Force
$webHash = Get-FileHash -Algorithm SHA256 -LiteralPath $webZipPath
"$($webHash.Hash)  $(Split-Path -Leaf $webZipPath)" | Set-Content -LiteralPath "$webZipPath.sha256" -Encoding ASCII

Write-Host "Packaged: $zipPath"
Write-Host "Packaged: $webZipPath"
