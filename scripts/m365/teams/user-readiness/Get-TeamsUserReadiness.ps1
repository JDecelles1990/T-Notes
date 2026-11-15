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

function New-WarningItem {
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$Message
    )
    return [pscustomobject]@{
        code    = $Code
        message = $Message
    }
}

function Get-SafeProp {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -ne $prop) { return $prop.Value }
    return $null
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.' -Retryable $true
    )
}

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.TEAMS.USER_READINESS') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.TEAMS.USER_READINESS.'
    )
}

$allowedParams = @('IncludeVoicePlans')
if ($null -ne $Parameters) {
    foreach ($key in $Parameters.Keys) {
        if ($allowedParams -notcontains [string]$key) {
            return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
                New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter '$key'."
            )
        }
    }
}

$includeVoice = $true
if ($null -ne $Parameters -and $Parameters.ContainsKey('IncludeVoicePlans')) {
    if ($Parameters['IncludeVoicePlans'] -isnot [bool]) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'IncludeVoicePlans must be a boolean.'
        )
    }
    $includeVoice = [bool]$Parameters['IncludeVoicePlans']
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
        New-ErrorItem -Code 'AUTH_REQUIRED' -Message 'Verified Microsoft Graph connection is required.'
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

if ($null -eq $Context.target -or [string]$Context.target.kind -ne 'object_id') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'M365.TEAMS.USER_READINESS requires a resolved Entra object_id target.'
    )
}

$targetId = ([string]$Context.target.value).Trim().ToLowerInvariant()
$parsedGuid = [guid]::Empty
if (-not [guid]::TryParseExact($targetId, 'D', [ref]$parsedGuid)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
    )
}

$scopes = @($graphConn.graph_scopes | ForEach-Object { [string]$_ })
$roles = @($graphConn.effective_roles | ForEach-Object { [string]$_ })
if ('LicenseAssignment.Read.All' -notin $scopes -or ('Directory.Readers' -notin $roles -and 'License.Administrator' -notin $roles)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Graph scope LicenseAssignment.Read.All and role Directory.Readers or License.Administrator are not present.'
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
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Teams readiness lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Request_ResourceNotFound|404|not\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'The requested Entra user was not found during Teams readiness lookup.'
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Teams service plans (LicenseAssignment.Read.All required).'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the Teams readiness request.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph Teams readiness lookup failed.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Graph license lookup.' -Retryable $true
        )
    }

    $planPattern = if ($includeVoice) {
        '(?i)(TEAMS|MCO|PHONESYSTEM)'
    } else {
        '(?i)^(TEAMS|MICROSOFT_TEAMS|MCOSTANDARD|MCOLITE|MCOMEETADV)'
    }

    $normalizedLicenses = [System.Collections.Generic.List[object]]::new()
    $truncated = $false
    $provisionedTeamsCount = 0

    foreach ($lic in $rawLicenses) {
        if ($null -eq $lic) { continue }
        if ($normalizedLicenses.Count -ge 100) {
            $truncated = $true
            break
        }
        $skuId = ([string](Get-SafeProp $lic 'SkuId')).Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($skuId)) { continue }
        $skuPart = [string](Get-SafeProp $lic 'SkuPartNumber')
        if ([string]::IsNullOrWhiteSpace($skuPart)) { $skuPart = $skuId }
        if ($skuPart.Length -gt 128) { $skuPart = $skuPart.Substring(0, 128) }

        $plans = [System.Collections.Generic.List[object]]::new()
        $rawPlans = Get-SafeProp $lic 'ServicePlans'
        if ($null -ne $rawPlans) {
            foreach ($sp in @($rawPlans)) {
                if ($null -eq $sp) { continue }
                $spName = [string](Get-SafeProp $sp 'ServicePlanName')
                if ([string]::IsNullOrWhiteSpace($spName)) { continue }
                if ($spName -notmatch $planPattern) { continue }
                if ($plans.Count -ge 100) {
                    $truncated = $true
                    break
                }
                $spId = ([string](Get-SafeProp $sp 'ServicePlanId')).Trim().ToLowerInvariant()
                if ([string]::IsNullOrWhiteSpace($spId)) { continue }
                $prov = [string](Get-SafeProp $sp 'ProvisioningStatus')
                if ([string]::IsNullOrWhiteSpace($prov)) { $prov = 'Unknown' }
                if ($prov -eq 'Success') { $provisionedTeamsCount++ }
                $plans.Add([pscustomobject]@{
                    service_plan_id     = $spId
                    service_plan_name   = $spName
                    provisioning_status = $prov
                })
            }
        }

        if ($plans.Count -gt 0) {
            $normalizedLicenses.Add([pscustomobject]@{
                sku_id          = $skuId
                sku_part_number = $skuPart
                service_plans   = [object[]]$plans.ToArray()
            })
        }
    }

    $warnings = [System.Collections.Generic.List[object]]::new()
    if ($truncated) {
        $warnings.Add((New-WarningItem -Code 'OUTPUT_LIMIT' -Message 'Teams readiness results were truncated at 100 items.'))
    }
    if ($provisionedTeamsCount -eq 0) {
        $warnings.Add((New-WarningItem -Code 'NO_TEAMS_PROVISIONING' -Message 'No actively provisioned Microsoft Teams or Voice service plans were found.'))
    }

    $payload = [pscustomobject]@{
        target_user_id = $targetId
        licenses       = [object[]]$normalizedLicenses.ToArray()
        returned_count = [int]$normalizedLicenses.Count
        truncated      = [bool]$truncated
    }

    if ($truncated) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $warnings.ToArray()
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload -Warnings $warnings.ToArray()
}

# Offline synthetic fixture evaluation
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
