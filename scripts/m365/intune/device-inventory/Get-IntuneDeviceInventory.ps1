#requires -Version 7.0
<#
.SYNOPSIS
    Inventory Endpoint Devices & OS Posture from Sign-Ins (M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE).
.DESCRIPTION
    Catalog distinct client endpoints observed in Entra ID sign-in DeviceDetail telemetry
    (OperatingSystem, Browser, TrustType, IsManaged, IsCompliant), flagging unmanaged BYOD
    and non-compliant device sign-ins.
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

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE.'
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
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE requires a resolved Entra object_id target.'
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
$telemetryWarning = New-WarningItem -Code 'TELEMETRY_SCOPE' -Message "Endpoint device inventory is inferred from Entra ID sign-in DeviceDetail telemetry over the last ${lookbackDays}d (not direct Intune MDM APIs)."

$mgSignInCmd = Get-Command -Name 'Get-MgAuditLogSignIn' -ErrorAction SilentlyContinue
if ($null -ne $mgSignInCmd) {
    $filter = "userId eq '$targetId' and createdDateTime ge $lookbackStartStr"
    try {
        $rawEvents = @(Get-MgAuditLogSignIn -Filter $filter -Top 100 -Property @('Id', 'UserId', 'CreatedDateTime', 'AppDisplayName', 'DeviceDetail', 'ConditionalAccessStatus', 'Status') -ErrorAction Stop)
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during endpoint device telemetry query.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges|PremiumLicense|Neither tenant is B2C') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied reading Entra sign-in logs for device inventory (requires AuditLog.Read.All, Reports.Reader/Security.Reader, and Entra ID P1/P2).'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the device inventory sign-in query.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph sign-in query failed while inspecting device inventory.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after device inventory telemetry query.' -Retryable $true
        )
    }

    $normalizedEvents = [System.Collections.Generic.List[object]]::new()
    $distinctDevices = @{}
    $distinctSummaries = [System.Collections.Generic.List[string]]::new()
    $osCounts = @{}
    $unmanagedKeys = @{}
    $nonCompliantKeys = @{}
    $truncated = $false

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

        $dev = Get-SafeProp $ev 'DeviceDetail'
        if ($null -eq $dev) { continue }

        $devId = ([string](Get-SafeProp $dev 'DeviceId')).Trim()
        $devName = ([string](Get-SafeProp $dev 'DisplayName')).Trim()
        $devOs = ([string](Get-SafeProp $dev 'OperatingSystem')).Trim()
        $browser = ([string](Get-SafeProp $dev 'Browser')).Trim()
        $trustType = ([string](Get-SafeProp $dev 'TrustType')).Trim()
        $isManaged = Get-SafeProp $dev 'IsManaged'
        $isCompliant = Get-SafeProp $dev 'IsCompliant'

        $hasAnyDeviceField = (-not [string]::IsNullOrWhiteSpace($devId)) -or
            (-not [string]::IsNullOrWhiteSpace($devName)) -or
            (-not [string]::IsNullOrWhiteSpace($devOs)) -or
            (-not [string]::IsNullOrWhiteSpace($browser)) -or
            (-not [string]::IsNullOrWhiteSpace($trustType)) -or
            ($null -ne $isManaged) -or
            ($null -ne $isCompliant)

        if (-not $hasAnyDeviceField) { continue }

        $endpointKey = if (-not [string]::IsNullOrWhiteSpace($devId)) {
            $devId.ToLowerInvariant()
        } else {
            "$devName|$devOs|$trustType|$browser".ToLowerInvariant()
        }

        if (-not $distinctDevices.ContainsKey($endpointKey)) {
            $distinctDevices[$endpointKey] = $true
            $osLabel = if (-not [string]::IsNullOrWhiteSpace($devOs)) { $devOs } else { 'Unknown OS' }
            if ($osCounts.ContainsKey($osLabel)) { $osCounts[$osLabel]++ } else { $osCounts[$osLabel] = 1 }

            $epName = if (-not [string]::IsNullOrWhiteSpace($devName)) { $devName } elseif (-not [string]::IsNullOrWhiteSpace($devId)) { "Device:$devId" } else { 'Unnamed Endpoint' }
            $epFlags = [System.Collections.Generic.List[string]]::new()
            $epFlags.Add($osLabel)
            if (-not [string]::IsNullOrWhiteSpace($trustType)) { $epFlags.Add($trustType) }
            if ($null -ne $isManaged) { $epFlags.Add("Managed=$isManaged") }
            if ($null -ne $isCompliant) { $epFlags.Add("Compliant=$isCompliant") }
            if ($distinctSummaries.Count -lt 6) {
                $distinctSummaries.Add("$epName ($($epFlags -join ', '))")
            }
        }

        if ($isManaged -eq $false) { $unmanagedKeys[$endpointKey] = $true }
        if ($isCompliant -eq $false) { $nonCompliantKeys[$endpointKey] = $true }

        if ($normalizedEvents.Count -ge $effectiveCap) {
            $truncated = $true
            continue
        }

        $appName = ([string](Get-SafeProp $ev 'AppDisplayName')).Trim()
        if ([string]::IsNullOrWhiteSpace($appName)) { $appName = 'Client Sign-In' }
        $tags = [System.Collections.Generic.List[string]]::new()
        if (-not [string]::IsNullOrWhiteSpace($devName)) { $tags.Add("Device:$devName") }
        if (-not [string]::IsNullOrWhiteSpace($devOs)) { $tags.Add("OS:$devOs") }
        if (-not [string]::IsNullOrWhiteSpace($browser)) { $tags.Add("Browser:$browser") }
        if (-not [string]::IsNullOrWhiteSpace($trustType)) { $tags.Add("Trust:$trustType") }
        if ($null -ne $isManaged) { $tags.Add("Managed:$isManaged") }
        if ($null -ne $isCompliant) { $tags.Add("Compliant:$isCompliant") }
        $label = if ($tags.Count -gt 0) { "$appName [$($tags -join ' | ')]" } else { $appName }
        if ($label.Length -gt 256) { $label = $label.Substring(0, 253) + '...' }

        $normalizedEvents.Add([pscustomobject]@{
            created_at       = $createdDt.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
            app_display_name = $label
            success          = ($errCode -eq 0)
            error_code       = [int]$errCode
        })
    }

    $warnings = [System.Collections.Generic.List[object]]::new()
    $warnings.Add($telemetryWarning)
    if ($truncated) {
        $warnings.Add((New-WarningItem -Code 'OUTPUT_LIMIT' -Message "Device inventory sign-in events were truncated at $effectiveCap items (schema cap 50)."))
    }
    if ($distinctDevices.Count -eq 0) {
        $warnings.Add((New-WarningItem -Code 'DEVICE_INVENTORY_SUMMARY' -Message "Distinct endpoints: 0 (no DeviceDetail telemetry present in sign-ins over the last ${lookbackDays}d)."))
    } else {
        $osText = @($osCounts.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', '
        $warnings.Add((New-WarningItem -Code 'DEVICE_INVENTORY_SUMMARY' -Message "Distinct endpoints ($($distinctDevices.Count) | OS: $osText): $($distinctSummaries -join '; ')"))
    }
    if ($unmanagedKeys.Count -gt 0) {
        $warnings.Add((New-WarningItem -Code 'UNMANAGED_DEVICE_DETECTED' -Message "$($unmanagedKeys.Count) distinct endpoint(s) reported IsManaged=False (unmanaged/BYOD client sign-in)."))
    }
    if ($nonCompliantKeys.Count -gt 0) {
        $warnings.Add((New-WarningItem -Code 'NONCOMPLIANT_DEVICE_SIGNIN' -Message "$($nonCompliantKeys.Count) distinct endpoint(s) reported IsCompliant=False."))
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
        created_at       = $nowUtc.AddHours(-2).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        app_display_name = 'Microsoft Teams [Device:WS-WIN11-042 | OS:Windows 11 | Trust:AzureAdJoined | Managed:True | Compliant:True]'
        success          = $true
        error_code       = 0
    },
    [pscustomobject]@{
        created_at       = $nowUtc.AddHours(-9).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        app_display_name = 'Microsoft Outlook [Device:iPhone-15 | OS:iOS 17 | Trust:Workplace | Managed:False | Compliant:False]'
        success          = $true
        error_code       = 0
    }
)

$truncated = $allEvents.Length -gt $effectiveCap
[object[]]$selectedEvents = @($allEvents | Select-Object -First $effectiveCap)
$offlineWarnings = [System.Collections.Generic.List[object]]::new()
$offlineWarnings.Add($telemetryWarning)
if ($truncated) {
    $offlineWarnings.Add((New-WarningItem -Code 'OUTPUT_LIMIT' -Message "Events truncated to MaxRecords=$effectiveCap."))
}
$offlineWarnings.Add((New-WarningItem -Code 'DEVICE_INVENTORY_SUMMARY' -Message 'Distinct endpoints (2 | OS: Windows 11=1, iOS 17=1): WS-WIN11-042 (Windows 11, AzureAdJoined, Managed=True, Compliant=True); iPhone-15 (iOS 17, Workplace, Managed=False, Compliant=False)'))
$offlineWarnings.Add((New-WarningItem -Code 'UNMANAGED_DEVICE_DETECTED' -Message '1 distinct endpoint(s) reported IsManaged=False (unmanaged/BYOD client sign-in).'))
$offlineWarnings.Add((New-WarningItem -Code 'NONCOMPLIANT_DEVICE_SIGNIN' -Message '1 distinct endpoint(s) reported IsCompliant=False.'))

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

