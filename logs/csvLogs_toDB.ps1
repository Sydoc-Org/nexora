$nexoraLogFolder = 'D:\sydoc\nexora\logs'
$dbServer = 'PRDSQL01'
$dbName = 'nexora'
$dbTable = 'Logs'
Get-ChildItem -Directory $nexoraLogFolder | ForEach-Object {
    Import-Csv ($_.FullName + '\nexora_logs.csv') | ForEach-Object {
        $query = @"
        INSERT INTO $($dbTable) (SessionID,
        RequestIpAddress,
        UserID,
        Username,
        HttpRequestMethod,
        Path,
        HttpResponseCode,
        Args,
        durationSeconds
        )
        VALUES (
            '$($_.SessionID)',
            '$($_.RequestIpAddress)',
            '$($_.UserID)',
            '$($_.Username)',
            '$($_.HttpRequestMethod)',
            '$($_.Path)',
            '$($_.HttpResponseCode)',
            '$($_.Args)',
            '$($_.durationSeconds)'
        )
"@
        Invoke-Sqlcmd -ServerInstance $dbServer -Database $dbName -Query $query -TrustServerCertificate
    }
}