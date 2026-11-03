# Deterministic non-destructive merge specification

Status: **DRAFT — APPROVAL PENDING**. Specification for future
`company_directory_merge.py`; no such production module is delivered here.

The future pure module accepts a detached normalized local directory and imported
JSON bytes plus pinned schema/domain validation dependencies. It imports no Qt,
SQLite, host service or authentication library. App-specific adapters project their
models to neutral records and inject validation; importing T-Notes' CompanyDirectory
from the reusable module would violate portability. Both hosts must use identical
reviewed normalization, planning and conflict rules, with byte-identical fixtures.

## Atomic validation versus skippable conflicts

Parsing/schema/semantic defects anywhere in the imported document reject the
**entire import**. Invalid local metadata also blocks planning. No partial salvage
of malformed inputs: duplicate tenants/company IDs/names/admin UPNs, unknown or
secret fields, dangling defaults, malformed timestamps and internally conflicting
domain ownership are whole-document errors. Local data remains byte-for-byte
unchanged on rejection. Error diagnostics contain no imported values.

For two individually valid directories, resolvable conflicts against the local
directory can be skipped according to this matrix. The plan includes all skips;
no conflict authorizes silently overwriting local values.

| Condition | Proposed action | Diagnostic / scope |
|---|---|---|
| New tenant with unused company ID/name and safe primary domain | Add complete record, retaining imported IDs/timestamps | Addition |
| Same tenant, different company IDs | Match tenant; retain local company ID; remap imported references to it | ID alias, not a conflict |
| Imported company ID already belongs to a different local tenant | Skip whole incoming company; never rebind either ID | COMPANY_ID_TENANT_CONFLICT |
| New tenant's name equals another local company's normalized name | Skip whole incoming company; no automatic rename | NAME_COLLISION |
| Existing tenant has a different name, nonempty notes or cloud | Keep local value, including empty notes | VALUE_CONFLICT per differing nonempty field |
| Different primary domain for the same tenant | Preserve local primary; do not promote conflicting primary into additional domains | PRIMARY_DOMAIN_DIFFERENCE; imported additional domains are evaluated separately |
| Missing non-conflicting additional domain | Add normalized domain once | Update |
| Domain already present in this tenant | No change, including primary/additional overlap across inputs | Unchanged field |
| New tenant's primary domain is locally attributed to another tenant | Skip whole incoming company | DOMAIN_TENANT_CONFLICT |
| Incoming additional domain belongs to another local tenant | Skip that domain only; preserve other safe additions | DOMAIN_TENANT_CONFLICT |
| Existing tenant's conflicting incoming primary belongs elsewhere | Keep local primary and skip incoming domain | DOMAIN_TENANT_CONFLICT |
| Same normalized UPN within matched tenant | Retain local admin ID, UPN casing and label (including empty); map imported ID to local ID | Differing label is VALUE_CONFLICT |
| New UPN, admin ID unused within matched tenant | Add imported admin ID/UPN/label | Update |
| New UPN, imported admin ID already belongs to another local UPN in that company | Skip incoming account; never reassign an ID | ADMIN_ID_UPN_CONFLICT |
| Imported preferred account maps to accepted/matched admin and local default is null | Fill default using mapped local admin ID | Update |
| Local preferred account already exists | Preserve it; report differing mapped preference | DEFAULT_CONFLICT |
| Imported default account was skipped | Keep local default, including null | DEFAULT_UNAVAILABLE |
| Added domains/admins would exceed model capacity | Skip the whole incoming company delta atomically | CAPACITY_CONFLICT; local record unchanged |
| Full planned result fails schema/domain validation | Reject entire plan | RESULT_INVALID; no persistence |
| Adapter backup or transactional write fails | Reject entire persistence operation; roll back | BACKUP_FAILED / STORAGE_FAILED |

For a new company whose unsafe additional domains are omitted, retain it only when
its remaining fields/default still validate. A preferred account on an entirely
skipped company is not independently imported. No records are deleted.

## Deterministic ordering, timestamps and identifiers

Process incoming companies by normalized tenant UUID, then company UUID. Validate
uniqueness before sorting; input order must not select a winner. Conflicting claims
between incoming companies are rejected as input ambiguity, not resolved by order.
For a matched company, decide ID ownership before applying fields; a reused local
company ID pointing elsewhere wins over a tenant-match alias and skips that delta.
Compare administrators by normalized UPN, then admin UUID; domains by lowercase
ordinal text. Use no random UUIDs, local clock, locale sort order or network state.

Do not update timestamps during pure planning. Existing created_at and updated_at
stay local, including when a plan enriches domains/accounts. New records retain
imported metadata in the plan. Set a separate `requires_timestamp_on_commit` flag
for added/enriched companies; it is plan metadata, never an exchange field.

Only a future adapter's successful atomic commit may update modification timestamps
for actually changed records. Capture one explicit UTC commit instant for that
transaction. For existing records use max(local updated_at, local created_at,
commit instant); imported updated_at never replaces local updated_at. For a new
record use max(imported created_at, commit instant), retaining imported creation.
Preserve the local spelling on equal instants. The timestamp is staged with all
other writes, revalidated, and rolls back if any write/commit fails. Unchanged or
skipped records are never stamped. The pure plan is deterministic without a clock;
final storage serialization is deterministic for the same plan and explicit commit
instant. Repeating an import does not restamp unchanged data. Timestamps are metadata,
not a mechanism for choosing a conflicting imported name, configuration or identity.

Serialization of a planned/exported directory uses UTF-8 without BOM, LF, no NaN,
fixed envelope/company/admin field order as in the schema, company order by tenant
UUID, admin order by casefolded UPN/UUID and sorted additional domains. UUIDs/domains
are lowercase, UPNs NFC; JSON formatting is two-space indentation with terminal LF.
This canonical exchange ordering does not reorder application tabs or company IDs.

## Results, counts and idempotence

Return a detached candidate plus companies_added, existing_companies_enriched,
administrators_added, additional_domains_added, records_unchanged, conflicts_skipped
and validation_failures; include per-company added/enriched/unchanged/skipped status,
domain/admin addition counts, validation failures and ordered diagnostics. Each diagnostic carries code,
scope (company/field/domain/admin), incoming company index, optional admin index and
field name, with no full records or raw identifiers. Sort diagnostics by normalized
tenant processing order, scope, field and source index. Maintain internal ID alias
maps for default projection; do not export transient maps or auth state.

Each incoming company is exactly one of added, updated, unchanged or skipped.
Partly accepted fields make that company updated; a company with only field skips
is unchanged. `skipped_conflicts` counts conflict diagnostics separately and is not
a disjoint company count. Reports distinguish duplicate no-ops from skipped values.
Pure duplicate/alias matches produce no diagnostic or persistence write. Repeating
a conflicting file can report the same skipped conflicts but must leave data unchanged.

Required algebra: for valid inputs, `merge(merge(L, I).candidate, I).candidate`
equals `merge(L, I).candidate` after canonical serialization. The second run has no
new additions/updates; it can retain conflict diagnostics. The same detached L/I
inputs produce identical candidates and diagnostics. No stable IDs are regenerated.
Golden fixtures specify examples only; executable idempotence is NOT VERIFIED until
the future module exists and is independently tested.

## Future host activation sequence

After contract, module and adapter review, the single new Settings control is
exactly **Merge**. Picker cancel is a no-op. The adapter reads bounded JSON,
validates, computes a detached plan and validates the full result before any write.
Keep transaction revision guards against local changes after planning. Recompute
or reject a stale plan; never apply it over newer local state.

Persistent application requires the timestamped, complete, independently verified
JSON pre-merge backup in [BACKUP_SPEC.md](BACKUP_SPEC.md). Where database-level
recovery is needed, it additionally requires a consistent SQLite online backup,
verified integrity/restore behavior, and one host-owned transaction for companies,
admins, defaults and associations. Never copy only a live WAL main file, share a
database between apps, hold a DB transaction over user input, or silently fall back
to partial writes. A backup failure blocks all writes. Any storage/commit failure
rolls back all changes. No-op plans perform no write; a summary still reports them.
Storage rollback fault tests and stale-plan tests belong to each eventual adapter.

T-Notes Notes-integrity approval and Company Directory independent rereview remain
gates. F7Hub needs its own tenant/admin/portable-ID model and approved adapter.
Neither the draft nor schema validation activates persistent import or verifies
tenant ownership, authentication, privileges or PowerShell execution eligibility.
