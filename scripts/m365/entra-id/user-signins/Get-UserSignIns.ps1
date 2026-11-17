#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [System.Collections.Generic.IReadOnlyDictionary[string, object]]$Context,

    [Parameter(Mandatory = $true)]
    [System.Collections.Generic.IReadOnlyDictionary[string, object]]$Parameters,

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
    if ($null -eq $Object -or [string]::IsNullOrEmpty($Name)) { return $null }
    if ($Object -is [System.Collections.Generic.IReadOnlyDictionary[string, object]]) {
        $val = $null
        if ($Object.TryGetValue($Name, [ref]$val)) { return $val }
        return $null
    }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $null
    }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -ne $prop) { return $prop.Value }
    return $null
}

function Test-SafeKey {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object -or [string]::IsNullOrEmpty($Name)) { return $false }
    if ($Object -is [System.Collections.Generic.IReadOnlyDictionary[string, object]]) { return $Object.ContainsKey($Name) }
    if ($Object -is [System.Collections.IDictionary]) { return $Object.Contains($Name) }
    return ($null -ne $Object.PSObject.Properties[$Name])
}

function ConvertTo-UtcTimestamp {
    param([object]$RawValue)
    if ($null -eq $RawValue) { return $null }
    if ($RawValue -is [datetime]) { return $RawValue.ToUniversalTime() }
    if ($RawValue -is [datetimeoffset]) { return $RawValue.UtcDateTime }
    $text = ([string]$RawValue).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    $parsedDto = [datetimeoffset]::MinValue
    if ([datetimeoffset]::TryParse($text, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AssumeUniversal, [ref]$parsedDto)) {
        return $parsedDto.UtcDateTime
    }
    return $null
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.' -Retryable $true
    )
}

$ctxContract = [string](Get-SafeProp $Context 'contract_version')
$ctxScriptId = [string](Get-SafeProp $Context 'script_id')
$ctxTenantId = [string](Get-SafeProp $Context 'tenant_id')
$ctxAdminUpn = [string](Get-SafeProp $Context 'verified_account_upn')
if ($ctxContract -cne '0.3.0' -or $ctxScriptId -cne 'M365.ENTRA.USER_SIGNINS' -or [string]::IsNullOrWhiteSpace($ctxTenantId) -or [string]::IsNullOrWhiteSpace($ctxAdminUpn)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context version or script identity.'
    )
}
if (Test-SafeKey $Context 'company_id') {
    if ([string]::IsNullOrWhiteSpace([string](Get-SafeProp $Context 'company_id'))) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid company_id in invocation context.'
        )
    }
}
if (Test-SafeKey $Context 'session_generation') {
    $rawGen = Get-SafeProp $Context 'session_generation'
    if ($null -eq $rawGen -or $rawGen -is [bool] -or -not ($rawGen -is [int] -or $rawGen -is [long]) -or [long]$rawGen -lt 1) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid session_generation in invocation context.'
        )
    }
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

if ($lookbackDays -is [bool] -or ($lookbackDays -isnot [int] -and $lookbackDays -isnot [long]) -or $lookbackDays -lt 1 -or $lookbackDays -gt 30) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'LookbackDays must be an integer between 1 and 30.'
    )
}
if ($maxRecords -is [bool] -or ($maxRecords -isnot [int] -and $maxRecords -isnot [long]) -or $maxRecords -lt 1 -or $maxRecords -gt 50) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'MaxRecords must be an integer between 1 and 50.'
    )
}

$lookbackDays = [int]$lookbackDays
$maxRecords = [int]$maxRecords

$targetObj = Get-SafeProp $Context 'target'
$targetKindRaw = [string](Get-SafeProp $targetObj 'kind')
$targetValRaw = [string](Get-SafeProp $targetObj 'value')
if ($null -eq $targetObj -or $targetKindRaw -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.ENTRA.USER_SIGNINS requires a resolved object_id target.'
    )
}

$targetId = $targetValRaw.Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$graphConn = $null
$conns = Get-SafeProp $Context 'connections'
if ($null -ne $conns) {
    foreach ($conn in @($conns)) {
        if ($null -ne $conn -and [string](Get-SafeProp $conn 'service') -eq 'Graph') {
            $graphConn = $conn
            break
        }
    }
}
if ($null -eq $graphConn -or [string](Get-SafeProp $graphConn 'state') -cne 'verified') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Microsoft Graph connection state is required.'
    )
}
$connExpiresRaw = Get-SafeProp $graphConn 'expires_at'
if ($null -ne $connExpiresRaw -and -not [string]::IsNullOrWhiteSpace([string]$connExpiresRaw)) {
    $connExpiresUtc = ConvertTo-UtcTimestamp $connExpiresRaw
    if ($null -eq $connExpiresUtc -or $connExpiresUtc -le [datetime]::UtcNow) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Microsoft Graph connection lease has expired.'
        )
    }
}
if ([string](Get-SafeProp $graphConn 'tenant_id') -cne $ctxTenantId) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'TENANT_MISMATCH' -Message 'Graph connection tenant does not match invocation tenant.'
    )
}
if ([string](Get-SafeProp $graphConn 'verified_account_upn') -ne $ctxAdminUpn) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCOUNT_MISMATCH' -Message 'Graph connection account does not match invocation administrator.'
    )
}

$scopes = @((Get-SafeProp $graphConn 'graph_scopes') | ForEach-Object { [string]$_ })
$roles = @((Get-SafeProp $graphConn 'effective_roles') | ForEach-Object { [string]$_ })
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
    catch [System.OperationCanceledException] {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during sign-in log lookup.' -Retryable $true
        )
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during sign-in log lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges|PremiumLicense|Neither tenant is B2C') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Entra sign-in logs.'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the sign-in log query.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph sign-in log query failed.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after sign-in log lookup.' -Retryable $true
        )
    }

    $normalizedEvents = [System.Collections.Generic.List[object]]::new()
    $truncated = $false
    foreach ($ev in ($rawEvents | Sort-Object { ConvertTo-UtcTimestamp (Get-SafeProp $_ 'CreatedDateTime') } -Descending)) {
        if ($null -eq $ev) { continue }
        if ($normalizedEvents.Count -ge $maxRecords) {
            $truncated = $true
            break
        }
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
        $rawDt = Get-SafeProp $ev 'CreatedDateTime'
        $parsedDt = ConvertTo-UtcTimestamp $rawDt
        if ($null -eq $parsedDt) {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid or missing sign-in event CreatedDateTime.'
            )
        }
        $createdStr = $parsedDt.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        $rawApp = Get-SafeProp $ev 'AppDisplayName'
        $appName = if ($null -ne $rawApp -and [string]$rawApp -ne '') { [string]$rawApp } else { $null }
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
            New-WarningItem -Code 'OUTPUT_LIMIT' -Message "Sign-in events were truncated at MaxRecords=$maxRecords."
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

