<#
.SYNOPSIS
  Runs every check: backend lint + tests, frontend typecheck + lint + unit tests + build,
  and optionally the browser E2E journey against a running stack.

.EXAMPLE
  ./scripts/test.ps1            # needs a MongoDB replica set at MONGODB_URI for backend tests
  ./scripts/test.ps1 -E2E       # also runs Playwright against http://localhost:3000
  ./scripts/test.ps1 -Docker    # runs backend tests inside Docker against the compose mongo
#>
param([switch]$E2E, [switch]$Docker)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$failed = @()

function Step([string]$Name, [string]$Dir, [scriptblock]$Cmd) {
  Write-Host "`n=== $Name ===" -ForegroundColor Cyan
  Push-Location $Dir
  try { & $Cmd; if ($LASTEXITCODE -ne 0) { $script:failed += $Name } } catch { Write-Host $_; $script:failed += $Name } finally { Pop-Location }
}

$api = Join-Path $Root 'apps/api'; $web = Join-Path $Root 'apps/web'
if ($Docker) {
  Step 'backend tests (docker)' $Root { docker compose run --rm --no-deps -e MONGODB_URI=mongodb://mongo:27017/?replicaSet=rs0 -v "${api}:/src" -w /src api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" }
} else {
  Step 'backend lint (ruff)' $api { uv run ruff check app tests }
  Step 'backend tests (pytest)' $api { uv run pytest -q }
}
Step 'frontend typecheck' $web { npm run typecheck }
Step 'frontend lint' $web { npm run lint }
Step 'frontend unit tests' $web { npm test }
Step 'frontend build' $web { npm run build }
if ($E2E) {
  Step 'e2e (playwright)' $web { npx playwright install chromium; npx playwright test }
}

if ($failed.Count) { Write-Host "`nFAILED: $($failed -join ', ')" -ForegroundColor Red; exit 1 }
Write-Host "`nAll checks passed." -ForegroundColor Green
