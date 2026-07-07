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

node --check web\app.js
node --check web\optimize-core.js
node --check web\worker.js
node --check web\service-worker.js
node --check functions\_middleware.js
Get-Content -Raw -LiteralPath web\avif-jxl-worker.js | node --input-type=module --check
Get-Content -Raw -LiteralPath web\vendor\jsquash-avif\encode.js | node --input-type=module --check
Get-Content -Raw -LiteralPath web\vendor\jsquash-jxl\encode.js | node --input-type=module --check
& $PythonExe -m unittest tests.test_web_assets -v

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
Assert-TextContains -Path "web\index.html" -Needle "./vendor/jszip.min.js"
Assert-TextContains -Path "web\index.html" -Needle "./vendor/pdf-lib.min.js"
Assert-TextContains -Path "web\service-worker.js" -Needle "./vendor/jszip.min.js"
Assert-TextContains -Path "web\service-worker.js" -Needle "./vendor/pdf-lib.min.js"
Assert-TextContains -Path "web\service-worker.js" -Needle "./PRIVACY.md"
Assert-TextContains -Path "web\PRIVACY.md" -Needle "not uploaded"
Assert-TextContains -Path "web\PRIVACY.md" -Needle "does not include analytics"
Assert-TextContains -Path "web\service-worker.js" -Needle 'caches.match("./index.html")'
Assert-TextContains -Path "wrangler.toml" -Needle 'pages_build_output_dir = "./web"'
Assert-TextContains -Path "wrangler.toml" -Needle 'name = "optimizerzero"'
Assert-TextContains -Path "deploy-cloudflare.ps1" -Needle "Dry run only"
Assert-TextContains -Path "deploy-cloudflare.ps1" -Needle "wrangler@latest"
Assert-TextContains -Path ".github\workflows\deploy-cloudflare.yml" -Needle "workflow_dispatch:"
Assert-TextContains -Path ".github\workflows\deploy-cloudflare.yml" -Needle "cloudflare/wrangler-action@v3"
Assert-TextContains -Path ".github\workflows\deploy-cloudflare.yml" -Needle "pages deploy web --project-name optimizerzero"
Assert-TextContains -Path "docs\GITHUB_SECRETS_CLOUDFLARE_KO.md" -Needle "CLOUDFLARE_API_TOKEN"
Assert-TextContains -Path "docs\GITHUB_SECRETS_CLOUDFLARE_KO.md" -Needle "CLOUDFLARE_ACCOUNT_ID"

if (-not (Test-Path -LiteralPath "web\vendor\JSZIP_LICENSE.markdown")) {
  throw "Missing JSZip license file."
}
if (-not (Test-Path -LiteralPath "web\vendor\PDF_LIB_LICENSE.md")) {
  throw "Missing pdf-lib license file."
}
if (-not (Test-Path -LiteralPath "web\vendor\JSQUASH_LICENSE.md")) {
  throw "Missing jSquash (AVIF/JXL) license file."
}
if (-not (Test-Path -LiteralPath "web\vendor\jsquash-avif\avif_enc.wasm")) {
  throw "Missing AVIF encoder wasm."
}
if (-not (Test-Path -LiteralPath "web\vendor\jsquash-jxl\jxl_enc.wasm")) {
  throw "Missing JXL encoder wasm."
}

Write-Host "Web Lite verified."
