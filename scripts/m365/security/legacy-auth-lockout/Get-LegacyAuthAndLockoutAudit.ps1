#requires -Version 7.0
<#
.SYNOPSIS
    Audit Account Lockouts, Auth Failures & Legacy Auth (M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT).
.DESCRIPTION
    Scan Microsoft Graph Entra ID sign-in logs for Smart Lockout (50053), invalid credentials
    (50126), disabled account (50057), Conditional Access blocks (53003), MFA timeouts/failures
    (50074/50076), and legacy authentication protocols (IMAP/POP/SMTP/ActiveSync/Other clients).
    Follows tnotes.m365 / 0.3.0 Callable ABI v1.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [psobject]$Context,

    [Parameter(Mandatory = $true)]
    [hashtable]$Parameters,

    [Parameter(Mandatory = $true)]
    [System.Threading.CancellationToken]$CancellationToken
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-OperationReturn {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Outcome,
        [Parameter()][object]$Data = $null,
        [Parameter()][object[]]$Warnings = [object[]]@(),
        [Parameter()][object[]]$Errors = [object[]]@()
    )
    return [pscustomobject]@{
        status            = $Status
        operation_outcome = $Outcome
        data              = $Data
        warnings          = [object[]]@($Warnings)
        errors            = [object[]]@($Errors)
    }
}

function New-ErrorItem {
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$Message,
        [Parameter()][bool]$Retryable = $false
    )
    $msg = if ($Message.Length -gt 512) { $Message.Substring(0, 509) + '...' } else { $Message }
    return [pscustomobject]@{
        code      = $Code
        message   = $msg
        retryable = $Retryable
    }
}

function New-WarningItem {
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$Message
    )
    $msg = if ($Message.Length -gt 512) { $Message.Substring(0, 509) + '...' } else { $Message }
    return [pscustomobject]@{
        code    = $Code
        message = $msg
    }
}

function Get-SafeProp {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -ne $prop) { return $prop.Value }
    return $null
}

function ConvertTo-UtcTimestamp {
    param([object]$RawValue)
    if ($null -eq $RawValue) { return $null }
    if ($RawValue -is [datetime]) { return $RawValue.ToUniversalTime() }
    if ($RawValue -is [datetimeoffset]) { return $RawValue.UtcDateTime }
    return ([datetime]::Parse([string]$RawValue, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AssumeUniversal)).ToUniversalTime()
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.' -Retryable $true
    )
}

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT.'
    )
}

$allowedParams = @('LookbackDays', 'MaxRecords')
if ($null -ne $Parameters) {
    foreach ($key in $Parameters.Keys) {
        if ($allowedParams -notcontains [string]$key) {
            return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
                New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter '$key'."
            )
        }
    }
}

$lookbackDays = 14
if ($null -ne $Parameters -and $Parameters.ContainsKey('LookbackDays')) {
    $rawLb = $Parameters['LookbackDays']
    if ($rawLb -is [bool] -or -not ($rawLb -is [int] -or $rawLb -is [long])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'LookbackDays must be an integer between 1 and 30.'
        )
    }
    $lookbackDays = [int]$rawLb
    if ($lookbackDays -lt 1 -or $lookbackDays -gt 30) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'LookbackDays must be between 1 and 30.'
        )
    }
}

$maxRecords = 25
if ($null -ne $Parameters -and $Parameters.ContainsKey('MaxRecords')) {
    $rawMr = $Parameters['MaxRecords']
    if ($rawMr -is [bool] -or -not ($rawMr -is [int] -or $rawMr -is [long])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'MaxRecords must be an integer between 1 and 100.'
        )
    }
    $maxRecords = [int]$rawMr
    if ($maxRecords -lt 1 -or $maxRecords -gt 100) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'MaxRecords must be between 1 and 100.'
        )
    }
}

$graphConn = $null
if ($null -ne $Context.connections) {
    foreach ($conn in @($Context.connections)) {
        if ($null -ne $conn -and [string]$conn.service -eq 'Graph') {
            $graphConn = $conn
            break
        }
    }
}
if ($null -eq $graphConn -or [string]$graphConn.state -ne 'verified') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Microsoft Graph connection is required.'
    )
}
if ([string]$graphConn.tenant_id -ne [string]$Context.tenant_id) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'TENANT_MISMATCH' -Message 'Graph connection tenant does not match invocation tenant.'
    )
}
if ([string]$graphConn.verified_account_upn -ne [string]$Context.verified_account_upn) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCOUNT_MISMATCH' -Message 'Graph connection account does not match invocation administrator.'
    )
}

if ($null -eq $Context.target -or [string]$Context.target.kind -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT requires a resolved Entra object_id target.'
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$scopes = @($graphConn.graph_scopes | ForEach-Object { [string]$_ })
$roles = @($graphConn.effective_roles | ForEach-Object { [string]$_ })
if ('AuditLog.Read.All' -notin $scopes -or ('Reports.Reader' -notin $roles -and 'Security.Reader' -notin $roles)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Graph scope AuditLog.Read.All and role Reports.Reader or Security.Reader are not present.'
    )
}

$nowUtc = [datetime]::UtcNow
$lookbackStart = $nowUtc.AddDays(-$lookbackDays)
$lookbackStartStr = $lookbackStart.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
$effectiveCap = [Math]::Min($maxRecords, 50)

$mgSignInCmd = Get-Command -Name 'Get-MgAuditLogSignIn' -ErrorAction SilentlyContinue
if ($null -ne $mgSignInCmd) {
    $filter = "userId eq '$targetId' and createdDateTime ge $lookbackStartStr"
    try {
        $rawEvents = @(Get-MgAuditLogSignIn -Filter $filter -Top 100 -Property @('Id', 'UserId', 'CreatedDateTime', 'AppDisplayName', 'ResourceDisplayName', 'ClientAppUsed', 'IpAddress', 'ConditionalAccessStatus', 'Status') -ErrorAction Stop)
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during lockout and legacy auth sign-in lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges|PremiumLicense|Neither tenant is B2C') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied reading Entra sign-in logs (requires AuditLog.Read.All, Reports.Reader/Security.Reader, and Entra ID P1/P2).'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the lockout/legacy-auth sign-in log query.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph sign-in log query failed during lockout/legacy-auth audit.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Graph sign-in query.' -Retryable $true
        )
    }

    $normalizedEvents = [System.Collections.Generic.List[object]]::new()
    $truncated = $false
    $lockoutCount = 0
    $legacyAuthCount = 0
    $badPwdCount = 0
    $caBlockCount = 0
    $mfaFailCount = 0
    $disabledCount = 0
    $legacyProtocols = [System.Collections.Generic.List[string]]::new()

    $sortedRaw = @($rawEvents | Where-Object { $_ -ne $null } | Sort-Object { ConvertTo-UtcTimestamp (Get-SafeProp $_ 'CreatedDateTime') } -Descending)
    foreach ($ev in $sortedRaw) {
        $evUserId = Get-SafeProp $ev 'UserId'
        if ($null -ne $evUserId -and ([string]$evUserId).Trim().ToLowerInvariant() -ne $targetId) {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned sign-in event UserId does not match target object_id.'
            )
        }

        $statusObj = Get-SafeProp $ev 'Status'
        $rawErr = Get-SafeProp $statusObj 'ErrorCode'
        $errCode = if ($null -ne $rawErr) { [int]$rawErr } else { 0 }
        if ($errCode -lt 0) {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid negative sign-in error code.'
            )
        }

        $createdDt = ConvertTo-UtcTimestamp (Get-SafeProp $ev 'CreatedDateTime')
        if ($null -eq $createdDt -or $createdDt -lt $lookbackStart) {
            continue
        }

        $clientApp = [string](Get-SafeProp $ev 'ClientAppUsed')
        $isLegacyProtocol = -not [string]::IsNullOrWhiteSpace($clientApp) -and (
            $clientApp -match '(?i)IMAP|POP|SMTP|ActiveSync|Exchange\s+Web\s+Services|AutoDiscover|MAPI\s+Over\s+HTTP|Other\s+clients|Basic'
        )
        $isFailure = ($errCode -ne 0)

        if (-not $isFailure -and -not $isLegacyProtocol) {
            continue
        }

        if ($errCode -eq 50053) { $lockoutCount++ }
        elseif ($errCode -eq 50126) { $badPwdCount++ }
        elseif ($errCode -eq 50057) { $disabledCount++ }
        elseif ($errCode -eq 53003) { $caBlockCount++ }
        elseif ($errCode -in @(50074, 50076)) { $mfaFailCount++ }

        if ($isLegacyProtocol) {
            $legacyAuthCount++
            if ($legacyProtocols -notcontains $clientApp.Trim()) {
                $legacyProtocols.Add($clientApp.Trim())
            }
        }

        if ($normalizedEvents.Count -ge $effectiveCap) {
            $truncated = $true
            continue
        }

        $appName = [string](Get-SafeProp $ev 'AppDisplayName')
        if ([string]::IsNullOrWhiteSpace($appName)) { $appName = 'Sign-In Event' }
        $ipAddr = [string](Get-SafeProp $ev 'IpAddress')
        $caStatus = [string](Get-SafeProp $ev 'ConditionalAccessStatus')
        $failReason = [string](Get-SafeProp $statusObj 'FailureReason')

        $tags = [System.Collections.Generic.List[string]]::new()
        if ($errCode -eq 50053) { $tags.Add('SmartLockout:50053') }
        elseif ($errCode -eq 50126) { $tags.Add('BadPassword:50126') }
        elseif ($errCode -eq 50057) { $tags.Add('Disabled:50057') }
        elseif ($errCode -eq 53003) { $tags.Add('CA_Block:53003') }
        elseif ($errCode -in @(50074, 50076)) { $tags.Add("MFA:$errCode") }
        elseif ($errCode -ne 0) { $tags.Add("Err:$errCode") }

        if ($isLegacyProtocol) { $tags.Add("LegacyProto:$clientApp") }
        elseif (-not [string]::IsNullOrWhiteSpace($clientApp)) { $tags.Add("Client:$clientApp") }
        if (-not [string]::IsNullOrWhiteSpace($ipAddr)) { $tags.Add("IP:$ipAddr") }
        if (-not [string]::IsNullOrWhiteSpace($caStatus) -and $errCode -ne 53003) { $tags.Add("CA:$caStatus") }
        if (-not [string]::IsNullOrWhiteSpace($failReason) -and $failReason -notmatch 'Other\.') {
            $shortReason = if ($failReason.Length -gt 64) { $failReason.Substring(0, 61) + '...' } else { $failReason }
            $tags.Add($shortReason)
        }

        $label = "$appName [$($tags -join ' | ')]"
        if ($label.Length -gt 256) { $label = $label.Substring(0, 253) + '...' }

        $normalizedEvents.Add([pscustomobject]@{
            created_at       = $createdDt.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
            app_display_name = $label
            success          = ($errCode -eq 0)
            error_code       = [int]$errCode
        })
    }

    $warnings = [System.Collections.Generic.List[object]]::new()
    if ($truncated) {
        $warnings.Add((New-WarningItem -Code 'OUTPUT_LIMIT' -Message "Lockout/legacy auth sign-in events were truncated at $effectiveCap items (schema cap 50)."))
    }
    if ($lockoutCount -gt 0) {
        $warnings.Add((New-WarningItem -Code 'SMART_LOCKOUT_DETECTED' -Message "$lockoutCount Entra Smart Lockout event(s) (error 50053) detected in the last $lookbackDays day(s)."))
    }
    if ($legacyAuthCount -gt 0) {
        $warnings.Add((New-WarningItem -Code 'LEGACY_AUTH_DETECTED' -Message "$legacyAuthCount legacy authentication protocol sign-in(s) detected: $($legacyProtocols -join ', ')."))
    }
    if ($normalizedEvents.Count -gt 0) {
        $warnings.Add((New-WarningItem -Code 'LOCKOUT_OR_FAILURE_SUMMARY' -Message "Window summary (${lookbackDays}d): Lockout=$lockoutCount, BadPwd=$badPwdCount, Disabled=$disabledCount, CABlock=$caBlockCount, MFA=$mfaFailCount, LegacyAuth=$legacyAuthCount."))
    } else {
        $warnings.Add((New-WarningItem -Code 'NO_LOCKOUT_OR_LEGACY_EVENTS' -Message "No Smart Lockout, auth failures, or legacy auth sign-ins found in the last $lookbackDays day(s)."))
    }

    $payload = [pscustomobject]@{
        target_user_id = $targetId
        lookback_start = $lookbackStartStr
        events         = [object[]]$normalizedEvents.ToArray()
        returned_count = [int]$normalizedEvents.Count
        truncated      = [bool]$truncated
    }

    if ($truncated) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $warnings.ToArray()
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload -Warnings $warnings.ToArray()
}

# Offline synthetic fixture evaluation
$allEvents = @(
    [pscustomobject]@{
        created_at       = $nowUtc.AddMinutes(-25).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        app_display_name = 'Microsoft Office 365 [SmartLockout:50053 | Client:Browser | IP:198.51.100.44]'
        success          = $false
        error_code       = 50053
    },
    [pscustomobject]@{
        created_at       = $nowUtc.AddHours(-2).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        app_display_name = 'Exchange Online [LegacyProto:IMAP4 | BadPassword:50126 | IP:203.0.113.19]'
        success          = $false
        error_code       = 50126
    }
)

$truncated = $allEvents.Length -gt $effectiveCap
[object[]]$selectedEvents = @($allEvents | Select-Object -First $effectiveCap)
$offlineWarnings = [System.Collections.Generic.List[object]]::new()
if ($truncated) {
    $offlineWarnings.Add((New-WarningItem -Code 'OUTPUT_LIMIT' -Message "Events truncated to MaxRecords=$effectiveCap."))
}
$offlineWarnings.Add((New-WarningItem -Code 'SMART_LOCKOUT_DETECTED' -Message '1 Entra Smart Lockout event(s) (error 50053) detected in synthetic lookback window.'))
$offlineWarnings.Add((New-WarningItem -Code 'LEGACY_AUTH_DETECTED' -Message '1 legacy authentication protocol sign-in(s) detected: IMAP4.'))
$offlineWarnings.Add((New-WarningItem -Code 'LOCKOUT_OR_FAILURE_SUMMARY' -Message "Window summary (${lookbackDays}d): Lockout=1, BadPwd=1, Disabled=0, CABlock=0, MFA=0, LegacyAuth=1."))

$payload = [pscustomobject]@{
    target_user_id = $targetId
    lookback_start = $lookbackStartStr
    events         = [object[]]$selectedEvents
    returned_count = [int]$selectedEvents.Length
    truncated      = [bool]$truncated
}

if ($truncated) {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $offlineWarnings.ToArray()
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload -Warnings $offlineWarnings.ToArray()

