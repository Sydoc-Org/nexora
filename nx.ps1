# No param() block — $args used directly so PowerShell doesn't intercept -v/--verbose etc.

$AppDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Python    = "C:\Users\bes\AppData\Local\Programs\Python\Python313\python.exe"
$AppPy     = Join-Path $AppDir "app.py"
$LogDir    = Join-Path $AppDir "logs\system"
$null      = New-Item -ItemType Directory -Force -Path $LogDir
$StderrLog    = "$LogDir\app_stderr.log"
$StdoutLog    = "$LogDir\app_stdout.log"
$EnvStateFile = "$LogDir\current_env"

# ── output helpers ────────────────────────────────────────────────────────────
function Write-Ok   ($msg) { Write-Host "  ✓  $msg" -ForegroundColor DarkGreen  }
function Write-Fail ($msg) { Write-Host "  ✗  $msg" -ForegroundColor DarkRed    }
function Write-Warn ($msg) { Write-Host "  ⚠  $msg" -ForegroundColor DarkYellow }
function Write-Info ($msg) { Write-Host "  →  $msg" -ForegroundColor Blue       }
function Write-Dim  ($msg) { Write-Host "     $msg" -ForegroundColor Gray       }

function Show-Help {
    Write-Host ""
    Write-Host "  nexora dev CLI" -ForegroundColor Blue
    Write-Host ""
    Write-Host "  Usage:" -ForegroundColor Gray
    Write-Host "    nx <command> [options]"
    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor Gray
    Write-Host "    -u, --up        Start nexora"
    Write-Host "    -d, --down      Stop nexora"
    Write-Host "    -r, --restart   Restart nexora"
    Write-Host "    -l, --logs      Stream live logs  " -NoNewline
    Write-Host "(requires a running instance)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Options:" -ForegroundColor Gray
    Write-Host "    -?, --help             Show this help"
    Write-Host "    -v, --verbose          Also stream logs after start / restart"
    Write-Host "    -b, --browser              Open browser  " -NoNewline
    Write-Host "(standalone or with -u / -r)" -ForegroundColor Gray
    Write-Host "    --loginas:<username>       Switch to user in browser  " -NoNewline
    Write-Host "(any INT username, implies -b)" -ForegroundColor Gray
    Write-Host "    --env                      Print current env from .env"
    Write-Host "    --env:<int|staging>        Switch env file  " -NoNewline
    Write-Host "(requires -u / -r, prod not allowed)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Examples:" -ForegroundColor Gray
    Write-Host "    nx -u                           start"
    Write-Host "    nx -u -v                        start and stream logs"
    Write-Host "    nx -u -b                        start and open browser"
    Write-Host "    nx --env                        show current env from .env"
    Write-Host "    nx -u --env:staging             start with STAGING env"
    Write-Host "    nx -u -b --loginas:username     start, open browser, log in as username"
    Write-Host "    nx --loginas:username           switch browser session to username"
    Write-Host "    nx -r --verbose                 restart and stream logs"
    Write-Host "    nx -l                           watch live logs"
    Write-Host ""
}

# ── flag parsing ──────────────────────────────────────────────────────────────
$action      = $null
$verbose     = $false
$browser     = $false
$loginAs     = $null
$envOverride = $null
$unknown     = @()

for ($i = 0; $i -lt $args.Count; $i++) {
    $arg = $args[$i]
    if ($arg -match '^--loginas:(.*)$') {
        $val = $Matches[1]
        if ($val -eq '') {
            $i++
            $val = if ($i -lt $args.Count) { $args[$i] } else { '' }
        }
        $loginAs = $val
        continue
    }
    if ($arg -match '^--env$') {
        $action = 'env-show'
        continue
    }
    if ($arg -match '^--env:(.+)$') {
        $envOverride = $Matches[1].ToUpper()
        continue
    }
    switch -Exact ($arg.ToLower()) {
        '-u'        { $action = 'start'   }
        '--up'      { $action = 'start'   }
        '-r'        { $action = 'restart' }
        '--restart' { $action = 'restart' }
        '-d'        { $action = 'stop'    }
        '--down'    { $action = 'stop'    }
        '-l'        { $action = 'logs'    }
        '--logs'    { $action = 'logs'    }
        '-v'        { $verbose = $true      }
        '--verbose' { $verbose = $true      }
        '-b'        { $browser = $true      }
        '--browser' { $browser = $true      }
        '-?'        { Show-Help; exit 0     }
        '--help'    { Show-Help; exit 0     }
        default     { $unknown += $arg      }
    }
}

if ($unknown.Count -gt 0) {
    Write-Fail "Unknown flag(s): $($unknown -join ', ')"
    Show-Help
    exit 1
}

if ($loginAs) { $browser = $true }  

if (-not $action) { $action = if ($browser) { 'browser' } else { 'status' } }

if ($verbose -and $action -notin @('start', 'restart')) {
    Write-Fail "-v / --verbose can only be used with -u / --up or -r / --restart"
    exit 1
}

if ($envOverride) {
    if ($envOverride -eq 'PROD') {
        Write-Fail "--env:prod is not allowed from nx CLI"
        exit 1
    }
    if ($envOverride -notin @('INT', 'STAGING')) {
        Write-Fail "--env: must be one of int, staging (got '$($envOverride.ToLower())')"
        exit 1
    }
    if ($action -notin @('start', 'restart')) {
        Write-Fail "--env:<value> can only be used with -u / --up or -r / --restart"
        exit 1
    }
}

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
        Remove-Item -Path $EnvStateFile -ErrorAction SilentlyContinue
        Write-Ok "Stopped"
    } else {
        Write-Warn "Nothing to stop — nexora is not running"
    }
}

function Start-App {
    $existing = Find-AppProcess
    if ($existing) {
        Write-Warn "Already running on PID $($existing.Id) — use -r / --restart to restart"
        return $null
    }
    $envValue = if ($envOverride) { $envOverride } else { "INT" }
    Write-Info "Starting nexora ($envValue)..."
    $prev = [System.Environment]::GetEnvironmentVariable("ENVIRONMENT")
    try {
        $env:ENVIRONMENT = $envValue
        $p = Start-Process -FilePath $Python `
                 -ArgumentList "`"$AppPy`"" `
                 -WorkingDirectory $AppDir `
                 -WindowStyle Hidden `
                 -RedirectStandardOutput $StdoutLog `
                 -RedirectStandardError  $StderrLog `
                 -PassThru
        $envValue | Out-File -FilePath $EnvStateFile -Encoding utf8 -NoNewline
        Write-Ok "Started  (PID $($p.Id))"
        return $p
    } finally {
        if ($null -eq $prev) { Remove-Item Env:ENVIRONMENT -ErrorAction SilentlyContinue }
        else                  { $env:ENVIRONMENT = $prev }
    }
}

function Show-CurrentEnv {
    $p = Find-AppProcess
    if ($p) {
        if (Test-Path $EnvStateFile) {
            $running = (Get-Content $EnvStateFile -Raw).Trim()
            Write-Info "Current env: $running  (running, PID $($p.Id))"
        } else {
            Write-Warn "Running on PID $($p.Id) but env unknown (started outside nx?)"
        }
        return
    }
    $envFile = Join-Path $AppDir '.env'
    if (-not (Test-Path $envFile)) {
        Write-Fail ".env not found at $envFile"
        return
    }
    $envLine = Get-Content $envFile | Where-Object { $_ -match '^\s*ENVIRONMENT\s*=' } | Select-Object -First 1
    if ($envLine -match '^\s*ENVIRONMENT\s*=\s*"?([^"\s]+)"?\s*$') {
        Write-Info "Not running. Default env from .env: $($Matches[1])"
    } else {
        Write-Warn ".env has no ENVIRONMENT= line"
    }
}

function Wait-ForStartup {
    param([System.Diagnostics.Process]$Process, [int]$TimeoutSec = 20)
    Write-Info "Waiting for nexora to be ready..."
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) {
            Start-Sleep -Milliseconds 200  # let OS flush the log file
            return 'failed'
        }
        try {
            $tcp = [System.Net.Sockets.TcpClient]::new()
            $tcp.Connect('127.0.0.1', 8000)
            $tcp.Close()
            return 'ready'
        } catch { }
        Start-Sleep -Milliseconds 300
    }
    return 'timeout'
}

function Show-StartupError {
    Write-Host ""
    if (Test-Path $StderrLog) {
        Get-Content $StderrLog -Tail 30 | ForEach-Object { Write-Dim $_ }
    }
    Write-Host ""
}

function Open-Browser {
    $url = if ($loginAs) { "http://127.0.0.1:8000/dev/login/$loginAs" } else { "http://127.0.0.1:8000" }
    Write-Info "Opening $url..."
    Start-Process $url
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
        $p = Start-App
        if ($p) {
            $result = Wait-ForStartup $p
            switch ($result) {
                'ready'   { Write-Ok "nexora is ready"; if ($browser) { Open-Browser } }
                'failed'  { Write-Fail "nexora crashed on startup — output:"; Show-StartupError }
                'timeout' { Write-Warn "Timed out waiting for nexora — it may still be starting"; if ($browser) { Open-Browser } }
            }
            if ($verbose -and $result -ne 'failed') { Watch-Logs }
        }
    }
    'restart' {
        Stop-App; Start-Sleep -Seconds 2
        $p = Start-App
        if ($p) {
            $result = Wait-ForStartup $p
            switch ($result) {
                'ready'   { Write-Ok "nexora is ready"; if ($browser) { Open-Browser } }
                'failed'  { Write-Fail "nexora crashed on startup — output:"; Show-StartupError }
                'timeout' { Write-Warn "Timed out waiting for nexora — it may still be starting"; if ($browser) { Open-Browser } }
            }
            if ($verbose -and $result -ne 'failed') { Watch-Logs }
        }
    }
    'browser' {
        $p = Find-AppProcess
        if (-not $p) {
            Write-Fail "nexora is not running — start it first with -u / --up"
            exit 1
        }
        Open-Browser
    }
    'stop'     { Stop-App }
    'env-show' { Show-CurrentEnv }
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
