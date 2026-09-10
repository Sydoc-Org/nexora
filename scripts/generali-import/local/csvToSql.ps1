$root_location = "\\prdimpexp01\d$\sydoc\scripts\generali"
$datafoldergen = "$root_location\import"

function load_from_dot_env([string]$Path = '.env') {
    Get-Content $Path | ForEach-Object {
        $nvSplit = $_ -split '=', 2
        $name, $value = $nvSplit
        if ([string]::IsNullOrWhiteSpace($name) -or $name.Contains('#')) {
            return
        }
        Set-Content env:\$name $value
    }
}
load_from_dot_env "$root_location\.env"

$fullData = Get-ChildItem $datafoldergen -File
$serverInstances = @('INTSQL01', 'PRDSQL01')

$logDir = "$root_location\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "csvToSql_$(Get-Date -Format 'yyyy-MM-dd').log"

function get_access_token_graphAPI {
    $headers = @{
        "Content-Type" = "application/x-www-form-urlencoded"
    }

    $body = @{
        "client_id"     = $env:CLIENT_ID
        "username"      = $env:USERNAME
        "password"      = $env:PASSWORD
        "grant_type"    = $env:GRANT_TYPE
        "scope"         = "Mail.Send"
        "client_secret" = $env:CLIENT_SECRET
    }

    $tenant_id = $env:TENANT_ID
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


function isLocal{
    # local backup copy: always interactive (confirmation prompts + progress) when run by hand.
    return $true
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

function Get-IntLiteral {
    param([string]$value, [string]$colName, [string]$docId)
    if ([string]::IsNullOrEmpty($value) -or $value -eq 'null') { return 'NULL' }
    $intVal = 0
    if ([int]::TryParse($value, [ref]$intVal)) { return "$intVal" }
    $script:dataQualityIssues.Add([pscustomobject]@{
            DocId  = $docId
            Column = $colName
            Value  = $value
        })
    return 'NULL'
}

if (isLocal) {
    Write-host "Are you sure you want to merge the following $($fullData.count) file(s):"
    $fullData | % { Write-Host "-" $_.BaseName }
    $continue = Read-Host "[Y]es|[N]o"
    if ($continue -ne 'Y') { Write-Host "Aborting Execution" -ForegroundColor Red; Exit }
    Write-host "The script will run on " -NoNewline
    Write-host "INTSQL01" -ForegroundColor Cyan -NoNewline
    Write-host " first; if it completes with no errors or warnings, it will then run on " -NoNewline
    Write-host "PRDSQL01" -ForegroundColor Red -NoNewline
    Write-host ". Continue?"
    $continue = Read-Host "[Y]es|[N]o"
    if ($continue -ne 'Y') { Write-Host "Aborting Execution" -ForegroundColor Red; Exit }
}
Log "Script started: $($fullData.Count) file(s); planned servers: $($serverInstances -join ' -> ')"

foreach ($serverinstance in $serverInstances) {
    Log "=== Starting run on $serverinstance ==="
    $script:abortRun = $false
    $script:runHadWarnings = $false

$fullData | ForEach-Object {
    if ($script:abortRun) { return }
    $csvFilePath = $_.FullName
    $csvFileNameShort = $_.Name
    $batchSize = 500

    $rows = Import-Csv $csvFilePath -Delimiter ";"
    $csvRows = $rows.Count
    $csvRowsInserted = 0
    $valuesList = [System.Collections.Generic.List[string]]::new()

    $insertedTotal = 0
    $updatedTotal = 0
    $minScan = $null
    $maxScan = $null
    $docIdsInBatch = [System.Collections.Generic.List[string]]::new()
    $sapValuesList = [System.Collections.Generic.List[string]]::new()
    $script:lastQuery = $null
    $script:dataQualityIssues = [System.Collections.Generic.List[psobject]]::new()

    $fileEsc = $csvFileNameShort.Replace("'", "''")
    $startQuery = @"
INSERT INTO ImportRuns (FileName, StartedAt, CSVRowCount, RowsInserted, RowsUpdated, [Status])
OUTPUT INSERTED.ID AS NewID
VALUES ('$fileEsc', GETDATE(), $csvRows, 0, 0, 'running');
"@
    $startResult = Invoke-Sqlcmd -ServerInstance $serverinstance -Database $env:DATABASE -TrustServerCertificate -Query $startQuery -ErrorAction Stop
    $importLogID = [int]$startResult.NewID
    Log "Processing '$csvFileNameShort' (rows=$csvRows, import_log_id=$importLogID)"

    function Flush_Batch {
        param($valuesList, $docIdsInBatch, $csvRowsInserted, $csvRows, $sapValuesList)
        $cols = @(
            'ScanCaseId', 'ScanCaseFolderName', 'DocumentId', 'EnvelopeId', 'CaseId', 'CreatedAt',
            'EnvelopeDocumentCount', 'CommunicationTypeId', 'InitialUser', 'InitialScannedAt', 'ScannedAt',
            'DocumentTypeId', 'RecipientId', 'RecipientAddress', 'LanguageId', 'NotificationStatusId',
            'ConfidentialityCode', 'DirectionId', 'DOC_DOKUMENT_ID', 'DocumentOrder', 'DocumentStatusId',
            'InboundChannelId', 'ApplicationNo', 'ApplicationNos', 'PartnerNoSyrius', 'PartnerNoGav',
            'PartnerNoGpv', 'PartnerNoRgi', 'ProductCode', 'Remark', 'ScanLocationId', 'ScanUser',
            'FormNo', 'PersonnelNo', 'PolicyNo', 'PolicyNos', 'ClaimNo', 'ProceedingNo', 'CurrencyId',
            'AmountText', 'CompanyCode', 'QuantityText', 'BusinessType', 'ContactPerson', 'VendorNo',
            'QuoteNo', 'AccountNo', 'Description', 'PendingText', 'VoucherDateText', 'FundName', 'ContractNo',
            'ContractPartner', 'DossierNo', 'ReferenceNo', 'OriginId', 'InterfaceLinkId', 'PostCheck1Id',
            'PostCheck2Id', 'SourceCsvFileName'
        )
        $bracketed = ($cols | ForEach-Object { "[$_]" }) -join ', '
        $updateSet = ($cols | Where-Object { $_ -ne 'DocumentId' } | ForEach-Object { "[$_] = s.[$_]" }) -join ",`n            "
        $insertVals = ($cols | ForEach-Object { "s.[$_]" }) -join ', '
        $query = @"
DECLARE @actions TABLE([action] NVARCHAR(10));
WITH src AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY [DocumentId] ORDER BY (SELECT NULL)) AS rn
    FROM (VALUES
$($valuesList -join ",`n")
    ) AS v ($bracketed)
)
MERGE INTO Documents AS t
USING (SELECT $bracketed FROM src WHERE rn = 1 OR [DocumentId] IS NULL) AS s
ON t.[DocumentId] = s.[DocumentId]
WHEN MATCHED THEN
    UPDATE SET
        $updateSet
WHEN NOT MATCHED THEN
    INSERT ($bracketed)
    VALUES ($insertVals)
OUTPUT `$action INTO @actions([action]);

SELECT
    ISNULL(SUM(CASE WHEN [action] = 'INSERT' THEN 1 ELSE 0 END), 0) AS Inserted,
    ISNULL(SUM(CASE WHEN [action] = 'UPDATE' THEN 1 ELSE 0 END), 0) AS Updated
FROM @actions;
"@
        $script:lastQuery = $query
        $batchResult = Invoke-Sqlcmd -ServerInstance $serverinstance -Database $env:DATABASE -TrustServerCertificate -Query $query -ErrorAction Stop

        # dbo.DocumentSapMetadata is 1:1 with Documents and carries the six SAP
        # fields that used to sit in the main table (#220 phase 4). Runs after
        # the MERGE above, so every row it joins to already exists. Same rn = 1
        # dedupe as the main statement: a CSV may repeat a DOC_ID and MERGE
        # refuses to touch the same target row twice.
        if ($sapValuesList.Count -gt 0) {
            $sapQuery = @"
MERGE INTO DocumentSapMetadata AS t
USING (
    SELECT d.Id AS DocumentRecordId, s.SapComponents, s.SapComponentSize, s.SapContentType,
           s.SapDocumentId, s.SapDocumentProtection, s.SapType
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY [DocumentId] ORDER BY (SELECT NULL)) AS rn
        FROM (VALUES
$($sapValuesList -join ",`n")
        ) AS v ([DocumentId], [SapComponents], [SapComponentSize], [SapContentType],
                [SapDocumentId], [SapDocumentProtection], [SapType])
    ) AS s
    JOIN Documents d ON d.DocumentId = s.[DocumentId]
    WHERE s.rn = 1
) AS src
ON t.DocumentRecordId = src.DocumentRecordId
WHEN MATCHED THEN
    UPDATE SET SapComponents         = src.SapComponents,
               SapComponentSize      = src.SapComponentSize,
               SapContentType        = src.SapContentType,
               SapDocumentId         = src.SapDocumentId,
               SapDocumentProtection = src.SapDocumentProtection,
               SapType               = src.SapType
WHEN NOT MATCHED THEN
    INSERT (DocumentRecordId, SapComponents, SapComponentSize, SapContentType,
            SapDocumentId, SapDocumentProtection, SapType)
    VALUES (src.DocumentRecordId, src.SapComponents, src.SapComponentSize, src.SapContentType,
            src.SapDocumentId, src.SapDocumentProtection, src.SapType);
"@
            Invoke-Sqlcmd -ServerInstance $serverinstance -Database $env:DATABASE -TrustServerCertificate -Query $sapQuery -ErrorAction Stop | Out-Null
            $sapValuesList.Clear()
        }
        $valuesList.Clear()
        $docIdsInBatch.Clear()
        return @{
            Inserted = [int]$batchResult.Inserted
            Updated  = [int]$batchResult.Updated
            Query    = $query
        }
    }

    try {
        foreach ($row in $rows) {
            $DOC_DateCreated = $row.DOC_DateCreated -ne 'null' ? [datetime]::ParseExact($row.DOC_DateCreated, [string[]]@('dd.MM.yyyy HH:mm', 'dd.MM.yyyy HH:mm:ss'), $null, [System.Globalization.DateTimeStyles]::None).ToString("yyyy-MM-dd HH:mm:ss") : ''
            $DOC_SCANDATUM = $row.DOC_SCANDATUM -ne 'null' ? [datetime]::ParseExact($row.DOC_SCANDATUM, [string[]]@('dd.MM.yyyy HH:mm', 'dd.MM.yyyy HH:mm:ss'), $null, [System.Globalization.DateTimeStyles]::None).ToString("yyyy-MM-dd HH:mm:ss") : ''
            $DOC_SCANDATUM_INITIAL = $row.DOC_SCANDATUM_INITIAL -ne 'null' ? [datetime]::ParseExact($row.DOC_SCANDATUM_INITIAL, [string[]]@('dd.MM.yyyy HH:mm', 'dd.MM.yyyy HH:mm:ss'), $null, [System.Globalization.DateTimeStyles]::None).ToString("yyyy-MM-dd HH:mm:ss") : ''

            if ($DOC_SCANDATUM -ne '') {
                try {
                    $sd = [datetime]::ParseExact($DOC_SCANDATUM, 'yyyy-MM-dd HH:mm:ss', $null)
                    if ($null -eq $minScan -or $sd -lt $minScan) { $minScan = $sd }
                    if ($null -eq $maxScan -or $sd -gt $maxScan) { $maxScan = $sd }
                }
                catch {}
            }

            $values = @"
(
        $($row.CASE_ID -eq 'null' ? 'NULL' : "'$($row.CASE_ID.Replace("'","''"))'"),
        $($row.CASE_FOLDERNAME -eq 'null' ? 'NULL' : "'$($row.CASE_FOLDERNAME.Replace("'","''"))'"),
        $($row.DOC_ID -eq 'null' ? 'NULL' : "'$($row.DOC_ID.Replace("'","''"))'"),
        $($row.DOC_COUVERT_ID -eq 'null' ? 'NULL' : "'$($row.DOC_COUVERT_ID.Replace("'","''"))'"),
        $($row.DOC_CASE_ID -eq 'null' ? 'NULL' : "'$($row.DOC_CASE_ID.Replace("'","''"))'"),
        $($DOC_DateCreated -eq '' ? 'NULL' : "'$DOC_DateCreated'"),
        $(Get-IntLiteral $row.DOC_COUVERTDOCCOUNT 'DOC_COUVERTDOCCOUNT' $row.DOC_ID),
        $(Get-IntLiteral $row.DOC_KOMMUNIKATION 'DOC_KOMMUNIKATION' $row.DOC_ID),
        $($row.DOC_INITIAL_USER -eq 'null' ? 'NULL' : "'$($row.DOC_INITIAL_USER.Replace("'","''"))'"),
        $($DOC_SCANDATUM_INITIAL -eq '' ? 'NULL' : "'$DOC_SCANDATUM_INITIAL'"),
        $($DOC_SCANDATUM -eq '' ? 'NULL' : "'$DOC_SCANDATUM'"),
        $(Get-IntLiteral $row.DOC_DOKUMENTENTYP 'DOC_DOKUMENTENTYP' $row.DOC_ID),
        $(Get-IntLiteral $row.DOC_EMPFAENGER 'DOC_EMPFAENGER' $row.DOC_ID),
        $($row.DOC_EMPFAENGERADRESSE -eq 'null' ? 'NULL' : "'$($row.DOC_EMPFAENGERADRESSE.Replace("'","''"))'"),
        $(Get-IntLiteral $row.DOC_SPRACHE 'DOC_SPRACHE' $row.DOC_ID),
        $(Get-IntLiteral $row.DOC_NOTIFIKATIONSSTATUS 'DOC_NOTIFIKATIONSSTATUS' $row.DOC_ID),
        $($row.DOC_VERTRAULICHKEIT -eq 'null' ? 'NULL' : "'$($row.DOC_VERTRAULICHKEIT.Replace("'","''"))'"),
        $(Get-IntLiteral $row.DOC_RICHTUNG 'DOC_RICHTUNG' $row.DOC_ID),
        $($row.DOC_DOKUMENT_ID -eq 'null' ? 'NULL' : "'$($row.DOC_DOKUMENT_ID.Replace("'","''"))'"),
        $($row.DOC_DOKUMENTENORDER -eq 'null' ? 'NULL' : "'$($row.DOC_DOKUMENTENORDER.Replace("'","''"))'"),
        $(Get-IntLiteral $row.DOC_DOKUMENTENSTATUS 'DOC_DOKUMENTENSTATUS' $row.DOC_ID),
        $(Get-IntLiteral $row.DOC_EINGANGSKANAL 'DOC_EINGANGSKANAL' $row.DOC_ID),
        $($row.DOC_ANTRAG_NR -eq 'null' ? 'NULL' : "'$($row.DOC_ANTRAG_NR.Replace("'","''"))'"),
        $($row.DOC_ANTRAG_NR_MULTI -eq 'null' ? 'NULL' : "'$($row.DOC_ANTRAG_NR_MULTI.Replace("'","''"))'"),
        $($row.DOC_PARTNER_NR_SYRIUS -eq 'null' ? 'NULL' : "'$($row.DOC_PARTNER_NR_SYRIUS.Replace("'","''"))'"),
        $($row.DOC_PARTNER_NR_GAV -eq 'null' ? 'NULL' : "'$($row.DOC_PARTNER_NR_GAV.Replace("'","''"))'"),
        $($row.DOC_PARTNER_NR_GPV -eq 'null' ? 'NULL' : "'$($row.DOC_PARTNER_NR_GPV.Replace("'","''"))'"),
        $($row.DOC_PARTNER_NR_RGI -eq 'null' ? 'NULL' : "'$($row.DOC_PARTNER_NR_RGI.Replace("'","''"))'"),
        $($row.DOC_PRODUKT_CODE -eq 'null' ? 'NULL' : "'$($row.DOC_PRODUKT_CODE.Replace("'","''"))'"),
        $($row.DOC_BEMERKUNG -eq 'null' ? 'NULL' : "'$($row.DOC_BEMERKUNG.Replace("'","''"))'"),
        $(Get-IntLiteral $row.DOC_SCANORT 'DOC_SCANORT' $row.DOC_ID),
        $($row.DOC_SCANUSER -eq 'null' ? 'NULL' : "'$($row.DOC_SCANUSER.Replace("'","''"))'"),
        $($row.DOC_FORMULAR_NR -eq 'null' ? 'NULL' : "'$($row.DOC_FORMULAR_NR.Replace("'","''"))'"),
        $($row.DOC_PERSONAL_NR -eq 'null' ? 'NULL' : "'$($row.DOC_PERSONAL_NR.Replace("'","''"))'"),
        $($row.DOC_POLICEN_NR -eq 'null' ? 'NULL' : "'$($row.DOC_POLICEN_NR.Replace("'","''"))'"),
        $($row.DOC_POLICEN_NR_MULTI -eq 'null' ? 'NULL' : "'$($row.DOC_POLICEN_NR_MULTI.Replace("'","''"))'"),
        $($row.DOC_SCHADEN_NR -eq 'null' ? 'NULL' : "'$($row.DOC_SCHADEN_NR.Replace("'","''"))'"),
        $($row.DOC_VERFAHREN_NR -eq 'null' ? 'NULL' : "'$($row.DOC_VERFAHREN_NR.Replace("'","''"))'"),
        $(Get-IntLiteral $row.DOC_WAEHRUNG 'DOC_WAEHRUNG' $row.DOC_ID),
        $($row.DOC_BETRAG -eq 'null' ? 'NULL' : "'$($row.DOC_BETRAG.Replace("'","''"))'"),
        $($row.DOC_BUCHUNGSKREIS_NR -eq 'null' ? 'NULL' : "'$($row.DOC_BUCHUNGSKREIS_NR.Replace("'","''"))'"),
        $($row.DOC_ANZAHL -eq 'null' ? 'NULL' : "'$($row.DOC_ANZAHL.Replace("'","''"))'"),
        $($row.DOC_GESCHAEFTSART -eq 'null' ? 'NULL' : "'$($row.DOC_GESCHAEFTSART.Replace("'","''"))'"),
        $($row.DOC_KONTAKTPERSON -eq 'null' ? 'NULL' : "'$($row.DOC_KONTAKTPERSON.Replace("'","''"))'"),
        $($row.DOC_KREDITOREN_NR -eq 'null' ? 'NULL' : "'$($row.DOC_KREDITOREN_NR.Replace("'","''"))'"),
        $($row.DOC_OFFERTEN_NR -eq 'null' ? 'NULL' : "'$($row.DOC_OFFERTEN_NR.Replace("'","''"))'"),
        $($row.DOC_KONTONUMMER -eq 'null' ? 'NULL' : "'$($row.DOC_KONTONUMMER.Replace("'","''"))'"),
        $($row.DOC_BEZEICHNUNG -eq 'null' ? 'NULL' : "'$($row.DOC_BEZEICHNUNG.Replace("'","''"))'"),
        $($row.DOC_PENDING -eq 'null' ? 'NULL' : "'$($row.DOC_PENDING.Replace("'","''"))'"),
        $($row.DOC_BELEGDATUM -eq 'null' ? 'NULL' : "'$($row.DOC_BELEGDATUM.Replace("'","''"))'"),
        $($row.DOC_FONDSNAME -eq 'null' ? 'NULL' : "'$($row.DOC_FONDSNAME.Replace("'","''"))'"),
        $($row.DOC_VERTRAGSNUMMER -eq 'null' ? 'NULL' : "'$($row.DOC_VERTRAGSNUMMER.Replace("'","''"))'"),
        $($row.DOC_VERTRAGSPARTNER -eq 'null' ? 'NULL' : "'$($row.DOC_VERTRAGSPARTNER.Replace("'","''"))'"),
        $($row.DOC_DOSSIER_NR -eq 'null' ? 'NULL' : "'$($row.DOC_DOSSIER_NR.Replace("'","''"))'"),
        $($row.DOC_REFERENZNUMMER -eq 'null' ? 'NULL' : "'$($row.DOC_REFERENZNUMMER.Replace("'","''"))'"),
        $(Get-IntLiteral $row.DOC_ORIGIN 'DOC_ORIGIN' $row.DOC_ID),
        $(Get-IntLiteral $row.DOC_INTERFACE_LINK 'DOC_INTERFACE_LINK' $row.DOC_ID),
        $(Get-IntLiteral $row.DOC_NK1 'DOC_NK1' $row.DOC_ID),
        $(Get-IntLiteral $row.DOC_NK2 'DOC_NK2' $row.DOC_ID),
        '$fileEsc'
)
"@

            # SAP metadata goes to its own table now; only rows that carry any.
            if ($row.DOC_SAPComps -ne 'null' -or $row.DOC_SAPCompSize -ne 'null' -or
                $row.DOC_SAPContType -ne 'null' -or $row.DOC_SAPDocId -ne 'null' -or
                $row.DOC_SAPDocProt -ne 'null' -or $row.DOC_SAPType -ne 'null') {
                $sapValuesList.Add(@"
(
        $($row.DOC_ID -eq 'null' ? 'NULL' : "'$($row.DOC_ID.Replace("'","''"))'"),
        $($row.DOC_SAPComps -eq 'null' ? 'NULL' : "'$($row.DOC_SAPComps.Replace("'","''"))'"),
        $($row.DOC_SAPCompSize -eq 'null' ? 'NULL' : "'$($row.DOC_SAPCompSize.Replace("'","''"))'"),
        $($row.DOC_SAPContType -eq 'null' ? 'NULL' : "'$($row.DOC_SAPContType.Replace("'","''"))'"),
        $($row.DOC_SAPDocId -eq 'null' ? 'NULL' : "'$($row.DOC_SAPDocId.Replace("'","''"))'"),
        $($row.DOC_SAPDocProt -eq 'null' ? 'NULL' : "'$($row.DOC_SAPDocProt.Replace("'","''"))'"),
        $($row.DOC_SAPType -eq 'null' ? 'NULL' : "'$($row.DOC_SAPType.Replace("'","''"))'")
)
"@)
            }
            $valuesList.Add($values)
            $docIdsInBatch.Add($row.DOC_ID)
            $csvRowsInserted++
            if (isLocal){
                Write-Host "`r$($csvFileNameShort):[$([math]::Round(($csvRowsInserted / $csvRows * 100), 1))%] Inserting row $csvRowsInserted / $csvRows..." -NoNewline -ForegroundColor Green
            }

            if ($valuesList.Count -ge $batchSize) {
                $stats = Flush_Batch $valuesList $docIdsInBatch $csvRowsInserted $csvRows $sapValuesList
                $insertedTotal += $stats.Inserted
                $updatedTotal += $stats.Updated
            }

        }

        if ($valuesList.Count -gt 0) {
            $stats = Flush_Batch $valuesList $docIdsInBatch $csvRowsInserted $csvRows $sapValuesList
            $insertedTotal += $stats.Inserted
            $updatedTotal += $stats.Updated
        }

        # log success
        $minScanSql = if ($null -eq $minScan) { 'NULL' } else { "'$($minScan.ToString('yyyy-MM-dd HH:mm:ss'))'" }
        $maxScanSql = if ($null -eq $maxScan) { 'NULL' } else { "'$($maxScan.ToString('yyyy-MM-dd HH:mm:ss'))'" }
        $endQuery = @"
UPDATE ImportRuns SET
    FinishedAt = GETDATE(),
    RowsInserted = $insertedTotal,
    RowsUpdated  = $updatedTotal,
    MinScannedAt = $minScanSql,
    MaxScannedAt = $maxScanSql,
    [Status] = 'success'
WHERE ID = $importLogID;
"@
        $script:lastQuery = $endQuery
        Invoke-Sqlcmd -ServerInstance $serverinstance -Database $env:DATABASE -TrustServerCertificate -Query $endQuery -ErrorAction Stop
    }
    catch {
        Log "Insert interrupted due to an Error in '$csvFileNameShort' - see '$logFile' for full details" 'ERROR'

        $sep = '=' * 80
        @(
            ''
            $sep
            "Import error in $csvFileNameShort"
            "Time:           $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
            "Progress:       $csvRowsInserted / $csvRows rows enqueued from CSV"
            "Failing batch:  $($docIdsInBatch.Count) row(s) in the batch that was being flushed"
            "Inserted/Updated so far: $insertedTotal / $updatedTotal"
            "Import log ID:  $importLogID"
            $sep
            ''
            '----- Error -----'
        ) | Out-File $logFile -Append
        $_ | Out-File $logFile -Append

        if ($docIdsInBatch.Count -gt 0) {
            @(
                ''
                "----- DOC_IDs in failing batch ($($docIdsInBatch.Count) row(s)) -----"
                '(grep these IDs in the source CSV to inspect the offending rows)'
            ) | Out-File $logFile -Append
            $docIdsInBatch | Out-File $logFile -Append
        }

        if ($null -ne $script:lastQuery) {
            @(
                ''
                '----- Failing SQL (last query attempted) -----'
            ) | Out-File $logFile -Append
            $script:lastQuery | Out-File $logFile -Append
        }

        if ($script:dataQualityIssues.Count -gt 0) {
            @(
                ''
                "----- Data quality warnings ($($script:dataQualityIssues.Count) value(s) sanitized to NULL before failure) -----"
            ) | Out-File $logFile -Append
            $script:dataQualityIssues | Format-Table -AutoSize | Out-String | Out-File $logFile -Append
        }

        $failQuery = @"
UPDATE ImportRuns SET
    FinishedAt = GETDATE(),
    RowsInserted = $insertedTotal,
    RowsUpdated  = $updatedTotal,
    [Status] = 'failed'
WHERE ID = $importLogID;
"@
        try { Invoke-Sqlcmd -ServerInstance $serverinstance -Database $env:DATABASE -TrustServerCertificate -Query $failQuery } catch {}

        $errorText = ($_ | Out-String).Trim()
        if ($_.ScriptStackTrace) { $errorText += "`n`nStack trace:`n" + $_.ScriptStackTrace }
        $docIdsText = if ($docIdsInBatch.Count -gt 0) { ($docIdsInBatch -join "`n") } else { '' }
        $dqText = if ($script:dataQualityIssues.Count -gt 0) { ($script:dataQualityIssues | Format-Table -AutoSize | Out-String).Trim() } else { '' }
        $body_html = @"
<h2>Generali CSV import &mdash; error in $csvFileNameShort</h2>
<p><b>Time:</b> $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
<p><b>Host:</b> $env:COMPUTERNAME</p>
<p><b>File:</b> $csvFileNameShort</p>
<p><b>Progress:</b> $csvRowsInserted / $csvRows rows enqueued from CSV</p>
<p><b>Failing batch:</b> $($docIdsInBatch.Count) row(s)</p>
<p><b>Inserted/Updated so far:</b> $insertedTotal / $updatedTotal</p>
<p><b>Import log ID:</b> $importLogID</p>
<h3>Error</h3>
<pre>$([System.Net.WebUtility]::HtmlEncode($errorText))</pre>
$(if ($docIdsText) { "<h3>DOC_IDs in failing batch ($($docIdsInBatch.Count))</h3><pre>$([System.Net.WebUtility]::HtmlEncode($docIdsText))</pre>" })
$(if ($script:lastQuery) { "<h3>Failing SQL (last query attempted)</h3><pre>$([System.Net.WebUtility]::HtmlEncode($script:lastQuery))</pre>" })
$(if ($dqText) { "<h3>Data quality warnings ($($script:dataQualityIssues.Count))</h3><pre>$([System.Net.WebUtility]::HtmlEncode($dqText))</pre>" })
<p>Full details written to <code>$logFile</code> on the import host.</p>
"@
        try { send_email_graphAPI "Generali CSV import - error in $csvFileNameShort" }
        catch { Write-Host "Failed to send error notification email: $_" -ForegroundColor Yellow }

        $script:abortRun = $true
        return
    }

    if ($script:dataQualityIssues.Count -gt 0) {
        $script:runHadWarnings = $true
        $sep = '=' * 80
        @(
            ''
            $sep
            "DATA QUALITY WARNINGS in $csvFileNameShort"
            "Time:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
            "Count: $($script:dataQualityIssues.Count) non-numeric value(s) sanitized to NULL in INT column(s)"
            $sep
        ) | Out-File $logFile -Append
        $script:dataQualityIssues | Format-Table -AutoSize | Out-String | Out-File $logFile -Append
        Log "$($script:dataQualityIssues.Count) non-numeric value(s) in INT columns sanitized to NULL in '$csvFileNameShort' - see '$logFile' for details" 'WARN'
    }

    Write-Host "`rDone! Inserted $csvRowsInserted / $csvRows rows. (new: $insertedTotal, updated: $updatedTotal)" -ForegroundColor Green
    Log "Done with '$csvFileNameShort': inserted=$insertedTotal updated=$updatedTotal rows=$csvRowsInserted/$csvRows"
    if ($serverinstance -like 'INT*') { Copy-Item -Path $csvFilePath -Destination "$datafoldergen/doneINT" -Force }
    else {
        Move-item -Path $csvFilePath -Destination "$datafoldergen/donePROD" -Force
    }
}

    if ($script:abortRun) {
        Log "=== Aborted: errors during '$serverinstance' run; skipping further servers ===" 'ERROR'
        break
    }
    if ($script:runHadWarnings) {
        Log "=== Stopping: warnings during '$serverinstance' run; skipping further servers ===" 'WARN'
        break
    }
    Log "=== Completed '$serverinstance' run ==="
}
