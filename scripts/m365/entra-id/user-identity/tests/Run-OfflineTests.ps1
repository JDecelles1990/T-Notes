# Fixed offline test entrypoint. JSON here is TEST evidence, never operation stdout.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3.0
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required.' }
. (Join-Path $PSScriptRoot 'OfflineHarness.ps1')
$modules = @(Get-Module -ListAvailable Pester | Sort-Object Version -Descending)
$pesterResult = $null
if ($modules.Count) {
    Import-Module $modules[0].Path -ErrorAction Stop
    $pesterResult = Invoke-Pester -Script (Join-Path $PSScriptRoot 'UserIdentity.Tests.ps1') -PassThru -Quiet
}
$fixtures = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'fixtures.json') -Raw | ConvertFrom-Json
$observations = @()
foreach ($case in $fixtures.cases) {
    $observed = Assert-ReferenceCase $case.name
    $observations += [pscustomobject]@{
        name=$case.name; status='PASS'; return_object=$observed.Items[0]; provider_calls=$observed.Calls
    }
}
$pesterSummary = if ($null -eq $pesterResult) {
    [pscustomobject]@{ status='NOT RUN'; reason='Pester is unavailable; no dependency installed.' }
} else {
    [pscustomobject]@{
        status=$(if ($pesterResult.FailedCount -eq 0 -and $pesterResult.PassedCount -eq ($fixtures.cases.Count + 2)) {'PASS'} else {'FAIL'})
        version=[string]$modules[0].Version; passed=$pesterResult.PassedCount; failed=$pesterResult.FailedCount
    }
}
$null = Get-ReferenceAst 'Operation.Template.ps1.reference'
Assert-FrozenBinding
[pscustomobject]@{
    evidence_kind='SYNTHETIC_OFFLINE_ONLY'; powershell=[string]$PSVersionTable.PSVersion
    pester=$pesterSummary; offline_cases=$observations; syntax_and_abi='PASS'
} | ConvertTo-Json -Depth 24 -Compress
if ($pesterSummary.status -ceq 'FAIL') { exit 1 }
