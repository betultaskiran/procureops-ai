# ─────────────────────────────────────────────────────────────────────────────
# scripts/backup_db.ps1
#
# Production PostgreSQL automated backup script for Windows hosts.
# Usage:
#   powershell -File .\scripts\backup_db.ps1 -OutputDir .\backups -RetentionDays 7
# ─────────────────────────────────────────────────────────────────────────────

[CmdletBinding()]
param (
    [string]$OutputDir = ".\backups",
    [string]$DbName = $env:POSTGRES_DB,
    [string]$DbUser = $env:POSTGRES_USER,
    [int]$RetentionDays = 0
)

$ErrorActionPreference = "Stop"

if (-not $DbName) { $DbName = "procureops" }
if (-not $DbUser) { $DbUser = "postgres" }

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$Filename = "procureops_backup_${DbName}_${Timestamp}.dump"
$TargetPath = Join-Path $OutputDir $Filename

Write-Host "[*] Starting PostgreSQL backup: database='$DbName', target='$TargetPath'"

try {
    # Run docker compose exec and stream binary output
    & docker compose exec -T postgres pg_dump -U $DbUser -d $DbName -Fc --no-owner --no-acl | Set-Content -Path $TargetPath -AsByteStream
}
catch {
    Write-Error "[-] Backup failed to execute: $_"
    if (Test-Path $TargetPath) { Remove-Item $TargetPath -Force }
    exit 1
}

if (-not (Test-Path $TargetPath) -or (Get-Item $TargetPath).Length -eq 0) {
    Write-Error "[-] Backup verification failed: Target file is empty (0 bytes). Removing..."
    if (Test-Path $TargetPath) { Remove-Item $TargetPath -Force }
    exit 1
}

$SizeKb = [math]::Round((Get-Item $TargetPath).Length / 1KB, 2)
Write-Host "[+] Backup successfully created: $TargetPath ($SizeKb KB)"

# Retention cleanup
if ($RetentionDays -gt 0) {
    $CutoffDate = (Get-Date).AddDays(-$RetentionDays)
    $OldFiles = Get-ChildItem -Path $OutputDir -Filter "procureops_backup_${DbName}_*.dump" | Where-Object { $_.LastWriteTime -lt $CutoffDate }
    foreach ($File in $OldFiles) {
        Write-Host "[*] Retention cleanup: removing expired backup '$($File.Name)'"
        Remove-Item $File.FullName -Force
    }
}

Write-Host "[+] Backup completed successfully."
exit 0
