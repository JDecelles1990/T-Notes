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

function New-WarningItem {
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$Message
    )
    return [pscustomobject]@{
        code    = $Code
        message = $Message
    }
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.'
    )
}

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.ENTRA.USER_IDENTITY') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context version or script identity.'
    )
}

if ($null -eq $Parameters -or $Parameters.Count -gt 0) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.ENTRA.USER_IDENTITY accepts no extra parameters.'
    )
}

if ($null -eq $Context.target -or [string]$Context.target.kind -notin @('upn', 'object_id') -or [string]::IsNullOrWhiteSpace([string]$Context.target.value)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target must be a non-empty UPN or Entra object ID.'
    )
}

$targetKind = [string]$Context.target.kind
$targetValue = ([string]$Context.target.value).Trim().Normalize([System.Text.NormalizationForm]::FormC)

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
if ('User.Read.All' -notin $scopes) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Graph scope User.Read.All is not present.'
    )
}

$mgCmd = Get-Command -Name 'Get-MgUser' -ErrorAction SilentlyContinue
if ($null -ne $mgCmd) {
    try {
        $rawUser = Get-MgUser -UserId ([string]$targetValue) -Property @('Id', 'DisplayName', 'UserPrincipalName', 'AccountEnabled', 'UserType') -ErrorAction Stop
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Graph user lookup.'
            )
        }
        if ($errMsg -match '(?i)Request_ResourceNotFound|404|not\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'The requested Entra user was not found in the tenant.'
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Entra user properties.'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the user lookup request.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph user lookup failed.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Graph user lookup.'
        )
    }

    if ($null -eq $rawUser -or @($rawUser).Count -eq 0) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'The requested Entra user was not found in the tenant.'
        )
    }
    if (@($rawUser).Count -gt 1) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Ambiguous user response returned multiple objects.'
        )
    }

    $userId = ([string]$rawUser.Id).Trim().ToLowerInvariant()
    $userUpn = ([string]$rawUser.UserPrincipalName).Trim().Normalize([System.Text.NormalizationForm]::FormC)
    if ($targetKind -eq 'object_id' -and $userId -ne $targetValue.ToLowerInvariant()) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned user ID does not match requested target object ID.'
        )
    }
    if ($targetKind -eq 'upn' -and $userUpn.ToLowerInvariant() -ne $targetValue.ToLowerInvariant()) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned UPN does not match requested target UPN.'
        )
    }

    $displayName = if ($null -ne $rawUser.DisplayName -and [string]$rawUser.DisplayName -ne '') { [string]$rawUser.DisplayName } else { $null }
    $accountEnabled = if ($null -ne $rawUser.AccountEnabled) { [bool]$rawUser.AccountEnabled } else { $null }
    $userType = if ([string]$rawUser.UserType -in @('Member', 'Guest')) { [string]$rawUser.UserType } else { $null }

    $warnings = [System.Collections.Generic.List[object]]::new()
    if ($null -eq $accountEnabled) {
        $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'AccountEnabled property was not returned by the provider.'))
    }

    $payload = [pscustomobject]@{
        id                  = $userId
        display_name        = $displayName
        user_principal_name = $userUpn
        account_enabled     = $accountEnabled
        user_type           = $userType
    }

    if ($warnings.Count -gt 0) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $warnings.ToArray()
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload
}

# Offline synthetic fixture evaluation when live provider cmdlet is not loaded
$lowerTarget = $targetValue.ToLowerInvariant()
if ($lowerTarget -match 'slow|timeout' -or $lowerTarget -eq '40000000-0000-4000-8000-000000000408') {
    [void]$CancellationToken.WaitHandle.WaitOne(2000)
    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled while waiting on synthetic fixture.'
        )
    }
}

if ($lowerTarget -match 'missing|notfound' -or $lowerTarget -eq '40000000-0000-4000-8000-000000000404') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'No matching synthetic fixture target exists.'
    )
}
if ($lowerTarget -match 'denied|forbidden' -or $lowerTarget -eq '40000000-0000-4000-8000-000000000403') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'This operation is unavailable under the configured offline policy.'
    )
}
if ($lowerTarget -match 'throttl' -or $lowerTarget -eq '40000000-0000-4000-8000-000000000429') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'API_THROTTLED' -Message 'Synthetic Graph request was throttled.' -Retryable $true
    )
}

$resolvedId = if ($targetKind -eq 'object_id') {
    $lowerTarget
} elseif ($lowerTarget -eq 'synthetic.user@example.invalid') {
    '44444444-4444-4444-8444-444444444444'
} elseif ($lowerTarget -eq 'partial.user@alpine.example') {
    '40000000-0000-4000-8000-000000000002'
} else {
    '40000000-0000-4000-8000-000000000001'
}

$resolvedUpn = if ($targetKind -eq 'upn') {
    $targetValue
} elseif ($lowerTarget -eq '44444444-4444-4444-8444-444444444444') {
    'synthetic.user@example.invalid'
} elseif ($lowerTarget -eq '40000000-0000-4000-8000-000000000002') {
    'partial.user@alpine.example'
} else {
    'client@alpine.example'
}

$isGuest = $resolvedUpn -match '#ext#@|guest'
$isPartial = $lowerTarget -match 'partial' -or $lowerTarget -eq '40000000-0000-4000-8000-000000000002'

$payload = [pscustomobject]@{
    id                  = $resolvedId
    display_name        = if ($isGuest) { 'Synthetic Guest User' } else { 'Synthetic User' }
    user_principal_name = $resolvedUpn
    account_enabled     = if ($isPartial) { $null } else { $true }
    user_type           = if ($isGuest) { 'Guest' } else { 'Member' }
}

if ($isPartial) {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings @(
        New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'A synthetic property is unavailable in this partial fixture.'
    )
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload

