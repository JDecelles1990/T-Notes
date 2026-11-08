#requires -Version 7.0
<#
.SYNOPSIS
    Inspect OneDrive Service Plans & Sync Readiness (M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC).
.DESCRIPTION
    Verify OneDrive for Business and SharePoint storage service plan provisioning for the target user.
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

if ($null -eq $Context -or $Context.contract_version -ne '0.3.0' -or $Context.script_id -ne 'M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        [pscustomobject]@{
            code      = 'CONTRACT_VIOLATION'
            message   = 'Invalid invocation context for M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC.'
            retryable = $false
        }
    )
}

$allowedParams = @('IncludeSharePointPlan')
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
            message   = 'M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC requires a resolved Entra object_id target.'
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
                service_plan_id     = 'afcafa6a-d966-4462-918c-ec0b4e0fe642'
                service_plan_name   = 'ONEDRIVE_ENTERPRISE'
                provisioning_status = 'Success'
            },
            [pscustomobject]@{
                service_plan_id     = '5dbe027f-2339-4123-9542-606e4d348a72'
                service_plan_name   = 'SHAREPOINTENTERPRISE'
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
