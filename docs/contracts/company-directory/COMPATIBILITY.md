# Compatibility and host projections

Status: **DRAFT — APPROVAL PENDING**. No adapters implemented.

## T-Notes current model

Inspected Company, Administrator, CompanyDirectory and the in-memory export/import
envelope, CompanyContextService, ADR 0010 and company-directory feature/checkpoint.
Existing memory envelope is `{format: "m365.company-directory", version: 1,
companies: [...]}`. This is not an approved exchange protocol. The PowerShell
`tnotes.m365 / 0.3.0` single-admin profile is a separate interface; do not reuse,
modify, extend or silently convert execution requests into directory exchange.

| Existing model | Draft exchange projection |
|---|---|
| In-memory format/version | Explicitly replace envelope keys with portable format/schema_version on export; reverse only after validation on import |
| Company/admin stored fields | Same field names, values and UUID identities; retain multiple admins and nullable preferred reference |
| Derived preferred_admin_upn | Excluded; derive from preferred_administrator_id, never store a competing copy |
| Empty timestamp defaults during creation | Export concrete stored timestamps; empty imports reject and never obtain current time automatically |
| UTC strings accepted by current model | Exchange uses stricter UTC calendar/time grammar; valid canonical metadata projects losslessly |
| Overlapping domains across companies allowed locally | Draft semantic exchange validation rejects ambiguous cross-tenant attribution; requires manual resolution, no automatic deletion |
| CompanyDirectory.save touches updated_at | Future adapter must not replay saves during pure planning or no-op imports; otherwise determinism/idempotence break; only a successful adapter commit stamps actual changes |
| Search/display ordering | Exchange canonical tenant order is separate; restore UI sorting through its model |
| Connections, targets, selected/confirmed state | Excluded completely; importing metadata must invalidate stale context through the host boundary |

Lossless conversion is defined for metadata that passes both validators: replace
only the envelope discriminator/version, normalize UUID/domain/UPN spellings per
model rules and retain every company/admin stored field. Round-trip comparison is
by normalized field values and stable IDs, not historical whitespace/object order.
Never silently truncate domains/labels or discard a nonconforming local record.
If legacy data cannot be represented under stricter rules, block export/import and
report a safe diagnostic; an approved migration or manual correction is required.
These restrictions are breaking compatibility risks requiring reviewer acceptance.

The design validator mirrors model constraints without importing host services.
Independent compatibility checks must also construct CompanyDirectory from the
projected valid fixtures. This tests current model compatibility only, not an
approved exchange adapter or production persistence.

## F7Hub read-only assessment

The inspected existing CompanyRecord/CompanyService/CompanyRepository implement
basic local companies with integer company_id, optional company_code/domain and
contact information. They do not implement this tenant UUID/multi-administrator
directory. Their presence does not establish exchange compatibility.

An eventual F7Hub adapter needs an approved portable UUID-to-local-integer mapping,
explicit tenant UUID binding and separate admin/default associations. Never cast
integer IDs into UUIDs or match tenants solely by company name/domain. Preserve
existing ticket/company relationships; imported portable IDs must not replace
local relational keys. Contact fields outside this contract remain local and are
not dropped or inserted into unknown exchange fields. A new mapping/storage model,
its migration/rollback and adapter need separate F7Hub design and review authority.
No F7Hub source, settings or database was modified for this draft.

T-Notes-to-F7Hub and reverse golden examples use projected portable documents only.
They do NOT establish real cross-application round trips. Host adapter round-trip,
association preservation, consistent backup, rollback and persistence tests are
NOT RUN because the adapters are not implemented.

## Review and release compatibility gates

1. Independently approve the exact schema, semantic policy and merge rules.
2. Implement/test the pure module without host imports, Qt, SQLite or execution.
3. Review each host projection and local ID/tenant/admin ownership mapping.
4. Test both actual adapter directions, idempotence, conflict diagnostics, stale
   plan rejection, full-result validation, pre-merge backup/restore and rollback.
5. Obtain Notes-integrity and company-directory rereview approval before T-Notes
   persistent import activation; obtain separate F7Hub adapter approval as well.
6. Add exactly one new Settings button, Merge, per host only at activation gate.

No shared live SQLite connection, automatic sync, live Graph/Exchange login,
credential handling or executable operation registration follows from exchange.
