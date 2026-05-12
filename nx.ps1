# No param() block — $args used directly so PowerShell doesn't intercept -v/--verbose etc.

$AppDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Python    = "C:\Users\bes\AppData\Local\Programs\Python\Python313\python.exe"
$AppPy     = Join-Path $AppDir "nx_main.py"
$LogDir    = Join-Path $AppDir "logs\system"
$null      = New-Item -ItemType Directory -Force -Path $LogDir
$StderrLog    = "$LogDir\app_stderr.log"
$StdoutLog    = "$LogDir\app_stdout.log"
$EnvStateFile = "$LogDir\current_env"

# Zero-arg → interactive nexora TUI
if ($args.Count -eq 0) {
    $prevEnc    = [Console]::OutputEncoding
    $prevPyEnc  = $env:PYTHONIOENCODING
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $env:PYTHONIOENCODING = "utf-8"
    Push-Location -LiteralPath $AppDir
    try {
        & $Python -m nx_lib.cli
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
        [Console]::OutputEncoding = $prevEnc
        if ($null -eq $prevPyEnc) { Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue }
        else                       { $env:PYTHONIOENCODING = $prevPyEnc }
    }
    exit $code
}

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
    Write-Host "    nx                       launch interactive TUI (splash + REPL)"
    Write-Host "    nx <command> [options]   one-shot mode"
    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor Gray
    Write-Host "    -u, --up              Start nexora"
    Write-Host "    -d, --down            Stop nexora"
    Write-Host "    -r, --restart         Restart nexora"
    Write-Host "    -l, --logs            Stream live logs  " -NoNewline
    Write-Host "(requires a running instance)" -ForegroundColor Gray
    Write-Host "    -md, --maindir        cd into the nexora project directory"
    Write-Host "    --routes[:<regex>]    List Flask routes (optional regex filter)"
    Write-Host ""
    Write-Host "  Options:" -ForegroundColor Gray
    Write-Host "    -?, --help                 Show this help"
    Write-Host "    -v, --verbose              Also stream logs after start / restart"
    Write-Host "    -b, --browser[:<route>]    Open browser  " -NoNewline
    Write-Host "(standalone or with -u / -r; optional route path)" -ForegroundColor Gray
    Write-Host "    --loginas:<username>       Switch to user in browser  " -NoNewline
    Write-Host "(any INT username, implies -b)" -ForegroundColor Gray
    Write-Host "    --env                      Print current env from .env"
    Write-Host "    --env:<int|staging>        Switch env file  " -NoNewline
    Write-Host "(requires -u / -r / --routes, prod not allowed)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Examples:" -ForegroundColor Gray
    Write-Host "    nx -u                                start"
    Write-Host "    nx -u -v                             start and stream logs"
    Write-Host "    nx -u -b                             start and open browser"
    Write-Host "    nx -b:/admin/users                   open browser to /admin/users"
    Write-Host "    nx -u -b:/admin --loginas:username   start, log in as username, navigate to /admin"
    Write-Host "    nx --routes                          list all Flask routes"
    Write-Host "    nx --routes:admin                    list routes matching regex /admin/i"
    Write-Host "    nx --routes:^/api                    list routes whose path starts with /api"
    Write-Host "    nx --env                             show current env from .env"
    Write-Host "    nx -u --env:staging                  start with STAGING env"
    Write-Host "    nx --loginas:username                switch browser session to username"
    Write-Host "    nx -r --verbose                      restart and stream logs"
    Write-Host "    nx -l                                watch live logs"
    Write-Host "    nx -md                               cd into the nexora project directory"
    Write-Host ""
}

# ── flag parsing ──────────────────────────────────────────────────────────────
$action        = $null
$verbose       = $false
$browser       = $false
$browserRoute  = $null
$routesPattern = $null
$loginAs       = $null
$envOverride   = $null
$unknown       = @()

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
    # -b / --browser[:route]  (colon-form only; bare -b opens root)
    if ($arg -match '^(?:-b|--browser)(?::(.*))?$') {
        $browser = $true
        if ($Matches[1]) { $browserRoute = $Matches[1] }
        continue
    }
    # --routes[:regex]  (colon-form only; bare --routes lists all)
    if ($arg -match '^--routes(?::(.*))?$') {
        $action = 'routes'
        if ($Matches[1]) { $routesPattern = $Matches[1] }
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
        '-md'       { $action = 'maindir' }
        '--maindir' { $action = 'maindir' }
        '-v'        { $verbose = $true      }
        '--verbose' { $verbose = $true      }
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
    if ($action -notin @('start', 'restart', 'routes')) {
        Write-Fail "--env:<value> can only be used with -u / --up, --restart, or -r / --routes"
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
    $base = "http://127.0.0.1:8000"
    $path = ""
    if ($browserRoute) {
        $path = $browserRoute.Trim()
        if ($path -and -not $path.StartsWith('/')) { $path = "/$path" }
    }
    if ($loginAs) {
        $loginUrl = "$base/dev/login/$loginAs"
        Write-Info "Opening $loginUrl..."
        Start-Process $loginUrl
        if ($path) {
            Start-Sleep -Milliseconds 1500
            $target = "$base$path"
            Write-Info "Navigating to $target..."
            Start-Process $target
        }
    } else {
        $url = "$base$path"
        Write-Info "Opening $url..."
        Start-Process $url
    }
}

function Show-Routes {
    param([string]$Pattern)
    $envValue = if ($envOverride) { $envOverride } else { "INT" }
    $py = @'
import sys, os, warnings, re, inspect
warnings.filterwarnings("ignore")
pattern = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
regex = None
if pattern:
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        print(f"invalid regex '{pattern}': {exc}", file=sys.stderr)
        raise SystemExit(2)
try:
    from nx_main import app
except Exception as exc:
    print(f"failed to import nx_main: {exc}", file=sys.stderr)
    raise SystemExit(1)

root = os.getcwd()

def origin(endpoint):
    fn = app.view_functions.get(endpoint)
    if not fn:
        return ""
    try:
        fn = inspect.unwrap(fn)
        src = inspect.getsourcefile(fn) or ""
        line = inspect.getsourcelines(fn)[1]
    except (OSError, TypeError, ValueError):
        return ""
    if not src:
        return ""
    try:
        rel = os.path.relpath(src, root)
        if not rel.startswith(".."):
            src = rel
    except ValueError:
        pass
    return f"{src}:{line}"

rules = sorted(app.url_map.iter_rules(), key=lambda r: r.rule)
rows = []
total = 0
for rule in rules:
    total += 1
    if regex and not regex.search(rule.rule) and not regex.search(rule.endpoint):
        continue
    methods = ",".join(sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS")))
    rows.append((methods, rule.rule, rule.endpoint, origin(rule.endpoint)))

mw = max((len(r[0]) for r in rows), default=6)
rw = max((len(r[1]) for r in rows), default=4)
ew = max((len(r[2]) for r in rows), default=8)

for methods, rule_path, endpoint, where in rows:
    print(f"{methods:<{mw}}  {rule_path:<{rw}}  {endpoint:<{ew}}  {where}")

print()
if pattern:
    print(f"{len(rows)} of {total} routes matching /{pattern}/i")
else:
    print(f"{total} routes total")
'@
    $prev = [System.Environment]::GetEnvironmentVariable("ENVIRONMENT")
    $prevPyEnc = $env:PYTHONIOENCODING
    try {
        $env:ENVIRONMENT = $envValue
        $env:PYTHONIOENCODING = "utf-8"
        Push-Location -LiteralPath $AppDir
        try {
            $patternArg = if ($Pattern) { $Pattern } else { '' }
            & $Python -c $py $patternArg
        } finally {
            Pop-Location
        }
    } finally {
        if ($null -eq $prev) { Remove-Item Env:ENVIRONMENT -ErrorAction SilentlyContinue }
        else                  { $env:ENVIRONMENT = $prev }
        if ($null -eq $prevPyEnc) { Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue }
        else                       { $env:PYTHONIOENCODING = $prevPyEnc }
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
    'maindir'  {
        # NOTE: when invoked as `nx -md` via the profile function, that wrapper
        # intercepts this flag and runs Set-Location in the caller's scope.
        # The Set-Location below is only a fallback for dot-sourced invocations.
        Set-Location -LiteralPath $AppDir
        Write-Ok "cd $AppDir"
    }
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
    'routes' { Show-Routes -Pattern $routesPattern }
}
