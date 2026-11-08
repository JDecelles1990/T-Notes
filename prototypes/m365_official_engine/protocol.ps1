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
    # CLR calls bypass PowerShell ETS methods, including on boxed value types and arrays.
    Add-Type -TypeDefinition @'
public static class TNotesNativeReturnTypes {
    private static void ValidateClrOnlyMembers(System.Management.Automation.PSObject pso) {
        foreach (System.Management.Automation.PSMemberInfo member in pso.Members) {
            if (member.MemberType == System.Management.Automation.PSMemberTypes.Property &&
                member is System.Management.Automation.PSProperty) {
                continue;
            }
            if (member.MemberType == System.Management.Automation.PSMemberTypes.ParameterizedProperty &&
                member is System.Management.Automation.PSParameterizedProperty) {
                continue;
            }
            if (member.MemberType == System.Management.Automation.PSMemberTypes.Method &&
                !(member is System.Management.Automation.PSScriptMethod) &&
                !(member is System.Management.Automation.PSCodeMethod)) {
                continue;
            }
            throw new System.InvalidOperationException("Unsupported native member");
        }
    }

    private static void ValidatePsoMembers(System.Management.Automation.PSObject pso, bool isCustomObject) {
        if (!isCustomObject) {
            ValidateClrOnlyMembers(pso);
            return;
        }
        foreach (System.Management.Automation.PSMemberInfo member in pso.Members) {
            ValidateClrOnlyMembers(System.Management.Automation.PSObject.AsPSObject(member));
            if (member.MemberType == System.Management.Automation.PSMemberTypes.NoteProperty &&
                member is System.Management.Automation.PSNoteProperty) {
                continue;
            }
            if (member.MemberType == System.Management.Automation.PSMemberTypes.Method &&
                !(member is System.Management.Automation.PSScriptMethod) &&
                !(member is System.Management.Automation.PSCodeMethod)) {
                continue;
            }
            throw new System.InvalidOperationException("Unsupported native property");
        }
    }

    private static object UnwrapValidated(object value, out System.Management.Automation.PSObject customObjectWrapper) {
        customObjectWrapper = null;
        if (value == null) {
            return null;
        }
        object current = value;
        while (current is System.Management.Automation.PSObject) {
            System.Management.Automation.PSObject pso = (System.Management.Automation.PSObject)current;
            object immediate = pso.ImmediateBaseObject;
            bool isCustom = immediate is System.Management.Automation.PSCustomObject;
            ValidatePsoMembers(pso, isCustom);
            if (isCustom) {
                ValidateClrOnlyMembers(System.Management.Automation.PSObject.AsPSObject(immediate));
                customObjectWrapper = pso;
                return immediate;
            }
            current = immediate;
        }
        ValidateClrOnlyMembers(System.Management.Automation.PSObject.AsPSObject(current));
        return current;
    }

    private static object UnwrapRaw(object value) {
        object current = value;
        while (current is System.Management.Automation.PSObject) {
            System.Management.Automation.PSObject pso = (System.Management.Automation.PSObject)current;
            object immediate = pso.ImmediateBaseObject;
            if (immediate is System.Management.Automation.PSCustomObject) {
                return immediate;
            }
            current = immediate;
        }
        return current;
    }

    public static System.Type Get(object value) {
        System.Management.Automation.PSObject customObjectWrapper;
        object raw = UnwrapValidated(value, out customObjectWrapper);
        return raw == null ? null : raw.GetType();
    }

    public static bool IsArray(object value) {
        System.Management.Automation.PSObject customObjectWrapper;
        object raw = UnwrapValidated(value, out customObjectWrapper);
        return raw is System.Array;
    }

    public static object GetReferenceTarget(object value) {
        System.Management.Automation.PSObject customObjectWrapper;
        object raw = UnwrapValidated(value, out customObjectWrapper);
        return customObjectWrapper != null ? (object)customObjectWrapper : raw;
    }

    public static int GetArrayLength(object value) {
        System.Management.Automation.PSObject customObjectWrapper;
        object raw = UnwrapValidated(value, out customObjectWrapper);
        System.Array array = raw as System.Array;
        if (array == null || array.Rank != 1 || array.GetLowerBound(0) != 0) {
            throw new System.InvalidOperationException("Unsupported native array");
        }
        return array.Length;
    }

    public static object GetArrayElement(object value, int index) {
        System.Array array = UnwrapRaw(value) as System.Array;
        if (array == null || array.Rank != 1 || array.GetLowerBound(0) != 0) {
            throw new System.InvalidOperationException("Unsupported native array");
        }
        return array.GetValue(index);
    }

    public static string[] GetNotePropertyNames(object value) {
        System.Management.Automation.PSObject customObjectWrapper;
        UnwrapValidated(value, out customObjectWrapper);
        if (customObjectWrapper == null) {
            throw new System.InvalidOperationException("Invalid native object");
        }
        int count = 0;
        foreach (System.Management.Automation.PSPropertyInfo prop in customObjectWrapper.Properties) {
            if (!(prop is System.Management.Automation.PSNoteProperty)) {
                throw new System.InvalidOperationException("Unsupported native property");
            }
            count++;
        }
        string[] names = new string[count];
        int index = 0;
        foreach (System.Management.Automation.PSPropertyInfo prop in customObjectWrapper.Properties) {
            names[index++] = prop.Name;
        }
        return names;
    }

    public static object[] GetNotePropertyValues(object value) {
        System.Management.Automation.PSObject customObjectWrapper;
        UnwrapValidated(value, out customObjectWrapper);
        if (customObjectWrapper == null) {
            throw new System.InvalidOperationException("Invalid native object");
        }
        int count = 0;
        foreach (System.Management.Automation.PSPropertyInfo prop in customObjectWrapper.Properties) {
            if (!(prop is System.Management.Automation.PSNoteProperty)) {
                throw new System.InvalidOperationException("Unsupported native property");
            }
            count++;
        }
        object[] values = new object[count];
        int index = 0;
        foreach (System.Management.Automation.PSPropertyInfo prop in customObjectWrapper.Properties) {
            values[index++] = ((System.Management.Automation.PSNoteProperty)prop).Value;
        }
        return values;
    }

    public static object GetNotePropertyValue(object value, string name) {
        System.Management.Automation.PSObject customObjectWrapper;
        UnwrapValidated(value, out customObjectWrapper);
        if (customObjectWrapper == null) {
            throw new System.InvalidOperationException("Invalid native object");
        }
        System.Management.Automation.PSPropertyInfo prop = customObjectWrapper.Properties[name];
        if (prop == null ||
            !string.Equals(prop.Name, name, System.StringComparison.Ordinal) ||
            !(prop is System.Management.Automation.PSNoteProperty)) {
            throw new System.InvalidOperationException("Invalid native return fields");
        }
        return ((System.Management.Automation.PSNoteProperty)prop).Value;
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
    $names = [TNotesNativeReturnTypes]::GetNotePropertyNames($Value)
    $nameCount = [TNotesNativeReturnTypes]::GetArrayLength($names)
    if ($nameCount -ne 5) { throw 'Invalid native return fields' }
    foreach ($name in @('status','operation_outcome','data','warnings','errors')) {
        if ($names -cnotcontains $name) { throw 'Invalid native return fields' }
    }
    $data = [TNotesNativeReturnTypes]::GetNotePropertyValue($Value, 'data')
    if ($null -ne $data -and [TNotesNativeReturnTypes]::Get($data) -ne [System.Management.Automation.PSCustomObject]) {
        throw 'Invalid native data object'
    }
    foreach ($name in @('warnings','errors')) {
        $items = [TNotesNativeReturnTypes]::GetNotePropertyValue($Value, $name)
        if ($null -eq $items -or [TNotesNativeReturnTypes]::Get($items) -ne [object[]]) {
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
    $isArray = [TNotesNativeReturnTypes]::IsArray($Value)
    if (-not $isObject -and -not $isArray) { throw 'Unsupported native return value' }
    $target = [TNotesNativeReturnTypes]::GetReferenceTarget($Value)
    if (-not $Active.Add($target)) { throw 'Cyclic native return value' }
    try {
        if ($isObject) {
            $values = [TNotesNativeReturnTypes]::GetNotePropertyValues($Value)
            $length = [TNotesNativeReturnTypes]::GetArrayLength($values)
            for ($index = 0; $index -lt $length; $index++) {
                $item = [TNotesNativeReturnTypes]::GetArrayElement($values, $index)
                Assert-NativeJsonValue -Value $item -Depth ($Depth + 1) -Active $Active -Budget $Budget
            }
        } else {
            $length = [TNotesNativeReturnTypes]::GetArrayLength($Value)
            for ($index = 0; $index -lt $length; $index++) {
                $item = [TNotesNativeReturnTypes]::GetArrayElement($Value, $index)
                Assert-NativeJsonValue -Value $item -Depth ($Depth + 1) -Active $Active -Budget $Budget
            }
        }
    } finally { [void]$Active.Remove($target) }
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
