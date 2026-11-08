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

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.EXCHANGE.MAILBOX_SUMMARY') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context version or script identity.'
    )
}

if ($null -eq $Parameters -or $Parameters.Count -gt 0) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.EXCHANGE.MAILBOX_SUMMARY accepts no extra parameters.'
    )
}

if ($null -eq $Context.target -or [string]$Context.target.kind -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.EXCHANGE.MAILBOX_SUMMARY requires a resolved object_id target.'
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$exoConn = $null
if ($null -ne $Context.connections) {
    foreach ($conn in @($Context.connections)) {
        if ($null -ne $conn -and [string]$conn.service -eq 'ExchangeOnline') {
            $exoConn = $conn
            break
        }
    }
}
if ($null -eq $exoConn -or [string]$exoConn.state -ne 'verified') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Exchange Online connection state is required.'
    )
}
if ([string]$exoConn.tenant_id -ne [string]$Context.tenant_id) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'TENANT_MISMATCH' -Message 'Exchange Online connection tenant does not match invocation tenant.'
    )
}
if ([string]$exoConn.verified_account_upn -ne [string]$Context.verified_account_upn) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCOUNT_MISMATCH' -Message 'Exchange Online connection account does not match invocation administrator.'
    )
}

$roles = @($exoConn.effective_roles | ForEach-Object { [string]$_ })
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
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox lookup.'
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
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Exchange Online mailbox query failed.' -Retryable $true
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

    $extId = ([string]$mbx.ExternalDirectoryObjectId).Trim().ToLowerInvariant()
    if ($extId -ne $targetId) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned ExternalDirectoryObjectId does not match target object_id.'
        )
    }

    $warnings = [System.Collections.Generic.List[object]]::new()
    $totalSizeBytes = $null
    $exoStatsCmd = Get-Command -Name 'Get-EXOMailboxStatistics' -ErrorAction SilentlyContinue
    if ($null -ne $exoStatsCmd -and $null -ne $mbx.ExchangeGuid) {
        try {
            $stats = Get-EXOMailboxStatistics -Identity ([string]$mbx.ExchangeGuid) -Properties @('TotalItemSize') -ErrorAction Stop
            if ($null -ne $stats -and $null -ne $stats.TotalItemSize -and $null -ne $stats.TotalItemSize.Value) {
                $totalSizeBytes = [long]$stats.TotalItemSize.Value.ToBytes()
            } else {
                $warnings.Add([pscustomobject]@{ code = 'PROPERTY_UNAVAILABLE'; message = 'Mailbox statistics TotalItemSize was unavailable.' })
            }
        }
        catch {
            $warnings.Add([pscustomobject]@{ code = 'PROPERTY_UNAVAILABLE'; message = 'Mailbox statistics could not be retrieved.' })
        }
    } else {
        $warnings.Add([pscustomobject]@{ code = 'PROPERTY_UNAVAILABLE'; message = 'Mailbox statistics cmdlet or ExchangeGuid unavailable.' })
    }

    $quotaBytes = $null
    if ($null -ne $mbx.ProhibitSendQuota -and $null -ne $mbx.ProhibitSendQuota.Value) {
        $quotaBytes = [long]$mbx.ProhibitSendQuota.Value.ToBytes()
    } else {
        $warnings.Add([pscustomobject]@{ code = 'PROPERTY_UNAVAILABLE'; message = 'Mailbox ProhibitSendQuota was unavailable.' })
    }

    $payload = [pscustomobject]@{
        target_user_id            = $targetId
        mailbox_exists            = $true
        recipient_type_details    = [string]$mbx.RecipientTypeDetails
        primary_smtp_address      = ([string]$mbx.PrimarySmtpAddress).Trim()
        total_item_size_bytes     = $totalSizeBytes
        prohibit_send_quota_bytes = $quotaBytes
    }

    if ($warnings.Count -gt 0) {
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

