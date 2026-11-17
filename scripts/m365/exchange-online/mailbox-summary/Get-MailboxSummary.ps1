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
if ($ctxContract -cne '0.3.0' -or $ctxScriptId -cne 'M365.EXCHANGE.MAILBOX_SUMMARY' -or [string]::IsNullOrWhiteSpace($ctxTenantId) -or [string]::IsNullOrWhiteSpace($ctxAdminUpn)) {
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

if ($null -eq $Parameters -or $Parameters.Count -gt 0) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.EXCHANGE.MAILBOX_SUMMARY accepts no extra parameters.'
    )
}

$targetObj = Get-SafeProp $Context 'target'
$targetKindRaw = [string](Get-SafeProp $targetObj 'kind')
$targetValRaw = [string](Get-SafeProp $targetObj 'value')
if ($null -eq $targetObj -or $targetKindRaw -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.EXCHANGE.MAILBOX_SUMMARY requires a resolved object_id target.'
    )
}

$targetId = $targetValRaw.Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$exoConn = $null
$conns = Get-SafeProp $Context 'connections'
if ($null -ne $conns) {
    foreach ($conn in @($conns)) {
        if ($null -ne $conn -and [string](Get-SafeProp $conn 'service') -eq 'ExchangeOnline') {
            $exoConn = $conn
            break
        }
    }
}
if ($null -eq $exoConn -or [string](Get-SafeProp $exoConn 'state') -cne 'verified') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Exchange Online connection state is required.'
    )
}
$connExpiresRaw = Get-SafeProp $exoConn 'expires_at'
if ($null -ne $connExpiresRaw -and -not [string]::IsNullOrWhiteSpace([string]$connExpiresRaw)) {
    $connExpiresUtc = ConvertTo-UtcTimestamp $connExpiresRaw
    if ($null -eq $connExpiresUtc -or $connExpiresUtc -le [datetime]::UtcNow) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Exchange Online connection lease has expired.'
        )
    }
}
if ([string](Get-SafeProp $exoConn 'tenant_id') -cne $ctxTenantId) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'TENANT_MISMATCH' -Message 'Exchange Online connection tenant does not match invocation tenant.'
    )
}
if ([string](Get-SafeProp $exoConn 'verified_account_upn') -ne $ctxAdminUpn) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCOUNT_MISMATCH' -Message 'Exchange Online connection account does not match invocation administrator.'
    )
}

$roles = @((Get-SafeProp $exoConn 'effective_roles') | ForEach-Object { [string]$_ })
if ('cmdlet.Get-EXOMailbox' -notin $roles -or 'cmdlet.Get-EXOMailboxStatistics' -notin $roles) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Exchange Online RBAC cmdlet permissions are not present.'
    )
}

$exoMailboxCmd = Get-Command -Name 'Get-EXOMailbox' -ErrorAction SilentlyContinue
if ($null -ne $exoMailboxCmd) {
    try {
        $mbx = Get-EXOMailbox -ExternalDirectoryObjectId $parsedGuid -Properties @('ExternalDirectoryObjectId', 'ExchangeGuid', 'RecipientTypeDetails', 'PrimarySmtpAddress', 'ProhibitSendQuota') -ErrorAction Stop
    }
    catch [System.OperationCanceledException] {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox lookup.' -Retryable $true
        )
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)ManagementObjectNotFoundException|not\s+found|couldn''t\s+be\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'MAILBOX_NOT_FOUND' -Message 'No Exchange Online mailbox exists for the target user.'
            )
        }
        if ($errMsg -match '(?i)AccessDenied|not\s+authorized|Forbidden|RBAC') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Exchange Online mailbox.'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl|MicroDelay') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Exchange Online throttled the mailbox summary request.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Exchange Online mailbox query failed.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Exchange mailbox lookup.' -Retryable $true
        )
    }

    if ($null -eq $mbx -or @($mbx).Count -eq 0) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'MAILBOX_NOT_FOUND' -Message 'No Exchange Online mailbox exists for the target user.'
        )
    }
    if (@($mbx).Count -gt 1) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Ambiguous mailbox lookup returned multiple recipients.'
        )
    }

    $extId = ([string](Get-SafeProp $mbx 'ExternalDirectoryObjectId')).Trim().ToLowerInvariant()
    if ($extId -ne $targetId) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned ExternalDirectoryObjectId does not match target object_id.'
        )
    }

    $warnings = [System.Collections.Generic.List[object]]::new()
    $totalSizeBytes = $null
    $exoStatsCmd = Get-Command -Name 'Get-EXOMailboxStatistics' -ErrorAction SilentlyContinue
    $exGuid = Get-SafeProp $mbx 'ExchangeGuid'
    if ($null -ne $exoStatsCmd -and $null -ne $exGuid) {
        try {
            $stats = Get-EXOMailboxStatistics -Identity ([string]$exGuid) -Properties @('TotalItemSize') -ErrorAction Stop
            if ($CancellationToken.IsCancellationRequested) {
                return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                    New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Exchange mailbox statistics lookup.' -Retryable $true
                )
            }
            $totalItemSizeObj = Get-SafeProp $stats 'TotalItemSize'
            $totalValObj = Get-SafeProp $totalItemSizeObj 'Value'
            if ($null -ne $stats -and $null -ne $totalItemSizeObj -and $null -ne $totalValObj) {
                $totalSizeBytes = [long]$totalValObj.ToBytes()
            } else {
                $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox statistics TotalItemSize was unavailable.'))
            }
        }
        catch [System.OperationCanceledException] {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox statistics lookup.' -Retryable $true
            )
        }
        catch {
            if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
                return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                    New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox statistics lookup.' -Retryable $true
                )
            }
            $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox statistics could not be retrieved.'))
        }
    } else {
        $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox statistics cmdlet or ExchangeGuid unavailable.'))
    }

    $quotaBytes = $null
    $prohibitSendQuota = Get-SafeProp $mbx 'ProhibitSendQuota'
    $quotaValObj = Get-SafeProp $prohibitSendQuota 'Value'
    if ($null -ne $prohibitSendQuota -and $null -ne $quotaValObj) {
        $quotaBytes = [long]$quotaValObj.ToBytes()
    } else {
        $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox ProhibitSendQuota was unavailable.'))
    }

    $payload = [pscustomobject]@{
        target_user_id            = $targetId
        mailbox_exists            = $true
        recipient_type_details    = [string](Get-SafeProp $mbx 'RecipientTypeDetails')
        primary_smtp_address      = ([string](Get-SafeProp $mbx 'PrimarySmtpAddress')).Trim()
        total_item_size_bytes     = $totalSizeBytes
        prohibit_send_quota_bytes = $quotaBytes
    }

    if ($warnings.Count -gt 0 -or $null -eq $totalSizeBytes -or $null -eq $quotaBytes) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $warnings.ToArray()
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload
}

# Offline synthetic fixture evaluation
if ($targetId -eq '40000000-0000-4000-8000-000000000405' -or $targetId -eq '40000000-0000-4000-8000-000000000404') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'MAILBOX_NOT_FOUND' -Message 'No matching Exchange Online mailbox exists in the synthetic fixture.'
    )
}
if ($targetId -eq '40000000-0000-4000-8000-000000000403') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'This operation is unavailable under the configured offline policy.'
    )
}

$smtp = if ($targetId -eq '44444444-4444-4444-8444-444444444444') {
    'synthetic.user@example.invalid'
} elseif ($targetId -eq '40000000-0000-4000-8000-000000000002') {
    'partial.user@alpine.example'
} else {
    'client@alpine.example'
}

$isPartial = ($targetId -eq '40000000-0000-4000-8000-000000000002')
$payload = [pscustomobject]@{
    target_user_id            = $targetId
    mailbox_exists            = $true
    recipient_type_details    = 'UserMailbox'
    primary_smtp_address      = $smtp
    total_item_size_bytes     = if ($isPartial) { $null } else { [long]104857600 }
    prohibit_send_quota_bytes = [long]53687091200
}

if ($isPartial) {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings @(
        [pscustomobject]@{ code = 'PROPERTY_UNAVAILABLE'; message = 'A synthetic property is unavailable in this partial fixture.' }
    )
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload

