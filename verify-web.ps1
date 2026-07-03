$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

node --check web\app.js
node --check web\service-worker.js
python -m unittest tests.test_web_assets -v

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
Assert-TextContains -Path "web\service-worker.js" -Needle "./vendor/jszip.min.js"
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

if (-not (Test-Path -LiteralPath "web\vendor\JSZIP_LICENSE.markdown")) {
  throw "Missing JSZip license file."
}

Write-Host "Web Lite verified."
