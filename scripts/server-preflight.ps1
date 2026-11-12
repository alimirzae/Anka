#Requires -RunAsAdministrator
# Safe, non-destructive preflight only: DOES NOT configure MySQL or deploy.
$ErrorActionPreference = "Stop"
Write-Host "=== Anka server preflight ==="
$exe = "C:\Program Files\dotnet\dotnet.exe"
if (-not (Test-Path $exe)) { throw ".NET SDK is missing" }
& $exe --list-sdks
Import-Module WebAdministration
$site = Get-Website -Name "anka.iyashil.com"
if (-not $site) { throw "IIS site not found" }
if ([IO.Path]::GetFullPath($site.physicalPath).TrimEnd('\') -ine "C:\inetpub\anka.iyashil.com") {
    throw "IIS physical path is not the expected Anka folder"
}
Write-Host "IIS site: $($site.Name) / $($site.State)"
Get-Service -Name "actions.runner.*" | Format-Table Name,Status -AutoSize
if (-not (Test-Path "C:\inetpub\anka.iyashil.com\appsettings.Production.json")) {
    Write-Warning "No production settings file. Configure database before deployment."
}
Write-Host "Endpoint: https://anka.iyashil.com/api/health"
