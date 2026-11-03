# TEST FIXTURE ONLY. No Microsoft cmdlets, authentication or system mutations.
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [System.Collections.Generic.IReadOnlyDictionary[string,object]] $Context,
    [Parameter(Mandatory)]
    [System.Collections.Generic.IReadOnlyDictionary[string,object]] $Parameters,
    [Parameter(Mandatory)]
    [System.Threading.CancellationToken] $CancellationToken
)
$ErrorActionPreference = 'Stop'
$CancellationToken.ThrowIfCancellationRequested()
$scenario = $Parameters['Scenario']
$elapsed = 0
while ($elapsed -lt $Parameters['DelayMs']) {
    $CancellationToken.ThrowIfCancellationRequested()
    [Threading.Thread]::Sleep(10)
    $elapsed += 10
}
if ($scenario -eq 'throw') { throw 'SYNTHETIC_SECRET_SENTINEL' }
if ($scenario -eq 'extra_output') { 'unwanted pipeline object' }
if ($scenario -eq 'console_noise') { [Console]::Out.WriteLine('unexpected console banner') }
if ($scenario -eq 'immutable') {
    $blocked = 0
    try { $Context['tenant_id'] = 'changed' } catch { $blocked++ }
    try { $Context['target']['value'] = 'changed' } catch { $blocked++ }
    try { $Context['connections'][0]['graph_scopes'][0] = 'changed' } catch { $blocked++ }
    try { $Parameters['DelayMs'] = [long]0 } catch { $blocked++ }
    if ($Parameters['Count'] -isnot [long] -or $Parameters['Ratio'] -isnot [double] -or
        $Parameters['Flag'] -isnot [bool] -or $Parameters['Flag'] -ne $false -or
        $Parameters['Names'] -isnot [System.Collections.ObjectModel.ReadOnlyCollection[string]]) {
        throw 'All parameter kinds must retain exact ABI types'
    }
    try { $Parameters['Names'][0] = 'changed' } catch { $blocked++ }
    if ($blocked -ne 5 -or $Parameters['DelayMs'] -isnot [long] -or $Parameters['Scenario'] -isnot [string]) {
        throw 'ABI mutability/type failure'
    }
}
if ($scenario -eq 'error') {
    return [pscustomobject]@{status='error';operation_outcome='failed';data=$null;warnings=@();
        errors=@([pscustomobject]@{code='ACCESS_DENIED';message='SYNTHETIC_SECRET_SENTINEL';retryable=$false})}
}
$id = '44444444-4444-4444-8444-444444444444'
$upn = 'synthetic.user@example.invalid'
$target = $Context['target']
if (($target['kind'] -eq 'object_id' -and $target['value'] -cne $id) -or
    ($target['kind'] -eq 'upn' -and $target['value'] -ine $upn)) {
    return [pscustomobject]@{status='error';operation_outcome='failed';data=$null;warnings=@();
        errors=@([pscustomobject]@{code='TARGET_NOT_FOUND';message='No fixture target.';retryable=$false})}
}
$partial = $scenario -eq 'partial'
$data = [pscustomobject]@{id=$id;display_name='Synthetic Fixture';user_principal_name=$upn;
    account_enabled=$(if ($partial) {$null} else {$true});user_type='Member'}
$warnings = [object[]]@()
if ($partial) { $warnings = @([pscustomobject]@{code='PROPERTY_UNAVAILABLE';message='Synthetic missing property.'}) }
$result = [pscustomobject]@{status=$(if ($partial) {'partial'} else {'success'});
    operation_outcome=$(if ($partial) {'partially_succeeded'} else {'succeeded'});data=$data;
    warnings=$warnings;errors=@()}
# Native-return regression cases only; no provider calls or new operation.
if ($scenario -like 'native_nested*' -or $scenario -eq 'native_enum') {
    $event = [pscustomobject]@{created_at='2026-11-03T00:00:00Z';app_display_name=$null;success=$true;error_code=[long]0}
    $result.data = [pscustomobject]@{target_user_id=$id;lookback_start='2026-11-02T00:00:00Z';
        events=@($event,$event);returned_count=[int]2;truncated=$false}
    switch ($scenario) {
        'native_enum' { $event.error_code = [DayOfWeek]::Sunday } # Serializes as schema-valid 0.
        'native_nested_object' { $event.app_display_name = [uri]'https://example.invalid/' }
        'native_nested_array' { $result.data.events = @([datetime]::UtcNow) }
        'native_nested_dictionary' { $result.data.events = @(@{created_at=$event.created_at;app_display_name=$null;success=$true;error_code=0}) }
        'native_nested_null' { $event.created_at = $null }
    }
}
switch ($scenario) {
    'native_hashtable' { $result.data = @{id=$id;display_name='Synthetic Fixture';user_principal_name=$upn;account_enabled=$true;user_type='Member'} }
    'native_datetime' { $result.data.display_name = [datetime]::new(2026,11,3,0,0,0,[DateTimeKind]::Utc) }
    'native_datetimeoffset' { $result.data.display_name = [DateTimeOffset]::UtcNow }
    'native_null_data' { $result.data = $null }
    'native_null_field' { $result.data.id = $null }
    'native_cycle' { $result.data.display_name = $result.data }
    'native_array_cycle' { $cycle = [object[]]@($null); $cycle[0] = $cycle; $result.warnings = $cycle }
    'native_depth' {
        $node = [pscustomobject]@{value='leaf'}
        for ($i=0; $i -lt 25; $i++) { $node = [pscustomobject]@{value=$node} }
        $result.data.display_name = $node
    }
    'native_container' { $result.warnings = [System.Collections.ArrayList]::new() }
    'native_nonfinite' { $result.data.display_name = [double]::NaN }
    'native_getter' {
        $result.data | Add-Member -MemberType ScriptProperty -Name display_name -Value {
            [Console]::Out.WriteLine('NATIVE_GETTER_MUST_NOT_RUN'); 'Synthetic Fixture'
        } -Force
    }
    'native_type_method' {
        $value = [datetime]::new(2026,11,3,0,0,0,[DateTimeKind]::Utc)
        $value | Add-Member -MemberType ScriptMethod -Name GetType -Value {
            [Console]::Out.WriteLine('NATIVE_TYPE_METHOD_MUST_NOT_RUN'); [string]
        } -Force
        $result.data.display_name = $value
    }
    'native_outer_dictionary' {
        return @{status=$result.status;operation_outcome=$result.operation_outcome;data=$result.data;warnings=@();errors=@()}
    }
}
return $result
