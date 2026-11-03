# Isolated Company Directory merge prototype

Status: **PARTIAL — STORAGE GATED; independent review required**.
This is a detached offline prototype against the unapproved
`company-directory.exchange / 1.0.0-draft.1` schema/policy. It is outside `src/`,
has no application imports or registration, and provides no production entrypoint.
Do not mistake a valid plan or the DraftContract object for release approval.

`company_directory_merge.py` is one portable Python file with standard-library and
existing jsonschema dependencies. It imports no Qt, host services, SQLite, network,
authentication, PowerShell or other-app code. The caller supplies exact raw draft
schema and policy bytes; both SHA-256 pins must match before any input is accepted.
There is no implicit schema path, IO, provider lookup or network `$ref` resolution.
Reviewed packaging/dependency pins remain future work before reuse.

`plan_merge_prototype(local, imported_json, DraftContract(...))` validates complete
inputs, normalizes detached copies, plans local-first changes by canonical tenant
UUID, then validates the full result. It returns MergePlan with candidate, counts,
ordered conflicts, validation failures, per-company statuses and changed_company_ids.
Results always carry prototype_only=True, durable=False and backup_status=
NOT IMPLEMENTED. No timestamps are stamped: changed IDs identify records needing
a future approved adapter's transactional commit timestamp.

Input arrays and object-key order do not choose winners. Companies/admins/domains
sort canonically. Diagnostics refer to canonical incoming company/admin indices,
not original file positions; this deliberate prototype convention supports equal
results for equivalent reordered inputs and needs contract-review reconciliation.
No raw identifiers, notes, credentials or imported values enter error messages.
Data returned is detached from caller inputs, but dictionaries are not an immutable
authorization object; any future adapter must revalidate and bind its frozen plan
and local revision before writes. This prototype supplies no storage authority.

Pure repeats are no-ops; repeated conflicting imports can repeat skip diagnostics
without changing data. Local scalar values, stable IDs, labels/defaults and primary
domains remain local. New accounts match casefolded normalized UPN within one tenant.
Capacity violations skip the whole company's delta, without partial counters or
domain/account writes. Invalid inputs reject the entire plan, including a valid
prefix followed by an invalid record. Invalid complete results produce no candidate.

## Pending contract decisions

The pinned draft is preserved verbatim. Its new-company golden scenarios contain
administrator-addition count zero despite two administrators in the added directory.
The prototype reports two, as required by actual additions; tests verify candidate
documents separately from those inconsistent draft counts. This is a contract
fixture discrepancy, not proof of full golden-result conformance.

The prototype additionally rejects escaped unpaired Unicode surrogates. They can
pass the draft's structural checks but cannot be exported as strict UTF-8. This
parser hardening and canonical diagnostic indices require review before production.
Neither change silently promotes or modifies the existing draft schema/policy.

See the implementation checkpoint for exact hashes, retained failures and tests.
