# Contract compatibility and release limitations

This is an offline reference under the explicit provisional task, not an approved
operation. Exact read inputs are bound in tests/evidence/entry-preservation.json
and each final validation report's inputs map. No shared artifact is changed.

| Contract concern | Reference disposition |
|---|---|
| Callable ABI v1 | Mandatory Context and Parameters: IReadOnlyDictionary[string,object]; CancellationToken: System.Threading.CancellationToken; no additional operation parameters |
| Context | Host owns full schema/release validation, immutable context construction and current live lease verification before dispatch and acceptance; local defensive checks cannot prove authority |
| Operation identifier | M365.ENTRA.USER_IDENTITY; exact provisional version 0.3.0-proposed.1 |
| Accepted targets | upn and object_id; no pre-existing resolution required; normalized exact string to Get-MgUser -UserId |
| Target binding | Returned UPN compared OrdinalIgnoreCase after NFC input validation; object ID compared to canonical lowercase GUID; contradictions reject data |
| Service and scope | Graph only; graph_scopes=[User.Read.All] is Graph-specific delegated scope metadata; not effective authorization evidence |
| RBAC | required_roles=[] for this proposed basic identity read; no invented elevated role; actual applicable tenant policy and effective permissions remain host gates |
| Parameters | Empty descriptor list and empty effective Parameters; unknown parameters reject before any provider call |
| Runtime/module | Core/PS7 and Microsoft.Graph.Users; inherited 7.0.0/2.0.0 minima are illustrative only; tested runtime 7.6.9, real SDK NOT LOADED/NOT VERIFIED |
| Risk | read_only: one Get parameter-set lookup; no writes, filters, expansion, pagination, subprocess, file/SQLite access or authentication |
| Output binding | schemas/operation-data.schema.json#/$defs/user_identity; id and user_principal_name |
| Returned object | Exactly one PSCustomObject: status, operation_outcome, data, warnings, errors; typed payload and object[] arrays |
| Serialization | Host adapter exclusively owns wire JSON, envelope identity, timestamps, logical exits and release/context verification |
| Partial | Missing/null display_name, account_enabled or user_type becomes null plus PROPERTY_UNAVAILABLE; partial/partially_succeeded, never a guessed healthy value |
| Invalid identity/data | Missing required id/UPN, malformed property types or contradictory target -> CONTRACT_VIOLATION with null data |
| Absence/access | 404 or no rows -> TARGET_NOT_FOUND; 403 -> ACCESS_DENIED; neither becomes an empty successful identity |
| Other failures | Numeric typed status only: 401 AUTH_REQUIRED, 429 API_THROTTLED, 503 SERVICE_UNAVAILABLE; unknown exceptions -> sanitized INTERNAL_ERROR; no raw messages/headers/stack/SDK objects |
| Cancellation | Checked before call and before accepting/returning data; pre-call outcome not_started, after possible dispatch unknown; no automatic retry |
| Deadline | Proposed 90 seconds, cooperative_then_terminate; host converts deadline to TIMEOUT and owns cleanup; a token alone cannot interrupt synchronous SDK IO |
| Discovery | No executable .ps1, live manifest, release approval, trust anchor, catalog registration or application wiring |

## Payload fields and blocked additions

The selected schema has additionalProperties=false and exactly five required
fields: id, user_principal_name, display_name, account_enabled and user_type.
The last three permit null. Missing required identity fields cannot form partial
data. The operation discards every other provider field, including synthetic
tokens/password data and CreatedDateTime. Collection is limited to the five
explicitly requested properties. Identity data is customer_personal, not anonymous.

**Creation-date output is BLOCKED by the unchanged contract.** No creation-date
field or extra diagnostic attribute is added, requested or placed in warnings.
That requested portion needs separately authorized shared schema/version review.
This does not prevent review of the existing five-field identity reference.

## Microsoft Graph design verification (documentation only)

Official interfaces reviewed for this task:

- [Get-MgUser](https://learn.microsoft.com/en-us/powershell/module/microsoft.graph.users/get-mguser?view=graph-powershell-1.0): Get parameter set has -UserId string and -Property string[].
- [Graph v1.0 get user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0): endpoint accepts object ID or UPN; explicit selection is needed for non-default fields. Guest hash and leading-dollar UPNs have endpoint escaping considerations.

The planned call uses the SDK's typed UserId argument, never an interpolated URL,
OData expression or wildcard. Actual SDK escaping/error-object behavior remains
NOT VERIFIED. The installed Graph module is never imported by this task.

The current get-user documentation lists User.EnableDisableAccount.All plus
User.Read.All for reading/writing accountEnabled. This reference retains only
the contract's proposed User.Read.All scope and does not silently add a
write-capable permission. If an approved read cannot return accountEnabled, null
and partial are the truthful representation; if the whole request is denied,
return ACCESS_DENIED. Live permission/field behavior is NOT RUN. Before any real
release, approve an appropriate read strategy and verify it in an authorized
synthetic tenant. Declared scopes alone establish neither consent nor RBAC.

## Approval and integration gates

The contract and offline engine still need independent approval. This task neither
changes their trust anchors nor makes the synthetic-only engine accept real Graph
connections. A production adapter must verify actual owned tenant/account/service
leases and effective permissions before invocation and before accepting data.
It must validate both operation_return and selected payload, reject incidental
streams, handle late results/deadlines and perform owned-worker cleanup.
No actual wire-envelope, worker-process, real SDK, connection, permission, tenant,
production case-note, GUI, S001 or S002 integration acceptance is claimed here.
