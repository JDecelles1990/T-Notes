# Adversarial transport TEST FIXTURE ONLY. Explicitly pinned by a separate test catalog.
param([string]$PrototypeRoot, [string]$ContractRoot)
. "$PrototypeRoot/protocol.ps1"
$request = ConvertFrom-Json -InputObject ([Console]::In.ReadLine()) -AsHashtable -Depth 100
$mode = $request.parameters.Scenario
if ($mode -eq 'child_hang') {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = [Environment]::ProcessPath
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true
    foreach ($arg in @('-NoLogo','-NoProfile','-NonInteractive','-File',"$PrototypeRoot/tests/fixtures/Child-Sleeper.ps1")) { [void]$info.ArgumentList.Add($arg) }
    $child = [Diagnostics.Process]::Start($info)
    [Threading.Thread]::Sleep(60000) # Intentionally ignores cancellation to test job termination.
    exit 0
}
if ($mode -eq 'oversize') { [Console]::Out.Write(('x' * 1048577)); [Threading.Thread]::Sleep(60000); exit 0 }
if ($mode -eq 'malformed') { [Console]::Out.WriteLine('{broken JSON}'); exit 0 }
if ($mode -eq 'duplicate_keys') { [Console]::Out.WriteLine('{"x":1,"x":2}'); exit 0 }
if ($mode -eq 'invalid_utf8') { $stream=[Console]::OpenStandardOutput(); $stream.WriteByte(255); exit 0 }
$response = @{}
foreach ($key in @('contract_version','script_id','correlation_id','company_id','admin_identity_ref','session_generation','target','release_binding')) { $response[$key] = $request[$key] }
$response.tenant_id=$request.tenant_id; $response.context_state='verified'; $response.origin='worker'
$response.status='success'; $response.operation_outcome='succeeded'; $response.operation_exit_code=0
$response.started_at=[DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'"); $response.completed_at=$response.started_at
$response.duration_ms=0; $response.warnings=@(); $response.errors=@()
$response.data=@{id='44444444-4444-4444-8444-444444444444';display_name='Synthetic Fixture';user_principal_name='synthetic.user@example.invalid';account_enabled=$true;user_type='Member'}
switch ($mode) {
    'bad_correlation' { $response.correlation_id=[guid]::NewGuid().ToString() }
    'bad_version' { $response.contract_version='0.2.0-proposed.1' }
    'bad_date' { $response.completed_at='2026-02-30T12:00:00Z' }
    'stderr_secret' { [Console]::Error.WriteLine('SYNTHETIC_SECRET_SENTINEL bearer mock-token') }
    'leak_data' { $response.data.display_name='SYNTHETIC_SECRET_SENTINEL' }
    'unknown_payload' { $response.data.access_token='SYNTHETIC_SECRET_SENTINEL' }
    'wrong_logical_exit' { $response.operation_exit_code=30 }
    'console_noise' { [Console]::Out.WriteLine('unwanted banner') }
}
$text=ConvertTo-Json -InputObject $response -Depth 100 -Compress
[Console]::Out.WriteLine($text)
if ($mode -eq 'two_envelopes') { [Console]::Out.WriteLine($text) }
if ($mode -eq 'process_nonzero') { exit 23 }
exit 0
