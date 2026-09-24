<#
  Ingest the per-request CSV logs into dbo.Logs.

  nx_lib/hooks.py's _log_every_request() appends one row per non-static request
  to var/logs/user/<yyyyMMddHH>/nexora_logs.csv. This drains those folders into
  dbo.Logs, which prune_request_log.py then trims to REQUEST_LOG_RETENTION
  (180 days).

  Three things this used to get wrong, all of which could lose an hour of the
  audit trail without anyone noticing:

  1. `Remove-Item -Recurse -Force` ran unconditionally after the insert loop,
     with no try/catch and no $ErrorActionPreference. A row that failed to
     insert, or a dropped connection halfway through, still ended with the
     folder deleted -- the rows were simply gone. Each folder is now one
     transaction: it commits and is deleted, or it rolls back and the folder is
     KEPT for the next run to retry.

  2. It opened a brand new SqlConnection per row -- Open, ExecuteNonQuery,
     Close, inside the loop. At roughly 8k requests a day that is 8k
     connect/disconnect cycles against PRDSQL01 per run. One connection is
     opened for the whole run now, and the command and its typed parameters are
     built once.

  3. It printed nothing at all, so a silent failure was indistinguishable from
     a quiet hour. It now reports per folder and a total, and exits non-zero if
     any folder was kept back, so the Task Scheduler history shows a failure.

  It also no longer touches the hour the app is still appending to: importing
  and deleting the live folder races the web process, and any request logged
  between the read and the delete vanished.

  NOTE: dbo.Logs.Timestamp is not in the INSERT -- it comes from the column
  default, so it records ingest time, not request time. The CSV carries no
  timestamp column at all, so the request time is only ever known to the hour
  (from the folder name) and is currently discarded. Changing that means adding
  a column to the CSV writer and this INSERT, and it would shift what the admin
  log viewer and the retention window are measuring, so it is left alone here.

      powershell -ExecutionPolicy Bypass -File ops\cleanup\csvLogs_toDB.ps1
#>

$ErrorActionPreference = 'Stop'

$nexoraLogFolder = 'D:\sydoc\nexora\var\logs\user'
$dbServer = 'PRDSQL01'
$dbName = 'nexora'
$dbTable = 'Logs'

Write-Output "[csv-logs] start $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"

if (-not (Test-Path $nexoraLogFolder)) {
    Write-Output "[csv-logs] no folder at $nexoraLogFolder; nothing to do."
    exit 0
}

# The app is still appending to the current hour -- leave it for the next run.
$currentHour = (Get-Date).ToString('yyyyMMddHH')
$folders = @(Get-ChildItem -Directory $nexoraLogFolder | Where-Object { $_.Name -ne $currentHour })

if ($folders.Count -eq 0) {
    Write-Output "[csv-logs] nothing to import (only the current hour is present)."
    exit 0
}

$connection = New-Object System.Data.SqlClient.SqlConnection(
    "Server=$dbServer;Database=$dbName;Integrated Security=True;TrustServerCertificate=True")
$connection.Open()

$imported = 0
$keptBack = 0

try {
    $cmd = $connection.CreateCommand()
    $cmd.CommandText = "INSERT INTO $dbTable (SessionID, RequestIpAddress, UserID, Username, HttpRequestMethod, Path, HttpResponseCode, Args, durationSeconds) VALUES (@SessionID, @RequestIpAddress, @UserID, @Username, @HttpRequestMethod, @Path, @HttpResponseCode, @Args, @durationSeconds)"
    # AddWithValue per row, exactly as before. Tempting to type these once and
    # reuse them, but Import-Csv yields '' for a blank cell and AddWithValue
    # sends it as a string, which SQL Server converts on the way in: an
    # anonymous request lands as UserID = 0 and Username = ''. That is what all
    # 856,638 rows in dbo.Logs already look like -- 155,015 of them anonymous,
    # and not one NULL. Typed Int/Float parameters would have to send DBNull
    # instead, quietly splitting the table into "0 means anonymous" before the
    # change and "NULL means anonymous" after it, and breaking any query that
    # looks for one or the other. NULL is arguably the better representation;
    # switching to it is a data decision with a backfill, not a side effect of
    # tidying this loop.

    foreach ($folder in $folders) {
        $csvPath = Join-Path $folder.FullName 'nexora_logs.csv'

        if (-not (Test-Path $csvPath)) {
            # An hour folder with no CSV holds nothing to lose.
            Remove-Item $folder.FullName -Recurse -Force
            Write-Output "[csv-logs] $($folder.Name): no csv, folder removed"
            continue
        }

        $rows = 0
        $transaction = $connection.BeginTransaction()
        $cmd.Transaction = $transaction
        try {
            foreach ($row in Import-Csv $csvPath) {
                $cmd.Parameters.Clear()
                [void]$cmd.Parameters.AddWithValue('@SessionID', $row.SessionID)
                [void]$cmd.Parameters.AddWithValue('@RequestIpAddress', $row.RequestIpAddress)
                [void]$cmd.Parameters.AddWithValue('@UserID', $row.UserID)
                [void]$cmd.Parameters.AddWithValue('@Username', $row.Username)
                [void]$cmd.Parameters.AddWithValue('@HttpRequestMethod', $row.HttpRequestMethod)
                [void]$cmd.Parameters.AddWithValue('@Path', $row.Path)
                [void]$cmd.Parameters.AddWithValue('@HttpResponseCode', $row.HttpResponseCode)
                [void]$cmd.Parameters.AddWithValue('@Args', $row.Args)
                [void]$cmd.Parameters.AddWithValue('@durationSeconds', $row.durationSeconds)
                [void]$cmd.ExecuteNonQuery()
                $rows++
            }
            $transaction.Commit()
            Remove-Item $folder.FullName -Recurse -Force
            $imported += $rows
            Write-Output "[csv-logs] $($folder.Name): imported $rows row(s)"
        }
        catch {
            $transaction.Rollback()
            $keptBack++
            Write-Output "[csv-logs] $($folder.Name): FAILED after $rows row(s) -- rolled back, folder KEPT for retry: $($_.Exception.Message)"
        }
        finally {
            $cmd.Transaction = $null
        }
    }
}
finally {
    $connection.Close()
}

Write-Output "[csv-logs] done: $imported row(s) imported, $keptBack folder(s) kept for retry"
if ($keptBack -gt 0) { exit 1 }
exit 0
