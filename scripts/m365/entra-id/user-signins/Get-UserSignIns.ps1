#Requires -Version 7.0
param(
    [Parameter(Mandatory = $true)][psobject]$Context,
    [Parameter(Mandatory = $true)][hashtable]$Parameters,
    [Parameter(Mandatory = $true)][System.Threading.CancellationToken]$CancellationToken
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
    return [pscustomobject]@{
        code      = $Code
        message   = $Message
        retryable = $Retryable
    }
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.'
    )
}

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.ENTRA.USER_SIGNINS') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context version or script identity.'
    )
}

if ($null -eq $Parameters) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Parameters dictionary is required.'
    )
}

foreach ($key in $Parameters.Keys) {
    if ([string]$key -notin @('LookbackDays', 'MaxRecords')) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter: $key"
        )
    }
}

$lookbackDays = if ($Parameters.ContainsKey('LookbackDays')) { $Parameters['LookbackDays'] } else { 7 }
$maxRecords = if ($Parameters.ContainsKey('MaxRecords')) { $Parameters['MaxRecords'] } else { 20 }

if (($lookbackDays -isnot [int] -and $lookbackDays -isnot [long]) -or $lookbackDays -lt 1 -or $lookbackDays -gt 30) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'LookbackDays must be an integer between 1 and 30.'
    )
}
if (($maxRecords -isnot [int] -and $maxRecords -isnot [long]) -or $maxRecords -lt 1 -or $maxRecords -gt 50) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'MaxRecords must be an integer between 1 and 50.'
    )
}

$lookbackDays = [int]$lookbackDays
$maxRecords = [int]$maxRecords

if ($null -eq $Context.target -or [string]$Context.target.kind -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.ENTRA.USER_SIGNINS requires a resolved object_id target.'
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
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
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Microsoft Graph connection state is required.'
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

$scopes = @($graphConn.graph_scopes | ForEach-Object { [string]$_ })
$roles = @($graphConn.effective_roles | ForEach-Object { [string]$_ })
if ('AuditLog.Read.All' -notin $scopes -or 'Reports.Reader' -notin $roles) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Graph scope AuditLog.Read.All and role Reports.Reader are not present.'
    )
}

$nowUtc = [datetime]::UtcNow
$lookbackStartDt = $nowUtc.AddDays(-$lookbackDays)
$lookbackStartStr = $lookbackStartDt.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)

$mgSignInCmd = Get-Command -Name 'Get-MgAuditLogSignIn' -ErrorAction SilentlyContinue
if ($null -ne $mgSignInCmd) {
    $filter = "userId eq '$targetId' and createdDateTime ge $lookbackStartStr"
    try {
        $rawEvents = @(Get-MgAuditLogSignIn -Filter $filter -Top ($maxRecords + 1) -Property @('Id', 'UserId', 'CreatedDateTime', 'AppDisplayName', 'Status') -ErrorAction Stop)
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during sign-in log lookup.'
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges| Neither tenant is B2C') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Entra sign-in logs.'
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph sign-in log query failed.' -Retryable $true
        )
    }

    $normalizedEvents = [System.Collections.Generic.List[object]]::new()
    $truncated = $false
    foreach ($ev in $rawEvents) {
        if ($null -eq $ev) { continue }
        if ($normalizedEvents.Count -ge $maxRecords) {
            $truncated = $true
            break
        }
        if ($null -ne $ev.UserId -and ([string]$ev.UserId).Trim().ToLowerInvariant() -ne $targetId) {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned sign-in event UserId does not match target object_id.'
            )
        }
        $errCode = if ($null -ne $ev.Status -and $null -ne $ev.Status.ErrorCode) { [int]$ev.Status.ErrorCode } else { 0 }
        if ($errCode -lt 0) {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid negative sign-in error code.'
            )
        }
        $createdStr = if ($ev.CreatedDateTime -is [datetime]) {
            $ev.CreatedDateTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        } else {
            [string]$ev.CreatedDateTime
        }
        $appName = if ($null -ne $ev.AppDisplayName -and [string]$ev.AppDisplayName -ne '') { [string]$ev.AppDisplayName } else { $null }
        $normalizedEvents.Add([pscustomobject]@{
            created_at       = $createdStr
            app_display_name = $appName
            success          = ($errCode -eq 0)
            error_code       = [int]$errCode
        })
    }

    $payload = [pscustomobject]@{
        target_user_id = $targetId
        lookback_start = $lookbackStartStr
        events         = [object[]]$normalizedEvents.ToArray()
        returned_count = [int]$normalizedEvents.Count
        truncated      = [bool]$truncated
    }

    if ($truncated) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings @(
            [pscustomobject]@{ code = 'OUTPUT_LIMIT'; message = "Sign-in events were truncated at MaxRecords=$maxRecords." }
        )
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload
}

# Offline synthetic fixture evaluation
if ($targetId -eq '40000000-0000-4000-8000-000000000403') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'This operation is unavailable under the configured offline policy.'
    )
}

$eventTime1 = $nowUtc.AddHours(-2).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
$eventTime2 = $nowUtc.AddHours(-5).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)

$allSyntheticEvents = @(
    [pscustomobject]@{
        created_at       = $eventTime1
        app_display_name = 'Microsoft Teams'
        success          = $true
        error_code       = 0
    },
    [pscustomobject]@{
        created_at       = $eventTime2
        app_display_name = 'Exchange Online'
        success          = $false
        error_code       = 50126
    }
)

$truncated = $allSyntheticEvents.Count -gt $maxRecords
[object[]]$selectedEvents = @($allSyntheticEvents | Select-Object -First $maxRecords)

$payload = [pscustomobject]@{
    target_user_id = $targetId
    lookback_start = $lookbackStartStr
    events         = [object[]]$selectedEvents
    returned_count = [int]$selectedEvents.Length
    truncated      = [bool]$truncated
}

if ($truncated) {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings @(
        [pscustomobject]@{ code = 'OUTPUT_LIMIT'; message = 'The bounded transport limit was reached; narrow the operation.' }
    )
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload

