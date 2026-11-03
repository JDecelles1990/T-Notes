# User Diagnostic Snapshot — proposed first workflow

Status: **RELEASE CANDIDATE — INDEPENDENT REVIEW REQUIRED**. Contract `0.3.0`.
First future script: **Get-UserIdentity.ps1**, stable ID M365.ENTRA.USER_IDENTITY.
Do not implement all checks in one script. This specification replaces the older
snapshot only for this proposed review; historical files remain untouched.

## Operations and input/output contracts

Every operation uses the common request/result envelopes. Payload definitions are
in operation-data.schema.json; all examples are in examples/fixtures.json. No
actual operation script exists here. JSON serialization belongs to the fixed host
adapter, not the individual `.ps1` operation.

| Future script / stable ID | Required input and parameters | Typed output definition |
|---|---|---|
| Get-UserIdentity.ps1 / M365.ENTRA.USER_IDENTITY | Verified Graph context, target.kind=upn or object_id; no extra parameters; adapter binds target to exact Get-MgUser lookup | user_identity: GUID id, display_name nullable, canonical user_principal_name, account_enabled nullable bool, user_type Member/Guest/null |
| Get-UserLicenses.ps1 / M365.ENTRA.USER_LICENSES | Same verified tenant and identity-derived target.kind=object_id; no extra parameters | user_licenses: target_user_id, licenses array of sku_id/sku_part_number/service_plans, returned_count, truncated |
| Get-UserSignIns.ps1 / M365.ENTRA.USER_SIGNINS | Same object ID; LookbackDays integer 1–30 default 7; MaxRecords integer 1–50 default 20 | user_signins: target_user_id, lookback_start UTC, events created_at/app_display_name/success/error_code, returned_count, truncated |
| Get-MailboxSummary.ps1 / M365.EXCHANGE.MAILBOX_SUMMARY | Separately verified Exchange context for same tenant/account; identity-derived object ID | mailbox_summary: target_user_id, mailbox_exists=true, recipient_type_details, primary_smtp_address, total_item_size_bytes and prohibit_send_quota_bytes nullable integer |

Host owns target-to-script argument binding and effective parameter validation;
it never maps arbitrary request keys into an unrestricted PowerShell invocation.
Reject unknown parameters, wrong target kind or changed generation before calls.
Manifest minimum module/runtime versions are illustrative lower bounds, not a
tested support matrix; freeze actual versions in the future native spike.

## Permissions, modules and provider verification

| Operation | Proposed least-privilege starting point | Caveats / source |
|---|---|---|
| Identity | Microsoft.Graph.Users, delegated User.Read.All for another user's support properties | User.Read is self-only; select only approved properties. Readability of account_enabled in the selected permission/module/tenant combination requires native verification; never add a write permission automatically. [Get user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0) |
| Licenses | Microsoft.Graph.Users, delegated LicenseAssignment.Read.All and supported role such as Directory Readers | Effective licenseDetails/read permission and role are both required; schema metadata is not proof. [licenseDetails](https://learn.microsoft.com/en-us/graph/api/user-list-licensedetails?view=graph-rest-1.0) |
| Sign-ins | Microsoft.Graph.Reports, delegated AuditLog.Read.All plus supported role such as Reports Reader | Actual tenant entitlement, log availability and retention must be checked; no promise of 30 days. Exclude Conditional Access payloads/IP/location and do not request extra scopes for them. [List signIns](https://learn.microsoft.com/en-us/graph/api/signin-list?view=graph-rest-1.0) |
| Mailbox | ExchangeOnlineManagement, Exchange RBAC allowing both read cmdlets in the customer's scope | Verify effective permitted cmdlets/properties; no blanket Global Admin requirement. [Get-EXOMailbox](https://learn.microsoft.com/en-us/powershell/module/exchangepowershell/get-exomailbox?view=exchange-ps), [Get-EXOMailboxStatistics](https://learn.microsoft.com/en-us/powershell/module/exchangepowershell/get-exomailboxstatistics?view=exchange-ps) |

These sources were inspected on 2026-11-02; reverify when implementing. No tenant
permissions or module compatibility were tested. Role examples are not mandatory
overprivileged defaults. Ask only for selected checks' authorized permissions.

## Retrieval and failure semantics

Identity resolves one exact UPN or Entra object GUID with fixed typed SDK parameters,
not wildcard or user-built OData expression. Include guest/escaped-UPN cases in tests. Resolve
canonical ID once and bind all later checks to it and the originating verified
tenant. A missing identity produces TARGET_NOT_FOUND, distinct from ACCESS_DENIED;
do not run downstream calls when identity cannot be established. A partial identity
with verified ID may feed follow-on checks while clearly marking unavailable
properties. Missing account status is null/unavailable, never enabled/healthy.

### UPN and object-ID compatibility (I4)

For identity, pass the normalized target.value as System.String to Get-MgUser's
`-UserId` parameter, using the Get parameter set and explicit approved properties.
The underlying user endpoint supports an ID or userPrincipalName.
[Get-MgUser](https://learn.microsoft.com/en-us/powershell/module/microsoft.graph.users/get-mguser?view=graph-powershell-1.0),
[Graph get user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0).
For UPN requests compare returned user_principal_name using the contract's NFC,
trimmed case-insensitive comparison; for object-ID requests compare returned id
to the normalized GUID. A contradictory response is CONTRACT_VIOLATION, never
silent retargeting. Retain canonical UPN and ID in a RAM resolution record bound
to company/tenant/admin reference/generation; changing context invalidates it.

Follow-on licenses/sign-ins/mailbox operations require that record and the exact
object_id target; a raw UPN is ineligible until the explicit identity step resolves
it. Exchange uses that GUID as `-ExternalDirectoryObjectId` (System.Guid), then
verifies the returned ExternalDirectoryObjectId before mailbox statistics calls.
[Get-EXOMailbox](https://learn.microsoft.com/en-us/powershell/module/exchangepowershell/get-exomailbox?view=exchange-ps).
A script that declares only UPN support never receives an object ID implicitly,
or vice versa. target_policy.output_binding names approved top-level payload fields
for object-ID/UPN equality checks; these field names must exist with matching
schema types in the selected payload definition. required resolved identity also
compares returned identity against the retained resolution. None of these mock
contracts prove live guest-UPN escaping or module compatibility; native tests remain.

License checks use that object ID. An empty validated license list means no returned
assignments, not retrieval failure. Match returned_count to array length; do not
drop errors or turn denied access into an empty successful result.

Sign-ins use fixed approved filter construction from the verified GUID and UTC
bound, never unescaped UPN interpolation. Do not use unbounded -All. Limit retrieval
and output to requested MaxRecords <= 50 and the available retention window.
Validate each event's success against its error_code, and event times against
lookback and completion. Reaching a cap yields a valid partial result with an
OUTPUT_LIMIT warning, truncated=true and actual count. Empty events means no
records returned in the examined interval, not evidence of no sign-in problem.

Mailbox resolves the verified Entra ID using Get-EXOMailbox's supported
ExternalDirectoryObjectId parameter; obtain the mailbox GUID/verified SMTP identity
from that result for Get-EXOMailboxStatistics. Do not guess an Exchange identity
from the admin UPN or display name. Validate the directory-ID mapping before use.
Unavailable mailbox means MAILBOX_NOT_FOUND only when absence is established;
RBAC failure is ACCESS_DENIED. An existing mailbox with unavailable size/quota
returns null fields plus partial warning. Normalize bytes using tested typed module
properties, never culture-dependent size-string parsing or fabricated zero values.

## Workflow aggregation and privacy

Application service owns a workflow ID and four separate operation correlations,
all bound to the same company/tenant/target/generation. No extra unapproved wire
workflow envelope is introduced. The aggregator's view model is separate from
the operation result schema; it retains each section's source, status, time and
limitations. Run identity first, then the other checks serially initially.

| Outcomes | Workflow presentation |
|---|---|
| Identity cannot resolve target | Block downstream; show precise identity error, other sections not evaluated |
| All four valid complete successes | Complete diagnostic snapshot, not a remediation/health certification |
| Some validated data, some partial/denied/missing/failed checks | Partial snapshot, available sections retained and unavailable sections explained |
| No usable data and execution failures | Error; never successful empty snapshot |
| Cancel or timeout | Terminal cancelled/timeout indication with already completed sections retained as historical partial evidence; no remaining automatic calls |
| Company/admin/target generation changed | Quarantine old results; stop remainder and invalidate note insertion |

Retry only the explicitly selected failed check with a new correlation after
context/permission verification. Reuse identity only while tenant, target and
generation remain applicable. Do not replay successful sections unnecessarily.

Only allowlisted payload fields leave adapters; no raw Graph/Exchange SDK object,
headers, token, IP/location, stack trace or password. Results stay bounded in RAM.
Raw JSON is sanitized too. Note insertion follows workspace-architecture.md:
visible preview, actual ticket/tenant confirmation, text insertion via the existing
editor and autosave, no background replacement of notes.

## Pester and workflow acceptance

Each future script must have mocked success, not-found, denied-access, missing
module/connection, invalid-parameter and wrong-tenant tests. Assert exact provider
command count/typed arguments and **zero calls** after rejected context. Test
0/1/many rows, null versus unavailable, partial fields, throttling, caps, cancellation,
safe warnings/errors and absent secrets. Mock authentication ownership; assert
scripts never call Connect-MgGraph/Connect-ExchangeOnline or write app data.
[Pester v5 mocking](https://pester.dev/docs/v5/usage/mocking).

Host adapter tests assert one serialized envelope, stable arrays, no incidental
stdout, error/exit alignment and strict result/data schema checks. Workflow tests
cover every aggregation row above, tenant changes between all steps, expiry,
retry-only-one-section, notebook ticket switch and duplicate Insert prevention.
The first release gate includes actual PowerShell/module behavior in an authorized
synthetic test tenant and native UI lifecycle tests. Those tests are NOT RUN here.
