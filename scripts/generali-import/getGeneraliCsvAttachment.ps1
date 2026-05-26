$root_location = "\\prdimpexp01\d$\sydoc\scripts\generali"
$destDir = "$root_location\import"
$envVars = Get-Content -Raw "$root_location\env.json" | ConvertFrom-Json

$TENANT_ID = $envVars.TENANT_ID
$CLIENT_ID = $envVars.CLIENT_ID
$USERNAME = $envVars.USERNAME
$PASSWORD = $envVars.PASSWORD
$GRANT_TYPE = $envVars.GRANT_TYPE
$SCOPE = $envVars.SCOPE
$CLIENT_SECRET = $envVars.CLIENT_SECRET

$logDir = Join-Path $root_location 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "getGeneraliCsvAttachment_$(Get-Date -Format 'yyyy-MM-dd').log"
$script:errorList = [System.Collections.Generic.List[string]]::new()

function isLocal {
    return (Get-Location).Path -like "*bes*"
}

function Log {
    param([string]$message, [string]$level = 'INFO')
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$level] $message"
    Add-Content -Path $logFile -Value $line
    if (isLocal) {
        $color = switch ($level) {
            'ERROR' { 'Red' }
            'WARN'  { 'Yellow' }
            default { 'Gray' }
        }
        Write-Host $line -ForegroundColor $color
    }
}

function get_access_token_graphAPI {
    $headers = @{
        "Content-Type" = "application/x-www-form-urlencoded"
    }
    $body = @{
        client_id     = $envVars.CLIENT_ID
        username      = $envVars.USERNAME
        password      = $envVars.PASSWORD
        grant_type    = $envVars.GRANT_TYPE
        scope         = "Mail.Send"
        client_secret = $envVars.CLIENT_SECRET
    }
    $tenant_id = $envVars.TENANT_ID
    $uri = "https://login.microsoftonline.com/$tenant_id/oauth2/v2.0/token"
    $tokenrequest = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body
    return $tokenrequest.access_token
}

function send_email_graphAPI($subject) {
    $access_token = get_access_token_graphAPI
    $headers = @{
        "Authorization" = "Bearer $access_token"
        "Content-Type"  = "application/json"
    }
    $emailBody = @{
        message         = @{
            subject      = $subject
            body         = @{
                contentType = "HTML"
                content     = $body_html
            }
            toRecipients = @(
                @{
                    emailAddress = @{
                        address = "support.helpdesk@sydoc.ch"
                    }
                }
            )
        }
        saveToSentItems = "true"
    }
    $jsonPayload = $emailBody | ConvertTo-Json -Depth 10
    $uri = "https://graph.microsoft.com/v1.0/me/sendMail"
    Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $jsonPayload
}

function Notify-Error {
    param(
        [string]$subject,
        [string]$context,
        $errorRecord
    )
    $errorText = ''
    if ($errorRecord) {
        $errorText = (($errorRecord | Out-String).Trim())
        if ($errorRecord.ScriptStackTrace) {
            $errorText += "`n`nStack trace:`n" + $errorRecord.ScriptStackTrace
        }
    }
    $errorListText = $script:errorList -join "`n"
    $body_html = @"
<h2>Generali CSV Attachment Import &mdash; $subject</h2>
<p><b>Time:</b> $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
<p><b>Host:</b> $env:COMPUTERNAME</p>
<p><b>Script:</b> getGeneraliCsvAttachment.ps1</p>
<p><b>Context:</b> $context</p>
<p><b>Log file:</b> $logFile</p>
$(if ($errorText) { "<h3>Fatal error</h3><pre>$([System.Net.WebUtility]::HtmlEncode($errorText))</pre>" })
$(if ($errorListText) { "<h3>Recorded errors during run ($($script:errorList.Count))</h3><pre>$([System.Net.WebUtility]::HtmlEncode($errorListText))</pre>" })
"@
    try {
        send_email_graphAPI "Generali CSV Attachment Import - $subject"
        Log "Error notification email sent to support.helpdesk@sydoc.ch"
    } catch {
        Log "Failed to send error email: $_" 'ERROR'
    }
}

Log "===== Script started ====="

try {
    Log "Requesting Graph access token (scope=$SCOPE)..."
    $headers = @{
        "Content-Type" = "application/x-www-form-urlencoded"
    }
    $body = @{
        client_id     = $CLIENT_ID
        username      = $USERNAME
        password      = $PASSWORD
        grant_type    = $GRANT_TYPE
        scope         = $SCOPE
        client_secret = $CLIENT_SECRET
    }
    $token_request = Invoke-RestMethod -Method POST -Uri "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" -Headers $headers -Body $body
    $access_token = $token_request.access_token
    Log "Access token acquired (length=$($access_token.Length))"

    $GeneraliMailBoxID = $envVars.GENERALI_MAILBOX_ID
    $GeneraliMailBoxChildPosteingangID = $envVars.GENERALI_MAILBOX_POSTEINGANG_ID
    $GeneraliMailBoxChildGelöschtID = $envVars.GENERALI_MAILBOX_GELOESCHT_ID

    $ListMailBoxMessagesURI = "https://graph.microsoft.com/v1.0/me/mailFolders/$GeneraliMailBoxID/childFolders/$GeneraliMailBoxChildPosteingangID/messages"
    $headers = @{
        Authorization  = "Bearer $access_token"
        "Content-Type" = "application/json"
    }

    Log "Listing messages from Posteingang..."
    $ListMailBoxMessagesRequest = Invoke-RestMethod -Method GET -Uri $ListMailBoxMessagesURI -Headers $headers
    $messages = @($ListMailBoxMessagesRequest.Value)
    $messageCount = $messages.Count
    Log "Found $messageCount message(s) in Posteingang"

    $messageIndex = 0
    $totalAttachmentsSaved = 0
    foreach ($message in $messages) {
        $messageIndex++
        $messageid = $message.id
        $messageSubject = $message.subject
        Log "[$messageIndex/$messageCount] Processing message id=$messageid subject='$messageSubject'"
        try {
            $attachment_request_uri = "$ListMailBoxMessagesURI/$messageid/attachments"
            Log "  Fetching attachments..."
            $attachment_request = Invoke-RestMethod -Method GET -Uri $attachment_request_uri -Headers $headers
            $attachments = @($attachment_request.value)
            Log "  Found $($attachments.Count) attachment(s)"
            foreach ($attachment in $attachments) {
                try {
                    #if ($attachment.name -notlike "*.csv") { continue }
                    Log "    Attachment '$($attachment.name)' (size=$($attachment.size) bytes)"
                    $content_bytes = $attachment.contentBytes
                    if (-not $content_bytes) {
                        $msg = "No contentBytes for attachment '$($attachment.name)' on message $messageid - skipping"
                        Log $msg 'WARN'
                        $script:errorList.Add($msg)
                        continue
                    }
                    $bytes = [Convert]::FromBase64String($content_bytes)
                    $outputPath = Join-Path $root_location ((New-Guid).Guid + $attachment.name)
                    [IO.File]::WriteAllBytes($outputPath, $bytes)
                    Log "    Wrote $($bytes.Length) bytes to '$outputPath'"

                    if (-not (Test-Path $destDir)) {
                        New-Item -ItemType Directory -Path $destDir | Out-Null
                        Log "    Created destination directory '$destDir'"
                    }

                    if ($outputPath -like "*.gz") {
                        $outName  = [IO.Path]::GetFileNameWithoutExtension($outputPath)
                        $destFile = Join-Path $destDir $outName
                        Log "    Decompressing GZIP to '$destFile'"
                        $inStream  = [IO.File]::OpenRead($outputPath)
                        $gzStream  = New-Object IO.Compression.GZipStream($inStream, [IO.Compression.CompressionMode]::Decompress)
                        $outStream = [IO.File]::Create($destFile)
                        try   { $gzStream.CopyTo($outStream) }
                        finally {
                            $outStream.Dispose()
                            $gzStream.Dispose()
                            $inStream.Dispose()
                        }
                        Log "    Decompression complete (output size=$((Get-Item $destFile).Length) bytes)"
                    }
                    Move-Item $outputPath $root_location\done -Force
                    Log "    Moved source attachment to '$root_location\done'"
                    $totalAttachmentsSaved++
                } catch {
                    $msg = "Failed to process attachment '$($attachment.name)' on message $messageid - $_"
                    Log $msg 'ERROR'
                    $script:errorList.Add($msg)
                }
            }
            $moveBody = @{destinationId = $GeneraliMailBoxChildGelöschtID} | ConvertTo-Json
            Invoke-RestMethod -Method Post -Uri "$ListMailBoxMessagesURI/$messageid/move" -Body $moveBody -Headers $headers -StatusCodeVariable statusCode | Out-Null
            Log "  Moved message to Geloescht (HTTP $statusCode)"
        } catch {
            $msg = "Failed to process message $messageid - $_"
            Log $msg 'ERROR'
            $script:errorList.Add($msg)
        }
    }

    Log "===== Script finished ====="
    Log "Summary: messages=$messageIndex attachments_saved=$totalAttachmentsSaved errors=$($script:errorList.Count)"

    if ($script:errorList.Count -gt 0) {
        Notify-Error -subject "$($script:errorList.Count) error(s) during run" -context "Script completed with $($script:errorList.Count) non-fatal error(s)"
    }
} catch {
    Log "FATAL: $_" 'ERROR'
    Log "StackTrace: $($_.ScriptStackTrace)" 'ERROR'
    Notify-Error -subject "FATAL ERROR" -context "Script aborted due to a fatal error" -errorRecord $_
    exit 1
}
