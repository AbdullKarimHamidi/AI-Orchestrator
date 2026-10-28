<#
.SYNOPSIS
  One-command startup for Windows (PowerShell 5.1+ or PowerShell 7).

.DESCRIPTION
  Default (Docker): creates .env with a fresh encryption key if missing, then runs
  `docker compose up --build -d` and waits until the web app answers.

  -Local: runs the API, worker, and web natively in three new windows. Requires
  uv, Node.js 20.9+, and a MongoDB replica set at MONGODB_URI (see README).

.EXAMPLE
  ./scripts/dev.ps1
  ./scripts/dev.ps1 -Local
  ./scripts/dev.ps1 -Down
#>
param([switch]$Local, [switch]$Down)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Down) { docker compose down; exit $LASTEXITCODE }

$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
  $key = & (Join-Path $PSScriptRoot 'new-key.ps1')
  (Get-Content (Join-Path $Root '.env.example')) -replace '^ENCRYPTION_KEYS=.*$', "ENCRYPTION_KEYS=$key" |
    Set-Content -Encoding ascii $envFile
  Write-Host "Created .env with a new ENCRYPTION_KEYS value (keep it: stored provider keys depend on it)."
}

function Wait-Url([string]$Url, [int]$Seconds = 180) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3; if ($r.StatusCode -lt 500) { return $true } } catch { }
    Start-Sleep -Seconds 2
  }
  return $false
}

if (-not $Local) {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is not installed. Install Docker Desktop or use -Local." }
  docker compose up --build -d
  if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
} else {
  foreach ($c in 'uv', 'npm') { if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { throw "$c is required for -Local" } }
  # Load .env into this session so child windows inherit it.
  Get-Content $envFile | Where-Object { $_ -match '^\s*[A-Z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
  }
  $shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
  $api = Join-Path $Root 'apps/api'; $web = Join-Path $Root 'apps/web'
  Push-Location $api; uv sync; Pop-Location
  Push-Location $web; if (-not (Test-Path node_modules)) { npm ci }; Pop-Location
  Start-Process $shell -WorkingDirectory $api -ArgumentList '-NoExit', '-Command', 'uv run uvicorn app.main:app --port 8000'
  Start-Process $shell -WorkingDirectory $api -ArgumentList '-NoExit', '-Command', 'uv run python -m app.workers.main'
  Start-Process $shell -WorkingDirectory $web -ArgumentList '-NoExit', '-Command', 'npm run dev'
}

Write-Host "Waiting for http://localhost:3000 ..."
if (Wait-Url 'http://localhost:3000/login') {
  Write-Host "Ready: http://localhost:3000  (API docs: http://localhost:8000/api/docs)"
} else {
  Write-Warning "The web app did not respond in time. Check: docker compose logs -f  (or the three -Local windows)"
}
