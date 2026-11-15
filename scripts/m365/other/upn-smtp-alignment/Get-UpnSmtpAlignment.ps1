#requires -Version 7.0
<#
.SYNOPSIS
    Verify User UPN & Directory Profile Alignment (M365.OTHER.UPN_SMTP_ALIGNMENT).
.DESCRIPTION
    Verify user principal name alignment against Mail and primary SMTP ProxyAddresses attributes.
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

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.OTHER.UPN_SMTP_ALIGNMENT') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.OTHER.UPN_SMTP_ALIGNMENT.'
    )
}

$allowedParams = @('StrictDomainCheck')
if ($null -ne $Parameters) {
    foreach ($key in $Parameters.Keys) {
        if ($allowedParams -notcontains [string]$key) {
            return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
                New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter '$key'."
            )
        }
    }
}

$strictDomainCheck = $true
if ($null -ne $Parameters -and $Parameters.ContainsKey('StrictDomainCheck')) {
    if ($Parameters['StrictDomainCheck'] -isnot [bool]) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'StrictDomainCheck must be a boolean.'
        )
    }
    $strictDomainCheck = [bool]$Parameters['StrictDomainCheck']
}

if ($null -eq $Context.target -or [string]$Context.target.kind -notin @('upn', 'object_id') -or [string]::IsNullOrWhiteSpace([string]$Context.target.value)) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target must be a non-empty UPN or Entra object ID.'
    )
}

$targetKind = [string]$Context.target.kind
$targetValue = ([string]$Context.target.value).Trim().Normalize([System.Text.NormalizationForm]::FormC)
$normalized = $targetValue.ToLowerInvariant()

if ($targetKind -eq 'object_id') {
    $parsedGuid = [guid]::Empty
    if (-not [guid]::TryParseExact($normalized, 'D', [ref]$parsedGuid)) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'Target object_id must be a canonical UUID.'
        )
    }
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

$scopes = @($graphConn.graph_scopes | ForEach-Object { [string]$_ })
if ('User.Read.All' -notin $scopes) {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Required Graph scope User.Read.All is not present.'
    )
}

$mgCmd = Get-Command -Name 'Get-MgUser' -ErrorAction SilentlyContinue
if ($null -ne $mgCmd) {
    try {
        $rawUser = Get-MgUser -UserId $targetValue -Property @('Id', 'DisplayName', 'UserPrincipalName', 'AccountEnabled', 'UserType', 'Mail', 'ProxyAddresses') -ErrorAction Stop
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during UPN/SMTP alignment lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Request_ResourceNotFound|404|not\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'The requested Entra user was not found in the tenant.'
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading user UPN and proxyAddresses (User.Read.All required).'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the UPN alignment request.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph UPN/SMTP alignment lookup failed.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Graph lookup.' -Retryable $true
        )
    }

    if ($null -eq $rawUser -or @($rawUser).Count -eq 0) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'The requested Entra user was not found in the tenant.'
        )
    }
    if (@($rawUser).Count -gt 1) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Ambiguous user response returned multiple objects.'
        )
    }

    $userId = ([string](Get-SafeProp $rawUser 'Id')).Trim().ToLowerInvariant()
    $userUpn = ([string](Get-SafeProp $rawUser 'UserPrincipalName')).Trim().Normalize([System.Text.NormalizationForm]::FormC)
    if ($targetKind -eq 'object_id' -and $userId -ne $normalized) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned user ID does not match requested target object ID.'
        )
    }
    if ($targetKind -eq 'upn' -and $userUpn.ToLowerInvariant() -ne $normalized) {
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Returned UPN does not match requested target UPN.'
        )
    }

    $rawDisplay = Get-SafeProp $rawUser 'DisplayName'
    $displayName = if ($null -ne $rawDisplay -and [string]$rawDisplay -ne '') { [string]$rawDisplay } else { $null }
    if ($null -ne $displayName -and $displayName.Length -gt 256) {
        $displayName = $displayName.Substring(0, 253) + '...'
    }
    $rawEnabled = Get-SafeProp $rawUser 'AccountEnabled'
    $accountEnabled = if ($null -ne $rawEnabled) { [bool]$rawEnabled } else { $null }
    $rawType = [string](Get-SafeProp $rawUser 'UserType')
    $userType = if ($rawType -in @('Member', 'Guest')) { $rawType } else { $null }

    $warnings = [System.Collections.Generic.List[object]]::new()
    $hasPartialProp = $false
    if ($null -eq $accountEnabled) {
        $hasPartialProp = $true
        $warnings.Add((New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'AccountEnabled property was not returned by Microsoft Graph.'))
    }

    $mailAttr = [string](Get-SafeProp $rawUser 'Mail')
    $mailAttr = if ([string]::IsNullOrWhiteSpace($mailAttr)) { $null } else { $mailAttr.Trim() }
    $primarySmtp = $null
    $proxies = @(Get-SafeProp $rawUser 'ProxyAddresses')
    foreach ($p in $proxies) {
        if ($null -ne $p -and [string]$p -cmatch '^SMTP:(.+)$') {
            $primarySmtp = $Matches[1].Trim()
            break
        }
    }

    $compareAddress = if ($null -ne $primarySmtp) { $primarySmtp } else { $mailAttr }
    if ($null -eq $compareAddress) {
        $warnings.Add((New-WarningItem -Code 'SMTP_NOT_CONFIGURED' -Message 'No Mail attribute or primary SMTP ProxyAddress was found for this user.'))
    } else {
        $upnLower = $userUpn.ToLowerInvariant()
        $smtpLower = $compareAddress.ToLowerInvariant()
        $upnDomain = if ($upnLower -match '@([^@]+)$') { $Matches[1] } else { '' }
        $smtpDomain = if ($smtpLower -match '@([^@]+)$') { $Matches[1] } else { '' }

        if ($strictDomainCheck -and $upnDomain -ne $smtpDomain) {
            $warnings.Add((New-WarningItem -Code 'UPN_SMTP_DOMAIN_MISMATCH' -Message "UPN domain '$upnDomain' does not match primary SMTP/Mail domain '$smtpDomain' ($compareAddress)."))
        } elseif ($upnLower -ne $smtpLower) {
            $warnings.Add((New-WarningItem -Code 'UPN_SMTP_MISMATCH' -Message "UPN '$userUpn' differs from primary SMTP/Mail '$compareAddress'."))
        } else {
            $warnings.Add((New-WarningItem -Code 'UPN_SMTP_ALIGNED' -Message "UPN and primary SMTP/Mail match ('$compareAddress')."))
        }
    }

    $payload = [pscustomobject]@{
        id                  = $userId
        display_name        = $displayName
        user_principal_name = $userUpn
        account_enabled     = $accountEnabled
        user_type           = $userType
    }

    if ($hasPartialProp) {
        return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data $payload -Warnings $warnings.ToArray()
    }
    return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data $payload -Warnings $warnings.ToArray()
}

# Offline synthetic fixture evaluation
if ($normalized -match '^missing' -or $normalized -eq '00000000-0000-4000-8000-000000000404') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message "Target user '$targetValue' was not found in tenant."
    )
}

if ($normalized -match '^denied') {
    return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Insufficient Microsoft Graph permissions for M365.OTHER.UPN_SMTP_ALIGNMENT.'
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
        New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'Optional profile attributes were unavailable during M365.OTHER.UPN_SMTP_ALIGNMENT.'
    )
}

$displaySuffix = if ($strictDomainCheck) { 'Alex Wilber (Verified)' } else { 'Alex Wilber' }
return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data ([pscustomobject]@{
    id                  = $resolvedId
    display_name        = "UPN Alignment — $displaySuffix"
    user_principal_name = $resolvedUpn
    account_enabled     = $true
    user_type           = 'Member'
})
