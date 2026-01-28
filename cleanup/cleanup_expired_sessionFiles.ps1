$sessionFolder = 'D:\sydoc\nexora\session'
Get-ChildItem $sessionFolder | ForEach-Object {
    if ($_.CreationTime -le (Get-Date).AddHours(-4)){
        Remove-Item $_.FullName -Force
    }
}