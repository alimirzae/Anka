#Requires -RunAsAdministrator
<#
  Anka IIS + SQLite permissions (run once in elevated Windows PowerShell).
  Scoped to Anka only. Does not touch test.iyashil.com or app.iyashil.com.
#>
$ErrorActionPreference = 'Stop'
Import-Module WebAdministration
$siteName = 'anka.iyashil.com'
$sitePath = 'C:\inetpub\anka.iyashil.com'
$site = Get-Website -Name $siteName -ErrorAction Stop
if ([IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($site.PhysicalPath)).TrimEnd('\') -ine $sitePath) {
  throw "Unexpected Anka site path: $($site.PhysicalPath)"
}
$poolName = $site.ApplicationPool
if (-not (Test-Path "IIS:\AppPools\$poolName")) { throw "Missing app pool: $poolName" }

# Isolate the application process with the built-in application pool identity.
Set-ItemProperty "IIS:\AppPools\$poolName" -Name managedRuntimeVersion -Value ''
Set-ItemProperty "IIS:\AppPools\$poolName" -Name processModel.identityType -Value 'ApplicationPoolIdentity'
New-Item -ItemType Directory -Force -Path $sitePath | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $sitePath 'App_Data\epubs') | Out-Null

# Full Control ONLY for this IIS application pool on this site's directory.
# Runner runs as NETWORK SERVICE and needs Modify to publish files.
$poolAccount = "IIS AppPool\$poolName"
& icacls.exe $sitePath /grant "${poolAccount}:(OI)(CI)F" /T
if ($LASTEXITCODE -ne 0) { throw "Failed granting $poolAccount." }
& icacls.exe $sitePath /grant 'NT AUTHORITY\NETWORK SERVICE:(OI)(CI)M' /T
if ($LASTEXITCODE -ne 0) { throw 'Failed granting GitHub runner permissions.' }

Write-Host "IIS app pool: $poolName"
Write-Host "IIS Full Control on Anka folder: $poolAccount"
Write-Host "Runner Modify on Anka folder: NT AUTHORITY\NETWORK SERVICE"
Write-Host "SQLite database will be created automatically at: $sitePath\App_Data\anka.db"
Write-Host 'No MySQL, connection string, or appsettings.Production.json required.'
