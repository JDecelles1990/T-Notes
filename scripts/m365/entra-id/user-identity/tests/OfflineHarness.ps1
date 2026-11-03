# TEST INFRASTRUCTURE ONLY. Fixed local references; no operation discovery.
Set-StrictMode -Version 3.0
$script:OperationRoot = Split-Path $PSScriptRoot -Parent
$script:FixturesPath = Join-Path $PSScriptRoot 'fixtures.json'

function ConvertTo-FrozenValue($Value) {
    if ($Value -is [System.Collections.IDictionary]) {
        $map = [System.Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
        foreach ($key in $Value.Keys) { $map.Add([string]$key, (ConvertTo-FrozenValue $Value[$key])) }
        return ,([System.Collections.ObjectModel.ReadOnlyDictionary[string,object]]::new($map))
    }
    if ($Value -is [System.Collections.IList]) {
        $list = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $Value) { $list.Add((ConvertTo-FrozenValue $item)) }
        return ,($list.AsReadOnly())
    }
    return $Value
}

function Get-ReferenceAst([string] $FileName = 'Get-UserIdentity.ps1.reference') {
    if ($FileName -cnotin @('Get-UserIdentity.ps1.reference','Operation.Template.ps1.reference')) { throw 'Unknown reference.' }
    $tokens = $null; $parseErrors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $script:OperationRoot $FileName), [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw 'Reference syntax is invalid.' }
    $names = @($ast.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath })
    if (($names -join ',') -cne 'Context,Parameters,CancellationToken') { throw 'ABI parameter names changed.' }
    $types = @($ast.ParamBlock.Parameters | ForEach-Object { $_.StaticType.FullName })
    if ($types[0] -cne [System.Collections.Generic.IReadOnlyDictionary[string,object]].FullName -or
        $types[1] -cne $types[0] -or $types[2] -cne [Threading.CancellationToken].FullName) { throw 'ABI types changed.' }
    foreach ($parameter in $ast.ParamBlock.Parameters) {
        $attributes = @($parameter.Attributes | Where-Object { $_ -is [Management.Automation.Language.AttributeAst] })
        if ($attributes.Count -ne 1 -or $attributes[0].TypeName.FullName -ne 'Parameter' -or
            $attributes[0].NamedArguments.Count -ne 1 -or $attributes[0].NamedArguments[0].ArgumentName -ne 'Mandatory') {
            throw 'ABI binding attributes changed.'
        }
    }
    $guard = $ast.EndBlock.Statements[0]
    if ($guard -isnot [Management.Automation.Language.ThrowStatementAst] -or
        $guard.Extent.Text -cne "throw 'PROVISIONAL_REFERENCE_ONLY'") { throw 'Reference guard missing.' }
    # This is a small allowed-command inventory, not a hostile-code sandbox.
    $allowed = @('Set-StrictMode','New-OperationFailure','Test-GuidText','Test-UpnText',
        'Test-UtcText','Get-ProviderField','Get-MgUser','Get-Command')
    foreach ($command in $ast.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst]}, $true)) {
        if ($command.GetCommandName() -cnotin $allowed) { throw 'Unexpected operation command.' }
    }
    if ($ast.FindAll({param($node) $node -is [Management.Automation.Language.ExitStatementAst]}, $true).Count) { throw 'Operations cannot exit.' }
    return $ast
}

function Invoke-OfflineCase([string] $Name) {
    $fixtures = Get-Content -LiteralPath $script:FixturesPath -Raw | ConvertFrom-Json -AsHashtable -DateKind String
    $case = @($fixtures.cases | Where-Object { $_.name -ceq $Name })
    if ($case.Count -ne 1) { throw 'Unknown or duplicate fixture case.' }
    $case = $case[0]
    $context = $fixtures.context
    foreach ($path in $case.context_changes.Keys) {
        $segments = $path.Split('.')
        $cursor = $context
        for ($i = 0; $i -lt $segments.Count - 1; $i++) {
            # Assign inside each branch: an if-expression unwraps a singleton
            # connections array through PowerShell's success pipeline.
            if ($cursor -is [System.Collections.IDictionary]) { $cursor = $cursor[$segments[$i]] }
            else { $cursor = $cursor[[int]$segments[$i]] }
        }
        $cursor[$segments[-1]] = $case.context_changes[$path]
    }
    foreach ($field in $case.user_changes.Keys) { $fixtures.user[$field] = $case.user_changes[$field] }
    foreach ($field in $case.remove_user_fields) { $fixtures.user.Remove($field) }
    $cts = [Threading.CancellationTokenSource]::new()
    if ($case.mode -ceq 'cancel_before') { $cts.Cancel() }
    $state = [Management.Automation.Runspaces.InitialSessionState]::CreateDefault2()
    $state.Variables.Add([Management.Automation.Runspaces.SessionStateVariableEntry]::new(
        'PSModuleAutoLoadingPreference', 'None', 'Never autoload a real provider', [Management.Automation.ScopedItemOptions]::ReadOnly))
    $runspace = [Management.Automation.Runspaces.RunspaceFactory]::CreateRunspace($state)
    $pipeline = [powershell]::Create()
    try {
        $runspace.Open(); $pipeline.Runspace = $runspace
        $calls = [System.Collections.Generic.List[object]]::new()
        $runspace.SessionStateProxy.SetVariable('OfflineCalls', $calls)
        $runspace.SessionStateProxy.SetVariable('OfflineCase', $case)
        $runspace.SessionStateProxy.SetVariable('OfflineUser', [pscustomobject]$fixtures.user)
        $runspace.SessionStateProxy.SetVariable('OfflineCancellation', $cts)
        # Define the provider stub before compiling the reference. There is no
        # module import or fallback to command discovery. Exceptions are synthetic.
        $stub = @'
function Get-MgUser {
    [CmdletBinding()]
    param([string] $UserId, [string[]] $Property)
    $OfflineCalls.Add([pscustomobject]@{ UserId=$UserId; Property=$Property; ErrorAction=[string]$ErrorActionPreference })
    switch ($OfflineCase.mode) {
        'http_error' { throw [Net.Http.HttpRequestException]::new('SYNTHETIC_SECRET_SENTINEL', $null, [Net.HttpStatusCode]$OfflineCase.http_status) }
        'throw' { throw 'SYNTHETIC_SECRET_SENTINEL' }
        'nested_command_missing' { throw [Management.Automation.CommandNotFoundException]::new('SYNTHETIC_SECRET_SENTINEL') }
        'nonterminating' {
            $PSCmdlet.WriteError([Management.Automation.ErrorRecord]::new(
                [Exception]::new('SYNTHETIC_SECRET_SENTINEL'), 'SYNTHETIC',
                [Management.Automation.ErrorCategory]::NotSpecified, $null))
            return $OfflineUser
        }
        'cancel_during' { $OfflineCancellation.Cancel(); return $OfflineUser }
        'cancel_throw' { throw [OperationCanceledException]::new('SYNTHETIC_SECRET_SENTINEL') }
        'no_rows' { return }
        'multiple' { $OfflineUser; $OfflineUser; return }
        'string' { return 'SYNTHETIC_SECRET_SENTINEL' }
        default { return $OfflineUser }
    }
}
'@
        if ($case.mode -cne 'module_missing') { $null = $pipeline.AddScript($stub).Invoke(); $pipeline.Commands.Clear() }
        $ast = Get-ReferenceAst
        $source = $ast.Extent.Text
        $guard = $ast.EndBlock.Statements[0].Extent
        # Only this test-only loader removes the one exact unconditional guard.
        $source = $source.Remove($guard.StartOffset, $guard.EndOffset - $guard.StartOffset)
        $null = $pipeline.AddScript($source).AddParameter('Context', (ConvertTo-FrozenValue $context)).
            AddParameter('Parameters', (ConvertTo-FrozenValue $case.parameters)).AddParameter('CancellationToken', $cts.Token)
        $items = @($pipeline.Invoke())
        $streamCount = $pipeline.Streams.Error.Count + $pipeline.Streams.Warning.Count + $pipeline.Streams.Verbose.Count +
            $pipeline.Streams.Debug.Count + $pipeline.Streams.Information.Count + $pipeline.Streams.Progress.Count
        return [pscustomobject]@{ Name=$Name; Items=$items; Calls=$calls.ToArray(); StreamCount=$streamCount; Expected=$case.expected; TargetValue=$context.target.value; ExpectedUser=$fixtures.user }
    } finally {
        $pipeline.Dispose(); $runspace.Dispose(); $cts.Dispose()
    }
}

function Assert-ReferenceCase([string] $Name) {
    $observed = Invoke-OfflineCase $Name
    if ($observed.StreamCount -ne 0 -or $observed.Items.Count -ne 1) { throw "${Name}: output stream violation." }
    $result = $observed.Items[0]
    if ($result -isnot [pscustomobject] -or (@($result.PSObject.Properties.Name | Sort-Object) -join ',') -cne 'data,errors,operation_outcome,status,warnings') {
        throw "${Name}: return object fields/types changed."
    }
    if ($result.status -cne $observed.Expected.status -or $result.operation_outcome -cne $observed.Expected.outcome -or
        $observed.Calls.Count -ne $observed.Expected.calls) { throw "${Name}: status/outcome/provider count mismatch." }
    if ($result.errors -isnot [object[]] -or $result.warnings -isnot [object[]]) { throw "${Name}: arrays must stay object arrays." }
    if ($observed.Expected.code -and ($result.errors.Count -ne 1 -or $result.errors[0].code -cne $observed.Expected.code)) { throw "${Name}: wrong structured error." }
    if ($null -ne $result.data) {
        if ((@($result.data.PSObject.Properties.Name | Sort-Object) -join ',') -cne 'account_enabled,display_name,id,user_principal_name,user_type') { throw "${Name}: payload allowlist violated." }
        if ($result.status -ceq 'partial' -and $result.warnings.Count -lt 1) { throw "${Name}: missing partial warning." }
        if ($result.errors.Count) { throw "${Name}: unexpected data/error combination." }
        foreach ($pair in @(@('id','Id'),@('user_principal_name','UserPrincipalName'),@('display_name','DisplayName'),@('account_enabled','AccountEnabled'),@('user_type','UserType'))) {
            if ($result.data.($pair[0]) -cne $observed.ExpectedUser[$pair[1]]) { throw "${Name}: payload value was changed or invented." }
        }
    } elseif ($result.status -cin @('success','partial')) { throw "${Name}: missing payload." }
    foreach ($call in $observed.Calls) {
        if ($call.UserId -cne $observed.TargetValue -or ($call.Property -join ',') -cne 'id,userPrincipalName,displayName,accountEnabled,userType' -or $call.ErrorAction -cne 'Stop') { throw "${Name}: provider argument allowlist violated." }
    }
    $wire = $result | ConvertTo-Json -Depth 20 -Compress
    if ($wire -match 'SYNTHETIC_SECRET_SENTINEL|access_token|password|stacktrace') { throw "${Name}: secret escaped the allowlist." }
    return $observed
}

function Assert-FrozenBinding {
    $fixtures = Get-Content -LiteralPath $script:FixturesPath -Raw | ConvertFrom-Json -AsHashtable -DateKind String
    $context = ConvertTo-FrozenValue $fixtures.context
    $parameters = ConvertTo-FrozenValue @{}
    if ($context -isnot [System.Collections.Generic.IReadOnlyDictionary[string,object]] -or
        $parameters -isnot [System.Collections.Generic.IReadOnlyDictionary[string,object]] -or
        $context['session_generation'] -isnot [long]) { throw 'Frozen ABI types changed.' }
    $blocked = 0
    try { $context['company_id'] = 'changed' } catch { $blocked++ }
    try { $context['target']['value'] = 'changed' } catch { $blocked++ }
    try { $context['connections'][0]['graph_scopes'][0] = 'changed' } catch { $blocked++ }
    if ($blocked -ne 3) { throw 'Nested ABI state is mutable.' }
    $ast = Get-ReferenceAst
    $guarded = $ast.GetScriptBlock()
    $wasGuarded = $false
    try { $null = & $guarded -Context $context -Parameters $parameters -CancellationToken ([Threading.CancellationToken]::None) }
    catch { $wasGuarded = $_.Exception.Message -ceq 'PROVISIONAL_REFERENCE_ONLY' }
    if (-not $wasGuarded) { throw 'Reference can execute outside the offline loader.' }
}
