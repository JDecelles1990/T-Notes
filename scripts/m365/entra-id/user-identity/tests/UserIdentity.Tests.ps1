# Pester 3.4 supported here; assertions throw directly (no version-specific Should).
. (Join-Path $PSScriptRoot 'OfflineHarness.ps1')
Describe 'Provisional User Identity offline contract cases' {
    $fixtures = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'fixtures.json') -Raw | ConvertFrom-Json
    $cases = @($fixtures.cases | ForEach-Object { @{ Name = $_.name } })
    It 'returns one safe contract object for <Name>' -TestCases $cases {
        param($Name)
        $null = Assert-ReferenceCase $Name
    }
    It 'keeps the reusable template ABI and non-dispatchable guard' {
        $null = Get-ReferenceAst 'Operation.Template.ps1.reference'
    }
    It 'binds recursive read-only ABI types and refuses direct execution' {
        Assert-FrozenBinding
    }
}
