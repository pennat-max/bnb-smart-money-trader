$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (-not (Test-Path $BundledPython)) {
  $BundledPython = "python"
}

Start-Process -FilePath $BundledPython `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
  -WorkingDirectory $ApiDir `
  -WindowStyle Hidden

Start-Process -FilePath "npm.cmd" `
  -ArgumentList "run", "start", "--", "--port", "3001" `
  -WorkingDirectory $WebDir `
  -WindowStyle Hidden

Write-Host "Backend:   http://127.0.0.1:8000/health"
Write-Host "Dashboard: http://127.0.0.1:3001"
