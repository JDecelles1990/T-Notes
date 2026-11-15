#requires -Version 7.0
<#
.SYNOPSIS
    Audit Mailbox Delegation & Permissions (M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT).
.DESCRIPTION
    Inspect Exchange Online Full Access (Get-EXOMailboxPermission), Send As
    (Get-EXORecipientPermission), and Send on Behalf (GrantSendOnBehalfTo) delegates
    for a resolved Entra user mailbox. Excludes built-in NT AUTHORITY\SELF entries.
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

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT.'
    )
}

$allowedParams = @('IncludeSendAsCheck', 'MaxDelegates')
if ($null -ne $Parameters) {
    foreach ($key in $Parameters.Keys) {
        if ($allowedParams -notcontains [string]$key) {
            return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
                New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter '$key'."
            )
        }
    }
}

$includeSendAsCheck = $true
if ($null -ne $Parameters -and $Parameters.ContainsKey('IncludeSendAsCheck')) {
    $rawSendAs = $Parameters['IncludeSendAsCheck']
    if (-not ($rawSendAs -is [bool])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'IncludeSendAsCheck must be a boolean.'
        )
    }
    $includeSendAsCheck = [bool]$rawSendAs
}

$maxDelegates = 20
if ($null -ne $Parameters -and $Parameters.ContainsKey('MaxDelegates')) {
    $rawMax = $Parameters['MaxDelegates']
    if ($rawMax -is [bool] -or -not ($rawMax -is [int] -or $rawMax -is [long])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'MaxDelegates must be an integer between 1 and 50.'
        )
    }
    $maxDelegates = [int]$rawMax
    if ($maxDelegates -lt 1 -or $maxDelegates -gt 50) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'MaxDelegates must be between 1 and 50.'
        )
    }
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
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT requires a resolved Entra object_id target.'
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
        'GrantSendOnBehalfTo'
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
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Exchange mailbox permissions lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)ManagementObjectNotFoundException|not\s+found|couldn''t\s+be\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'MAILBOX_NOT_FOUND' -Message 'No Exchange Online mailbox exists for the target user.'
            )
        }
        if ($errMsg -match '(?i)AccessDenied|not\s+authorized|Forbidden|RBAC') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Exchange Online mailbox permissions.'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Exchange Online throttled the mailbox permissions audit query.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Exchange Online mailbox permissions query failed.' -Retryable $true
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
            $totalSizeBytes = ConvertTo-QuotaBytes (Get-SafeProp $stats 'TotalItemSize')
            if ($null -eq $totalSizeBytes) {
                $hasPartialProp = $true
                $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Mailbox TotalItemSize statistics were unavailable.'))
            }
        }
        catch {
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

    $fullAccessCmd = Get-Command -Name 'Get-EXOMailboxPermission' -ErrorAction SilentlyContinue
    if ($null -ne $fullAccessCmd) {
        try {
            $permRows = @(Get-EXOMailboxPermission -Identity $statsIdentity -ErrorAction Stop)
            $fullAccessUsers = [System.Collections.Generic.List[string]]::new()
            foreach ($row in $permRows) {
                if ($null -eq $row) { continue }
                $trustee = ([string](Get-SafeProp $row 'User')).Trim()
                if ([string]::IsNullOrWhiteSpace($trustee) -or $trustee -ieq 'NT AUTHORITY\SELF') { continue }
                $deny = Get-SafeProp $row 'Deny'
                if ($deny -eq $true) { continue }
                $rights = @((Get-SafeProp $row 'AccessRights') | ForEach-Object { [string]$_ })
                if ($rights -contains 'FullAccess') {
                    if ($fullAccessUsers -notcontains $trustee) {
                        $fullAccessUsers.Add($trustee)
                    }
                }
            }
            if ($fullAccessUsers.Count -eq 0) {
                $warnings.Add((New-WarningItem -Code 'FULL_ACCESS_DELEGATES' -Message 'Full Access delegates: None (excluding NT AUTHORITY\SELF).'))
            } else {
                $shown = @($fullAccessUsers | Select-Object -First $maxDelegates)
                $suffix = if ($fullAccessUsers.Count -gt $maxDelegates) { " (+$($fullAccessUsers.Count - $maxDelegates) more)" } else { '' }
                $warnings.Add((New-WarningItem -Code 'FULL_ACCESS_DELEGATES' -Message "Full Access delegates ($($fullAccessUsers.Count)): $($shown -join ', ')$suffix"))
            }
        }
        catch {
            $warnings.Add((New-WarningItem -Code 'FULL_ACCESS_DELEGATES' -Message 'Full Access delegate lookup failed or lacks RBAC permission for Get-EXOMailboxPermission.'))
        }
    } else {
        $warnings.Add((New-WarningItem -Code 'FULL_ACCESS_DELEGATES' -Message 'Get-EXOMailboxPermission cmdlet is unavailable in this Exchange session.'))
    }

    if ($includeSendAsCheck) {
        $sendAsCmd = Get-Command -Name 'Get-EXORecipientPermission' -ErrorAction SilentlyContinue
        if ($null -ne $sendAsCmd) {
            try {
                $recipRows = @(Get-EXORecipientPermission -Identity $statsIdentity -ErrorAction Stop)
                $sendAsTrustees = [System.Collections.Generic.List[string]]::new()
                foreach ($row in $recipRows) {
                    if ($null -eq $row) { continue }
                    $trustee = ([string](Get-SafeProp $row 'Trustee')).Trim()
                    if ([string]::IsNullOrWhiteSpace($trustee) -or $trustee -ieq 'NT AUTHORITY\SELF') { continue }
                    $rights = @((Get-SafeProp $row 'AccessRights') | ForEach-Object { [string]$_ })
                    if ($rights -contains 'SendAs') {
                        if ($sendAsTrustees -notcontains $trustee) {
                            $sendAsTrustees.Add($trustee)
                        }
                    }
                }
                if ($sendAsTrustees.Count -eq 0) {
                    $warnings.Add((New-WarningItem -Code 'SEND_AS_DELEGATES' -Message 'Send As trustees: None (excluding NT AUTHORITY\SELF).'))
                } else {
                    $shown = @($sendAsTrustees | Select-Object -First $maxDelegates)
                    $suffix = if ($sendAsTrustees.Count -gt $maxDelegates) { " (+$($sendAsTrustees.Count - $maxDelegates) more)" } else { '' }
                    $warnings.Add((New-WarningItem -Code 'SEND_AS_DELEGATES' -Message "Send As trustees ($($sendAsTrustees.Count)): $($shown -join ', ')$suffix"))
                }
            }
            catch {
                $warnings.Add((New-WarningItem -Code 'SEND_AS_DELEGATES' -Message 'Send As delegate lookup failed or lacks RBAC permission for Get-EXORecipientPermission.'))
            }
        } else {
            $warnings.Add((New-WarningItem -Code 'SEND_AS_DELEGATES' -Message 'Get-EXORecipientPermission cmdlet is unavailable in this Exchange session.'))
        }
    } else {
        $warnings.Add((New-WarningItem -Code 'SEND_AS_DELEGATES' -Message 'Send As lookup skipped (IncludeSendAsCheck=False).'))
    }

    $sendOnBehalf = @((Get-SafeProp $mbx 'GrantSendOnBehalfTo') | ForEach-Object { ([string]$_).Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($sendOnBehalf.Count -eq 0) {
        $warnings.Add((New-WarningItem -Code 'SEND_ON_BEHALF_DELEGATES' -Message 'Send on Behalf delegates: None.'))
    } else {
        $shown = @($sendOnBehalf | Select-Object -First $maxDelegates)
        $suffix = if ($sendOnBehalf.Count -gt $maxDelegates) { " (+$($sendOnBehalf.Count - $maxDelegates) more)" } else { '' }
        $warnings.Add((New-WarningItem -Code 'SEND_ON_BEHALF_DELEGATES' -Message "Send on Behalf delegates ($($sendOnBehalf.Count)): $($shown -join ', ')$suffix"))
    }

    $warnings.Add((New-WarningItem -Code 'DELEGATE_AUDIT_SCOPE' -Message "Delegate audit scope: read-only check excluding NT AUTHORITY\SELF (MaxDelegates=$maxDelegates)."))

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
$synthWarnings.Add((New-WarningItem -Code 'FULL_ACCESS_DELEGATES' -Message 'Full Access delegates (1): helpdesk.delegate@alpine.example'))
if ($includeSendAsCheck) {
    $synthWarnings.Add((New-WarningItem -Code 'SEND_AS_DELEGATES' -Message 'Send As trustees: None (excluding NT AUTHORITY\SELF).'))
} else {
    $synthWarnings.Add((New-WarningItem -Code 'SEND_AS_DELEGATES' -Message 'Send As lookup skipped (IncludeSendAsCheck=False).'))
}
$synthWarnings.Add((New-WarningItem -Code 'SEND_ON_BEHALF_DELEGATES' -Message 'Send on Behalf delegates: None.'))
$synthWarnings.Add((New-WarningItem -Code 'DELEGATE_AUDIT_SCOPE' -Message "Delegate audit scope: read-only check excluding NT AUTHORITY\SELF (MaxDelegates=$maxDelegates)."))

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
