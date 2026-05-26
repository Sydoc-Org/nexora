$csvPath = (Read-Host "CSV Path").replace('"','').replace("'",'')
$outputPath = (Read-Host "Output Path").replace('"','').replace("'",'')
$data = Import-Csv $csvPath -Delimiter ","
$headers = $data[0].psobject.properties.name 
$countImageHeaders = ($headers | Where-Object {$_ -like "Image*"}).length
$nonImageHeaders = $headers | Where-Object {$_ -notlike "Image*"}
$countNonImageHeaders = $nonImageHeaders.Length
$data | ForEach-Object {
    $workitemDirPath = Join-Path $outputPath $_."Workitem ID"
    New-Item -Path $workitemDirPath -ItemType Directory -Force
    $newDataCsvPath = (Join-Path $_."Workitem ID" "data.csv")
    $_ | Select-Object $nonImageHeaders | Export-Csv $newDataCsvPath -NoTypeInformation
    for($i = 1; $i -le $countImageHeaders; $i++)
    {
        [IO.File]::WriteAllBytes((Join-Path $workitemDirPath "Image_$i.jpg"), [Convert]::FromBase64String($_."Image $i (base64)"));
    }
}