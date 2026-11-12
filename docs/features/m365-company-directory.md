# M365 company directory and identity context

Status: **PHASE A — SYNTHETIC GUI IMPLEMENTED; INDEPENDENT REVIEW REQUIRED**.
No production profile storage, Microsoft authentication or operation dispatch.

## Authority and phases

Entry: clean `main`, `ef847af18572ce5b82b0dd263b75658efe1caacd`. Read root AGENTS.md,
GEMINI.md revision 2, official contract/release/schema package, compatibility records,
offline engine checkpoint, scripts README, launcher/catalog and Notes architecture.
The official v0.3.0 release record still says **RELEASE CANDIDATE — INDEPENDENT REVIEW
REQUIRED**, without effective implementation approval. Catalog and provisional
engine remain pinned to `0.3.0-proposed.1`. Neither files nor passing tests approve
these boundaries. No contract, engine or PowerShell operation is modified here.

| Phase | Delivered | Remaining gate |
|---|---|---|
| A | RAM-only directory and company/admin/target GUI | Independent review, physical desktop acceptance |
| B | Versioned metadata seam, temporary test-only SQLite roundtrip | Accepted Notes integrity corrections; verified backup/restore/migration plan; explicit storage activation |
| C | Synthetic per-service manager and context | Approved contract, separately authorized interactive adapter, actual identity/scopes/effective RBAC evidence |
| D | Negative eligibility/dispatch tests, no engine integration | Official engine migration, compatibility tests, engine/operation/integration approval |

## Non-secret metadata

CompanyDirectory has no Qt, SQLite, ticket or settings dependency, default storage
path, automatic save or migration. Startup shows labelled synthetic `.example`
records with no selected company. Changes last for the current session only.

| Field | Meaning |
|---|---|
| company_id | Stable canonical UUID, retained on rename |
| display_name | Required bounded name; case-insensitive duplicates rejected |
| tenant_id | Canonical UUID; duplicate tenants rejected, edit existing profile |
| primary_domain | Normalized DNS hint, never identity evidence |
| additional_verified_domains | At most 30 unique domain metadata assertions; no verification performed or inferred locally |
| administrators | Zero to 100 records with stable administrator_id, UPN and optional display_label |
| preferred_administrator_id | Nullable reference belonging to this company |
| preferred_admin_upn | Derived from default record, avoids a second mutable copy |
| preferred_cloud | Global, USGov, USGovDoD or China preference, no live adapter |
| notes | Optional bounded single-line non-secret text |
| created_at / updated_at | UTC Z; creation retained across edits |

UPNs use NFC normalization and case-insensitive identity comparison. Duplicates
within one company are rejected. The same UPN in another profile proves no access.
Labels grant no permissions. Removing the default clears its reference. Selecting
an account or setting a default never authenticates automatically.

Future JSON export/import envelope:

```json
{"format":"m365.company-directory","version":1,"companies":[]}
```

Each company has exactly its stored model fields, excluding derived preferred UPN.
Administrators have exactly administrator_id, upn and display_label. Import rejects
unknown/missing fields, unsupported versions, duplicate IDs/names/tenants/UPNs,
invalid identifiers/default references. Timestamp fields (created_at, updated_at) are
strictly validated against non-string types (integers, booleans, nulls), malformed ISO 8601
formats, and non-UTC offsets, raising explicit ValueError without automatic coercion.
In the GUI, additional domains use a lossless multiline representation that preserves all
validated domain metadata without length-bound silent truncation across editing sessions.
This format version is separate from the
PowerShell ABI. Current export/import operate on memory only, without file UI.
Future file parsing needs explicit size/encoding/duplicate-key constraints.

No credentials, tokens, connections, targets, generations or transient refs are
exported. Field allowlisting cannot detect arbitrary secrets pasted into notes or
labels; the form explicitly prohibits entering them. No password field exists.

The official candidate company-profile schema describes a single admin hint
(administrator_upn, tenant_domain), not multi-admin directory metadata. It is not
changed here. A future reviewed projection may map the selected hint/domain;
never use this metadata envelope as an execution request or identity proof.

## GUI behavior and identity ownership

The six launcher groups and fourteen-category sidebar remain. Company Selection
has an alphabetical dropdown, case-insensitive partial name/domain search,
Add/Edit, selected tenant/cloud and explicit Confirm Company Selection. Additional
domains are searchable. Empty results disable dependent controls; filtering out a
selected company clears selection without silently choosing another tenant.

Authentication & Tenant Context provides searchable administrator selection,
Add/Edit/Remove/Set Default, editable UPN hint, separate synthetic Graph and Exchange
Connect controls, status/warnings and Disconnect. Verified tenant and authenticated
administrator stay **none**. Ordinary Connect creates synthetic state with no scope
or role evidence. Failure and permission-warning fixtures are available to tests.

Client UPN and optional Entra object ID are separate controls. Every edit clears
previous resolution, including invalid edits. Synthetic resolution displays a
fixture labelled **not verified**, with Verified target **none**. Both supplied
identifiers must bind to the same fixture. Domain mismatch is advisory; matching
domains never authorize execution. TargetInput produces the candidate contract's
`{kind: upn|object_id, value: ...}` shape, preferring supplied object ID. No shell
strings or executable request are built.

CompanyContextService owns selected metadata, admin hint, transient
admin_identity_ref (separate from administrator-record ID), monotonic generation,
local company confirmation, target input and synthetic resolution. Company/admin/
hint changes, Disconnect and directory revisions clear connections, target and
confirmation. Connection changes clear target resolution/confirmation while keeping
the other service separate. Expiry is checked on every eligibility evaluation;
the view refreshes status every second while visible, with no reconnect or replay.
The refresh timer stops in the Notes workspace and rechecks state when shown.

SyntheticConnectionManager owns RAM fixture states: disconnected, simulated,
permission_warning, expired and error. It cannot mint verified state. Eligibility
always returns false, while reporting missing confirmation, unverified connections/
target, tenant/account mismatch and stale generation. There is no execution method,
provider adapter, credential object, subprocess call or engine import.

Future approved boundary:

```text
GUI -> Company / Target Context Service -> Authentication / Connection Manager
    -> Operation Eligibility Service -> Approved Execution Engine
    -> Trusted PowerShell Operation
```

Current UI stops at synthetic context/eligibility. A future adapter must own approved
Microsoft interactive MFA/Conditional Access sign-in, actual tenant/account checks
before invocation and result acceptance, scopes/effective RBAC, frozen typed
context/parameter objects and release binding. Fixture states are not contract
connection leases or runtime proof.

## Storage safety and F7Hub

No Notes repository, production schema/migration, settings, app_session or bootstrap
is changed. Temporary test-only SQLite roundtrip is not a production storage
implementation or approval. Accept case-note integrity corrections first. Review
separate company-domain storage, safe online backup, restore verification, WAL,
collision/version policy, rollback and interruption recovery before activation.

F7Hub may provide its own workspace/storage adapter using this metadata format and
the same approved operation packages. Never share a live T-Notes database. Portable
services use only Python standard-library modules and each other; Qt remains in
the panel. F7Hub is not modified.

## Required migration from proposed to official v0.3.0

1. Obtain effective independent contract approval bound to source revision and
   exact raw hashes for all seven schemas, ABI and release artifacts. Candidate
   inventory hashes alone are not an approval record.
2. Migrate catalog root/version and review pins from `0.3.0-proposed.1` to official
   `docs/contracts/m365/` and `0.3.0`, with manifest/fixture compatibility tests and
   explicit old-version rejection. Preserve historical evidence.
3. Migrate engine schema IDs, descriptors, contexts, trust anchors and dependency
   pins together. Rerun ABI/binding/trust/cancellation/native process cleanup/result
   tests and obtain independent execution-engine approval.
4. Approve each operation's exact bytes, dependencies and effective permissions,
   and the host-owned authentication adapter. Production integration and live
   tenant execution require their own authorization.

See the milestone checkpoint for exact inventory, evidence and reviewer handoff.


---

## Persistent storage & atomic JSON Merge (implemented)

Non-secret customer tenant and administrator metadata now persists in `techpad.db` (`m365_directory_meta`, `m365_companies`, `m365_administrators`) through:

- `M365CompanyRepository` (`src/repositories/m365_company_repository.py`): owns schema queries, optimistic revision concurrency checks, FK cascading deletes, and full transactional `replace_all` commits.
- `PersistentCompanyDirectory` (`src/services/m365_company_store.py`): preserves `CompanyDirectory`'s pure validation API for F7Hub reuse while keeping synthetic preview records (`.example` / `.invalid`) strictly in RAM when `techpad.db` contains zero real companies. Saving or merging a real company automatically clears the synthetic preview without writing synthetic IDs into SQLite.
- **Export & Pre-Backup Atomic Merge:** Technicians can export persisted companies (`format: "m365.company-directory"`, `version: 1`) or merge incoming JSON files directly from the M365 workspace (`Export JSON` / `Merge JSON`). Every Merge creates a verified timestamped pre-merge JSON backup under `<appDataDir>/backups/company-directory` before committing via `replace_all`; validation errors or optimistic revision conflicts roll back atomically. `SettingsDialog.btn_merge` remains intentionally disabled as the earlier UI prototype guard.
