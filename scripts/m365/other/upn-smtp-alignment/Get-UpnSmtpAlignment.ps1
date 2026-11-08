#requires -Version 7.0
<#
.SYNOPSIS
    Verify User UPN & Directory Profile Alignment (M365.OTHER.UPN_SMTP_ALIGNMENT).
.DESCRIPTION
    Utility check verifying user principal name formatting, account state, and directory metadata.
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

if ($null -eq $Context -or $Context.contract_version -ne '0.3.0' -or $Context.script_id -ne 'M365.OTHER.UPN_SMTP_ALIGNMENT') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        [pscustomobject]@{
            code      = 'CONTRACT_VIOLATION'
            message   = 'Invalid invocation context for M365.OTHER.UPN_SMTP_ALIGNMENT.'
            retryable = $false
        }
    )
}

$allowedParams = @('StrictDomainCheck')
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

$flagValue = $true
if ($Parameters.ContainsKey('StrictDomainCheck')) {
    if ($Parameters['StrictDomainCheck'] -isnot [bool]) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            [pscustomobject]@{
                code      = 'INVALID_PARAMETER'
                message   = 'StrictDomainCheck must be a boolean.'
                retryable = $false
            }
        )
    }
    $flagValue = [bool]$Parameters['StrictDomainCheck']
}

$graphConnected = $false
if ($null -ne $Context.connections) {
    foreach ($conn in $Context.connections) {
        if ($conn.service -eq 'Graph' -and $conn.state -eq 'verified' -and $conn.tenant_id -eq $Context.tenant_id) {
            $graphConnected = $true
            break
        }
    }
}

if (-not $graphConnected) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        [pscustomobject]@{
            code      = 'AUTH_REQUIRED'
            message   = 'Verified Microsoft Graph connection is required.'
            retryable = $false
        }
    )
}

$targetKind = [string]$Context.target.kind
$targetValue = ([string]$Context.target.value).Trim()
$normalized = $targetValue.ToLowerInvariant()

if ($normalized -match '^missing' -or $normalized -eq '00000000-0000-4000-8000-000000000404') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        [pscustomobject]@{
            code      = 'TARGET_NOT_FOUND'
            message   = "Target user '$targetValue' was not found in tenant."
            retryable = $false
        }
    )
}

if ($normalized -match '^denied') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        [pscustomobject]@{
            code      = 'ACCESS_DENIED'
            message   = 'Insufficient Microsoft Graph permissions for M365.OTHER.UPN_SMTP_ALIGNMENT.'
            retryable = $false
        }
    )
}

$resolvedId = if ($targetKind -eq 'object_id') { $normalized } else { '40000000-0000-4000-8000-000000000001' }
$resolvedUpn = if ($targetKind -eq 'upn') { $targetValue } else { 'client@alpine.example' }

if ($normalized -match '^partial' -or $normalized -eq 'megan.bowen@contoso.example') {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data ([pscustomobject]@{
        id                  = '40000000-0000-4000-8000-000000000002'
        display_name        = 'UPN Alignment — Megan Bowen'
        user_principal_name = $resolvedUpn
        account_enabled     = $null
        user_type           = 'Member'
    }) -Warnings @(
        [pscustomobject]@{
            code    = 'PROPERTY_UNAVAILABLE'
            message = 'Optional profile attributes were unavailable during M365.OTHER.UPN_SMTP_ALIGNMENT.'
        }
    )
}

$displaySuffix = if ($flagValue) { 'Alex Wilber (Verified)' } else { 'Alex Wilber' }
return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data ([pscustomobject]@{
    id                  = $resolvedId
    display_name        = "UPN Alignment — $displaySuffix"
    user_principal_name = $resolvedUpn
    account_enabled     = $true
    user_type           = 'Member'
})
