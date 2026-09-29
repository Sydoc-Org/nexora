<#
  Delete server-side session files older than SESSION_LIFETIME (24 hours).

  On PROD, Flask-Session keeps each signed-in user's session -- name, e-mail,
  organisation, permissions -- as a file under var\session. The cookie expires
  after 24 hours, so an older file serves nobody and only keeps personal data.

  Registered as "\sydoc\nexora\Cleanup Session Files" by deploy-env.yml's
  "Register scheduled tasks" step (daily 03:15, SYSTEM); the definition is
  cleanup-session-files-task.xml next to this script. Output goes to
  var\logs\system\cleanup_session_files.log.

      powershell -ExecutionPolicy Bypass -File ops\cleanup\cleanup_expired_sessionFiles.ps1
#>

$ErrorActionPreference = 'Stop'

$sessionFolder = 'D:\sydoc\nexora\var\session'
$cutoff = (Get-Date).AddHours(-24)

Write-Output "[session-files] start $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')), cutoff $($cutoff.ToString('yyyy-MM-dd HH:mm:ss'))"

if (-not (Test-Path $sessionFolder)) {
    Write-Output "[session-files] no folder at $sessionFolder; nothing to do."
    exit 0
}

$deleted = 0
$failed = 0
foreach ($file in Get-ChildItem -File $sessionFolder) {
    if ($file.CreationTime -le $cutoff) {
        try {
            Remove-Item $file.FullName -Force
            $deleted++
        }
        catch {
            # A file the app is writing right now can be locked; the next run gets it.
            $failed++
        }
    }
}

Write-Output "[session-files] done: $deleted deleted, $failed could not be deleted"
if ($failed -gt 0) { exit 1 }
exit 0
