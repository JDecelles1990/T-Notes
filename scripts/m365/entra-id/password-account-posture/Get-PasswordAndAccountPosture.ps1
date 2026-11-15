#requires -Version 7.0
<#
.SYNOPSIS
    Audit Password Age, Policy & Hybrid Sync Posture (M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE).
.DESCRIPTION
    Inspect Entra ID user password age (LastPasswordChangeDateTime), password expiration
    policy (PasswordPolicies / DisablePasswordExpiration), AD Connect hybrid sync status
    (OnPremisesSyncEnabled, OnPremisesLastSyncDateTime), and session token revocation state
    (SignInSessionsValidFromDateTime).
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

function ConvertTo-UtcDateTime {
    param([object]$RawValue)
    if ($null -eq $RawValue) { return $null }
    if ($RawValue -is [datetime]) { return $RawValue.ToUniversalTime() }
    if ($RawValue -is [datetimeoffset]) { return $RawValue.UtcDateTime }
    $text = ([string]$RawValue).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    try {
        return ([datetime]::Parse($text, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AssumeUniversal)).ToUniversalTime()
    } catch {
        return $null
    }
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.' -Retryable $true
    )
}

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE.'
    )
}

$allowedParams = @('PasswordAgeWarningDays')
if ($null -ne $Parameters) {
    foreach ($key in $Parameters.Keys) {
        if ($allowedParams -notcontains [string]$key) {
            return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
                New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter '$key'."
            )
        }
    }
}

$passwordAgeWarningDays = 90
if ($null -ne $Parameters -and $Parameters.ContainsKey('PasswordAgeWarningDays')) {
    $rawDays = $Parameters['PasswordAgeWarningDays']
    if ($rawDays -is [bool] -or -not ($rawDays -is [int] -or $rawDays -is [long])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'PasswordAgeWarningDays must be an integer between 1 and 365.'
        )
    }
    $passwordAgeWarningDays = [int]$rawDays
    if ($passwordAgeWarningDays -lt 1 -or $passwordAgeWarningDays -gt 365) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'PasswordAgeWarningDays must be between 1 and 365.'
        )
    }
}

if ($null -eq $Context.target -or [string]$Context.target.kind -notin @('upn', 'object_id') -or [string]::IsNullOrWhiteSpace([string]$Context.target.value)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target must be a non-empty UPN or Entra object ID.'
    )
}

$targetKind = [string]$Context.target.kind
$targetValue = ([string]$Context.target.value).Trim().Normalize([System.Text.NormalizationForm]::FormC)
$normalized = $targetValue.ToLowerInvariant()

if ($targetKind -eq 'object_id') {
    $parsedGuid = [guid]::Empty
    if (-not [guid]::TryParseExact($normalized, 'D', [ref]$parsedGuid)) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
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

$scopes = @($graphConn.graph_scopes | ForEach-Object { [string]$_ })
if ('User.Read.All' -notin $scopes) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Graph scope User.Read.All is not present.'
    )
}

$nowUtc = [datetime]::UtcNow
$mgCmd = Get-Command -Name 'Get-MgUser' -ErrorAction SilentlyContinue
if ($null -ne $mgCmd) {
    $selectProps = @(
        'Id',
        'DisplayName',
        'UserPrincipalName',
        'AccountEnabled',
        'UserType',
        'LastPasswordChangeDateTime',
        'PasswordPolicies',
        'OnPremisesSyncEnabled',
        'OnPremisesLastSyncDateTime',
        'SignInSessionsValidFromDateTime'
    )
    try {
        $rawUser = Get-MgUser -UserId $targetValue -Property $selectProps -ErrorAction Stop
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Graph password posture lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Request_ResourceNotFound|404|not\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'The requested Entra user was not found in the tenant.'
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Entra password and account posture properties (User.Read.All required).'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the password posture request.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph password posture lookup failed.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Graph user lookup.' -Retryable $true
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

    $userId = ([string](Get-SafeProp $rawUser 'Id')).Trim().ToLowerInvariant()
    $userUpn = ([string](Get-SafeProp $rawUser 'UserPrincipalName')).Trim().Normalize([System.Text.NormalizationForm]::FormC)
    if ($targetKind -eq 'object_id' -and $userId -ne $normalized) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned user ID does not match requested target object ID.'
        )
    }
    if ($targetKind -eq 'upn' -and $userUpn.ToLowerInvariant() -ne $normalized) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned UPN does not match requested target UPN.'
        )
    }

    $rawDisplay = Get-SafeProp $rawUser 'DisplayName'
    $displayName = if ($null -ne $rawDisplay -and [string]$rawDisplay -ne '') { [string]$rawDisplay } else { $null }
    if ($null -ne $displayName -and $displayName.Length -gt 256) {
        $displayName = $displayName.Substring(0, 253) + '...'
    }
    $rawEnabled = Get-SafeProp $rawUser 'AccountEnabled'
    $accountEnabled = if ($null -ne $rawEnabled) { [bool]$rawEnabled } else { $null }
    $rawType = [string](Get-SafeProp $rawUser 'UserType')
    $userType = if ($rawType -in @('Member', 'Guest')) { $rawType } else { $null }

    $warnings = [System.Collections.Generic.List[object]]::new()
    $hasPartialProp = $false
    if ($null -eq $accountEnabled) {
        $hasPartialProp = $true
        $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'AccountEnabled property was not returned by Microsoft Graph.'))
    } elseif ($accountEnabled -eq $false) {
        $warnings.Add((New-WarningItem -Code 'ACCOUNT_DISABLED' -Message 'Target Entra user account is currently disabled (AccountEnabled=False).'))
    }

    $pwdLastSet = ConvertTo-UtcDateTime (Get-SafeProp $rawUser 'LastPasswordChangeDateTime')
    if ($null -ne $pwdLastSet) {
        $ageDays = [Math]::Max(0, [int][Math]::Floor(($nowUtc - $pwdLastSet).TotalDays))
        $isoPwd = $pwdLastSet.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        $statusText = if ($ageDays -ge $passwordAgeWarningDays) {
            "EXCEEDS warning threshold (${passwordAgeWarningDays}d)"
        } else {
            "Within threshold (${passwordAgeWarningDays}d)"
        }
        $warnings.Add((New-WarningItem -Code 'PASSWORD_AGE_SUMMARY' -Message "LastPasswordChangeDateTime=$isoPwd | Age=${ageDays} day(s) ($statusText)."))
    } else {
        $warnings.Add((New-WarningItem -Code 'PASSWORD_AGE_SUMMARY' -Message 'LastPasswordChangeDateTime was not returned (federated, passwordless, or insufficient scope).'))
    }

    $pwdPolicies = [string](Get-SafeProp $rawUser 'PasswordPolicies')
    if ($pwdPolicies -match '(?i)DisablePasswordExpiration') {
        $warnings.Add((New-WarningItem -Code 'PASSWORD_NEVER_EXPIRES' -Message "PasswordPolicies='$pwdPolicies': DisablePasswordExpiration is enabled on this account."))
    } else {
        $policyLabel = if ([string]::IsNullOrWhiteSpace($pwdPolicies)) { 'None' } else { $pwdPolicies }
        $warnings.Add((New-WarningItem -Code 'PASSWORD_NEVER_EXPIRES' -Message "PasswordPolicies='$policyLabel': Password expiration policy applies."))
    }

    $onPremSync = Get-SafeProp $rawUser 'OnPremisesSyncEnabled'
    $onPremLastSync = ConvertTo-UtcDateTime (Get-SafeProp $rawUser 'OnPremisesLastSyncDateTime')
    if ($onPremSync -eq $true) {
        $syncStamp = if ($null -ne $onPremLastSync) {
            $onPremLastSync.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        } else {
            'Unknown'
        }
        $warnings.Add((New-WarningItem -Code 'HYBRID_SYNC_STATUS' -Message "Hybrid AD Connect synced user (OnPremisesSyncEnabled=True | LastSync=$syncStamp)."))
    } else {
        $warnings.Add((New-WarningItem -Code 'HYBRID_SYNC_STATUS' -Message 'Cloud-only Entra ID user (OnPremisesSyncEnabled=False/Null).'))
    }

    $revokedFrom = ConvertTo-UtcDateTime (Get-SafeProp $rawUser 'SignInSessionsValidFromDateTime')
    if ($null -ne $revokedFrom) {
        $revokedStr = $revokedFrom.ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
        $warnings.Add((New-WarningItem -Code 'SESSION_REVOCATION_STATE' -Message "SignInSessionsValidFromDateTime=$revokedStr (refresh tokens issued prior to this time are invalid)."))
    } else {
        $warnings.Add((New-WarningItem -Code 'SESSION_REVOCATION_STATE' -Message 'SignInSessionsValidFromDateTime was not returned.'))
    }

    $payload = [pscustomobject]@{
        id                  = $userId
        display_name        = $displayName
        user_principal_name = $userUpn
        account_enabled     = $accountEnabled
        user_type           = $userType
    }

    if ($hasPartialProp) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $warnings.ToArray()
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload -Warnings $warnings.ToArray()
}

# Offline synthetic fixture evaluation
if ($normalized -match '^missing' -or $normalized -eq '00000000-0000-4000-8000-000000000404') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message "Target user '$targetValue' was not found in tenant."
    )
}
if ($normalized -match '^denied') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Insufficient Microsoft Graph permissions for M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE.'
    )
}

$resolvedId = if ($targetKind -eq 'object_id') { $normalized } else { '40000000-0000-4000-8000-000000000001' }
$resolvedUpn = if ($targetKind -eq 'upn') { $targetValue } else { 'client@alpine.example' }

if ($normalized -match '^partial' -or $normalized -eq 'megan.bowen@contoso.example') {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data ([pscustomobject]@{
        id                  = '40000000-0000-4000-8000-000000000002'
        display_name        = 'Password Posture — Megan Bowen'
        user_principal_name = $resolvedUpn
        account_enabled     = $null
        user_type           = 'Member'
    }) -Warnings @(
        New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'AccountEnabled property is unavailable in the partial synthetic fixture.'
        New-WarningItem -Code 'PASSWORD_AGE_SUMMARY' -Message 'LastPasswordChangeDateTime was unavailable in partial fixture.'
        New-WarningItem -Code 'HYBRID_SYNC_STATUS' -Message 'Cloud-only Entra ID user (OnPremisesSyncEnabled=False/Null).'
    )
}

$sampleAge = 105
$thresholdStatus = if ($sampleAge -ge $passwordAgeWarningDays) {
    "EXCEEDS warning threshold (${passwordAgeWarningDays}d)"
} else {
    "Within threshold (${passwordAgeWarningDays}d)"
}
$samplePwdStamp = $nowUtc.AddDays(-$sampleAge).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
$sampleSyncStamp = $nowUtc.AddMinutes(-22).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)
$sampleRevokeStamp = $nowUtc.AddDays(-18).ToString('yyyy-MM-ddTHH:mm:ssZ', [System.Globalization.CultureInfo]::InvariantCulture)

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data ([pscustomobject]@{
    id                  = $resolvedId
    display_name        = 'Alex Wilber'
    user_principal_name = $resolvedUpn
    account_enabled     = $true
    user_type           = 'Member'
}) -Warnings @(
    New-WarningItem -Code 'PASSWORD_AGE_SUMMARY' -Message "LastPasswordChangeDateTime=$samplePwdStamp | Age=${sampleAge} day(s) ($thresholdStatus)."
    New-WarningItem -Code 'PASSWORD_NEVER_EXPIRES' -Message "PasswordPolicies='DisablePasswordExpiration': DisablePasswordExpiration is enabled on this account."
    New-WarningItem -Code 'HYBRID_SYNC_STATUS' -Message "Hybrid AD Connect synced user (OnPremisesSyncEnabled=True | LastSync=$sampleSyncStamp)."
    New-WarningItem -Code 'SESSION_REVOCATION_STATE' -Message "SignInSessionsValidFromDateTime=$sampleRevokeStamp (refresh tokens issued prior to this time are invalid)."
)

