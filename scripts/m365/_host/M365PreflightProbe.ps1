<#
.SYNOPSIS
    Non-destructive PowerShell 7 & M365 module availability probe for T-Notes preflight.
.DESCRIPTION
    Reads a JSON array of required PowerShell module names from stdin and emits
    a compressed JSON summary of pwsh version, edition, and installed module versions.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# Force UTF-8 (no BOM) for stdin/stdout JSON transport.
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$rawNames = [Console]::In.ReadToEnd()
$names = if ([string]::IsNullOrWhiteSpace($rawNames)) {
    @()
} else {
    @(ConvertFrom-Json -InputObject $rawNames)
}

$mods = @{}
foreach ($n in $names) {
    $best = Get-Module -ListAvailable -Name $n | Sort-Object Version -Descending | Select-Object -First 1
    $mods[$n] = if ($null -ne $best) { $best.Version.ToString() } else { $null }
}

$out = [pscustomobject]@{
    pwsh_found = $true
    version    = $PSVersionTable.PSVersion.ToString()
    edition    = [string]$PSVersionTable.PSEdition
    modules    = $mods
}
[Console]::Out.WriteLine((ConvertTo-Json -InputObject $out -Depth 5 -Compress))
