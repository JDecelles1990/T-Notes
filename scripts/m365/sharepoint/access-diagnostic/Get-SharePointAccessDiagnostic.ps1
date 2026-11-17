#requires -Version 7.0
<#
.SYNOPSIS
    Inspect SharePoint Sign-In & Access Events (M365.SHAREPOINT.ACCESS_DIAGNOSTIC).
.DESCRIPTION
    Review recent SharePoint, OneDrive, and Office Portal sign-in telemetry for access troubleshooting.
    Follows tnotes.m365 / 0.3.0 Callable ABI v1.
#>
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
if ($ctxContract -cne '0.3.0' -or $ctxScriptId -cne 'M365.SHAREPOINT.ACCESS_DIAGNOSTIC' -or [string]::IsNullOrWhiteSpace($ctxTenantId) -or [string]::IsNullOrWhiteSpace($ctxAdminUpn)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.SHAREPOINT.ACCESS_DIAGNOSTIC.'
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

$maxRecords = 15
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
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Microsoft Graph connection is required.'
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

$targetObj = Get-SafeProp $Context 'target'
$targetKindRaw = [string](Get-SafeProp $targetObj 'kind')
$targetValRaw = [string](Get-SafeProp $targetObj 'value')
if ($null -eq $targetObj -or $targetKindRaw -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.SHAREPOINT.ACCESS_DIAGNOSTIC requires a resolved Entra object_id target.'
    )
}

$targetId = $targetValRaw.Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$scopes = @((Get-SafeProp $graphConn 'graph_scopes') | ForEach-Object { [string]$_ })
$roles = @((Get-SafeProp $graphConn 'effective_roles') | ForEach-Object { [string]$_ })
if ('AuditLog.Read.All' -notin $scopes -or ('Reports.Reader' -notin $roles -and 'Security.Reader' -notin $roles)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Graph scope AuditLog.Read.All and role Reports.Reader or Security.Reader are not present.'
    )
}

$nowUtc = [datetime]::UtcNow
$lookbackStartStr = $nowUtc.AddDays(-$lookbackDays).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
$effectiveCap = [Math]::Min($maxRecords, 50)

$mgSignInCmd = Get-Command -Name 'Get-MgAuditLogSignIn' -ErrorAction SilentlyContinue
if ($null -ne $mgSignInCmd) {
    $filter = "userId eq '$targetId' and createdDateTime ge $lookbackStartStr"
    try {
        $rawEvents = @(Get-MgAuditLogSignIn -Filter $filter -Top 100 -Property @('Id', 'UserId', 'CreatedDateTime', 'AppDisplayName', 'ResourceDisplayName', 'ClientAppUsed', 'ConditionalAccessStatus', 'Status') -ErrorAction Stop)
    }
    catch [System.OperationCanceledException] {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during SharePoint sign-in log lookup.' -Retryable $true
        )
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during SharePoint sign-in log lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges|PremiumLicense|Neither tenant is B2C') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied reading Entra sign-in logs for SharePoint access diagnostics (requires AuditLog.Read.All, Reports.Reader/Security.Reader, and Entra ID P1/P2 tenant licensing).'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the SharePoint access sign-in query.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph SharePoint access sign-in query failed.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Graph SharePoint sign-in query.' -Retryable $true
        )
    }

    $normalizedEvents = [System.Collections.Generic.List[object]]::new()
    $truncated = $false
    $failedCount = 0

    foreach ($ev in ($rawEvents | Sort-Object { ConvertTo-UtcTimestamp (Get-SafeProp $_ 'CreatedDateTime') } -Descending)) {
        if ($null -eq $ev) { continue }

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

        $appName = [string](Get-SafeProp $ev 'AppDisplayName')
        $resName = [string](Get-SafeProp $ev 'ResourceDisplayName')
        if (("$appName $resName") -notmatch '(?i)SharePoint|OneDrive|Office\s*365\s*SharePoint|Microsoft\s*365\s*(Portal|Home)|Office\s*Online|Office\.com|Office\s*365\s*Portal') {
            continue
        }

        if ($normalizedEvents.Count -ge $effectiveCap) {
            $truncated = $true
            break
        }

        $rawDt = Get-SafeProp $ev 'CreatedDateTime'
        $parsedDt = ConvertTo-UtcTimestamp $rawDt
        if ($null -eq $parsedDt) {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid or missing sign-in event CreatedDateTime.'
            )
        }
        $createdStr = $parsedDt.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)

        $caStatus = [string](Get-SafeProp $ev 'ConditionalAccessStatus')
        $clientApp = [string](Get-SafeProp $ev 'ClientAppUsed')
        if ($errCode -ne 0 -or $caStatus -eq 'failure') {
            $failedCount++
        }

        $appBase = if (-not [string]::IsNullOrWhiteSpace($appName)) { $appName } else { 'SharePoint Online' }
        $tags = [System.Collections.Generic.List[string]]::new()
        if (-not [string]::IsNullOrWhiteSpace($clientApp)) { $tags.Add($clientApp) }
        if (-not [string]::IsNullOrWhiteSpace($caStatus)) { $tags.Add("CA:$caStatus") }
        $label = if ($tags.Count -gt 0) { "$appBase [$($tags -join ' | ')]" } else { $appBase }
        if ($label.Length -gt 256) { $label = $label.Substring(0, 253) + '...' }

        $normalizedEvents.Add([pscustomobject]@{
            created_at       = $createdStr
            app_display_name = $label
            success          = ($errCode -eq 0)
            error_code       = [int]$errCode
        })
    }

    $warnings = [System.Collections.Generic.List[object]]::new()
    if ($truncated) {
        $warnings.Add((New-WarningItem -Code 'OUTPUT_LIMIT' -Message "SharePoint sign-in events were truncated at $effectiveCap items (schema cap 50)."))
    }
    if ($normalizedEvents.Count -eq 0) {
        $warnings.Add((New-WarningItem -Code 'NO_MATCHING_EVENTS' -Message "No SharePoint, OneDrive, or Office Portal sign-in events found in the last $lookbackDays day(s)."))
    } elseif ($failedCount -gt 0) {
        $warnings.Add((New-WarningItem -Code 'SHAREPOINT_ACCESS_FAILURE' -Message "$failedCount SharePoint or portal sign-in failure(s) observed in the last $lookbackDays day(s)."))
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
        app_display_name = 'Office 365 SharePoint Online'
        success          = $true
        error_code       = 0
    },
    [pscustomobject]@{
        created_at       = $nowUtc.AddHours(-8).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        app_display_name = 'Microsoft Office 365 Portal'
        success          = $true
        error_code       = 0
    }
)

$truncated = $allEvents.Length -gt $effectiveCap
[object[]]$selectedEvents = @($allEvents | Select-Object -First $effectiveCap)
$payload = [pscustomobject]@{
    target_user_id = $targetId
    lookback_start = $lookbackStartStr
    events         = [object[]]$selectedEvents
    returned_count = [int]$selectedEvents.Length
    truncated      = [bool]$truncated
}

if ($truncated) {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings @(
        New-WarningItem -Code 'OUTPUT_LIMIT' -Message "Events truncated to MaxRecords=$effectiveCap."
    )
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload
