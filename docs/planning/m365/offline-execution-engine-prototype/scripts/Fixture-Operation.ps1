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
    if ($blocked -ne 4 -or $Parameters['DelayMs'] -isnot [long] -or $Parameters['Scenario'] -isnot [string]) {
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
return [pscustomobject]@{status=$(if ($partial) {'partial'} else {'success'});
    operation_outcome=$(if ($partial) {'partially_succeeded'} else {'succeeded'});data=$data;
    warnings=$warnings;errors=@()}
