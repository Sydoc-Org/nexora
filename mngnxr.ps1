# No param() block — $args used directly so PowerShell doesn't intercept -v/--verbose etc.

$AppDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Python    = "C:\Users\bes\AppData\Local\Programs\Python\Python313\python.exe"
$AppPy     = Join-Path $AppDir "app.py"
$LogDir    = Join-Path $AppDir "logs\system"
$null      = New-Item -ItemType Directory -Force -Path $LogDir
$StderrLog = "$LogDir\app_stderr.log"
$StdoutLog = "$LogDir\app_stdout.log"

# ── output helpers ────────────────────────────────────────────────────────────
function Write-Ok   ($msg) { Write-Host "  ✓  $msg" -ForegroundColor Green  }
function Write-Fail ($msg) { Write-Host "  ✗  $msg" -ForegroundColor Red    }
function Write-Warn ($msg) { Write-Host "  ⚠  $msg" -ForegroundColor Yellow }
function Write-Info ($msg) { Write-Host "  →  $msg" -ForegroundColor Cyan   }
function Write-Dim  ($msg) { Write-Host "     $msg" -ForegroundColor DarkGray }

function Show-Help {
    Write-Host ""
    Write-Host "  nexora dev CLI" -ForegroundColor White
    Write-Host ""
    Write-Host "  Usage:" -ForegroundColor DarkGray
    Write-Host "    mngnxr <command> [-v]"
    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor DarkGray
    Write-Host "    -u, --up        Start nexora"
    Write-Host "    -k, --kill      Stop nexora"
    Write-Host "    -r, --restart   Restart nexora"
    Write-Host "    -s, --status    Show running status  " -NoNewline
    Write-Host "(default)" -ForegroundColor DarkGray
    Write-Host "    -l, --logs      Stream live logs  " -NoNewline
    Write-Host "(requires a running instance)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Options:" -ForegroundColor DarkGray
    Write-Host "    -v, --verbose   Also stream logs after start / restart"
    Write-Host ""
    Write-Host "  Examples:" -ForegroundColor DarkGray
    Write-Host "    mngnxr -u              start"
    Write-Host "    mngnxr -u -v           start and stream logs"
    Write-Host "    mngnxr -r --verbose    restart and stream logs"
    Write-Host "    mngnxr -l              watch live logs"
    Write-Host ""
}

# ── flag parsing ──────────────────────────────────────────────────────────────
$action   = $null
$verbose  = $false
$unknown  = @()

foreach ($arg in $args) {
    switch -Exact ($arg.ToLower()) {
        '-u'        { $action = 'start'   }
        '--up'      { $action = 'start'   }
        '-r'        { $action = 'restart' }
        '--restart' { $action = 'restart' }
        '-k'        { $action = 'stop'    }
        '--kill'    { $action = 'stop'    }
        '-s'        { $action = 'status'  }
        '--status'  { $action = 'status'  }
        '-l'        { $action = 'logs'    }
        '--logs'    { $action = 'logs'    }
        '-v'        { $verbose = $true    }
        '--verbose' { $verbose = $true    }
        default     { $unknown += $arg    }
    }
}

if ($unknown.Count -gt 0) {
    Write-Fail "Unknown flag(s): $($unknown -join ', ')"
    Show-Help
    exit 1
}

if (-not $action) { $action = 'status' }

# ── core functions ────────────────────────────────────────────────────────────
function Find-AppProcess {
    $conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
    if ($conn) { Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue }
}

function Stop-App {
    $p = Find-AppProcess
    if ($p) {
        Write-Info "Stopping PID $($p.Id)..."
        $p | Stop-Process -Force
        Start-Sleep -Seconds 1
        Write-Ok "Stopped"
    } else {
        Write-Warn "Nothing to stop — nexora is not running"
    }
}

function Start-App {
    $existing = Find-AppProcess
    if ($existing) {
        Write-Warn "Already running on PID $($existing.Id) — use -r / --restart to restart"
        return
    }
    Write-Info "Starting nexora..."
    $prev = [System.Environment]::GetEnvironmentVariable("ENVIRONMENT")
    try {
        $env:ENVIRONMENT = "INT"
        $p = Start-Process -FilePath $Python `
                 -ArgumentList "`"$AppPy`"" `
                 -WorkingDirectory $AppDir `
                 -WindowStyle Hidden `
                 -RedirectStandardOutput $StdoutLog `
                 -RedirectStandardError  $StderrLog `
                 -PassThru
        Write-Ok "Started  (PID $($p.Id))"
    } finally {
        if ($null -eq $prev) { Remove-Item Env:ENVIRONMENT -ErrorAction SilentlyContinue }
        else                  { $env:ENVIRONMENT = $prev }
    }
}

function Watch-Logs {
    Write-Dim "Streaming logs — Ctrl+C to stop watching, nexora keeps running"
    Write-Host ""
    try {
        Get-Content -Path $StderrLog -Wait -Tail 20
    } finally {
        Write-Host ""
        Write-Dim "Stopped watching — nexora is still running"
    }
}

# ── actions ───────────────────────────────────────────────────────────────────
switch ($action) {
    'start' {
        Start-App
        if ($verbose) { Start-Sleep -Seconds 1; Watch-Logs }
    }
    'restart' {
        Stop-App; Start-Sleep -Seconds 2; Start-App
        if ($verbose) { Start-Sleep -Seconds 1; Watch-Logs }
    }
    'stop' { Stop-App }
    'logs' {
        $p = Find-AppProcess
        if (-not $p) {
            Write-Fail "nexora is not running — start it first with -u / --up"
            exit 1
        }
        Watch-Logs
    }
    'status' {
        $p = Find-AppProcess
        if ($p) {
            Write-Ok "Running  (PID $($p.Id)  ·  port 8000)"
        } else {
            Write-Warn "Not running  — use -u / --up to start"
        }
    }
}
