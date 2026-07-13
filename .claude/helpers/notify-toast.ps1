# Windows desktop notification helper used by Claude Code Stop/Notification hooks.
#
# Usage:
#   powershell.exe -ExecutionPolicy Bypass -File <this-file> "<title>" "<body>"
#
# Toasts are shown under a dedicated "Claude Code" AppUserModelID (registered in
# HKCU on first run). A fresh AppID starts with banners enabled, so notifications
# pop as banners even when the generic "Windows PowerShell" identity has had its
# banner turned off. If a banner still does not appear, check Windows Settings >
# Notifications: Do Not Disturb / Focus off, and "Claude Code" banners on.

param(
    [string]$Title = "Claude Code",
    [string]$Body  = "Needs your attention"
)

$ErrorActionPreference = 'SilentlyContinue'
$logFile = "$PSScriptRoot\notify-toast.log"
$AppId   = 'Claude.Code'

function Log($msg) {
    try { "$([DateTime]::Now.ToString('HH:mm:ss.fff')) $msg" | Add-Content -Path $logFile } catch {}
}

Log "----- invoked -----"
Log "PSVersion : $($PSVersionTable.PSVersion)"
Log "Title     : $Title"
Log "Body      : $Body"

# --- audible cue ---
try { [System.Media.SystemSounds]::Exclamation.Play(); Log "Sound     : played" }
catch { Log "Sound err : $_" }

# --- register a dedicated AppUserModelID once (cheap HKCU key, no shortcut needed) ---
try {
    $key = "HKCU:\Software\Classes\AppUserModelId\$AppId"
    if (-not (Test-Path $key)) {
        New-Item -Path $key -Force | Out-Null
        New-ItemProperty -Path $key -Name DisplayName -Value 'Claude Code' -PropertyType String -Force | Out-Null
        Log "AppId     : registered $AppId"
    }
} catch { Log "AppId err : $_" }

# --- WinRT toast under the Claude Code identity ---
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02
    )
    $textNodes = $template.GetElementsByTagName('text')
    $textNodes.Item(0).AppendChild($template.CreateTextNode($Title)) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode($Body))  | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($toast)
    Log "WinRT     : shown under $AppId"
    Log "----- done -----`n"
    exit 0
} catch {
    Log "WinRT err : $_"
}

# --- NotifyIcon balloon fallback (only reached if the WinRT toast threw) ---
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $balloon = New-Object System.Windows.Forms.NotifyIcon
    $balloon.Icon = [System.Drawing.SystemIcons]::Information
    $balloon.BalloonTipTitle = $Title
    $balloon.BalloonTipText  = $Body
    $balloon.Visible = $true
    $balloon.ShowBalloonTip(5000)
    Start-Sleep -Milliseconds 800
    $balloon.Dispose()
    Log "Balloon   : shown (fallback)"
} catch { Log "Balloon err: $_" }

Log "----- done -----`n"
exit 0
