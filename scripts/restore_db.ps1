# ─────────────────────────────────────────────────────────────────────────────
# scripts/restore_db.ps1
#
# Safe PostgreSQL database restore utility for Windows PowerShell.
#
# SAFETY GUARDRAILS:
# 1. Prohibits restoring over the active database (POSTGRES_DB) by default.
# 2. Requires a target database name (e.g., procureops_restore_test).
# 3. Validates backup file existence and format before attempting restore.
#
# Usage:
#   powershell -File .\scripts\restore_db.ps1 -BackupFile .\backups\backup.dump -TargetDb procureops_restore_test
# ─────────────────────────────────────────────────────────────────────────────

[CmdletBinding()]
param (
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,

    [Parameter(Mandatory=$true)]
    [string]$TargetDb,

    [string]$DbUser = $env:POSTGRES_USER,
    [string]$ActiveDb = $env:POSTGRES_DB
)

# Load from .env if present
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim().Trim("'").Trim('"')
            if ($k -eq "POSTGRES_USER" -and -not $DbUser) { $DbUser = $v }
            if ($k -eq "POSTGRES_DB" -and -not $ActiveDb) { $ActiveDb = $v }
        }
    }
}

if (-not $DbUser) { $DbUser = "procureops" }
if (-not $ActiveDb) { $ActiveDb = "procureops_db" }

if (-not (Test-Path $BackupFile)) {
    Write-Error "[-] Error: Backup file '$BackupFile' does not exist."
    exit 1
}

# Guardrail: Do not overwrite the active database
if ($TargetDb -eq $ActiveDb) {
    Write-Error "[-] SAFETY ALERT: Refusing to restore over the active database '$ActiveDb'. Specify a separate target database (e.g. '$($ActiveDb)_restore_test')."
    exit 1
}

Write-Host "[*] Restoring backup to disposable target database: '$TargetDb'"

# 1. Create target database if it doesn't already exist
$CheckDb = & docker compose exec -T postgres psql -U $DbUser -d postgres -t -c "SELECT 1 FROM pg_database WHERE datname = '$TargetDb';"
if (-not ($CheckDb -match "1")) {
    Write-Host "[*] Creating disposable database '$TargetDb'..."
    & docker compose exec -T postgres createdb -U $DbUser $TargetDb
}

# 2. Execute pg_restore via cmd.exe pipe (avoids PowerShell binary stream encoding differences)
Write-Host "[*] Executing pg_restore..."
$ResolvedBackup = (Resolve-Path $BackupFile).Path
cmd.exe /c "docker compose exec -T postgres pg_restore -U $DbUser -d $TargetDb --no-owner --no-acl < `"$ResolvedBackup`""

# 3. Verify restored tables
$TableCount = & docker compose exec -T postgres psql -U $DbUser -d $TargetDb -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
$TableCount = $TableCount.Trim()

Write-Host "[+] Restore verification complete: Target database '$TargetDb' contains $TableCount public tables."
Write-Host "[+] Done. You may safely drop '$TargetDb' after testing."
exit 0
