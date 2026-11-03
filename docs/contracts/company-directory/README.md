# Portable Company Directory Exchange Contract v1

Status: **DRAFT — APPROVAL PENDING**. Design and offline synthetic validation only.
Proposed contract: `company-directory.exchange / 1.0.0-draft.1`.
No production importer, merge module, Settings control, storage adapter or live
Microsoft operation is implemented or authorized by this package.

## Identity and validation order

JSON Schema Draft 2020-12. The schema identifier is
`https://company-directory.invalid/exchange/1.0.0-draft.1/company-directory.schema.json`.
It is an identifier, not a download endpoint. Resolve the reviewed schema locally;
never accept a schema URL, `$ref`, executable expression or validator from input.

Envelope: exactly `format`, `schema_version`, `companies`. Format is exactly
`company-directory.exchange`; version is exactly `1.0.0-draft.1`. No aliases,
downgrades or implicit acceptance of in-memory `version: 1` are permitted.

1. Read a selected local file as strict UTF-8, maximum 8 MiB. Reject BOM, invalid
   UTF-8, duplicate JSON keys, nonfinite numbers, malformed JSON and nesting over
   32 levels. File cancellation performs no reads or changes. Bound reading to
   limit+1 bytes before parsing; checking size after an unbounded read is unsafe.
2. Validate the entire document against the exact local reviewed schema, with
   date-time format checking enabled. Every protocol object is closed to unknown
   properties. All company/admin fields are required; optional values use empty
   strings or a nullable default reference, matching the current model.
3. Apply semantic rules below. JSON Schema alone does not prove cross-record
   uniqueness, timestamp ordering, preferred-account ownership or domain safety.
4. A future adapter projects normalized metadata into its domain validator,
   computes a pure merge plan, validates the complete result, and shows/records a
   concise outcome. It must not mutate a live directory while validating.
5. Only after independent contract, importer and adapter approvals may a host
   persist the validated result. Each host owns its own consistent pre-merge
   backup and one rollback-capable transaction. See MERGE_SPEC.md.

## Data and semantic rules

Company fields preserve company_id, display_name, tenant_id, primary_domain,
additional_verified_domains, administrators, preferred_administrator_id,
preferred_cloud, notes, created_at and updated_at. Administrators retain
administrator_id, upn and display_label. There are at most 1,000 companies,
30 additional domains and 100 administrators per company. Zero administrators
and no default are valid. Cloud values are Global, USGov, USGovDoD and China.

Normalize canonical UUID strings to lowercase, domain strings to lowercase,
trim names/labels/notes, and normalize trimmed UPNs to NFC. Compare names and UPNs
using Unicode casefold. Retain local display casing when matching. Reject duplicate
company IDs, tenant UUIDs or casefolded names within an input. Administrator IDs
and casefolded UPNs must be unique within their company; identical UPNs or admin
IDs in separate companies remain scoped metadata, never shared authentication.
Preferred administrator must reference an account in the same company after UUID
normalization. Domains must be unique within a company, including the primary.

**Proposed stricter exchange policy:** a normalized domain cannot be attributed
to two tenants in one exchange/result directory. This detects ambiguity, not actual
DNS ownership. Existing CompanyDirectory permits overlapping domains; this stricter
portable rule requires explicit reviewer acceptance. Legacy ambiguous local data
blocks merge until independently resolved; never silently move or drop its domains.
No organization or administrator is authenticated by identifiers or matching domains.

Timestamps must be real UTC calendar instants written as
`YYYY-MM-DDTHH:MM:SS[.fraction]Z`, with 1–6 fractional digits when present.
Offsets such as +00:00, empty values, date-only strings, leap seconds and wrong
types reject. Compare parsed instants; updated_at must not precede created_at.
No timestamp is invented during import or pure merging. Only a future successful
commit stamps actually changed records, with an explicit adapter-supplied instant;
see MERGE_SPEC.md and Addendum D.

## Security and privacy

Closed objects reject password/token/API-key/credential fields, authentication or
synthetic sessions, transient target context, executable fields and every other
undeclared property at every level. Rejection happens before a merge plan exists.
No credential processing, provider login, network resolution or content execution.

Company names, domains, tenant IDs, admin UPNs, labels and notes are non-secret
identifiers/metadata but can be confidential organizational or personal information.
Manual exchange needs appropriate file access and retention controls. Diagnostics
use stable codes and record indices/counts; do not echo full payloads, UPNs, notes,
provider exceptions or secret-like input values. No telemetry upload is specified.
Property allowlisting cannot identify a password pasted into the allowed notes or
label field. Users must not place secrets there; automatic secret detection is
not claimed. These fields are inert plain text, never HTML or shell input.

## Versioning and review

Every draft revision changes the exact version suffix and schema identifier and
requires refreshed hashes, fixtures and independent review. Stable `1.0.0` needs
an explicit release decision; removing `-draft.1` is not approval. After release,
breaking field/identity/merge semantics require a major version; backward-compatible
changes still require an explicitly supported schema/version and consumer tests.
Unknown versions fail before any mutations. Strict unknown-field rejection means
adding fields requires coordinated versioned consumers, never best-effort parsing.

See [MERGE_SPEC.md](MERGE_SPEC.md) for conflict decisions,
[COMPATIBILITY.md](COMPATIBILITY.md) for host projections, and
[CHECKPOINT.md](CHECKPOINT.md) for reproducible evidence and review limits.
[BACKUP_SPEC.md](BACKUP_SPEC.md) owns mandatory verified pre-merge JSON backup,
no-op behavior, rollback and separate restore acceptance (Addendum E).
