<#
.SYNOPSIS
  Consistent MongoDB backup from the running compose stack into .\backups\<timestamp>.archive.gz
  Also keep a copy of .env (ENCRYPTION_KEYS): without it, stored provider keys cannot be decrypted.
.EXAMPLE
  ./scripts/backup.ps1
  ./scripts/backup.ps1 -Keep 30
#>
param([int]$Keep = 14)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force backups | Out-Null
$db = 'orchestrator'
$line = Get-Content .env -ErrorAction SilentlyContinue | Where-Object { $_ -match '^MONGODB_DB=(.+)$' } | Select-Object -First 1
if ($line) { $db = ($line -split '=', 2)[1].Trim() }
$out = Join-Path 'backups' ((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '.archive.gz')
# cmd's redirection keeps the binary archive intact (PowerShell 5.1 '>' would re-encode it).
cmd /c "docker compose exec -T mongo mongodump --quiet --db $db --archive --gzip > `"$out`""
if ($LASTEXITCODE -ne 0) { throw 'mongodump failed' }
Write-Host "Wrote $out"
Get-ChildItem backups -Filter *.archive.gz | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep | Remove-Item
