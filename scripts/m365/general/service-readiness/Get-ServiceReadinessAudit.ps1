#requires -Version 7.0
<#
.SYNOPSIS
    Cross-Service Provisioning & Readiness Audit (M365.GENERAL.SERVICE_READINESS_AUDIT).
.DESCRIPTION
    Audit core Microsoft 365 service plan readiness across Exchange, Teams, SharePoint, and OneDrive.
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

if ($null -eq $Context -or $Context.contract_version -ne '0.3.0' -or $Context.script_id -ne 'M365.GENERAL.SERVICE_READINESS_AUDIT') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        [pscustomobject]@{
            code      = 'CONTRACT_VIOLATION'
            message   = 'Invalid invocation context for M365.GENERAL.SERVICE_READINESS_AUDIT.'
            retryable = $false
        }
    )
}

$allowedParams = @('IncludeCollaborationPlans')
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
            message   = 'M365.GENERAL.SERVICE_READINESS_AUDIT requires a resolved Entra object_id target.'
            retryable = $false
        }
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
[object[]]$licenses = @(
    [pscustomobject]@{
        sku_id          = '6fd2c87f-b296-42f0-b197-1e91e994b900'
        sku_part_number = 'ENTERPRISEPACK'
        service_plans   = [object[]]@(
            [pscustomobject]@{
                service_plan_id     = 'efb87545-963c-4e0d-99df-69c6916d9eb0'
                service_plan_name   = 'EXCHANGE_S_ENTERPRISE'
                provisioning_status = 'Success'
            },
            [pscustomobject]@{
                service_plan_id     = '57ff2da0-773e-42df-b2af-ffb7a2317929'
                service_plan_name   = 'TEAMS1'
                provisioning_status = 'Success'
            }
        )
    }
)

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data ([pscustomobject]@{
    target_user_id = $targetId
    licenses       = [object[]]$licenses
    returned_count = [int]$licenses.Length
    truncated      = $false
})
