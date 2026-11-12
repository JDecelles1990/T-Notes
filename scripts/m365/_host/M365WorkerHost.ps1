<#
.SYNOPSIS
    Persistent isolated PowerShell 7 worker host for T-Notes M365 live authentication and pilot execution.
.DESCRIPTION
    Communicates with the Python host over UTF-8 line-delimited JSON on stdin/stdout.
    Redirects Console.Out to a synchronized intercept writer before importing or running
    third-party M365 modules so device-code prompts and module notices emit structured JSON
    events without corrupting the protocol stream.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Force UTF-8 (no BOM) for protocol frames before grabbing the raw Console.Out writer.
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$script:ProtocolOut = [System.IO.TextWriter]::Synchronized([Console]::Out)
$script:ProtocolLock = [object]::new()
$script:ActiveRequestId = ''
$script:ActiveRequestKind = ''
$script:ProtocolInitialized = $false
$script:CancellationMap = [System.Collections.Concurrent.ConcurrentDictionary[string, System.Threading.CancellationTokenSource]]::new()
$script:CommandQueue = [System.Collections.Concurrent.BlockingCollection[object]]::new()
$script:InputEof = $false

function Write-ProtocolFrame {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Frame
    )
    $json = ConvertTo-Json -InputObject $Frame -Depth 25 -Compress
    [System.Threading.Monitor]::Enter($script:ProtocolLock)
    try {
        $script:ProtocolOut.WriteLine($json)
        $script:ProtocolOut.Flush()
    }
    finally {
        [System.Threading.Monitor]::Exit($script:ProtocolLock)
    }
}

function Hide-SensitiveText {
    param([AllowEmptyString()][string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return '' }
    $redacted = [regex]::Replace($Text, '(?i)(bearer\s+)[A-Za-z0-9._-]+', '$1[REDACTED]')
    $redacted = [regex]::Replace($redacted, 'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*', '[REDACTED_JWT]')
    $redacted = [regex]::Replace($redacted, '(?i)(client_secret|refresh_token|access_token|password|secret)\s*[:=]\s*\S+', '$1=[REDACTED]')
    if ($redacted.Length -gt 512) {
        return $redacted.Substring(0, 512)
    }
    return $redacted
}

$script:DeviceUrlRegex = [regex]::new('(https://(?:microsoft\.com/devicelogin|login\.microsoftonline\.com/[^\s]*devicelogin[^\s]*))', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
$script:DeviceCodeRegex = [regex]::new('(?:enter the code|code)\s+([A-Z0-9]{6,15})\b', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)

Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Text;

public sealed class M365ConsoleInterceptWriter : TextWriter
{
    private readonly Action<string> _onLine;
    private readonly StringBuilder _buffer = new StringBuilder();
    private readonly object _sync = new object();

    public M365ConsoleInterceptWriter(Action<string> onLine)
    {
        _onLine = onLine;
    }

    public override Encoding Encoding => new UTF8Encoding(false);

    public override void Write(char value)
    {
        lock (_sync)
        {
            if (value == '\n' || value == '\r')
            {
                FlushBuffer();
            }
            else
            {
                _buffer.Append(value);
            }
        }
    }

    public override void Write(string value)
    {
        if (string.IsNullOrEmpty(value)) { return; }
        lock (_sync)
        {
            foreach (char ch in value)
            {
                if (ch == '\n' || ch == '\r')
                {
                    FlushBuffer();
                }
                else
                {
                    _buffer.Append(ch);
                }
            }
        }
    }

    public override void WriteLine(string value)
    {
        Write(value);
        lock (_sync)
        {
            FlushBuffer();
        }
    }

    public override void Flush()
    {
        lock (_sync)
        {
            FlushBuffer();
        }
    }

    private void FlushBuffer()
    {
        if (_buffer.Length == 0) { return; }
        string line = _buffer.ToString().Trim();
        _buffer.Clear();
        if (!string.IsNullOrEmpty(line))
        {
            _onLine(line);
        }
    }
}
"@

$onConsoleLine = [System.Action[string]]{
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line)) { return }

    $safe = Hide-SensitiveText -Text $Line
    $reqId = $script:ActiveRequestId
    $reqKind = $script:ActiveRequestKind

    $urlMatch = $script:DeviceUrlRegex.Match($safe)
    $codeMatch = $script:DeviceCodeRegex.Match($safe)
    if ($urlMatch.Success -or $codeMatch.Success) {
        Write-ProtocolFrame -Frame @{
            type             = 'event'
            event            = 'device_code'
            request_id       = $reqId
            verification_uri = if ($urlMatch.Success) { $urlMatch.Groups[1].Value } else { 'https://microsoft.com/devicelogin' }
            user_code        = if ($codeMatch.Success) { $codeMatch.Groups[1].Value } else { '' }
            message          = $safe
        }
        return
    }

    if ($reqKind -in @('connect_graph', 'connect_exchange')) {
        Write-ProtocolFrame -Frame @{
            type       = 'event'
            event      = 'auth_notice'
            request_id = $reqId
            message    = $safe
        }
    }
}

$script:InterceptWriter = [M365ConsoleInterceptWriter]::new($onConsoleLine)
[Console]::SetOut($script:InterceptWriter)

function Parse-ModuleVersion {
    param([string]$RawVersion)
    $clean = ([string]$RawVersion).Split('-')[0].Trim()
    return [version]::Parse($clean)
}

function Import-RequiredModuleStrict {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [string]$MinimumVersion = '0.0.0',
        [string]$MaximumVersion = '999.999.999'
    )

    $minVer = Parse-ModuleVersion -RawVersion $MinimumVersion
    $maxVer = Parse-ModuleVersion -RawVersion $MaximumVersion

    # If an acceptable version is already loaded in session, reuse it without re-importing.
    $loaded = @(Get-Module -Name $Name | Where-Object {
        $_.Version -ge $minVer -and $_.Version -le $maxVer
    } | Sort-Object Version -Descending)
    if ($loaded.Count -gt 0) {
        return $loaded[0]
    }

    $available = @(Get-Module -Name $Name -ListAvailable | Where-Object {
        $_.Version -ge $minVer -and $_.Version -le $maxVer
    } | Sort-Object Version -Descending)
    if ($available.Count -eq 0) {
        throw [System.InvalidOperationException]::new("MODULE_MISSING::$Name ($MinimumVersion..$MaximumVersion)")
    }

    $chosen = $available[0]
    Import-Module -FullyQualifiedName @{
        ModuleName      = $Name
        RequiredVersion = $chosen.Version
    } -Global -ErrorAction Stop | Out-Null
    return $chosen
}

function Ensure-ProtocolInitialized {
    param([string]$ProtocolPath)
    if ($script:ProtocolInitialized) { return }
    if ([string]::IsNullOrWhiteSpace($ProtocolPath) -or -not (Test-Path -LiteralPath $ProtocolPath -PathType Leaf)) {
        throw [System.InvalidOperationException]::new('CONTRACT_VIOLATION::Protocol adapter path is invalid.')
    }
    . $ProtocolPath
    Initialize-NativeReturnValidation
    $script:ProtocolInitialized = $true
}

function New-HostOperationFailure {
    param(
        [Parameter(Mandatory)][string]$Code,
        [Parameter(Mandatory)][string]$Message,
        [bool]$Retryable = $false
    )
    return @{
        status            = 'error'
        operation_outcome = 'failed'
        data              = $null
        warnings          = @()
        errors            = @(
            @{
                code      = $Code
                message   = (Hide-SensitiveText -Text $Message)
                retryable = $Retryable
            }
        )
    }
}

function Test-GraphContextMatch {
    param(
        [string]$ExpectedTenantId,
        [string]$ExpectedUpn
    )
    $getCtxCmd = Get-Command -Name 'Get-MgContext' -ErrorAction SilentlyContinue
    if ($null -eq $getCtxCmd) {
        return @{ ok = $false; code = 'MODULE_MISSING'; message = 'Microsoft.Graph.Authentication is not loaded.' }
    }
    $ctx = Get-MgContext
    if ($null -eq $ctx -or [string]::IsNullOrWhiteSpace([string]$ctx.TenantId) -or [string]::IsNullOrWhiteSpace([string]$ctx.Account)) {
        return @{ ok = $false; code = 'AUTH_REQUIRED'; message = 'Microsoft Graph session is not connected.' }
    }
    $actualTenant = ([string]$ctx.TenantId).Trim().ToLowerInvariant()
    $wantTenant = ([string]$ExpectedTenantId).Trim().ToLowerInvariant()
    if ($actualTenant -ne $wantTenant) {
        return @{
            ok      = $false
            code    = 'TENANT_MISMATCH'
            message = "Microsoft Graph connected to unexpected tenant '$actualTenant' instead of '$wantTenant'."
            actual_tenant_id = $actualTenant
            actual_upn       = [string]$ctx.Account
        }
    }
    $actualUpn = ([string]$ctx.Account).Trim()
    $wantUpn = ([string]$ExpectedUpn).Trim()
    if ($actualUpn.ToLowerInvariant() -ne $wantUpn.ToLowerInvariant()) {
        return @{
            ok      = $false
            code    = 'ACCOUNT_MISMATCH'
            message = "Microsoft Graph connected as '$actualUpn' instead of '$wantUpn'."
            actual_tenant_id = $actualTenant
            actual_upn       = $actualUpn
        }
    }
    $scopes = @()
    if ($null -ne $ctx.Scopes) {
        $scopes = @($ctx.Scopes | ForEach-Object { [string]$_ })
    }
    return @{
        ok         = $true
        tenant_id  = $actualTenant
        account_upn = $actualUpn
        scopes     = $scopes
        auth_type  = [string]$ctx.AuthType
    }
}

function Test-ExchangeContextMatch {
    param(
        [string]$ExpectedTenantId,
        [string]$ExpectedUpn
    )
    $getConnCmd = Get-Command -Name 'Get-ConnectionInformation' -ErrorAction SilentlyContinue
    if ($null -eq $getConnCmd) {
        return @{ ok = $false; code = 'MODULE_MISSING'; message = 'ExchangeOnlineManagement is not loaded.' }
    }
    $conns = @(Get-ConnectionInformation | Where-Object { ([string]$_.State) -eq 'Connected' })
    if ($conns.Count -eq 0) {
        return @{ ok = $false; code = 'AUTH_REQUIRED'; message = 'Exchange Online session is not connected.' }
    }
    $active = $conns[0]
    $actualTenant = ([string]$active.TenantID).Trim().ToLowerInvariant()
    $wantTenant = ([string]$ExpectedTenantId).Trim().ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($actualTenant) -or $actualTenant -ne $wantTenant) {
        return @{
            ok      = $false
            code    = 'TENANT_MISMATCH'
            message = "Exchange Online connected to unexpected tenant '$actualTenant' instead of '$wantTenant'."
            actual_tenant_id = $actualTenant
            actual_upn       = [string]$active.UserPrincipalName
        }
    }
    $actualUpn = ([string]$active.UserPrincipalName).Trim()
    $wantUpn = ([string]$ExpectedUpn).Trim()
    if ([string]::IsNullOrWhiteSpace($actualUpn) -or $actualUpn.ToLowerInvariant() -ne $wantUpn.ToLowerInvariant()) {
        return @{
            ok      = $false
            code    = 'ACCOUNT_MISMATCH'
            message = "Exchange Online connected as '$actualUpn' instead of '$wantUpn'."
            actual_tenant_id = $actualTenant
            actual_upn       = $actualUpn
        }
    }

    $roles = [System.Collections.Generic.List[string]]::new()
    if ($null -ne (Get-Command -Name 'Get-EXOMailbox' -ErrorAction SilentlyContinue)) {
        $roles.Add('cmdlet.Get-EXOMailbox')
    }
    if ($null -ne (Get-Command -Name 'Get-EXOMailboxStatistics' -ErrorAction SilentlyContinue)) {
        $roles.Add('cmdlet.Get-EXOMailboxStatistics')
    }

    return @{
        ok              = $true
        tenant_id       = $actualTenant
        account_upn     = $actualUpn
        effective_roles = @($roles)
    }
}

function Invoke-ConnectGraphCommand {
    param([string]$RequestId, $Req)
    $mod = if ($Req.module) { $Req.module } else { @{ name = 'Microsoft.Graph.Authentication'; minimum_version = '2.0.0'; maximum_version = '2.99.999' } }
    Import-RequiredModuleStrict -Name ([string]$mod.name) -MinimumVersion ([string]$mod.minimum_version) -MaximumVersion ([string]$mod.maximum_version) | Out-Null

    try { Disconnect-MgGraph -ErrorAction SilentlyContinue | Out-Null } catch {}

    $cmd = Get-Command -Name 'Connect-MgGraph' -ErrorAction Stop
    $params = @{
        TenantId    = ([string]$Req.tenant_id).Trim()
        ErrorAction = 'Stop'
    }
    if ($cmd.Parameters.ContainsKey('NoWelcome')) { $params['NoWelcome'] = $true }
    if ($cmd.Parameters.ContainsKey('ContextScope')) { $params['ContextScope'] = 'Process' }

    $scopes = @($Req.scopes | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ })
    if ($scopes.Count -gt 0) {
        $params['Scopes'] = $scopes
    }

    $authMode = ([string]$Req.auth_mode).Trim().ToLowerInvariant()
    if ($authMode -eq 'device_code') {
        $params['UseDeviceCode'] = $true
    } elseif ($cmd.Parameters.ContainsKey('LoginHint') -and -not [string]::IsNullOrWhiteSpace([string]$Req.expected_account_upn)) {
        $params['LoginHint'] = ([string]$Req.expected_account_upn).Trim()
    }

    Connect-MgGraph @params | Out-Null
    $script:InterceptWriter.Flush()

    $check = Test-GraphContextMatch -ExpectedTenantId ([string]$Req.tenant_id) -ExpectedUpn ([string]$Req.expected_account_upn)
    if (-not $check.ok) {
        try { Disconnect-MgGraph -ErrorAction SilentlyContinue | Out-Null } catch {}
        return @{ ok = $false; code = $check.code; message = $check.message }
    }

    return @{
        ok   = $true
        data = @{
            service     = 'Graph'
            tenant_id   = $check.tenant_id
            account_upn = $check.account_upn
            scopes      = $check.scopes
            auth_mode   = $authMode
            verified    = $true
        }
    }
}

function Invoke-ConnectExchangeCommand {
    param([string]$RequestId, $Req)
    $mod = if ($Req.module) { $Req.module } else { @{ name = 'ExchangeOnlineManagement'; minimum_version = '3.0.0'; maximum_version = '3.99.999' } }
    Import-RequiredModuleStrict -Name ([string]$mod.name) -MinimumVersion ([string]$mod.minimum_version) -MaximumVersion ([string]$mod.maximum_version) | Out-Null

    try { Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch {}

    $cmd = Get-Command -Name 'Connect-ExchangeOnline' -ErrorAction Stop
    $params = @{
        ErrorAction = 'Stop'
    }
    if ($cmd.Parameters.ContainsKey('ShowBanner')) { $params['ShowBanner'] = $false }
    if ($cmd.Parameters.ContainsKey('ShowProgress')) { $params['ShowProgress'] = $false }

    $authMode = ([string]$Req.auth_mode).Trim().ToLowerInvariant()
    if ($authMode -eq 'device_code') {
        if (-not $cmd.Parameters.ContainsKey('Device')) {
            return @{ ok = $false; code = 'INVALID_PARAMETER'; message = 'Installed ExchangeOnlineManagement module does not support -Device auth.' }
        }
        $params['Device'] = $true
    } elseif ($cmd.Parameters.ContainsKey('UserPrincipalName') -and -not [string]::IsNullOrWhiteSpace([string]$Req.expected_account_upn)) {
        $params['UserPrincipalName'] = ([string]$Req.expected_account_upn).Trim()
    }

    if ($cmd.Parameters.ContainsKey('Organization') -and -not [string]::IsNullOrWhiteSpace([string]$Req.organization)) {
        $params['Organization'] = ([string]$Req.organization).Trim()
    }

    Connect-ExchangeOnline @params | Out-Null
    $script:InterceptWriter.Flush()

    $check = Test-ExchangeContextMatch -ExpectedTenantId ([string]$Req.tenant_id) -ExpectedUpn ([string]$Req.expected_account_upn)
    if (-not $check.ok) {
        try { Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch {}
        return @{ ok = $false; code = $check.code; message = $check.message }
    }

    return @{
        ok   = $true
        data = @{
            service         = 'ExchangeOnline'
            tenant_id       = $check.tenant_id
            account_upn     = $check.account_upn
            effective_roles = $check.effective_roles
            auth_mode       = $authMode
            verified        = $true
        }
    }
}

function Invoke-VerifyContextCommand {
    param($Req)
    $results = @{}
    foreach ($svc in @($Req.services)) {
        $svcName = [string]$svc
        if ($svcName -eq 'Graph') {
            $results['Graph'] = Test-GraphContextMatch -ExpectedTenantId ([string]$Req.tenant_id) -ExpectedUpn ([string]$Req.expected_account_upn)
        } elseif ($svcName -eq 'ExchangeOnline') {
            $results['ExchangeOnline'] = Test-ExchangeContextMatch -ExpectedTenantId ([string]$Req.tenant_id) -ExpectedUpn ([string]$Req.expected_account_upn)
        }
    }
    return @{ ok = $true; data = $results }
}

function Invoke-OperationCommand {
    param([string]$RequestId, $Req)
    Ensure-ProtocolInitialized -ProtocolPath ([string]$Req.protocol_path)

    $scriptPath = [string]$Req.script_path
    if ([string]::IsNullOrWhiteSpace($scriptPath) -or -not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        return @{
            ok   = $true
            data = (New-HostOperationFailure -Code 'CONTRACT_VIOLATION' -Message 'Target script file was not found.')
        }
    }

    # Fail-closed module check BEFORE invoking the operation script so scripts never fall back to synthetic fixtures.
    foreach ($mod in @($Req.required_modules)) {
        try {
            Import-RequiredModuleStrict -Name ([string]$mod.name) -MinimumVersion ([string]$mod.minimum_version) -MaximumVersion ([string]$mod.maximum_version) | Out-Null
        }
        catch {
            return @{
                ok   = $true
                data = (New-HostOperationFailure -Code 'MODULE_MISSING' -Message "Required PowerShell module '$($mod.name)' ($($mod.minimum_version)..$($mod.maximum_version)) is missing or out of range.")
            }
        }
    }

    $ctx = $Req.context
    $expectedTenant = [string]$ctx.tenant_id
    $expectedUpn = [string]$ctx.verified_account_upn

    foreach ($svc in @($Req.connection_requirements)) {
        $svcName = [string]$svc
        if ($svcName -eq 'Graph') {
            $check = Test-GraphContextMatch -ExpectedTenantId $expectedTenant -ExpectedUpn $expectedUpn
            if (-not $check.ok) {
                return @{ ok = $true; data = (New-HostOperationFailure -Code $check.code -Message $check.message) }
            }
        } elseif ($svcName -eq 'ExchangeOnline') {
            $check = Test-ExchangeContextMatch -ExpectedTenantId $expectedTenant -ExpectedUpn $expectedUpn
            if (-not $check.ok) {
                return @{ ok = $true; data = (New-HostOperationFailure -Code $check.code -Message $check.message) }
            }
        }
    }

    foreach ($cmdName in @($Req.required_cmdlets)) {
        $resolvedCmd = Get-Command -Name ([string]$cmdName) -ErrorAction SilentlyContinue
        if ($null -eq $resolvedCmd) {
            return @{
                ok   = $true
                data = (New-HostOperationFailure -Code 'MODULE_MISSING' -Message "Required Microsoft cmdlet '$cmdName' is unavailable in the live session.")
            }
        }
    }

    $params = @{}
    if ($null -ne $Req.parameters) {
        foreach ($prop in $Req.parameters.PSObject.Properties) {
            $params[$prop.Name] = $prop.Value
        }
    }

    $cts = [System.Threading.CancellationTokenSource]::new()
    $null = $script:CancellationMap.TryAdd($RequestId, $cts)
    try {
        if ([bool]$Req.already_cancelled) {
            $cts.Cancel()
        }
        $ret = & $scriptPath -Context $ctx -Parameters $params -CancellationToken $cts.Token
        Assert-NativeOperationReturn $ret
        return @{ ok = $true; data = $ret }
    }
    finally {
        $removed = $null
        $null = $script:CancellationMap.TryRemove($RequestId, [ref]$removed)
        $cts.Dispose()
    }
}

function Invoke-DisconnectCommand {
    param($Req)
    $services = @($Req.services)
    if ($services.Count -eq 0) {
        $services = @('Graph', 'ExchangeOnline')
    }
    foreach ($svc in $services) {
        $svcName = [string]$svc
        if ($svcName -eq 'Graph') {
            if ($null -ne (Get-Command -Name 'Disconnect-MgGraph' -ErrorAction SilentlyContinue)) {
                try { Disconnect-MgGraph -ErrorAction SilentlyContinue | Out-Null } catch {}
            }
        } elseif ($svcName -eq 'ExchangeOnline') {
            if ($null -ne (Get-Command -Name 'Disconnect-ExchangeOnline' -ErrorAction SilentlyContinue)) {
                try { Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch {}
            }
        }
    }
    return @{ ok = $true; data = @{ disconnected = $services } }
}

# Dedicated stdin reader runspace so cancel commands are handled even while an operation or auth blocks.
$script:StdinRunspace = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspace()
$script:StdinRunspace.Open()
$script:StdinPowerShell = [System.Management.Automation.PowerShell]::Create()
$script:StdinPowerShell.Runspace = $script:StdinRunspace
$null = $script:StdinPowerShell.AddScript({
    param($Queue, $CancelMap)
    while ($true) {
        $line = [Console]::In.ReadLine()
        if ($null -eq $line) {
            $Queue.Add([pscustomobject]@{ cmd = '__eof__'; id = '' })
            break
        }
        $trimmed = $line.Trim()
        if ([string]::IsNullOrEmpty($trimmed)) { continue }
        try {
            $obj = ConvertFrom-Json -InputObject $trimmed -Depth 25
            if ([string]$obj.cmd -eq 'cancel') {
                $targetId = [string]$obj.target_id
                $cts = $null
                if (-not [string]::IsNullOrWhiteSpace($targetId) -and $CancelMap.TryGetValue($targetId, [ref]$cts)) {
                    $cts.Cancel()
                }
                else {
                    foreach ($entry in $CancelMap.Values) {
                        try { $entry.Cancel() } catch {}
                    }
                }
                continue
            }
            $Queue.Add($obj)
        }
        catch {
            $Queue.Add([pscustomobject]@{ cmd = '__invalid_json__'; id = '' })
        }
    }
}).AddArgument($script:CommandQueue).AddArgument($script:CancellationMap)
$script:StdinAsync = $script:StdinPowerShell.BeginInvoke()

Write-ProtocolFrame -Frame @{
    type       = 'event'
    event      = 'ready'
    pid        = $PID
    ps_version = [string]$PSVersionTable.PSVersion
}

try {
    foreach ($req in $script:CommandQueue.GetConsumingEnumerable()) {
        $cmdName = [string]$req.cmd
        $reqId = [string]$req.id

        if ($cmdName -eq '__eof__' -or $cmdName -eq 'shutdown') {
            if ($cmdName -eq 'shutdown') {
                try { Invoke-DisconnectCommand -Req ([pscustomobject]@{ services = @('Graph', 'ExchangeOnline') }) | Out-Null } catch {}
                Write-ProtocolFrame -Frame @{ type = 'response'; id = $reqId; ok = $true; data = @{ stopped = $true } }
            }
            break
        }

        if ($cmdName -eq '__invalid_json__') {
            Write-ProtocolFrame -Frame @{ type = 'response'; id = $reqId; ok = $false; code = 'CONTRACT_VIOLATION'; message = 'Malformed JSON request frame.' }
            continue
        }

        $script:ActiveRequestId = $reqId
        $script:ActiveRequestKind = $cmdName
        try {
            $outcome = switch ($cmdName) {
                'ping' {
                    @{
                        ok   = $true
                        data = @{
                            pid        = $PID
                            ps_version = [string]$PSVersionTable.PSVersion
                        }
                    }
                }
                'connect_graph' {
                    Invoke-ConnectGraphCommand -RequestId $reqId -Req $req
                }
                'connect_exchange' {
                    Invoke-ConnectExchangeCommand -RequestId $reqId -Req $req
                }
                'verify_context' {
                    Invoke-VerifyContextCommand -Req $req
                }
                'invoke_operation' {
                    Invoke-OperationCommand -RequestId $reqId -Req $req
                }
                'disconnect' {
                    Invoke-DisconnectCommand -Req $req
                }
                default {
                    @{ ok = $false; code = 'CONTRACT_VIOLATION'; message = "Unsupported host command '$cmdName'." }
                }
            }

            if ($outcome.ok) {
                Write-ProtocolFrame -Frame @{
                    type = 'response'
                    id   = $reqId
                    ok   = $true
                    data = $outcome.data
                }
            }
            else {
                Write-ProtocolFrame -Frame @{
                    type    = 'response'
                    id      = $reqId
                    ok      = $false
                    code    = [string]$outcome.code
                    message = (Hide-SensitiveText -Text ([string]$outcome.message))
                }
            }
        }
        catch {
            $errText = Hide-SensitiveText -Text $_.Exception.Message
            $errCode = 'INTERNAL_ERROR'
            if ($errText -match '^MODULE_MISSING::(.*)$') {
                $errCode = 'MODULE_MISSING'
                $errText = "Required module missing: $($Matches[1])"
            }
            elseif ($errText -match '^CONTRACT_VIOLATION::(.*)$') {
                $errCode = 'CONTRACT_VIOLATION'
                $errText = $Matches[1]
            }
            Write-ProtocolFrame -Frame @{
                type    = 'response'
                id      = $reqId
                ok      = $false
                code    = $errCode
                message = $errText
            }
        }
        finally {
            try { $script:InterceptWriter.Flush() } catch {}
            $script:ActiveRequestId = ''
            $script:ActiveRequestKind = ''
        }
    }
}
finally {
    try { $script:CommandQueue.CompleteAdding() } catch {}
    try { $script:StdinPowerShell.Dispose() } catch {}
    try { $script:StdinRunspace.Dispose() } catch {}
}

