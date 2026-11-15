#requires -Version 7.0
<#
.SYNOPSIS
    Inspect Mailbox Quota, Archive & Holds (M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD).
.DESCRIPTION
    Query Exchange Online mailbox statistics, quota headroom, archive status, and
    litigation/in-place hold flags for a resolved user target.
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

function Get-SafeProp {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -ne $prop) { return $prop.Value }
    return $null
}

function ConvertTo-QuotaBytes {
    param([object]$RawValue)
    if ($null -eq $RawValue) { return $null }
    $str = ([string]$RawValue).Trim()
    if ([string]::IsNullOrWhiteSpace($str) -or $str -match '(?i)^Unlimited$') { return $null }
    if ($RawValue -is [int] -or $RawValue -is [long] -or $RawValue -is [double] -or $RawValue -is [decimal]) {
        $v = [int64]$RawValue
        if ($v -ge 0) { return $v }
        return $null
    }
    $valObj = Get-SafeProp $RawValue 'Value'
    if ($null -ne $valObj) {
        $toBytesMethod = $valObj.PSObject.Methods['ToBytes']
        if ($null -ne $toBytesMethod) {
            return [int64]$valObj.ToBytes()
        }
    }
    $directToBytes = $RawValue.PSObject.Methods['ToBytes']
    if ($null -ne $directToBytes) {
        return [int64]$RawValue.ToBytes()
    }
    if ($str -match '\(([0-9,]+)\s*bytes?\)') {
        $digits = $Matches[1] -replace ',', ''
        return [int64]$digits
    }
    if ($str -match '^([0-9]+(?:\.[0-9]+)?)\s*(B|KB|MB|GB|TB)$') {
        $num = [double]$Matches[1]
        switch ($Matches[2].ToUpperInvariant()) {
            'B'  { return [int64]$num }
            'KB' { return [int64]($num * 1024) }
            'MB' { return [int64]($num * 1048576) }
            'GB' { return [int64]($num * 1073741824) }
            'TB' { return [int64]($num * 1099511627776) }
        }
    }
    if ($str -match '^[0-9]+$') {
        return [int64]$str
    }
    return $null
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.' -Retryable $true
    )
}

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD.'
    )
}

$allowedParams = @('IncludeArchiveCheck')
if ($null -ne $Parameters) {
    foreach ($key in $Parameters.Keys) {
        if ($allowedParams -notcontains [string]$key) {
            return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
                New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter '$key'."
            )
        }
    }
}

$includeArchiveCheck = $true
if ($null -ne $Parameters -and $Parameters.ContainsKey('IncludeArchiveCheck')) {
    $rawArch = $Parameters['IncludeArchiveCheck']
    if ($rawArch -isnot [bool]) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'IncludeArchiveCheck must be a boolean.'
        )
    }
    $includeArchiveCheck = [bool]$rawArch
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
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Exchange Online connection is required.'
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

if ($null -eq $Context.target -or [string]$Context.target.kind -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD requires a resolved Entra object_id target.'
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$roles = @($exoConn.effective_roles | ForEach-Object { [string]$_ })
$hasMailboxRole = ('cmdlet.Get-EXOMailbox' -in $roles) -or ('View-Only.Recipients' -in $roles)
$hasStatsRole = ('cmdlet.Get-EXOMailboxStatistics' -in $roles) -or ('View-Only.Recipients' -in $roles)
if (-not ($hasMailboxRole -and $hasStatsRole)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Exchange Online RBAC role (View-Only Recipients) or cmdlets Get-EXOMailbox and Get-EXOMailboxStatistics are not available.'
    )
}

$exoMbxCmd = Get-Command -Name 'Get-EXOMailbox' -ErrorAction SilentlyContinue
$exoStatsCmd = Get-Command -Name 'Get-EXOMailboxStatistics' -ErrorAction SilentlyContinue
if ($null -ne $exoMbxCmd -and $null -ne $exoStatsCmd) {
    $mbx = $null
    try {
        $exoMbxParams = @{ ErrorAction = 'Stop' }
        if ($exoMbxCmd.Parameters.ContainsKey('ExternalDirectoryObjectId')) {
            $exoMbxParams['ExternalDirectoryObjectId'] = $parsedGuid
        } else {
            $exoMbxParams['Identity'] = $targetId
        }
        if ($exoMbxCmd.Parameters.ContainsKey('Properties')) {
            $exoMbxParams['Properties'] = @(
                'PrimarySmtpAddress',
                'RecipientTypeDetails',
                'ProhibitSendQuota',
                'ProhibitSendReceiveQuota',
                'IssueWarningQuota',
                'LitigationHoldEnabled',
                'InPlaceHolds',
                'RetentionHoldEnabled',
                'ArchiveStatus',
                'ExternalDirectoryObjectId',
                'UserPrincipalName'
            )
        }
        $mbx = Get-EXOMailbox @exoMbxParams
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange Online mailbox lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)ManagementObjectNotFound|couldn''t\s+be\s+found|not\s+found|does\s+not\s+have\s+a\s+mailbox|Ex6F9304') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'MAILBOX_NOT_FOUND' -Message 'No Exchange Online mailbox exists for the resolved target user.'
            )
        }
        if ($errMsg -match '(?i)Authorization|Access\s+is\s+denied|401|403|Forbidden|RBAC|management\s+role|isn''t\s+assigned') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied reading Exchange Online mailbox properties (View-Only Recipients RBAC role required).'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl|MicroDelay|ServerBusy') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Exchange Online throttled the mailbox lookup request.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Exchange Online mailbox query failed.' -Retryable $true
        )
    }

    if ($null -eq $mbx) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'MAILBOX_NOT_FOUND' -Message 'No Exchange Online mailbox exists for the resolved target user.'
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Exchange Online mailbox lookup.' -Retryable $true
        )
    }

    $extId = Get-SafeProp $mbx 'ExternalDirectoryObjectId'
    if ($null -ne $extId -and -not [string]::IsNullOrWhiteSpace([string]$extId)) {
        if (([string]$extId).Trim().ToLowerInvariant() -ne $targetId) {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned mailbox ExternalDirectoryObjectId does not match target object_id.'
            )
        }
    }

    $primarySmtp = [string](Get-SafeProp $mbx 'PrimarySmtpAddress')
    if ([string]::IsNullOrWhiteSpace($primarySmtp)) {
        $primarySmtp = [string](Get-SafeProp $mbx 'UserPrincipalName')
    }
    if ([string]::IsNullOrWhiteSpace($primarySmtp)) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Exchange Online mailbox did not return a primary SMTP address.'
        )
    }

    $recipientType = [string](Get-SafeProp $mbx 'RecipientTypeDetails')
    if ([string]::IsNullOrWhiteSpace($recipientType)) { $recipientType = 'UserMailbox' }

    $statsIdentity = if (-not [string]::IsNullOrWhiteSpace($primarySmtp)) { $primarySmtp } else { $targetId }
    $warnings = [System.Collections.Generic.List[object]]::new()
    $totalBytes = $null

    try {
        $stats = Get-EXOMailboxStatistics -Identity $statsIdentity -ErrorAction Stop
        if ($null -ne $stats) {
            $totalBytes = ConvertTo-QuotaBytes (Get-SafeProp $stats 'TotalItemSize')
        }
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange Online statistics lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Authorization|Access\s+is\s+denied|401|403|Forbidden|RBAC|management\s+role') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied reading Exchange Online mailbox statistics.'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl|MicroDelay|ServerBusy') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Exchange Online throttled the mailbox statistics request.' -Retryable $true
            )
        }
        $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Primary mailbox statistics are currently unavailable for this mailbox.'))
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Exchange Online statistics lookup.' -Retryable $true
        )
    }

    $quotaBytes = ConvertTo-QuotaBytes (Get-SafeProp $mbx 'ProhibitSendQuota')

    # Hold posture summary
    $litHold = [bool](Get-SafeProp $mbx 'LitigationHoldEnabled')
    $retHold = [bool](Get-SafeProp $mbx 'RetentionHoldEnabled')
    $rawInPlace = Get-SafeProp $mbx 'InPlaceHolds'
    $inPlaceCount = if ($null -eq $rawInPlace) { 0 } else { @($rawInPlace | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count }
    $warnings.Add((New-WarningItem -Code 'HOLD_STATUS' -Message "Hold status: LitigationHoldEnabled=$litHold | RetentionHoldEnabled=$retHold | InPlaceHolds=$inPlaceCount."))

    # Quota headroom check (>= 85%)
    if ($null -ne $totalBytes -and $null -ne $quotaBytes -and $quotaBytes -gt 0) {
        $usagePct = [Math]::Round(($totalBytes / $quotaBytes) * 100.0, 1)
        if ($usagePct -ge 85.0) {
            $warnings.Add((New-WarningItem -Code 'QUOTA_HIGH' -Message "Mailbox quota usage is high ($usagePct% of ProhibitSendQuota: $totalBytes / $quotaBytes bytes)."))
        }
    }

    # Optional Archive mailbox check
    if ($includeArchiveCheck) {
        $archiveStatus = ([string](Get-SafeProp $mbx 'ArchiveStatus')).Trim()
        if ($archiveStatus -eq 'Active') {
            $archSizeText = 'Active (size unavailable)'
            if ($exoStatsCmd.Parameters.ContainsKey('Archive')) {
                try {
                    $archStats = Get-EXOMailboxStatistics -Identity $statsIdentity -Archive -ErrorAction Stop
                    if ($null -ne $archStats) {
                        $archBytes = ConvertTo-QuotaBytes (Get-SafeProp $archStats 'TotalItemSize')
                        if ($null -ne $archBytes) {
                            $archGb = [Math]::Round($archBytes / 1073741824.0, 2)
                            $archSizeText = "Active ($archBytes bytes / $archGb GB)"
                        } else {
                            $archSizeText = 'Active (0 or empty statistics)'
                        }
                    }
                }
                catch {
                    $archSizeText = 'Active (archive statistics not yet initialized)'
                }
            } else {
                $archSizeText = 'Active'
            }
            $warnings.Add((New-WarningItem -Code 'ARCHIVE_SUMMARY' -Message "In-Place Archive status: $archSizeText."))
        } else {
            $statusLabel = if ([string]::IsNullOrWhiteSpace($archiveStatus)) { 'None' } else { $archiveStatus }
            $warnings.Add((New-WarningItem -Code 'ARCHIVE_DISABLED' -Message "In-Place Archive is not active (ArchiveStatus='$statusLabel')."))
        }
    }

    $payload = [pscustomobject]@{
        target_user_id            = $targetId
        mailbox_exists            = $true
        recipient_type_details    = $recipientType
        primary_smtp_address      = $primarySmtp
        total_item_size_bytes     = $totalBytes
        prohibit_send_quota_bytes = $quotaBytes
    }

    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload -Warnings $warnings.ToArray()
}

# Offline synthetic fixture evaluation
$payload = [pscustomobject]@{
    target_user_id            = $targetId
    mailbox_exists            = $true
    recipient_type_details    = 'UserMailbox'
    primary_smtp_address      = 'synthetic.user@example.invalid'
    total_item_size_bytes     = [int64]26843545600
    prohibit_send_quota_bytes = [int64]53687091200
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload
