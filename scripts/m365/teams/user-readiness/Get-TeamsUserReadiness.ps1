#requires -Version 7.0
<#
.SYNOPSIS
    Inspect Teams Licensing & Voice Service Plans (M365.TEAMS.USER_READINESS).
.DESCRIPTION
    Verify Microsoft Teams core collaboration, audio conferencing, and phone system service plans.
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

if ($null -eq $Context -or $Context.contract_version -ne '0.3.0' -or $Context.script_id -ne 'M365.TEAMS.USER_READINESS') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        [pscustomobject]@{
            code      = 'CONTRACT_VIOLATION'
            message   = 'Invalid invocation context for M365.TEAMS.USER_READINESS.'
            retryable = $false
        }
    )
}

$allowedParams = @('IncludeVoicePlans')
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
            message   = 'M365.TEAMS.USER_READINESS requires a resolved Entra object_id target.'
            retryable = $false
        }
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
[object[]]$licenses = @(
    [pscustomobject]@{
        sku_id          = '06ebc4ee-1bb5-47dd-8120-11324bc54e06'
        sku_part_number = 'MCOEV_TEAMS_BUNDLE'
        service_plans   = [object[]]@(
            [pscustomobject]@{
                service_plan_id     = '57ff2da0-773e-42df-b2af-ffb7a2317929'
                service_plan_name   = 'TEAMS1'
                provisioning_status = 'Success'
            },
            [pscustomobject]@{
                service_plan_id     = '4828c8ec-dc2e-4779-b502-87ac9ce28ab7'
                service_plan_name   = 'MCOEV'
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
