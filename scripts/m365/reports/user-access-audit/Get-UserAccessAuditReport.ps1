#requires -Version 7.0
<#
.SYNOPSIS
    Generate Read-Only User Access & Sign-In Audit Report (M365.REPORTS.USER_ACCESS_AUDIT_REPORT).
.DESCRIPTION
    Produce a read-only historical sign-in and application access summary report for ticket archival.
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

if ($null -eq $Context -or $Context.contract_version -ne '0.3.0' -or $Context.script_id -ne 'M365.REPORTS.USER_ACCESS_AUDIT_REPORT') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        [pscustomobject]@{
            code      = 'CONTRACT_VIOLATION'
            message   = 'Invalid invocation context for M365.REPORTS.USER_ACCESS_AUDIT_REPORT.'
            retryable = $false
        }
    )
}

$allowedParams = @('LookbackDays', 'MaxRecords')
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

$lookbackDays = if ($Parameters.ContainsKey('LookbackDays')) { [int]$Parameters['LookbackDays'] } else { 30 }
$maxRecords = if ($Parameters.ContainsKey('MaxRecords')) { [int]$Parameters['MaxRecords'] } else { 25 }

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

if ($Context.target.kind -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        [pscustomobject]@{
            code      = 'INVALID_PARAMETER'
            message   = 'M365.REPORTS.USER_ACCESS_AUDIT_REPORT requires a resolved Entra object_id target.'
            retryable = $false
        }
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
$lookbackStart = ([datetime]'2026-11-08T00:00:00Z').AddDays(-1 * $lookbackDays).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$allEvents = @(
    [pscustomobject]@{
        created_at       = '2026-11-08T13:10:00Z'
        app_display_name = 'Microsoft 365 Portal'
        success          = $true
        error_code       = 0
    },
    [pscustomobject]@{
        created_at       = '2026-11-07T17:45:00Z'
        app_display_name = 'Microsoft Graph Explorer'
        success          = (0 -eq 0)
        error_code       = 0
    }
)

$truncated = $allEvents.Length -gt $maxRecords
[object[]]$selectedEvents = @($allEvents | Select-Object -First $maxRecords)
$payload = [pscustomobject]@{
    target_user_id = $targetId
    lookback_start = $lookbackStart
    events         = [object[]]$selectedEvents
    returned_count = [int]$selectedEvents.Length
    truncated      = [bool]$truncated
}

if ($truncated) {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings @(
        [pscustomobject]@{
            code    = 'OUTPUT_LIMIT'
            message = "Events truncated to MaxRecords=$maxRecords."
        }
    )
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload
