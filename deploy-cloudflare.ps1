param(
  [string]$ProjectName = "optimizerzero",
  [string]$Branch = "main",
  [switch]$Deploy
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

& (Join-Path $PSScriptRoot "verify-web.ps1")

$deployArgs = @(
  "--yes",
  "wrangler@latest",
  "pages",
  "deploy",
  "web",
  "--project-name",
  $ProjectName,
  "--branch",
  $Branch
)

Write-Host "Cloudflare Pages command:"
Write-Host ("npx " + ($deployArgs -join " "))

if (-not $Deploy) {
  Write-Host "Dry run only. Re-run with -Deploy to upload to Cloudflare Pages."
  exit 0
}

if (-not $env:CLOUDFLARE_API_TOKEN) {
  Write-Host "CLOUDFLARE_API_TOKEN is not set. Wrangler may open browser login or fail in non-interactive shells."
}

npx @deployArgs
