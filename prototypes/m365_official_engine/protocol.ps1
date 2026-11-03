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

function Initialize-NativeReturnValidation {
    # Compiled from this pinned source before the operation runspace starts.
    # CLR calls bypass PowerShell ETS methods, including on boxed value types.
    Add-Type -TypeDefinition @'
public static class TNotesNativeReturnTypes {
    public static System.Type Get(object value) {
        while (value is System.Management.Automation.PSObject) {
            value = ((System.Management.Automation.PSObject)value).BaseObject;
        }
        return value == null ? null : value.GetType();
    }
}
'@ -ReferencedAssemblies ([System.Management.Automation.PSObject].Assembly.Location)
}

function Assert-NativeOperationReturn($Value) {
    # CONTRACT.md callable ABI: typed objects, JSON primitives and object arrays.
    # This check MUST precede Assert-Schema: serialization erases CLR types.
    if ($null -eq $Value -or [TNotesNativeReturnTypes]::Get($Value) -ne [System.Management.Automation.PSCustomObject]) {
        throw 'Invalid native operation return'
    }
    # Validate the whole graph before reading return fields or serializing it.
    $active = [System.Collections.Generic.HashSet[object]]::new(
        [System.Collections.Generic.ReferenceEqualityComparer]::Instance)
    $budget = [long[]]@(1048576) # No valid <=1 MiB wire object can need more nodes.
    Assert-NativeJsonValue -Value $Value -Depth 0 -Active $active -Budget $budget
    $names = @($Value.PSObject.Properties.Name)
    if ($names.Count -ne 5) { throw 'Invalid native return fields' }
    foreach ($name in @('status','operation_outcome','data','warnings','errors')) {
        if ($names -cnotcontains $name) { throw 'Invalid native return fields' }
    }
    if ($null -ne $Value.data -and [TNotesNativeReturnTypes]::Get($Value.data) -ne [System.Management.Automation.PSCustomObject]) {
        throw 'Invalid native data object'
    }
    foreach ($name in @('warnings','errors')) {
        if ($null -eq $Value.$name -or [TNotesNativeReturnTypes]::Get($Value.$name) -ne [object[]]) {
            throw 'Invalid native diagnostic array'
        }
    }
    # Nullability, field types/bounds and status semantics remain schema-owned.
}

function Assert-NativeJsonValue($Value, [int] $Depth, $Active, [long[]] $Budget) {
    $Budget[0]--
    # Match the host strict parser's existing maximum nesting depth.
    if ($Depth -gt 20 -or $Budget[0] -lt 0) { throw 'Native return exceeds traversal bounds' }
    if ($null -eq $Value) { return }
    $type = [TNotesNativeReturnTypes]::Get($Value)
    if ($type -eq [string] -or $type -eq [bool]) { return }
    # Exact numeric types exclude Enum, Char, dates, BigInteger and SDK objects.
    if ($type -in @([sbyte],[byte],[int16],[uint16],[int32],[uint32],[int64],[uint64],[decimal])) { return }
    if ($type -eq [single] -or $type -eq [double]) {
        if ([double]::IsNaN($Value) -or [double]::IsInfinity($Value)) { throw 'Nonfinite native number' }
        return
    }
    $isObject = $type -eq [System.Management.Automation.PSCustomObject]
    $isArray = $Value -is [array]
    if (-not $isObject -and -not $isArray) { throw 'Unsupported native return value' }
    if (-not $Active.Add($Value)) { throw 'Cyclic native return value' }
    try {
        if ($isObject) {
            foreach ($property in $Value.PSObject.Properties) {
                # Do not execute user-supplied getters/aliases during traversal.
                if ($property.MemberType -ne [System.Management.Automation.PSMemberTypes]::NoteProperty) {
                    throw 'Unsupported native property'
                }
                Assert-NativeJsonValue -Value $property.Value -Depth ($Depth + 1) -Active $Active -Budget $Budget
            }
        } else {
            if ($Value.Rank -ne 1 -or $Value.GetLowerBound(0) -ne 0) { throw 'Unsupported native array' }
            foreach ($item in $Value) {
                Assert-NativeJsonValue -Value $item -Depth ($Depth + 1) -Active $Active -Budget $Budget
            }
        }
    } finally { [void]$Active.Remove($Value) }
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
