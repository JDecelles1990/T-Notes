# PROVISIONAL TEST-ONLY adapter. Simulated identity leases, never live auth.
param([Parameter(Mandatory)][string]$PrototypeRoot, [Parameter(Mandatory)][string]$ContractRoot)
try {
    $stage = 'initialization'
    . "$PSScriptRoot/protocol.ps1"
    Initialize-NativeReturnValidation
    $version = '0.3.0'
    $common = "https://tnotes.invalid/m365/$version/schemas/common.schema.json"
    $schemas = @([IO.Directory]::GetFiles("$ContractRoot/schemas", '*.schema.json') | ForEach-Object {
        ConvertFrom-Json -InputObject ([IO.File]::ReadAllText($_)) -AsHashtable -Depth 100
    })
    $options = New-SchemaOptions $schemas
    $inventory = ConvertFrom-Json -InputObject ([IO.File]::ReadAllText("$PrototypeRoot/catalog.json")) -AsHashtable -Depth 100
    $fixture = ConvertFrom-Json -InputObject ([IO.File]::ReadAllText("$PrototypeRoot/synthetic-context.json")) -AsHashtable -Depth 100
    # Console.In.ReadLineAsync can block synchronously on Windows SyncTextReader.
    # Use a bound .NET delegate on a dedicated Task; no PowerShell scriptblock
    # runs on the reader thread and therefore no thread-local runspace is needed.
    $readMethod = [IO.TextReader].GetMethod('ReadLine', [type[]]@())
    $readDelegate = [Delegate]::CreateDelegate([Func[string]], [Console]::In, $readMethod)
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        if ([Text.Encoding]::UTF8.GetByteCount($line) -gt 65536) { throw 'Oversize request' }
        $request = ConvertFrom-Json -InputObject $line -AsHashtable -Depth 100
        Assert-Schema $request "https://tnotes.invalid/m365/$version/schemas/execution-request.schema.json" $options
        $entries = @($inventory.operations | Where-Object { $_.script_id -ceq $request.script_id })
        if ($entries.Count -ne 1) { throw 'Unknown operation' }
        $manifest = ConvertFrom-Json -InputObject ([IO.File]::ReadAllText("$PrototypeRoot/$($entries[0].manifest)")) -AsHashtable -Depth 100
        foreach ($key in @('company_id','tenant_id','admin_identity_ref','session_generation')) {
            if ($request[$key] -cne $fixture.selection[$key]) { throw 'Synthetic context mismatch' }
        }
        $clock = [Diagnostics.Stopwatch]::StartNew()
        $started = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'")
        $context = @{}
        foreach ($key in @('contract_version','correlation_id','script_id','company_id','tenant_id','admin_identity_ref','session_generation','target','ticket_context','release_binding')) { $context[$key] = $request[$key] }
        $context.verified_account_upn = $fixture.account_upn
        $lease = @{service='Graph';connection_id=[guid]::NewGuid().ToString();owner_worker_id=[guid]::NewGuid().ToString();
            verified_account_upn=$fixture.account_upn;state='verified';verified_at=$started;expires_at=$null;graph_scopes=@('User.Read.All');effective_roles=@()}
        foreach ($key in @('company_id','tenant_id','admin_identity_ref','session_generation')) { $lease[$key] = $request[$key] }
        $context.connections = @($lease)
        Assert-Schema $context "$common# /`$defs/invocation_context".Replace('# /','#/') $options
        $parameters = @{}
        foreach ($descriptor in $manifest.parameters) {
            if ($request.parameters.ContainsKey($descriptor.name)) {
                $value = $request.parameters[$descriptor.name]
                $parameters[$descriptor.name] = switch ($descriptor.type) {
                    'integer' {[long]$value} 'number' {[double]$value} 'boolean' {[bool]$value}
                    default {$value}
                }
            }
        }
        $cts = [Threading.CancellationTokenSource]::new()
        $ps = [PowerShell]::Create()
        try {
            $stage = 'invocation'
            [void]$ps.AddCommand("$PrototypeRoot/$($manifest.script_path)").AddParameter('Context',(Freeze-Value $context)).AddParameter('Parameters',(Freeze-Value $parameters)).AddParameter('CancellationToken',$cts.Token)
            $async = $ps.BeginInvoke()
            $inputTask = ([Threading.Tasks.Task[string]]::Factory).StartNew($readDelegate)
            $cancelled = $false
            while (-not $async.IsCompleted) {
                if ($inputTask.IsCompleted) {
                    $controlLine = $inputTask.GetAwaiter().GetResult()
                    if ($null -eq $controlLine) { throw 'EOF during operation' }
                    try {
                        if ([Text.Encoding]::UTF8.GetByteCount($controlLine) -gt 4096) { throw 'Oversize control' }
                        $control = ConvertFrom-Json -InputObject $controlLine -AsHashtable -Depth 20
                        Assert-Schema $control "$common# /`$defs/cancel_control".Replace('# /','#/') $options
                        if ($control.correlation_id -ceq $request.correlation_id -and $control.company_id -ceq $request.company_id -and $control.session_generation -eq $request.session_generation) {
                            $cts.Cancel(); $cancelled = $true
                        }
                    } catch { } # Unmatched/malformed controls never affect another invocation.
                    $inputTask = ([Threading.Tasks.Task[string]]::Factory).StartNew($readDelegate)
                }
                [Threading.Thread]::Sleep(5)
            }
            $invokeFailed = $false
            $stage = 'return_capture'
            try { $objects = @($ps.EndInvoke($async)) } catch { $objects = @(); $invokeFailed = $true }
            if ($cancelled) { $result = New-SafeReturn 'CANCELLED' 'unknown' }
            elseif ($ps.Streams.Error.Count -gt 0 -or $invokeFailed) { $result = New-SafeReturn 'INTERNAL_ERROR' }
            elseif ($objects.Count -ne 1 -or $objects[0] -isnot [pscustomobject]) { $result = New-SafeReturn 'CONTRACT_VIOLATION' }
            else { $result = $objects[0] }
            try {
                $stage = 'return_validation'
                Assert-NativeOperationReturn $result
                Assert-Schema $result "$common# /`$defs/operation_return".Replace('# /','#/') $options
                if ($null -ne $result.data) {
                    $ref = $manifest.expected_output_schema.Replace('schemas/', "https://tnotes.invalid/m365/$version/schemas/")
                    Assert-Schema $result.data $ref $options
                }
            } catch { $result = New-SafeReturn 'CONTRACT_VIOLATION' }
            $envelope = @{}
            $stage = 'envelope_validation'
            foreach ($key in @('contract_version','script_id','correlation_id','company_id','admin_identity_ref','session_generation','target','release_binding')) { $envelope[$key] = $request[$key] }
            foreach ($key in @('status','operation_outcome','data','warnings','errors')) { $envelope[$key] = $result.$key }
            $envelope.tenant_id = $request.tenant_id; $envelope.context_state = 'verified'; $envelope.origin = 'worker'
            $envelope.started_at = $started; $envelope.completed_at = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'")
            $envelope.duration_ms = $clock.ElapsedMilliseconds; $envelope.operation_exit_code = Get-LogicalExit $result
            Assert-Schema $envelope "https://tnotes.invalid/m365/$version/schemas/execution-result.schema.json" $options
            [Console]::Out.WriteLine((ConvertTo-Json -InputObject $envelope -Depth 100 -Compress))
            $stage = 'idle_shutdown'
            # Reuse the pending reader, rather than issuing a second concurrent console read.
            $next = $inputTask.GetAwaiter().GetResult()
            if ($null -eq $next) { break }
            throw 'Prototype accepts one request per worker; use a fresh owned worker'
        } finally { $cts.Dispose(); $ps.Dispose() }
    }
    exit 0
} catch {
    [Console]::Error.WriteLine('OFFLINE_WORKER_PROTOCOL_FAILURE:' + $stage + ':' + $_.Exception.GetType().Name)
    exit 50
}
