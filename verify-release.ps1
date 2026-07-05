param(
  [string]$ReleaseZip = "releases\OptimizerZero-0.1.0-windows-pdf.zip",
  [string]$WebZip = "releases\OptimizerZero-0.1.0-web-lite.zip"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Get-PythonExe {
  $knownPaths = @()
  if ($env:USERPROFILE) {
    $knownPaths += Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\Python312\python.exe"
    $knownPaths += Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\Python311\python.exe"
    $knownPaths += Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\Python310\python.exe"
  }
  foreach ($path in $knownPaths) {
    if (Test-Path -LiteralPath $path) {
      return $path
    }
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python -and $python.Source -and (Split-Path $python.Source -Parent) -and (Test-Path -LiteralPath $python.Source) -and ($python.Source -notlike "*\WindowsApps\*")) {
    return $python.Source
  }
  $launcher = Get-Command py -ErrorAction SilentlyContinue
  if ($launcher -and $launcher.Source -and (Split-Path $launcher.Source -Parent) -and (Test-Path -LiteralPath $launcher.Source)) {
    return $launcher.Source
  }
  $candidates = @()
  if ($env:LOCALAPPDATA) {
    $candidates += Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA "Programs\Python") -Filter python.exe -Recurse -ErrorAction SilentlyContinue
  }
  $candidate = $candidates | Sort-Object FullName -Descending | Select-Object -First 1
  if ($candidate -and $candidate.FullName -and (Split-Path $candidate.FullName -Parent) -and ($candidate.FullName -notlike "*\WindowsApps\*")) {
    return $candidate.FullName
  }
  throw "Python was not found. Install Python 3.10+ or add python.exe to PATH."
}

$PythonExe = Get-PythonExe
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
& $PythonExe -m compileall src gui_entry.py
& $PythonExe -m unittest discover -s tests -v
& (Join-Path $PSScriptRoot "verify-web.ps1")

$manifestItems = @()

function Add-ManifestItem {
  param(
    [string]$Path,
    [string]$Role,
    [string]$Sha256
  )
  $item = Get-Item -LiteralPath $Path
  $script:manifestItems += [pscustomobject]@{
    name = $item.Name
    path = $Path
    role = $Role
    bytes = $item.Length
    sha256 = $Sha256
  }
}

function Test-Manifest {
  param([string]$ManifestPath)
  $manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
  foreach ($artifact in $manifest.artifacts) {
    if (-not (Test-Path -LiteralPath $artifact.path)) {
      throw "Manifest artifact missing: $($artifact.path)"
    }
    $item = Get-Item -LiteralPath $artifact.path
    if ($item.Length -ne $artifact.bytes) {
      throw "Manifest size mismatch: $($artifact.name)"
    }
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $artifact.path
    if ($hash.Hash -ne $artifact.sha256) {
      throw "Manifest SHA256 mismatch: $($artifact.name)"
    }
  }
}

if (Test-Path -LiteralPath $ReleaseZip) {
  $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $ReleaseZip
  "$($hash.Hash)  $(Split-Path -Leaf $ReleaseZip)" | Set-Content -LiteralPath "$ReleaseZip.sha256" -Encoding ASCII
  Add-ManifestItem -Path $ReleaseZip -Role "windows-app" -Sha256 $hash.Hash
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
  Add-ManifestItem -Path $WebZip -Role "web-lite" -Sha256 $webHash.Hash
  Write-Host "Web release verified: $WebZip"
  Write-Host "Web SHA256: $($webHash.Hash)"
}

if ($manifestItems.Count -gt 0) {
  $manifestPath = Join-Path $PSScriptRoot "releases\OptimizerZero-release-manifest.json"
  $manifest = [pscustomobject]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    app = "OptimizerZero"
    artifacts = $manifestItems
  }
  $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
  Test-Manifest -ManifestPath $manifestPath
  Write-Host "Manifest: $manifestPath"
}
