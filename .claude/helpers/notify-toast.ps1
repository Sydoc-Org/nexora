# Windows desktop notification helper used by Claude Code Stop/Notification hooks.
#
# Usage:
#   powershell.exe -ExecutionPolicy Bypass -File <this-file> "<title>" "<body>"

param(
    [string]$Title = "Claude Code",
    [string]$Body  = "Needs your attention"
)

$ErrorActionPreference = 'SilentlyContinue'
$logFile = "$PSScriptRoot\notify-toast.log"

function Log($msg) {
    try { "$([DateTime]::Now.ToString('HH:mm:ss.fff')) $msg" | Add-Content -Path $logFile } catch {}
}

Log "----- invoked -----"
Log "PSVersion : $($PSVersionTable.PSVersion)"
Log "Args      : $($args -join ' | ')"
Log "Title     : $Title"
Log "Body      : $Body"
Log "PSScript  : $PSScriptRoot"
Log "PWD       : $(Get-Location)"
Log "User      : $env:USERNAME"
Log "Session   : $env:SESSIONNAME"

# --- audible cue ---
try {
    [System.Media.SystemSounds]::Exclamation.Play()
    Log "Sound     : played"
} catch {
    Log "Sound err : $_"
}

# --- BurntToast ---
try {
    if (Get-Module -ListAvailable -Name BurntToast) {
        Import-Module BurntToast -ErrorAction Stop
        New-BurntToastNotification -Text $Title, $Body -ErrorAction Stop
        Log "BurntToast: shown"
        exit 0
    } else {
        Log "BurntToast: not installed"
    }
} catch {
    Log "BurntToast err: $_"
}

# --- WinRT toast under PowerShell AppUserModelID ---
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02
    )
    $textNodes = $template.GetElementsByTagName('text')
    $textNodes.Item(0).AppendChild($template.CreateTextNode($Title)) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode($Body))  | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(
        '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    ).Show($toast)
    Log "WinRT     : Show() called under registered PowerShell AppUserModelID"
} catch {
    Log "WinRT err : $_"
}

# --- NotifyIcon balloon fallback (always works) ---
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $balloon = New-Object System.Windows.Forms.NotifyIcon
    $balloon.Icon = [System.Drawing.SystemIcons]::Information
    $balloon.BalloonTipTitle = $Title
    $balloon.BalloonTipText  = $Body
    $balloon.Visible = $true
    $balloon.ShowBalloonTip(5000)
    Start-Sleep -Milliseconds 500
    $balloon.Dispose()
    Log "Balloon   : ShowBalloonTip() called and disposed"
} catch {
    Log "Balloon err: $_"
}

Log "----- done -----`n"
exit 0
