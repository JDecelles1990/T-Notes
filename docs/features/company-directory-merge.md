# Company Directory Merge milestone

Status: **PARTIAL — STORAGE GATED; independent review required**.

Settings has exactly one new button, **Merge**, currently disabled. A visible
explanation states that profiles remain session-only and that contract, storage
and backup approval are required. It has no handler, file picker, service link or
writer. Existing preferences and their save/cancel behavior remain unchanged.
Clicking the disabled button cannot mutate the in-memory company directory or DB.
No session-only import is represented as permanently saved.

An offline prototype lives in `prototypes/company_directory_merge/`, outside the
application import tree. It computes detached plans against exact pinned draft
schema/policy bytes. Plans are explicitly non-durable and cannot execute content,
authenticate a tenant or invoke the PowerShell engine. See its README and review
checkpoint; no application source imports it.

Persistent activation requires independent exchange-contract approval, Notes
integrity review, company-directory rereview, portable-module review and an approved
company storage/backup/recovery adapter. After activation, picker cancellation and
invalid files must cause no writes; bounded JSON/semantic validation and full-result
validation precede backup. No-ops report Already up to date without a backup. Changed
imports require a complete verified destination JSON backup, revision checks and
one rollback-capable storage transaction. None of those persistence paths is
implemented or tested by this disabled milestone. A directory JSON backup cannot
be described as a full Notes database backup.

## Optional workspace display mode

MSP/Single Company mode and Department are deferred. Current searchable selection
and fourteen-category sidebar remain. An approved future Single Company preference
should be application-local, fixing an existing company/tenant ID and leaving admin
and target selection intact. Department is a display/workspace attribute, not a
tenant, and must not alter the portable exchange schema. Adding these preferences
now would expand a concurrently reviewed context UI before review/storage gates
are resolved. No workspace-mode or Department setting has been persisted.

## F7Hub and TimeSpace portability

Both applications can reuse the isolated Python logic after contract/module review,
with their own domain projections, stable identity mappings and persistence adapters.
Neither app was modified. T-Notes still has no durable company adapter. F7Hub's
existing local integer company IDs need an approved mapping to portable UUIDs and
tenant/admin relationships. TimeSpace's model and adapter have not been inspected;
compatibility is NOT VERIFIED, not inferred from the shared file format.

The initial interoperability option is manual validated JSON exchange. Future
explicit one-way or bidirectional synchronization would need source authority,
stable identities, version negotiation, local-first/conflict policy, deletion and
replay semantics, explicit authorization and auditable outcomes. A Windows local
IPC or loopback service would additionally require authenticated access, endpoint
authorization and a reviewed trust boundary. No channel is selected or implemented
here; no live SQLite database may be shared and no real-time sync is introduced.
