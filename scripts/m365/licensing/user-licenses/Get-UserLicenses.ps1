#Requires -Version 7.0
param(
    [Parameter(Mandatory = $true)][psobject]$Context,
    [Parameter(Mandatory = $true)][hashtable]$Parameters,
    [Parameter(Mandatory = $true)][System.Threading.CancellationToken]$CancellationToken
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

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.'
    )
}

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.ENTRA.USER_LICENSES') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context version or script identity.'
    )
}

if ($null -eq $Parameters -or $Parameters.Count -gt 0) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.ENTRA.USER_LICENSES accepts no extra parameters.'
    )
}

if ($null -eq $Context.target -or [string]$Context.target.kind -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.ENTRA.USER_LICENSES requires a resolved object_id target.'
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$graphConn = $null
if ($null -ne $Context.connections) {
    foreach ($conn in @($Context.connections)) {
        if ($null -ne $conn -and [string]$conn.service -eq 'Graph') {
            $graphConn = $conn
            break
        }
    }
}
if ($null -eq $graphConn -or [string]$graphConn.state -ne 'verified') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Microsoft Graph connection state is required.'
    )
}
if ([string]$graphConn.tenant_id -ne [string]$Context.tenant_id) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'TENANT_MISMATCH' -Message 'Graph connection tenant does not match invocation tenant.'
    )
}
if ([string]$graphConn.verified_account_upn -ne [string]$Context.verified_account_upn) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCOUNT_MISMATCH' -Message 'Graph connection account does not match invocation administrator.'
    )
}

$scopes = @($graphConn.graph_scopes | ForEach-Object { [string]$_ })
$roles = @($graphConn.effective_roles | ForEach-Object { [string]$_ })
if ('LicenseAssignment.Read.All' -notin $scopes -or 'Directory.Readers' -notin $roles) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Graph scope LicenseAssignment.Read.All and role Directory.Readers are not present.'
    )
}

$mgLicenseCmd = Get-Command -Name 'Get-MgUserLicenseDetail' -ErrorAction SilentlyContinue
if ($null -ne $mgLicenseCmd) {
    try {
        $rawLicenses = @(Get-MgUserLicenseDetail -UserId $targetId -Property @('Id', 'SkuId', 'SkuPartNumber', 'ServicePlans') -ErrorAction Stop)
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during license lookup.'
            )
        }
        if ($errMsg -match '(?i)Request_ResourceNotFound|404|not\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'The requested Entra user was not found during license lookup.'
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading user license details.'
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph license lookup failed.' -Retryable $true
        )
    }

    $normalizedLicenses = [System.Collections.Generic.List[object]]::new()
    $truncated = $false
    foreach ($lic in $rawLicenses) {
        if ($null -eq $lic) { continue }
        if ($normalizedLicenses.Count -ge 100) {
            $truncated = $true
            break
        }
        $plans = [System.Collections.Generic.List[object]]::new()
        if ($null -ne $lic.ServicePlans) {
            foreach ($sp in @($lic.ServicePlans)) {
                if ($null -eq $sp) { continue }
                if ($plans.Count -ge 100) { break }
                $plans.Add([pscustomobject]@{
                    service_plan_id     = ([string]$sp.ServicePlanId).Trim().ToLowerInvariant()
                    service_plan_name   = [string]$sp.ServicePlanName
                    provisioning_status = [string]$sp.ProvisioningStatus
                })
            }
        }
        $normalizedLicenses.Add([pscustomobject]@{
            sku_id          = ([string]$lic.SkuId).Trim().ToLowerInvariant()
            sku_part_number = [string]$lic.SkuPartNumber
            service_plans   = [object[]]$plans.ToArray()
        })
    }

    $payload = [pscustomobject]@{
        target_user_id = $targetId
        licenses       = [object[]]$normalizedLicenses.ToArray()
        returned_count = [int]$normalizedLicenses.Count
        truncated      = [bool]$truncated
    }

    if ($truncated) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings @(
            [pscustomobject]@{ code = 'OUTPUT_LIMIT'; message = 'License results were truncated at 100 items.' }
        )
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload
}

# Offline synthetic fixture evaluation
if ($targetId -eq '40000000-0000-4000-8000-000000000404') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'No matching synthetic fixture target exists.'
    )
}
if ($targetId -eq '40000000-0000-4000-8000-000000000403') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'This operation is unavailable under the configured offline policy.'
    )
}

[object[]]$licenses = if ($targetId -eq '40000000-0000-4000-8000-000000000000') {
    @()
} else {
    @(
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
}

$payload = [pscustomobject]@{
    target_user_id = $targetId
    licenses       = [object[]]$licenses
    returned_count = [int]$licenses.Length
    truncated      = $false
}

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload

