#requires -Version 7.0
<#
.SYNOPSIS
    Audit Entra ID Group & Directory Admin Role Memberships (M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP).
.DESCRIPTION
    Summarize Security Groups, M365 Unified Groups, Mail-Enabled Groups, and Entra Directory
    Admin Roles for an Entra ID user (Get-MgUser + Get-MgUserMemberOf when available).
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

function Get-DirectoryObjectType {
    param([object]$DirObj)
    if ($null -eq $DirObj) { return '' }
    $addProps = Get-SafeProp $DirObj 'AdditionalProperties'
    if ($null -ne $addProps) {
        if ($addProps -is [System.Collections.IDictionary] -and $addProps.Contains('@odata.type')) {
            return [string]$addProps['@odata.type']
        }
        $apType = Get-SafeProp $addProps '@odata.type'
        if (-not [string]::IsNullOrWhiteSpace([string]$apType)) {
            return [string]$apType
        }
    }
    $directOdata = Get-SafeProp $DirObj '@odata.type'
    if (-not [string]::IsNullOrWhiteSpace([string]$directOdata)) {
        return [string]$directOdata
    }
    $roleTemplateId = Get-SafeProp $DirObj 'RoleTemplateId'
    if (-not [string]::IsNullOrWhiteSpace([string]$roleTemplateId)) {
        return '#microsoft.graph.directoryRole'
    }
    $groupTypes = Get-SafeProp $DirObj 'GroupTypes'
    $securityEnabled = Get-SafeProp $DirObj 'SecurityEnabled'
    $mailEnabled = Get-SafeProp $DirObj 'MailEnabled'
    if ($null -ne $groupTypes -or $null -ne $securityEnabled -or $null -ne $mailEnabled) {
        return '#microsoft.graph.group'
    }
    return ''
}

function Get-MemberDisplayName {
    param([object]$DirObj)
    $dn = [string](Get-SafeProp $DirObj 'DisplayName')
    if (-not [string]::IsNullOrWhiteSpace($dn)) { return $dn.Trim() }
    $addProps = Get-SafeProp $DirObj 'AdditionalProperties'
    if ($null -ne $addProps) {
        if ($addProps -is [System.Collections.IDictionary] -and $addProps.Contains('displayName')) {
            $apDn = [string]$addProps['displayName']
            if (-not [string]::IsNullOrWhiteSpace($apDn)) { return $apDn.Trim() }
        }
        $apPropDn = [string](Get-SafeProp $addProps 'displayName')
        if (-not [string]::IsNullOrWhiteSpace($apPropDn)) { return $apPropDn.Trim() }
    }
    $idVal = [string](Get-SafeProp $DirObj 'Id')
    if (-not [string]::IsNullOrWhiteSpace($idVal)) { return $idVal.Trim() }
    return 'Unnamed Directory Object'
}

if ($CancellationToken.IsCancellationRequested) {
    return New-OperationReturn -Status 'cancelled' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled before execution.' -Retryable $true
    )
}

if ($null -eq $Context -or [string]$Context.contract_version -ne '0.3.0' -or [string]$Context.script_id -ne 'M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP') {
    return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
        New-ErrorItem -Code 'CONTRACT_VIOLATION' -Message 'Invalid invocation context for M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP.'
    )
}

$allowedParams = @('IncludeAdminRoles', 'MaxGroups')
if ($null -ne $Parameters) {
    foreach ($key in $Parameters.Keys) {
        if ($allowedParams -notcontains [string]$key) {
            return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
                New-ErrorItem -Code 'INVALID_PARAMETER' -Message "Unexpected parameter '$key'."
            )
        }
    }
}

$includeAdminRoles = $true
if ($null -ne $Parameters -and $Parameters.ContainsKey('IncludeAdminRoles')) {
    $rawRolesParam = $Parameters['IncludeAdminRoles']
    if (-not ($rawRolesParam -is [bool])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'IncludeAdminRoles must be a boolean.'
        )
    }
    $includeAdminRoles = [bool]$rawRolesParam
}

$maxGroups = 25
if ($null -ne $Parameters -and $Parameters.ContainsKey('MaxGroups')) {
    $rawMax = $Parameters['MaxGroups']
    if ($rawMax -is [bool] -or -not ($rawMax -is [int] -or $rawMax -is [long])) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'MaxGroups must be an integer between 1 and 100.'
        )
    }
    $maxGroups = [int]$rawMax
    if ($maxGroups -lt 1 -or $maxGroups -gt 100) {
        return New-OperationReturn -Status 'error' -Outcome 'not_started' -Errors @(
            New-ErrorItem -Code 'INVALID_PARAMETER' -Message 'MaxGroups must be between 1 and 100.'
        )
    }
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
        $rawUser = Get-MgUser -UserId $targetValue -Property @('Id', 'DisplayName', 'UserPrincipalName', 'AccountEnabled', 'UserType') -ErrorAction Stop
    }
    catch {
        $errMsg = $_.Exception.Message
        if ($CancellationToken.IsCancellationRequested) {
            return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
                New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled during Graph user membership lookup.' -Retryable $true
            )
        }
        if ($errMsg -match '(?i)Request_ResourceNotFound|404|not\s+found') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'TARGET_NOT_FOUND' -Message 'The requested Entra user was not found in the tenant.'
            )
        }
        if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Access denied while reading Entra user for membership audit (User.Read.All required).'
            )
        }
        if ($errMsg -match '(?i)429|TooManyRequests|throttl') {
            return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
                New-ErrorItem -Code 'API_THROTTLED' -Message 'Microsoft Graph throttled the user membership audit.' -Retryable $true
            )
        }
        return New-OperationReturn -Status 'error' -Outcome 'failed' -Errors @(
            New-ErrorItem -Code 'SERVICE_UNAVAILABLE' -Message 'Microsoft Graph user lookup failed during membership audit.' -Retryable $true
        )
    }

    if ($CancellationToken.IsCancellationRequested) {
        return New-OperationReturn -Status 'cancelled' -Outcome 'unknown' -Errors @(
            New-ErrorItem -Code 'CANCELLED' -Message 'Operation cancelled after Graph user lookup.' -Retryable $true
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
    } elseif ($accountEnabled -eq $false) {
        $warnings.Add((New-WarningItem -Code 'ACCOUNT_DISABLED' -Message 'Target Entra user account is currently disabled (AccountEnabled=False).'))
    }

    $memberCmd = Get-Command -Name 'Get-MgUserMemberOf' -ErrorAction SilentlyContinue
    if ($null -ne $memberCmd) {
        try {
            $memberSplat = @{
                UserId      = $userId
                ErrorAction = 'Stop'
            }
            if ($memberCmd.Parameters.ContainsKey('All')) {
                $memberSplat['All'] = $true
            }
            $memberships = @(Get-MgUserMemberOf @memberSplat)

            $securityCount = 0
            $m365Count = 0
            $mailCount = 0
            $groupNames = [System.Collections.Generic.List[string]]::new()
            $adminRoleNames = [System.Collections.Generic.List[string]]::new()

            foreach ($m in $memberships) {
                if ($null -eq $m) { continue }
                $odataType = Get-DirectoryObjectType $m
                $label = Get-MemberDisplayName $m
                if ($odataType -match 'directoryRole') {
                    if ($adminRoleNames -notcontains $label) {
                        $adminRoleNames.Add($label)
                    }
                } elseif ($odataType -match 'group') {
                    $gTypes = @((Get-SafeProp $m 'GroupTypes') | ForEach-Object { [string]$_ })
                    $isUnified = ($gTypes -contains 'Unified')
                    $secEnabled = (Get-SafeProp $m 'SecurityEnabled') -eq $true
                    $mailEnabled = (Get-SafeProp $m 'MailEnabled') -eq $true
                    if ($isUnified) {
                        $m365Count++
                        $tag = 'M365'
                    } elseif ($secEnabled -and $mailEnabled) {
                        $securityCount++
                        $mailCount++
                        $tag = 'MailSec'
                    } elseif ($secEnabled) {
                        $securityCount++
                        $tag = 'Sec'
                    } elseif ($mailEnabled) {
                        $mailCount++
                        $tag = 'Dist'
                    } else {
                        $tag = 'Group'
                    }
                    if ($groupNames.Count -lt $maxGroups) {
                        $groupNames.Add("$label [$tag]")
                    }
                }
            }

            $totalGroups = $securityCount + $m365Count + ($mailCount - 0)
            # Count distinct groups seen reliably
            $distinctGroups = @($memberships | Where-Object { $_ -ne $null -and (Get-DirectoryObjectType $_) -match 'group' }).Count
            $shownList = if ($groupNames.Count -gt 0) { $groupNames -join ', ' } else { 'None' }
            $truncatedNote = if ($distinctGroups -gt $maxGroups) { " (+$($distinctGroups - $maxGroups) more)" } else { '' }
            $warnings.Add((New-WarningItem -Code 'GROUP_MEMBERSHIP_SUMMARY' -Message "Direct groups ($distinctGroups total | M365=$m365Count, Security=$securityCount, Mail=$mailCount): $shownList$truncatedNote"))

            if ($includeAdminRoles) {
                if ($adminRoleNames.Count -gt 0) {
                    $warnings.Add((New-WarningItem -Code 'ADMIN_ROLE_DETECTED' -Message "Privileged Entra directory role(s) assigned ($($adminRoleNames.Count)): $($adminRoleNames -join ', ')."))
                } else {
                    $warnings.Add((New-WarningItem -Code 'ADMIN_ROLE_DETECTED' -Message 'Privileged Entra directory roles: None (direct directoryRole memberships).'))
                }
            }
            $warnings.Add((New-WarningItem -Code 'MEMBERSHIP_TELEMETRY_SCOPE' -Message "Direct Entra memberships inspected via Get-MgUserMemberOf (MaxGroups=$maxGroups; transitive/PIM eligible roles excluded)."))
        }
        catch {
            $errMsg = $_.Exception.Message
            if ($errMsg -match '(?i)Authorization_RequestDenied|403|Forbidden|Insufficient\s+privileges') {
                $warnings.Add((New-WarningItem -Code 'MEMBERSHIP_TELEMETRY_SCOPE' -Message 'Get-MgUserMemberOf access denied (requires GroupMember.Read.All / Directory.Read.All for full membership list).'))
            } else {
                $warnings.Add((New-WarningItem -Code 'MEMBERSHIP_TELEMETRY_SCOPE' -Message "Get-MgUserMemberOf lookup failed: $errMsg"))
            }
        }
    } else {
        $warnings.Add((New-WarningItem -Code 'MEMBERSHIP_TELEMETRY_SCOPE' -Message 'Get-MgUserMemberOf cmdlet is unavailable in this Graph session; only base user identity checked.'))
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
        New-ErrorItem -Code 'ACCESS_DENIED' -Message 'Insufficient Microsoft Graph permissions for M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP.'
    )
}

$resolvedId = if ($targetKind -eq 'object_id') { $normalized } else { '40000000-0000-4000-8000-000000000001' }
$resolvedUpn = if ($targetKind -eq 'upn') { $targetValue } else { 'client@alpine.example' }

if ($normalized -match '^partial' -or $normalized -eq 'megan.bowen@contoso.example') {
    return New-OperationReturn -Status 'partial' -Outcome 'partially_succeeded' -Data ([pscustomobject]@{
        id                  = '40000000-0000-4000-8000-000000000002'
        display_name        = 'Group & Role Audit — Megan Bowen'
        user_principal_name = $resolvedUpn
        account_enabled     = $null
        user_type           = 'Member'
    }) -Warnings @(
        New-WarningItem -Code 'PROPERTY_UNAVAILABLE' -Message 'AccountEnabled property is unavailable in the partial synthetic fixture.'
        New-WarningItem -Code 'MEMBERSHIP_TELEMETRY_SCOPE' -Message "Direct Entra memberships inspected via synthetic fixture (MaxGroups=$maxGroups)."
    )
}

$synthWarnings = [System.Collections.Generic.List[object]]::new()
$synthWarnings.Add((New-WarningItem -Code 'GROUP_MEMBERSHIP_SUMMARY' -Message 'Direct groups (3 total | M365=1, Security=2, Mail=0): All Company [M365], VPN-Users [Sec], M365-MFA-Enforced [Sec]'))
if ($includeAdminRoles) {
    $synthWarnings.Add((New-WarningItem -Code 'ADMIN_ROLE_DETECTED' -Message 'Privileged Entra directory role(s) assigned (1): Helpdesk Administrator.'))
}
$synthWarnings.Add((New-WarningItem -Code 'MEMBERSHIP_TELEMETRY_SCOPE' -Message "Direct Entra memberships inspected (MaxGroups=$maxGroups; transitive/PIM eligible roles excluded)."))

return New-OperationReturn -Status 'success' -Outcome 'succeeded' -Data ([pscustomobject]@{
    id                  = $resolvedId
    display_name        = 'Alex Wilber'
    user_principal_name = $resolvedUpn
    account_enabled     = $true
    user_type           = 'Member'
}) -Warnings $synthWarnings.ToArray()

