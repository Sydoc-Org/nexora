$nexoraLogFolder = 'D:\sydoc\nexora\logs\user'
$dbServer = 'PRDSQL01'
$dbName = 'nexora'
$dbTable = 'Logs'

Get-ChildItem -Directory $nexoraLogFolder | ForEach-Object  {
    Import-Csv ($_.FullName + '\nexora_logs.csv') | ForEach-Object {
            $query = "INSERT INTO $dbTable (SessionID, RequestIpAddress, UserID, Username, HttpRequestMethod, Path, HttpResponseCode, Args, durationSeconds) VALUES (@SessionID, @RequestIpAddress, @UserID, @Username, @HttpRequestMethod, @Path, @HttpResponseCode, @Args, @durationSeconds)"
            $connection = New-Object System.Data.SqlClient.SqlConnection("Server=$dbServer;Database=$dbName;Integrated Security=True;TrustServerCertificate=True")
            $cmd = $connection.CreateCommand()
            $cmd.CommandText = $query
            $cmd.Parameters.AddWithValue("@SessionID", $_.SessionID) | Out-Null
            $cmd.Parameters.AddWithValue("@RequestIpAddress", $_.RequestIpAddress) | Out-Null
            $cmd.Parameters.AddWithValue("@UserID", $_.UserID) | Out-Null
            $cmd.Parameters.AddWithValue("@Username", $_.Username) | Out-Null
            $cmd.Parameters.AddWithValue("@HttpRequestMethod", $_.HttpRequestMethod) | Out-Null
            $cmd.Parameters.AddWithValue("@Path", $_.Path) | Out-Null
            $cmd.Parameters.AddWithValue("@HttpResponseCode", $_.HttpResponseCode) | Out-Null
            $cmd.Parameters.AddWithValue("@Args", $_.Args) | Out-Null
            $cmd.Parameters.AddWithValue("@durationSeconds", $_.durationSeconds) | Out-Null
            $connection.Open()
            $cmd.ExecuteNonQuery()
            $connection.Close()

        }
    Remove-Item $_.FullName -Recurse -Force
}

