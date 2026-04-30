$datafoldergen = "C:\Users\bes\OneDrive - TCG Informatik AG\Desktop\gen"
Get-ChildItem $datafoldergen -File | ForEach-Object {

$csvFilePath = $_.FullName
$csvFileNameShort = $_.Name
$batchSize = 500
$envVars = Get-Content -Raw "env.json" | ConvertFrom-Json

$rows = Import-Csv $csvFilePath -Delimiter ";"
$csvRows = $rows.Count
$csvRowsInserted = 0
$valuesList = [System.Collections.Generic.List[string]]::new()

function Flush_Batch {
    param($valuesList, $csvRowsInserted, $csvRows)
    try{
        $query = @"
        INSERT INTO reportjob
        ([CASE_ID]
      ,[CASE_FOLDERNAME]
      ,[DOC_ID]
      ,[DOC_COUVERT_ID]
      ,[DOC_CASE_ID]
      ,[DOC_JOURNAL_ID]
      ,[DOC_DateCreated]
      ,[DOC_COUVERTDOCCOUNT]
      ,[DOC_KOMMUNIKATION]
      ,[DOC_INITIAL_USER]
      ,[DOC_SCANDATUM_INITIAL]
      ,[DOC_SCANDATUM]
      ,[DOC_DOKUMENTENTYP]
      ,[DOC_EMPFAENGER]
      ,[DOC_EMPFAENGERADRESSE]
      ,[DOC_SPRACHE]
      ,[DOC_NOTIFIKATIONSSTATUS]
      ,[DOC_VERTRAULICHKEIT]
      ,[DOC_RICHTUNG]
      ,[DOC_DOKUMENT_ID]
      ,[DOC_DOKUMENTENORDER]
      ,[DOC_DOKUMENTENSTATUS]
      ,[DOC_DOKUMENT_URL]
      ,[DOC_EINGANGSKANAL]
      ,[DOC_ANTRAG_NR]
      ,[DOC_ANTRAG_NR_MULTI]
      ,[DOC_PARTNER_NR_SYRIUS]
      ,[DOC_PARTNER_NR_GAV]
      ,[DOC_PARTNER_NR_GPV]
      ,[DOC_PARTNER_NR_RGI]
      ,[DOC_PRODUKT_CODE]
      ,[DOC_BEMERKUNG]
      ,[DOC_SCANORT]
      ,[DOC_SCANUSER]
      ,[DOC_FORMULAR_NR]
      ,[DOC_PERSONAL_NR]
      ,[DOC_POLICEN_NR]
      ,[DOC_POLICEN_NR_MULTI]
      ,[DOC_SCHADEN_NR]
      ,[DOC_VERFAHREN_NR]
      ,[DOC_WAEHRUNG]
      ,[DOC_BETRAG]
      ,[DOC_BUCHUNGSKREIS_NR]
      ,[DOC_ANZAHL]
      ,[DOC_GESCHAEFTSART]
      ,[DOC_KONTAKTPERSON]
      ,[DOC_KREDITOREN_NR]
      ,[DOC_OFFERTEN_NR]
      ,[DOC_KONTONUMMER]
      ,[DOC_BEZEICHNUNG]
      ,[DOC_PENDING]
      ,[DOC_ALFdpages]
      ,[DOC_ALFpages]
      ,[DOC_PageSize]
      ,[DOC_SAPCompCharset]
      ,[DOC_SAPCompCreated]
      ,[DOC_SAPCompModified]
      ,[DOC_SAPComps]
      ,[DOC_SAPCompSize]
      ,[DOC_SAPCompVersion]
      ,[DOC_SAPContType]
      ,[DOC_SAPDocDate]
      ,[DOC_SAPDocId]
      ,[DOC_SAPDocProt]
      ,[DOC_SAPType]
      ,[DOC_BARCODENR]
      ,[DOC_BELEGDATUM]
      ,[DOC_FONDSNAME]
      ,[DOC_VERTRAGSNUMMER]
      ,[DOC_VERTRAGSPARTNER]
      ,[DOC_DOSSIER_NR]
      ,[DOC_REFERENZNUMMER]
      ,[DOC_ORIGIN]
      ,[DOC_INTERFACE_LINK]
      ,[DOC_NK1]
      ,[DOC_NK2],
      SourceCSVFileName)
        VALUES`n
"@ + ($valuesList -join ",`n")
        Invoke-Sqlcmd -ServerInstance $envVars.SERVERINSTANCE -Database $envVars.DATABASE -TrustServerCertificate -Query $query -ErrorAction Stop
        $valuesList.Clear()
    }
    catch{
        Write-Host "Insert interrupted due to an Error. See 'error.log' for further Information" -NoNewline -ForegroundColor Red
        $query | Out-File "error.log"
        $Error[0] | Out-File "error.log" -Append
        exit
    }
}

foreach ($row in $rows) {
        $DOC_DateCreated = $row.DOC_DateCreated -ne 'null' ? [datetime]::ParseExact($row.DOC_DateCreated, [string[]]@('dd.MM.yyyy HH:mm', 'dd.MM.yyyy HH:mm:ss'), $null, [System.Globalization.DateTimeStyles]::None).ToString("yyyy-MM-dd HH:mm:ss") : ''
        $DOC_SCANDATUM = $row.DOC_SCANDATUM -ne 'null' ? [datetime]::ParseExact($row.DOC_SCANDATUM, [string[]]@('dd.MM.yyyy HH:mm', 'dd.MM.yyyy HH:mm:ss'), $null, [System.Globalization.DateTimeStyles]::None).ToString("yyyy-MM-dd HH:mm:ss") : ''
        $DOC_SCANDATUM_INITIAL = $row.DOC_SCANDATUM_INITIAL -ne 'null' ? [datetime]::ParseExact($row.DOC_SCANDATUM_INITIAL, [string[]]@('dd.MM.yyyy HH:mm', 'dd.MM.yyyy HH:mm:ss'), $null, [System.Globalization.DateTimeStyles]::None).ToString("yyyy-MM-dd HH:mm:ss") : ''
        $DOC_SAPCompCreated = ''
        if ($row.DOC_SAPCompCreated -ne 'null') {
            try { $DOC_SAPCompCreated = [datetime]::ParseExact(($row.DOC_SAPCompCreated -split '00')[0], 'yyyyMM', $null).ToString("yyyy-MM-dd") } catch {}
        }
        $DOC_SAPCompModified = ''
        if ($row.DOC_SAPCompModified -ne 'null') {
            try { $DOC_SAPCompModified = [datetime]::ParseExact(($row.DOC_SAPCompModified -split '00')[0], 'yyyyMM', $null).ToString("yyyy-MM-dd") } catch {}
        }
        $DOC_SAPDocDate = ''
        if ($row.DOC_SAPDocDate -ne 'null') {
            try { $DOC_SAPDocDate = [datetime]::ParseExact(($row.DOC_SAPDocDate -split '00')[0], 'yyyyMM', $null).ToString("yyyy-MM-dd") } catch {}
        }

        $values = @"
(
        $($row.CASE_ID -eq 'null' ? 'NULL' : "'$($row.CASE_ID.Replace("'","''"))'"),
        $($row.CASE_FOLDERNAME -eq 'null' ? 'NULL' : "'$($row.CASE_FOLDERNAME.Replace("'","''"))'"),
        $($row.DOC_ID -eq 'null' ? 'NULL' : "'$($row.DOC_ID.Replace("'","''"))'"),
        $($row.DOC_COUVERT_ID -eq 'null' ? 'NULL' : "'$($row.DOC_COUVERT_ID.Replace("'","''"))'"),
        $($row.DOC_CASE_ID -eq 'null' ? 'NULL' : "'$($row.DOC_CASE_ID.Replace("'","''"))'"),
        $($row.DOC_JOURNAL_ID -eq 'null' ? 'NULL' : "'$($row.DOC_JOURNAL_ID.Replace("'","''"))'"),
        $($DOC_DateCreated -eq '' ? 'NULL' : "'$DOC_DateCreated'"),
        $($row.DOC_COUVERTDOCCOUNT -eq 'null' ? 'NULL' : "'$($row.DOC_COUVERTDOCCOUNT.Replace("'","''"))'"),
        $($row.DOC_KOMMUNIKATION -in @('null','') ? 'NULL' : "'$($row.DOC_KOMMUNIKATION.Replace("'","''"))'"),
        $($row.DOC_INITIAL_USER -eq 'null' ? 'NULL' : "'$($row.DOC_INITIAL_USER.Replace("'","''"))'"),
        $($DOC_SCANDATUM_INITIAL -eq '' ? 'NULL' : "'$DOC_SCANDATUM_INITIAL'"),
        $($DOC_SCANDATUM -eq '' ? 'NULL' : "'$DOC_SCANDATUM'"),
        $($row.DOC_DOKUMENTENTYP -in @('null','') ? 'NULL' : "'$($row.DOC_DOKUMENTENTYP.Replace("'","''"))'"),
        $($row.DOC_EMPFAENGER -in @('null','') ? 'NULL' : "'$($row.DOC_EMPFAENGER.Replace("'","''"))'"),
        $($row.DOC_EMPFAENGERADRESSE -eq 'null' ? 'NULL' : "'$($row.DOC_EMPFAENGERADRESSE.Replace("'","''"))'"),
        $($row.DOC_SPRACHE -in @('null','') ? 'NULL' : "'$($row.DOC_SPRACHE.Replace("'","''"))'"),
        $($row.DOC_NOTIFIKATIONSSTATUS -in @('null','') ? 'NULL' : "'$($row.DOC_NOTIFIKATIONSSTATUS.Replace("'","''"))'"),
        $($row.DOC_VERTRAULICHKEIT -eq 'null' ? 'NULL' : "'$($row.DOC_VERTRAULICHKEIT.Replace("'","''"))'"),
        $($row.DOC_RICHTUNG -in @('null','') ? 'NULL' : "'$($row.DOC_RICHTUNG.Replace("'","''"))'"),
        $($row.DOC_DOKUMENT_ID -eq 'null' ? 'NULL' : "'$($row.DOC_DOKUMENT_ID.Replace("'","''"))'"),
        $($row.DOC_DOKUMENTENORDER -eq 'null' ? 'NULL' : "'$($row.DOC_DOKUMENTENORDER.Replace("'","''"))'"),
        $($row.DOC_DOKUMENTENSTATUS -in @('null','') ? 'NULL' : "'$($row.DOC_DOKUMENTENSTATUS.Replace("'","''"))'"),
        $($row.DOC_DOKUMENT_URL -eq 'null' ? 'NULL' : "'$($row.DOC_DOKUMENT_URL.Replace("'","''"))'"),
        $($row.DOC_EINGANGSKANAL -in @('null','') ? 'NULL' : "'$($row.DOC_EINGANGSKANAL.Replace("'","''"))'"),
        $($row.DOC_ANTRAG_NR -eq 'null' ? 'NULL' : "'$($row.DOC_ANTRAG_NR.Replace("'","''"))'"),
        $($row.DOC_ANTRAG_NR_MULTI -eq 'null' ? 'NULL' : "'$($row.DOC_ANTRAG_NR_MULTI.Replace("'","''"))'"),
        $($row.DOC_PARTNER_NR_SYRIUS -eq 'null' ? 'NULL' : "'$($row.DOC_PARTNER_NR_SYRIUS.Replace("'","''"))'"),
        $($row.DOC_PARTNER_NR_GAV -eq 'null' ? 'NULL' : "'$($row.DOC_PARTNER_NR_GAV.Replace("'","''"))'"),
        $($row.DOC_PARTNER_NR_GPV -eq 'null' ? 'NULL' : "'$($row.DOC_PARTNER_NR_GPV.Replace("'","''"))'"),
        $($row.DOC_PARTNER_NR_RGI -eq 'null' ? 'NULL' : "'$($row.DOC_PARTNER_NR_RGI.Replace("'","''"))'"),
        $($row.DOC_PRODUKT_CODE -eq 'null' ? 'NULL' : "'$($row.DOC_PRODUKT_CODE.Replace("'","''"))'"),
        $($row.DOC_BEMERKUNG -eq 'null' ? 'NULL' : "'$($row.DOC_BEMERKUNG.Replace("'","''"))'"),
        $($row.DOC_SCANORT -in @('null','') ? 'NULL' : "'$($row.DOC_SCANORT.Replace("'","''"))'"),
        $($row.DOC_SCANUSER -eq 'null' ? 'NULL' : "'$($row.DOC_SCANUSER.Replace("'","''"))'"),
        $($row.DOC_FORMULAR_NR -eq 'null' ? 'NULL' : "'$($row.DOC_FORMULAR_NR.Replace("'","''"))'"),
        $($row.DOC_PERSONAL_NR -eq 'null' ? 'NULL' : "'$($row.DOC_PERSONAL_NR.Replace("'","''"))'"),
        $($row.DOC_POLICEN_NR -eq 'null' ? 'NULL' : "'$($row.DOC_POLICEN_NR.Replace("'","''"))'"),
        $($row.DOC_POLICEN_NR_MULTI -eq 'null' ? 'NULL' : "'$($row.DOC_POLICEN_NR_MULTI.Replace("'","''"))'"),
        $($row.DOC_SCHADEN_NR -eq 'null' ? 'NULL' : "'$($row.DOC_SCHADEN_NR.Replace("'","''"))'"),
        $($row.DOC_VERFAHREN_NR -eq 'null' ? 'NULL' : "'$($row.DOC_VERFAHREN_NR.Replace("'","''"))'"),
        $($row.DOC_WAEHRUNG -in @('null','') ? 'NULL' : "'$($row.DOC_WAEHRUNG.Replace("'","''"))'"),
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
        $($row.DOC_ALFdpages -eq 'null' ? 'NULL' : "'$($row.DOC_ALFdpages.Replace("'","''"))'"),
        $($row.DOC_ALFpages -eq 'null' ? 'NULL' : "'$($row.DOC_ALFpages.Replace("'","''"))'"),
        $($row.DOC_PageSize -eq 'null' ? 'NULL' : "'$($row.DOC_PageSize.Replace("'","''"))'"),
        $($row.DOC_SAPCompCharset -eq 'null' ? 'NULL' : "'$($row.DOC_SAPCompCharset.Replace("'","''"))'"),
        $($DOC_SAPCompCreated -eq '' ? 'NULL' : "'$DOC_SAPCompCreated'"),
        $($DOC_SAPCompModified -eq '' ? 'NULL' : "'$DOC_SAPCompModified'"),
        $($row.DOC_SAPComps -eq 'null' ? 'NULL' : "'$($row.DOC_SAPComps.Replace("'","''"))'"),
        $($row.DOC_SAPCompSize -eq 'null' ? 'NULL' : "'$($row.DOC_SAPCompSize.Replace("'","''"))'"),
        $($row.DOC_SAPCompVersion -eq 'null' ? 'NULL' : "'$($row.DOC_SAPCompVersion.Replace("'","''"))'"),
        $($row.DOC_SAPContType -eq 'null' ? 'NULL' : "'$($row.DOC_SAPContType.Replace("'","''"))'"),
        $($DOC_SAPDocDate -eq '' ? 'NULL' : "'$DOC_SAPDocDate'"),
        $($row.DOC_SAPDocId -eq 'null' ? 'NULL' : "'$($row.DOC_SAPDocId.Replace("'","''"))'"),
        $($row.DOC_SAPDocProt -eq 'null' ? 'NULL' : "'$($row.DOC_SAPDocProt.Replace("'","''"))'"),
        $($row.DOC_SAPType -eq 'null' ? 'NULL' : "'$($row.DOC_SAPType.Replace("'","''"))'"),
        $($row.DOC_BARCODENR -eq 'null' ? 'NULL' : "'$($row.DOC_BARCODENR.Replace("'","''"))'"),
        $($row.DOC_BELEGDATUM -eq 'null' ? 'NULL' : "'$($row.DOC_BELEGDATUM.Replace("'","''"))'"),
        $($row.DOC_FONDSNAME -eq 'null' ? 'NULL' : "'$($row.DOC_FONDSNAME.Replace("'","''"))'"),
        $($row.DOC_VERTRAGSNUMMER -eq 'null' ? 'NULL' : "'$($row.DOC_VERTRAGSNUMMER.Replace("'","''"))'"),
        $($row.DOC_VERTRAGSPARTNER -eq 'null' ? 'NULL' : "'$($row.DOC_VERTRAGSPARTNER.Replace("'","''"))'"),
        $($row.DOC_DOSSIER_NR -eq 'null' ? 'NULL' : "'$($row.DOC_DOSSIER_NR.Replace("'","''"))'"),
        $($row.DOC_REFERENZNUMMER -eq 'null' ? 'NULL' : "'$($row.DOC_REFERENZNUMMER.Replace("'","''"))'"),
        $($row.DOC_ORIGIN -in @('null','') ? 'NULL' : "'$($row.DOC_ORIGIN.Replace("'","''"))'"),
        $($row.DOC_INTERFACE_LINK -in @('null','') ? 'NULL' : "'$($row.DOC_INTERFACE_LINK.Replace("'","''"))'"),
        $($row.DOC_NK1 -in @('null','') ? 'NULL' : "'$($row.DOC_NK1.Replace("'","''"))'"),
        $($row.DOC_NK2 -in @('null','') ? 'NULL' : "'$($row.DOC_NK2.Replace("'","''"))'"),
        $csvFileNameShort
)
"@
        $valuesList.Add($values)
        $csvRowsInserted++
        Write-Host "`r[$([math]::Round(($csvRowsInserted / $csvRows * 100), 1))%] Inserting row $csvRowsInserted / $csvRows..." -NoNewline -ForegroundColor Yellow

        if ($valuesList.Count -ge $batchSize) {
            Flush_Batch $valuesList $csvRowsInserted $csvRows
        }
    
}

if ($valuesList.Count -gt 0) {
    Flush_Batch $valuesList $csvRowsInserted $csvRows
}
Write-Host "`rDone! Inserted $csvRowsInserted / $csvRows rows." -ForegroundColor Green
if ($envVars.SERVERINSTANCE -like 'INT*'){Copy-Item -Path $csvFilePath -Destination "$datafoldergen/doneINT" -Force}
else{Move-item -Path $csvFilePath -Destination "$datafoldergen/donePROD" -Force
}
}