[CmdletBinding()]
param([Parameter(Mandatory)][string]$ReportPath)
$ErrorActionPreference = 'Stop'
$modules = @(Get-Module -ListAvailable Pester | Sort-Object Version -Descending)
$summary = [ordered]@{status='NOT RUN'; reason='Pester unavailable or unsupported; no installation attempted'; powershell=[string]$PSVersionTable.PSVersion}
if ($modules.Count -and $modules[0].Version.Major -in @(3,4)) {
    Import-Module $modules[0].Path -ErrorAction Stop
    $result = Invoke-Pester -Script (Join-Path $PSScriptRoot 'Framework.Tests.ps1') -PassThru -Quiet
    $summary = [ordered]@{status=$(if ($result.FailedCount -eq 0 -and $result.PassedCount -eq 2) {'PASS'} else {'FAIL'});
        pester=[string]$modules[0].Version; powershell=[string]$PSVersionTable.PSVersion; passed=$result.PassedCount; failed=$result.FailedCount}
}
# Never replace prior evidence.
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($summary | ConvertTo-Json))
$stream = [IO.File]::Open([IO.Path]::GetFullPath($ReportPath), [IO.FileMode]::CreateNew)
try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
$summary | ConvertTo-Json -Compress
if ($summary.status -eq 'FAIL') { exit 1 }
if ($summary.status -eq 'NOT RUN') { exit 2 }
