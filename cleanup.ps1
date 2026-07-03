param(
  [switch]$BuildArtifacts,
  [switch]$DemoOutputs
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$targets = @()
$targets += Get-ChildItem -LiteralPath $PSScriptRoot -Recurse -Directory -Force -Filter "__pycache__"
$targets += Get-ChildItem -LiteralPath $PSScriptRoot -Recurse -File -Force -Filter "*.pyc"

if ($DemoOutputs) {
  $demoDir = Join-Path $PSScriptRoot "demo_assets"
  if (Test-Path -LiteralPath $demoDir) {
    $targets += Get-ChildItem -LiteralPath $demoDir -File -Force |
      Where-Object { $_.Name -like "*.ozero.*" -or $_.Name -like "*report.json" }
  }
}

if ($BuildArtifacts) {
  foreach ($name in @("build", "dist", "OptimizerZero.spec")) {
    $path = Join-Path $PSScriptRoot $name
    if (Test-Path -LiteralPath $path) {
      $targets += Get-Item -LiteralPath $path -Force
    }
  }
}

foreach ($target in $targets) {
  if (Test-Path -LiteralPath $target.FullName) {
    Remove-Item -LiteralPath $target.FullName -Recurse -Force
    Write-Host "removed: $($target.FullName)"
  }
}

Write-Host "cleanup complete"
