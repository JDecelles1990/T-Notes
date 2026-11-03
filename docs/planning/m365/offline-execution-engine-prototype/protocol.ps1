# PROVISIONAL OFFLINE protocol helpers. No Microsoft service modules.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::Out.NewLine = "`n"
$PSModuleAutoLoadingPreference = 'None'
Import-Module "$PSHOME/Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1" -ErrorAction Stop

function New-SchemaOptions($Schemas) {
    Test-Json -Json '{}' -Schema '{"type":"object"}' | Out-Null
    $options = [Json.Schema.EvaluationOptions]::new()
    $options.EvaluateAs = [Json.Schema.SpecVersion]::Draft202012
    $options.RequireFormatValidation = $true
    $options.ValidateAgainstMetaSchema = $false
    foreach ($schema in $Schemas) {
        $text = ConvertTo-Json -InputObject $schema -Depth 100 -Compress
        $options.SchemaRegistry.Register([Json.Schema.JsonSchema]::FromText($text))
    }
    foreach ($schema in $Schemas) {
        $text = ConvertTo-Json -InputObject $schema -Depth 100 -Compress
        $node = [System.Text.Json.Nodes.JsonNode]::Parse($text)
        if (-not [Json.Schema.MetaSchemas]::Draft202012.Evaluate($node, $options).IsValid) {
            throw 'Invalid pinned schema'
        }
    }
    return $options
}

function Assert-Schema($Value, [string] $Reference, $Options) {
    $schemaText = ConvertTo-Json -InputObject @{ '$ref' = $Reference } -Compress
    $schema = [Json.Schema.JsonSchema]::FromText($schemaText)
    $node = [System.Text.Json.Nodes.JsonNode]::Parse((ConvertTo-Json -InputObject $Value -Depth 100 -Compress))
    if (-not $schema.Evaluate($node, $Options).IsValid) { throw 'Schema rejected' }
}

function Freeze-Value($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Collections.IDictionary]) {
        $dictionary = [System.Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
        foreach ($key in $Value.Keys) { $dictionary.Add([string]$key, (Freeze-Value $Value[$key])) }
        return ,([System.Collections.ObjectModel.ReadOnlyDictionary[string,object]]::new($dictionary))
    }
    if ($Value -is [array] -or $Value -is [System.Collections.IList]) {
        $allStrings = $true
        foreach ($item in $Value) { if ($item -isnot [string]) { $allStrings = $false } }
        if ($allStrings) {
            $list = [System.Collections.Generic.List[string]]::new()
            foreach ($item in $Value) { $list.Add($item) }
            return ,($list.AsReadOnly())
        }
        $list = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $Value) { $list.Add((Freeze-Value $item)) }
        return ,($list.AsReadOnly())
    }
    if ($Value -is [int] -or $Value -is [long]) { return [long]$Value }
    return $Value
}

function Get-LogicalExit($Result) {
    switch ($Result.status) {
        'success' { return 0 }
        'partial' { return 2 }
        'cancelled' { return 40 }
        'timeout' { return 40 }
    }
    $codes = @($Result.errors | ForEach-Object { $_.code })
    if ($codes -contains 'INTERNAL_ERROR') { return 50 }
    foreach ($code in @('AUTH_REQUIRED','TENANT_MISMATCH','ACCOUNT_MISMATCH','ACCESS_DENIED')) { if ($codes -contains $code) { return 20 } }
    foreach ($code in @('INVALID_PARAMETER','CONTRACT_VIOLATION')) { if ($codes -contains $code) { return 10 } }
    foreach ($code in @('TIMEOUT','CANCELLED')) { if ($codes -contains $code) { return 40 } }
    return 30
}

function New-SafeReturn([string] $Code, [string] $Outcome = 'failed') {
    $status = switch ($Code) { 'CANCELLED' {'cancelled'} 'TIMEOUT' {'timeout'} default {'error'} }
    return [pscustomobject]@{ status=$status; operation_outcome=$Outcome; data=$null; warnings=@();
        errors=@([pscustomobject]@{code=$Code;message='Synthetic operation or adapter failure.';retryable=$false}) }
}
