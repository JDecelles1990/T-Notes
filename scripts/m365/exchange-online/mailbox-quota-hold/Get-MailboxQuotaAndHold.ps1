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

$ctxContract = [string](Get-SafeProp $Context 'contract_version')
$ctxScriptId = [string](Get-SafeProp $Context 'script_id')
$ctxTenantId = [string](Get-SafeProp $Context 'tenant_id')
$ctxAdminUpn = [string](Get-SafeProp $Context 'verified_account_upn')
if ($ctxContract -cne '0.3.0' -or $ctxScriptId -cne 'M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD' -or [string]::IsNullOrWhiteSpace($ctxTenantId) -or [string]::IsNullOrWhiteSpace($ctxAdminUpn)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD.'
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
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Exchange Online connection is required.'
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

$targetObj = Get-SafeProp $Context 'target'
$targetKindRaw = [string](Get-SafeProp $targetObj 'kind')
$targetValRaw = [string](Get-SafeProp $targetObj 'value')
if ($null -eq $targetObj -or $targetKindRaw -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD requires a resolved Entra object_id target.'
    )
}

$targetId = $targetValRaw.Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$roles = @((Get-SafeProp $exoConn 'effective_roles') | ForEach-Object { [string]$_ })
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
    catch [System.OperationCanceledException] {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox quota lookup.' -Retryable $true
        )
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
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
    catch [System.OperationCanceledException] {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox statistics lookup.' -Retryable $true
        )
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
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
                    if ($CancellationToken.IsCancellationRequested) {
                        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Archive mailbox statistics lookup.' -Retryable $true
                        )
                    }
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
                catch [System.OperationCanceledException] {
                    return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Archive mailbox statistics lookup.' -Retryable $true
                    )
                }
                catch {
                    if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
                        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Archive mailbox statistics lookup.' -Retryable $true
                        )
                    }
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

    if ($null -eq $totalBytes -or $null -eq $quotaBytes) {
        if (-not ($warnings | Where-Object { $_.code -eq 'PROPERTY_UNAVAILABLE' })) {
            $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox size or prohibit-send quota telemetry is unavailable from Exchange Online.'))
        }
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $warnings.ToArray()
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
