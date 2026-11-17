#requires -Version 7.0
<#
.SYNOPSIS
    Audit Mailbox Forwarding & Auto-Reply Posture (M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY).
.DESCRIPTION
    Inspect Exchange Online mailbox SMTP forwarding rules, DeliverToMailboxAndForward,
    Out-of-Office automatic replies (when Get-MailboxAutoReplyConfiguration is available),
    and Global Address List visibility for a resolved Entra user.
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
    param([object]$RawQuota)
    if ($null -eq $RawQuota) { return $null }

    $valProp = Get-SafeProp $RawQuota 'Value'
    $candidate = if ($null -ne $valProp) { $valProp } else { $RawQuota }

    if ($candidate -is [long] -or $candidate -is [int] -or $candidate -is [decimal] -or $candidate -is [double]) {
        return [long]$candidate
    }

    $toBytesMethod = $candidate.PSObject.Methods['ToBytes']
    if ($null -ne $toBytesMethod) {
        try {
            return [long]$candidate.ToBytes()
        } catch {
            return $null
        }
    }

    $text = ([string]$candidate).Trim()
    if ([string]::IsNullOrWhiteSpace($text) -or $text -match '^(?i)Unlimited$') {
        return $null
    }
    if ($text -match '\(([0-9,]+)\s*bytes\)') {
        $digits = $Matches[1] -replace ',', ''
        $parsed = [long]0
        if ([long]::TryParse($digits, [ref]$parsed)) { return $parsed }
    }
    $numericOnly = $text -replace ',', ''
    $directParsed = [long]0
    if ([long]::TryParse($numericOnly, [ref]$directParsed)) {
        return $directParsed
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
if ($ctxContract -cne '0.3.0' -or $ctxScriptId -cne 'M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY' -or [string]::IsNullOrWhiteSpace($ctxTenantId) -or [string]::IsNullOrWhiteSpace($ctxAdminUpn)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY.'
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

$allowedParams = @('IncludeAutoReplyCheck', 'WarnOnExternalForwarding')
if ($null -ne $Parameters) {
    foreach ($key in $Parameters.Keys) {
        if ($allowedParams -notcontains [string]$key) {
            return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
                New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter '$key'."
            )
        }
    }
}

$includeAutoReplyCheck = $true
if ($null -ne $Parameters -and $Parameters.ContainsKey('IncludeAutoReplyCheck')) {
    $rawAuto = $Parameters['IncludeAutoReplyCheck']
    if (-not ($rawAuto -is [bool])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'IncludeAutoReplyCheck must be a boolean.'
        )
    }
    $includeAutoReplyCheck = [bool]$rawAuto
}

$warnOnExternalForwarding = $true
if ($null -ne $Parameters -and $Parameters.ContainsKey('WarnOnExternalForwarding')) {
    $rawWarn = $Parameters['WarnOnExternalForwarding']
    if (-not ($rawWarn -is [bool])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'WarnOnExternalForwarding must be a boolean.'
        )
    }
    $warnOnExternalForwarding = [bool]$rawWarn
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
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY requires a resolved Entra object_id target.'
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
if (-not (('cmdlet.Get-EXOMailbox' -in $roles -and 'cmdlet.Get-EXOMailboxStatistics' -in $roles) -or ('View-Only Recipients' -in $roles) -or ('View-Only.Recipients' -in $roles) -or ('Organization Management' -in $roles))) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Exchange Online cmdlet roles (Get-EXOMailbox, Get-EXOMailboxStatistics or View-Only Recipients) are not present.'
    )
}

$exoMailboxCmd = Get-Command -Name 'Get-EXOMailbox' -ErrorAction SilentlyContinue
if ($null -ne $exoMailboxCmd) {
    $props = @(
        'ExternalDirectoryObjectId',
        'ExchangeGuid',
        'PrimarySmtpAddress',
        'RecipientTypeDetails',
        'ProhibitSendQuota',
        'ForwardingSmtpAddress',
        'ForwardingAddress',
        'DeliverToMailboxAndForward',
        'HiddenFromAddressListsEnabled'
    )
    try {
        $mbxSplat = @{
            Properties  = $props
            ErrorAction = 'Stop'
        }
        if ($exoMailboxCmd.Parameters.ContainsKey('ExternalDirectoryObjectId')) {
            $mbxSplat['ExternalDirectoryObjectId'] = $parsedGuid
        } else {
            $mbxSplat['Identity'] = $targetId
        }
        $mbx = Get-EXOMailbox @mbxSplat
    }
    catch [System.OperationCanceledException] {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox forwarding lookup.' -Retryable $true
        )
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange forwarding lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)ManagementObjectNotFoundException|not\s+found|couldn''t\s+be\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'MAILBOX_NOT_FOUND' -Message 'No Exchange Online mailbox exists for the target user.'
            )
        }
        if ($errMsg -match '(?i)AccessDenied|not\s+authorized|Forbidden|RBAC') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Exchange Online mailbox forwarding settings.'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Exchange Online throttled the mailbox forwarding lookup.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Exchange Online mailbox forwarding query failed.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Exchange mailbox query.' -Retryable $true
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
    $hasPartialProp = $false

    $rawStatsId = Get-SafeProp $mbx 'ExchangeGuid'
    $statsIdentity = if ($null -ne $rawStatsId -and -not [string]::IsNullOrWhiteSpace([string]$rawStatsId)) { [string]$rawStatsId } else { $targetId }

    $totalSizeBytes = $null
    $exoStatsCmd = Get-Command -Name 'Get-EXOMailboxStatistics' -ErrorAction SilentlyContinue
    if ($null -ne $exoStatsCmd) {
        try {
            $statsSplat = @{
                Identity    = $statsIdentity
                ErrorAction = 'Stop'
            }
            if ($exoStatsCmd.Parameters.ContainsKey('Properties')) {
                $statsSplat['Properties'] = @('TotalItemSize')
            }
            $stats = Get-EXOMailboxStatistics @statsSplat
            if ($CancellationToken.IsCancellationRequested) {
                return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                    New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Exchange mailbox statistics lookup.' -Retryable $true
                )
            }
            $totalSizeBytes = ConvertTo-QuotaBytes (Get-SafeProp $stats 'TotalItemSize')
            if ($null -eq $totalSizeBytes) {
                $hasPartialProp = $true
                $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox TotalItemSize statistics were unavailable.'))
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
            $hasPartialProp = $true
            $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox statistics could not be retrieved.'))
        }
    } else {
        $hasPartialProp = $true
        $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Get-EXOMailboxStatistics cmdlet is unavailable.'))
    }

    $quotaBytes = ConvertTo-QuotaBytes (Get-SafeProp $mbx 'ProhibitSendQuota')
    if ($null -eq $quotaBytes) {
        $hasPartialProp = $true
        $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox ProhibitSendQuota was unavailable or unlimited.'))
    }

    $fwdSmtp = ([string](Get-SafeProp $mbx 'ForwardingSmtpAddress')).Trim()
    $fwdInternal = ([string](Get-SafeProp $mbx 'ForwardingAddress')).Trim()
    $rawDeliver = Get-SafeProp $mbx 'DeliverToMailboxAndForward'
    $deliverCopy = if ($null -ne $rawDeliver) { [bool]$rawDeliver } else { $false }

    $hasFwdWarning = $false
    if (-not [string]::IsNullOrWhiteSpace($fwdSmtp)) {
        if ($warnOnExternalForwarding) {
            $warnings.Add((New-WarningItem -Code 'EXTERNAL_FORWARDING_ACTIVE' -Message "External SMTP forwarding is active -> $fwdSmtp (DeliverToMailboxAndForward=$deliverCopy)."))
            $hasFwdWarning = $true
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($fwdInternal)) {
        $warnings.Add((New-WarningItem -Code 'INTERNAL_FORWARDING_ACTIVE' -Message "Internal mailbox forwarding target is configured -> $fwdInternal (DeliverToMailboxAndForward=$deliverCopy)."))
        $hasFwdWarning = $true
    }
    if (-not $hasFwdWarning) {
        if (-not [string]::IsNullOrWhiteSpace($fwdSmtp) -and -not $warnOnExternalForwarding) {
            $warnings.Add((New-WarningItem -Code 'NO_FORWARDING_CONFIGURED' -Message "SMTP forwarding present ($fwdSmtp) with WarnOnExternalForwarding=False."))
        } else {
            $warnings.Add((New-WarningItem -Code 'NO_FORWARDING_CONFIGURED' -Message 'No external SMTP or internal mailbox forwarding is configured on this mailbox.'))
        }
    }

    $rawHidden = Get-SafeProp $mbx 'HiddenFromAddressListsEnabled'
    if ($null -ne $rawHidden) {
        $isHidden = [bool]$rawHidden
        if ($isHidden) {
            $warnings.Add((New-WarningItem -Code 'GAL_VISIBILITY' -Message 'Mailbox is hidden from the Global Address List (HiddenFromAddressListsEnabled=True).'))
        } else {
            $warnings.Add((New-WarningItem -Code 'GAL_VISIBILITY' -Message 'Mailbox is visible in the Global Address List (HiddenFromAddressListsEnabled=False).'))
        }
    }

    if ($includeAutoReplyCheck) {
        $autoReplyCmd = Get-Command -Name 'Get-MailboxAutoReplyConfiguration' -ErrorAction SilentlyContinue
        if ($null -ne $autoReplyCmd) {
            try {
                $oof = Get-MailboxAutoReplyConfiguration -Identity $statsIdentity -ErrorAction Stop
                $oofState = [string](Get-SafeProp $oof 'AutoReplyState')
                if ([string]::IsNullOrWhiteSpace($oofState)) { $oofState = 'Unknown' }
                $extAudience = [string](Get-SafeProp $oof 'ExternalAudience')
                $msg = "Automatic Replies (OOF): State=$oofState"
                if ($oofState -eq 'Scheduled') {
                    $startT = Get-SafeProp $oof 'StartTime'
                    $endT = Get-SafeProp $oof 'EndTime'
                    $msg += " | Window=$startT to $endT"
                }
                if (-not [string]::IsNullOrWhiteSpace($extAudience)) {
                    $msg += " | ExternalAudience=$extAudience"
                }
                $warnings.Add((New-WarningItem -Code 'AUTO_REPLY_STATUS' -Message $msg))
            }
            catch [System.OperationCanceledException] {
                return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                    New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Auto-Reply lookup.' -Retryable $true
                )
            }
            catch {
                if ($CancellationToken.IsCancellationRequested -or $_.Exception -is [System.OperationCanceledException]) {
                    return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Auto-Reply lookup.' -Retryable $true
                    )
                }
                $warnings.Add((New-WarningItem -Code 'AUTO_REPLY_STATUS' -Message 'Automatic Replies (OOF) lookup failed or lacks RBAC permissions for Get-MailboxAutoReplyConfiguration.'))
            }
        } else {
            $warnings.Add((New-WarningItem -Code 'AUTO_REPLY_STATUS' -Message 'Get-MailboxAutoReplyConfiguration cmdlet is unavailable in this Exchange session; OOF status not checked.'))
        }
    }

    $recType = [string](Get-SafeProp $mbx 'RecipientTypeDetails')
    if ([string]::IsNullOrWhiteSpace($recType)) { $recType = 'UserMailbox' }
    $primarySmtp = ([string](Get-SafeProp $mbx 'PrimarySmtpAddress')).Trim()

    $payload = [pscustomobject]@{
        target_user_id            = $targetId
        mailbox_exists            = $true
        recipient_type_details    = $recType
        primary_smtp_address      = $primarySmtp
        total_item_size_bytes     = $totalSizeBytes
        prohibit_send_quota_bytes = $quotaBytes
    }

    if ($hasPartialProp) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $warnings.ToArray()
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload -Warnings $warnings.ToArray()
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
$synthWarnings = [System.Collections.Generic.List[object]]::new()
if ($isPartial) {
    $synthWarnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox size telemetry is unavailable in the partial synthetic fixture.'))
}
if ($warnOnExternalForwarding -and $targetId -eq '40000000-0000-4000-8000-000000000003') {
    $synthWarnings.Add((New-WarningItem -Code 'EXTERNAL_FORWARDING_ACTIVE' -Message 'External SMTP forwarding is active -> smtp:forward@external.invalid (DeliverToMailboxAndForward=True).'))
} else {
    $synthWarnings.Add((New-WarningItem -Code 'NO_FORWARDING_CONFIGURED' -Message 'No external SMTP or internal mailbox forwarding is configured on this mailbox.'))
}
$synthWarnings.Add((New-WarningItem -Code 'GAL_VISIBILITY' -Message 'Mailbox is visible in the Global Address List (HiddenFromAddressListsEnabled=False).'))
if ($includeAutoReplyCheck) {
    $synthWarnings.Add((New-WarningItem -Code 'AUTO_REPLY_STATUS' -Message 'Automatic Replies (OOF): State=Disabled | ExternalAudience=All'))
}

$payload = [pscustomobject]@{
    target_user_id            = $targetId
    mailbox_exists            = $true
    recipient_type_details    = 'UserMailbox'
    primary_smtp_address      = $smtp
    total_item_size_bytes     = if ($isPartial) { $null } else { [long]104857600 }
    prohibit_send_quota_bytes = [long]53687091200
}

if ($isPartial) {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $synthWarnings.ToArray()
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload -Warnings $synthWarnings.ToArray()
