$envVars = Get-Content -Raw "env.json" | ConvertFrom-Json

$TENANT_ID = $envVars.TENANT_ID
$CLIENT_ID = $envVars.CLIENT_ID
$USERNAME = $envVars.USERNAME
$PASSWORD = $envVars.PASSWORD
$GRANT_TYPE = $envVars.GRANT_TYPE
$SCOPE = $envVars.SCOPE
$CLIENT_SECRET = $envVars.CLIENT_SECRET

$headers = @{
    "Content-Type" = "application/x-www-form-urlencoded"
}

$body = @{
    client_id = $CLIENT_ID
    username = $USERNAME
    password = $PASSWORD
    grant_type = $GRANT_TYPE
    scope = $SCOPE
    client_secret = $CLIENT_SECRET
}

$token_request = Invoke-RestMethod -Method POST -Uri "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" -Headers $headers -Body $body
$access_token = $token_request.access_token

$GeneraliMailBoxID = $envVars.GENERALI_MAILBOX_ID
$GeneraliMailBoxChildPosteingangID = $envVars.GENERALI_MAILBOX_POSTEINGANG_ID
$GeneraliMailBoxChildGelöschtID = $envVars.GENERALI_MAILBOX_GELOESCHT_ID

$ListMailBoxMessagesURI = "https://graph.microsoft.com/v1.0/me/mailFolders/$GeneraliMailBoxID/childFolders/$GeneraliMailBoxChildPosteingangID/messages"
$headers = @{
    Authorization = "Bearer $access_token"
    "Content-Type" = "application/json"
}

$ListMailBoxMessagesRequest = Invoke-RestMethod -Method GET -Uri $ListMailBoxMessagesURI -Headers $headers
foreach ($message in $ListMailBoxMessagesRequest.Value){
    $messageid = $message.id
    $attachment_request_uri = "$ListMailBoxMessagesURI/$messageid/attachments"
    Write-Host "Fetching attachments for message: $messageid"
    $attachment_request = Invoke-RestMethod -Method GET -Uri $attachment_request_uri -Headers $headers
    foreach($attachment in $attachment_request.value)
    {
        if ($attachment.name -notlike "*.csv") { continue }
        $content_bytes = $attachment.contentBytes
        if (-not $content_bytes) {
            Write-Warning "No contentBytes for attachment '$($attachment.name)' — skipping"
            continue
        }
        $bytes = [Convert]::FromBase64String($content_bytes)
        $outputPath = Join-Path (Get-Location) $attachment.name
        [IO.File]::WriteAllBytes($outputPath, $bytes)
        Write-Host "Saved: $outputPath"
    }
    $moveBody = @{destinationId = $GeneraliMailBoxChildGelöschtID} | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "$ListMailBoxMessagesURI/$messageid/moved" -Body $moveBody -Headers $headers -StatusCodeVariable statusCode
}