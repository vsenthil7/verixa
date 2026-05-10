# =============================================================================
# Verixa — ops.ps1 (Auditex BLD-019/028 lineage)
# =============================================================================
# Single dispatcher for all repo-side dev operations.
# Every action is logged to <repo>/src/logs/<action>_<timestamp>.log
# (per Auditex BLD-017 log-path convention; the "src/" prefix is kept for
# alignment with Auditex/SwarmScout patterns even though Verixa has no
# src/ directly under repo root).
#
# Hard rules carried from Auditex (claude-memory/global/lessons):
#   BLD-013  — file-backup before edit (Copy-Item to _backup/)
#   BLD-019  — every action MUST use Get-LogFile + Invoke-Logged
#   BLD-027  — git-add-files takes ONE file per call (audit trail)
#   BLD-027  — verify file writes via shell (Test-Path) before claiming done
#   BLD-028  — powershell -Command works for non-interactive ops
#
# Usage:
#   .\ops.ps1 <action> [args...]
#
# Examples:
#   .\ops.ps1 up
#   .\ops.ps1 health
#   .\ops.ps1 test
#   .\ops.ps1 test-py
#   .\ops.ps1 git-add-files .gitignore
#   .\ops.ps1 commit-staged "[FEAT] CP-X.Y -- summary"
#   .\ops.ps1 verify-mi300x
#
# Help:
#   .\ops.ps1 help
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Action = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Args = @()
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Repo-root resolution
# ---------------------------------------------------------------------------

$Script:RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:LogsDir = Join-Path $Script:RepoRoot "src/logs"
$Script:BackupDir = Join-Path $Script:RepoRoot "_backup"
$Script:ComposeDir = Join-Path $Script:RepoRoot "deploy/docker-compose"
$Script:VenvPython = Join-Path $Script:RepoRoot ".venv/Scripts/python.exe"
$Script:VenvPytest = Join-Path $Script:RepoRoot ".venv/Scripts/pytest.exe"

if (-not (Test-Path $Script:LogsDir)) {
    New-Item -ItemType Directory -Path $Script:LogsDir -Force | Out-Null
}
if (-not (Test-Path $Script:BackupDir)) {
    New-Item -ItemType Directory -Path $Script:BackupDir -Force | Out-Null
}

# ---------------------------------------------------------------------------
# Logging helpers (BLD-019)
# ---------------------------------------------------------------------------

function Get-LogFile {
    param([Parameter(Mandatory)][string]$Action)
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $safeAction = $Action -replace "[^a-zA-Z0-9_-]", "_"
    return Join-Path $Script:LogsDir "$($safeAction)_$timestamp.log"
}

function Invoke-Logged {
    param(
        [Parameter(Mandatory)][string]$LogFile,
        [Parameter(Mandatory)][scriptblock]$Block
    )
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$startedAt] === START ===" | Out-File -FilePath $LogFile -Encoding utf8 -Append
    try {
        & $Block 2>&1 | ForEach-Object {
            $line = [string]$_
            $line | Tee-Object -FilePath $LogFile -Append | Out-Host
        }
        $exit = $LASTEXITCODE
        if ($null -eq $exit) { $exit = 0 }
    } catch {
        "[ERROR] $_" | Out-File -FilePath $LogFile -Encoding utf8 -Append
        Write-Host "[ERROR] $_" -ForegroundColor Red
        $exit = 1
    }
    $endedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$endedAt] === END exit=$exit ===" | Out-File -FilePath $LogFile -Encoding utf8 -Append
    return $exit
}

# ---------------------------------------------------------------------------
# Action: help
# ---------------------------------------------------------------------------

function Invoke-Help {
    Write-Host @"
Verixa ops.ps1 — action dispatcher

Stack:
  up                       docker compose up -d (local dev stack)
  down                     docker compose down
  restart                  down + up
  health                   hit every service healthcheck
  logs <service>           tail compose logs for one service

Tests:
  test                     run all tests (pytest + vitest) at 100pct cov gate
  test-py                  pytest only
  test-ts                  vitest only
  lint                     ruff + tsc

Git (Auditex BLD-027 discipline):
  git-status               git status --short
  git-log                  git log --oneline -20
  git-add-files <path>     git add <path>  (one file per call)
  commit-staged "<msg>"    git commit -m "<msg>"  (only what is staged)
  push                     git push origin main

DB (active after CP-3):
  db-migrate               alembic upgrade head
  db-reset                 drop + recreate dev DB then upgrade head

Verixa-specific:
  compliance-check <file>  scan file for forbidden phrases
  verify-mi300x            ping the configured MI300X reviewer endpoint

Backup (Auditex BLD-013):
  backup <file>            copy <file> to _backup/<basename>_<timestamp>.<ext>

Help:
  help                     this message
"@
}

# ---------------------------------------------------------------------------
# Action: up / down / restart / health / logs
# ---------------------------------------------------------------------------

function Invoke-Up {
    $log = Get-LogFile "up"
    return Invoke-Logged -LogFile $log -Block {
        Push-Location $Script:ComposeDir
        try {
            docker compose up -d
        } finally {
            Pop-Location
        }
    }
}

function Invoke-Down {
    $log = Get-LogFile "down"
    return Invoke-Logged -LogFile $log -Block {
        Push-Location $Script:ComposeDir
        try {
            docker compose down
        } finally {
            Pop-Location
        }
    }
}

function Invoke-Restart {
    [void](Invoke-Down)
    return Invoke-Up
}

function Invoke-Health {
    $log = Get-LogFile "health"
    return Invoke-Logged -LogFile $log -Block {
        $endpoints = @(
            @{ Name = "postgres"; Url = $null; Port = 5432 },
            @{ Name = "redis"; Url = $null; Port = 6379 },
            @{ Name = "opa"; Url = "http://localhost:8181/health"; Port = 8181 },
            @{ Name = "vault"; Url = "http://localhost:8200/v1/sys/health"; Port = 8200 },
            @{ Name = "minio"; Url = "http://localhost:9000/minio/health/live"; Port = 9000 },
            @{ Name = "prometheus"; Url = "http://localhost:9090/-/healthy"; Port = 9090 }
        )
        foreach ($ep in $endpoints) {
            if ($ep.Url) {
                try {
                    $resp = Invoke-WebRequest -Uri $ep.Url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
                    Write-Host ("[OK]   {0,-12} HTTP {1}" -f $ep.Name, $resp.StatusCode) -ForegroundColor Green
                } catch {
                    Write-Host ("[FAIL] {0,-12} {1}" -f $ep.Name, $_.Exception.Message) -ForegroundColor Red
                }
            } else {
                $tcp = Test-NetConnection -ComputerName "localhost" -Port $ep.Port -WarningAction SilentlyContinue
                if ($tcp.TcpTestSucceeded) {
                    Write-Host ("[OK]   {0,-12} TCP :{1}" -f $ep.Name, $ep.Port) -ForegroundColor Green
                } else {
                    Write-Host ("[FAIL] {0,-12} TCP :{1} not listening" -f $ep.Name, $ep.Port) -ForegroundColor Red
                }
            }
        }
    }
}

function Invoke-Logs {
    if ($Script:Args.Count -lt 1) {
        Write-Host "Usage: ops.ps1 logs <service>" -ForegroundColor Yellow
        return 1
    }
    $service = $Script:Args[0]
    Push-Location $Script:ComposeDir
    try {
        docker compose logs --tail=200 -f $service
    } finally {
        Pop-Location
    }
    return 0
}

# ---------------------------------------------------------------------------
# Action: tests
# ---------------------------------------------------------------------------

function Invoke-TestPy {
    $log = Get-LogFile "test-py"
    return Invoke-Logged -LogFile $log -Block {
        Push-Location $Script:RepoRoot
        try {
            & $Script:VenvPython -m pytest
        } finally {
            Pop-Location
        }
    }
}

function Invoke-TestTs {
    $log = Get-LogFile "test-ts"
    return Invoke-Logged -LogFile $log -Block {
        Push-Location (Join-Path $Script:RepoRoot "packages/verixa-ts")
        try {
            pnpm test:coverage
        } finally {
            Pop-Location
        }
    }
}

function Invoke-Test {
    $py = Invoke-TestPy
    $ts = Invoke-TestTs
    if ($py -ne 0 -or $ts -ne 0) {
        Write-Host "[FAIL] tests: py=$py ts=$ts" -ForegroundColor Red
        return 1
    }
    Write-Host "[OK] all tests green" -ForegroundColor Green
    return 0
}

function Invoke-Lint {
    $log = Get-LogFile "lint"
    return Invoke-Logged -LogFile $log -Block {
        Push-Location $Script:RepoRoot
        try {
            & $Script:VenvPython -m ruff check .
            & $Script:VenvPython -m mypy --config-file pyproject.toml apps packages 2>$null
            Push-Location (Join-Path $Script:RepoRoot "packages/verixa-ts")
            try {
                pnpm typecheck
            } finally {
                Pop-Location
            }
        } finally {
            Pop-Location
        }
    }
}

# ---------------------------------------------------------------------------
# Action: git
# ---------------------------------------------------------------------------

function Invoke-GitStatus {
    git -C $Script:RepoRoot status --short
    return $LASTEXITCODE
}

function Invoke-GitLog {
    git -C $Script:RepoRoot log --oneline -20
    return $LASTEXITCODE
}

function Invoke-GitAddFiles {
    if ($Script:Args.Count -ne 1) {
        Write-Host "Usage: ops.ps1 git-add-files <path>" -ForegroundColor Yellow
        Write-Host "       (Auditex BLD-027: ONE file per call)" -ForegroundColor Yellow
        return 1
    }
    $log = Get-LogFile "git-add-files"
    return Invoke-Logged -LogFile $log -Block {
        git -C $Script:RepoRoot add $Script:Args[0]
    }
}

function Invoke-CommitStaged {
    if ($Script:Args.Count -lt 1) {
        Write-Host 'Usage: ops.ps1 commit-staged "<message>"' -ForegroundColor Yellow
        return 1
    }
    $msg = $Script:Args -join " "
    $log = Get-LogFile "commit-staged"
    return Invoke-Logged -LogFile $log -Block {
        git -C $Script:RepoRoot commit -m $msg
    }
}

function Invoke-Push {
    $log = Get-LogFile "push"
    return Invoke-Logged -LogFile $log -Block {
        git -C $Script:RepoRoot push origin main
    }
}

# ---------------------------------------------------------------------------
# Action: db (placeholders; active after CP-3)
# ---------------------------------------------------------------------------

function Invoke-DbMigrate {
    Push-Location $Script:RepoRoot
    try {
        & $Script:VenvPython -m alembic upgrade head
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

function Invoke-DbReset {
    Write-Host "[WARN] db-reset will drop and recreate the dev DB" -ForegroundColor Yellow
    $confirm = Read-Host "Type YES to proceed"
    if ($confirm -ne "YES") {
        Write-Host "[ABORT] not confirmed" -ForegroundColor Yellow
        return 1
    }
    Push-Location $Script:ComposeDir
    try {
        docker compose exec -T postgres psql -U verixa -d postgres -c "DROP DATABASE IF EXISTS verixa;"
        docker compose exec -T postgres psql -U verixa -d postgres -c "CREATE DATABASE verixa;"
    } finally {
        Pop-Location
    }
    return Invoke-DbMigrate
}

# ---------------------------------------------------------------------------
# Action: verixa-specific
# ---------------------------------------------------------------------------

function Invoke-ComplianceCheck {
    if ($Script:Args.Count -ne 1) {
        Write-Host "Usage: ops.ps1 compliance-check <file>" -ForegroundColor Yellow
        return 1
    }
    $file = Resolve-Path $Script:Args[0] -ErrorAction SilentlyContinue
    if (-not $file) {
        Write-Host "[FAIL] file not found: $($Script:Args[0])" -ForegroundColor Red
        return 1
    }
    Push-Location $Script:RepoRoot
    try {
        & $Script:VenvPython -c @"
import sys
from pathlib import Path
sys.path.insert(0, 'packages/verixa-python')
from verixa.compliance_language import check_text
text = Path(r'$file').read_text(encoding='utf-8', errors='replace')
violations = check_text(text)
if not violations:
    print('[OK] no violations'); sys.exit(0)
print(f'[FAIL] {len(violations)} violation(s):')
for v in violations: print(f'  - {v}')
sys.exit(1)
"@
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

function Invoke-VerifyMi300x {
    $endpoint = "http://165.245.133.120:8000/v1/models"
    $log = Get-LogFile "verify-mi300x"
    return Invoke-Logged -LogFile $log -Block {
        Write-Host "Pinging MI300X reviewer endpoint: $endpoint"
        try {
            $resp = Invoke-WebRequest -Uri $endpoint -TimeoutSec 10 -UseBasicParsing
            Write-Host "[OK] HTTP $($resp.StatusCode); response excerpt:" -ForegroundColor Green
            $resp.Content | Select-String -Pattern '"id"' | Select-Object -First 5
        } catch {
            Write-Host "[FAIL] $_" -ForegroundColor Red
            throw
        }
    }
}

# ---------------------------------------------------------------------------
# Action: backup (BLD-013)
# ---------------------------------------------------------------------------

function Invoke-Backup {
    if ($Script:Args.Count -ne 1) {
        Write-Host "Usage: ops.ps1 backup <file>" -ForegroundColor Yellow
        return 1
    }
    $src = Resolve-Path $Script:Args[0] -ErrorAction SilentlyContinue
    if (-not $src) {
        Write-Host "[FAIL] file not found: $($Script:Args[0])" -ForegroundColor Red
        return 1
    }
    $base = [System.IO.Path]::GetFileNameWithoutExtension($src)
    $ext = [System.IO.Path]::GetExtension($src)
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $dest = Join-Path $Script:BackupDir "$($base)_$($timestamp)$($ext)"
    Copy-Item -Path $src -Destination $dest
    Write-Host "[OK] backed up: $dest" -ForegroundColor Green
    return 0
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

$Script:Args = $Args  # bind for sub-functions

$result = switch ($Action.ToLower()) {
    "help" { Invoke-Help; 0 }
    "up" { Invoke-Up }
    "down" { Invoke-Down }
    "restart" { Invoke-Restart }
    "health" { Invoke-Health }
    "logs" { Invoke-Logs }
    "test" { Invoke-Test }
    "test-py" { Invoke-TestPy }
    "test-ts" { Invoke-TestTs }
    "lint" { Invoke-Lint }
    "git-status" { Invoke-GitStatus }
    "git-log" { Invoke-GitLog }
    "git-add-files" { Invoke-GitAddFiles }
    "commit-staged" { Invoke-CommitStaged }
    "push" { Invoke-Push }
    "db-migrate" { Invoke-DbMigrate }
    "db-reset" { Invoke-DbReset }
    "compliance-check" { Invoke-ComplianceCheck }
    "verify-mi300x" { Invoke-VerifyMi300x }
    "backup" { Invoke-Backup }
    default {
        Write-Host "[FAIL] unknown action: $Action" -ForegroundColor Red
        Invoke-Help
        1
    }
}

exit $result
