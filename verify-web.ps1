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
Assert-TextContains -Path "web\service-worker.js" -Needle "Promise.allSettled"
Assert-TextContains -Path "web\service-worker.js" -Needle 'caches.match("./index.html")'

Write-Host "Web Lite verified."
