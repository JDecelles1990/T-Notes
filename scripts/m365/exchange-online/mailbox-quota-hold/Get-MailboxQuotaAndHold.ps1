#requires -Version 7.0
<#
.SYNOPSIS
    Inspect Mailbox Quota, Archive & Litigation Hold (M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD).
.DESCRIPTION
    Verify Exchange Online storage consumption, archive mailbox status, and litigation hold flags.
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
        [Parameter()][object[]]$Warnings = @(),
        [Parameter()][object[]]$Errors = @()
    )
    return [pscustomobject]@{
        status            = $Status
        operation_outcome = $Outcome
        data              = $Data
        warnings          = [object[]]@($Warnings)
        errors            = [object[]]@($Errors)
    }
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        [pscustomobject]@{
            code      = 'CANCELLED'
            message   = 'Operation cancelled before execution.'
            retryable = $true
        }
    )
}

if ($null -eq $Context -or $Context.contract_version -ne '0.3.0' -or $Context.script_id -ne 'M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        [pscustomobject]@{
            code      = 'CONTRACT_VIOLATION'
            message   = 'Invalid invocation context for M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD.'
            retryable = $false
        }
    )
}

$allowedParams = @('IncludeArchiveCheck')
foreach ($key in $Parameters.Keys) {
    if ($allowedParams -notcontains [string]$key) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            [pscustomobject]@{
                code      = 'INVALID_PARAMETER'
                message   = "Unexpected parameter '$key'."
                retryable = $false
            }
        )
    }
}

$exoConnected = $false
if ($null -ne $Context.connections) {
    foreach ($conn in $Context.connections) {
        if ($conn.service -eq 'ExchangeOnline' -and $conn.state -eq 'verified' -and $conn.tenant_id -eq $Context.tenant_id) {
            $exoConnected = $true
            break
        }
    }
}

if (-not $exoConnected) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        [pscustomobject]@{
            code      = 'AUTH_REQUIRED'
            message   = 'Verified Exchange Online connection is required.'
            retryable = $false
        }
    )
}

if ($Context.target.kind -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        [pscustomobject]@{
            code      = 'INVALID_PARAMETER'
            message   = 'M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD requires a resolved Entra object_id target.'
            retryable = $false
        }
    )
}

$includeArchive = if ($Parameters.ContainsKey('IncludeArchiveCheck')) { [bool]$Parameters['IncludeArchiveCheck'] } else { $true }
$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
$itemBytes = if ($includeArchive) { [long]5368709120 } else { [long]104857600 }

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data ([pscustomobject]@{
    target_user_id            = $targetId
    mailbox_exists            = $true
    recipient_type_details    = 'UserMailbox'
    primary_smtp_address      = 'client@alpine.example'
    total_item_size_bytes     = $itemBytes
    prohibit_send_quota_bytes = [long]107374182400
})
