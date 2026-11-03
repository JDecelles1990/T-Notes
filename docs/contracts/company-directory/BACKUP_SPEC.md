# Automatic destination backup before Merge

Status: **DRAFT — APPROVAL PENDING**, incorporating Addendum E. No backup writer,
restore tool, adapter or persistent Merge is implemented here.

## Required sequence

Settings has exactly one new control: **Merge**. No backup settings, advanced
options or conflict controls. Picker cancellation is a no-op. After bounded JSON,
schema and semantic validation, compute the local-first plan and validate its full
candidate. Invalid imports and plans never create a backup or write destination
data. If there are no additions/enrichments, report **Already up to date** with
counts, skipped conflicts if any, and backup status **not needed**. Do not restamp
timestamps or create repeated backups for unchanged imports.

For a changed plan, take a detached consistent destination-directory snapshot,
with its storage revision and complete portable company/admin/default metadata.
Create and verify the backup below before any destination writes. Only then begin
the host's single merge transaction, recheck that revision/snapshot identity and
stage validated changes and changed-record timestamps. Validate the stamped result
and commit. Any failure rolls back, retains the verified backup and reports failure.

A changed destination after backup makes the plan stale: roll back before writing,
recompute/revalidate against the new snapshot and create/verify a corresponding
backup before applying it. Never proceed using an unrelated older snapshot backup.
Do not hold a SQLite write transaction while waiting for file IO or user input.

## Filename and publication

Use an application-controlled local backup directory with restricted permissions
for the current user and necessary OS/service principals only. Explicitly validate
the directory/parent ACLs; fail closed if the host cannot establish the approved
permissions. Portable schema approval does not select a production path or Windows
ACL implementation. Hosts own and independently test those details.

Filename: `company-directory-backup-YYYYMMDD-HHMMSS.json`, with UTC date/time.
Use a collision-resistant suffix before `.json`, for example
`company-directory-backup-20261102-230001-<32 hex UUID>.json`. Always using the suffix
is permitted. Never overwrite an existing backup. Allocate unique temporary and
final names within the same approved directory/filesystem; user JSON cannot supply
backup paths, filenames, `$ref` sources or permissions.

1. Canonically serialize the complete validated destination snapshot to strict
   UTF-8 JSON. Include every portable stored field, stable company/admin UUID,
   tenant, domain, preference and timestamp. Exclude credentials, authentication,
   target context, transient maps and session/connection state.
2. Create an exclusive temporary file with restricted permissions before content
   becomes visible. Write all bytes; flush, fsync where supported, close, and check
   write completion. Errors remove only this attempt's temporary artifact and block
   all destination writes; they must not remove an older backup.
3. Compute SHA-256 of the expected complete bytes. Publish by an atomic same-filesystem
   rename to a unique final name without replacing existing files. Test publication
   atomicity, collision behavior and filesystem durability on each supported host.
   Where required, flush directory metadata; unsupported guarantees block release
   claims rather than being assumed.
4. Reopen the published file independently, read with the bounded parser, hash its
   actual bytes, and compare the digest. Then validate its schema and semantics and
   project/reload through the host's backup recovery validator. Verify normalized
   round-trip equality of all original metadata and IDs against the detached snapshot.
   An independently reopened file is required; validating only the pre-write buffer
   is insufficient. Any digest/parse/schema/round-trip error blocks merge.
5. Record only backup filename/reference, UTC time, byte count, SHA-256, contract
   version, source storage revision and outcome in host-owned local audit metadata.
   Do not append audit fields to the closed exchange envelope or log account data.
   A hash is corruption detection, not authenticity or identity proof; a hostile
   replacement of both file and audit digest is outside this guarantee.

Temporary, failed and interrupted artifacts must never be listed as verified
backups. Retain the old complete backup on publication failure. Retention/deletion
policy is a future separately reviewed host concern; no configuration UI is added.

## Restore and rollback boundaries

Transaction rollback preserves the pre-merge directory if insertion, update,
association/default handling, timestamp validation or commit fails. Never perform
an automatic whole-database restore over the running application. If a crash occurs
after commit but before success is displayed, reload the committed directory and
recompute the same import; idempotence must prevent duplicate records or stamping.
Never report success when commit acknowledgement is ambiguous.

A JSON directory backup must be restorable through a separately validated recovery
procedure, with its own preview, authorization and atomic write semantics. A future
recovery validator must prove exact portable metadata/ID preservation. Ordinary
local-first Merge is NOT exact restoration: it intentionally preserves conflicting
local values and cannot remove records added after the backup.

The JSON backup covers only Company Directory metadata. It does not back up Notes,
images, tickets, local integer mappings, unrelated Settings or all application data.
F7Hub's ticket associations/portable-ID mappings need an explicitly approved recovery
strategy and, where required, a SQLite-consistent online database backup. A raw copy
of a live WAL main file is forbidden as a recovery guarantee. Never share a live
database between applications.

## Summary and test acceptance matrix

The concise summary reports companies added, companies updated (the same metric
as existing companies enriched), administrators added, domains added, conflicts
skipped and backup status. Structured results also retain unchanged records and
validation failures. Backup states: not needed / verified / failed; a verified
backup can coexist with a failed merge. Never call an unverified file a backup success.

| Synthetic scenario | Required destination/backup outcome | Adapter execution |
|---|---|---|
| Changed valid import and recovery rehearsal | Verified backup equals original complete snapshot; committed result equals approved plan | NOT RUN |
| Invalid source/version/secret field | No destination change and no backup | NOT RUN |
| Existing destination conflicts only | Preserve local values; report skips; no backup if no enrichment | NOT RUN |
| Identical repeated import | Already up to date; no new backup/write/timestamp | NOT RUN |
| Backup write/flush/close/publication failure | No destination writes; older backups intact | NOT RUN |
| Published backup parse/schema/round-trip failure | No destination writes | NOT RUN |
| SHA-256 mismatch | No destination writes; failed status | NOT RUN |
| Same-second filename collision | Unique suffix, no overwrite, both complete files independently verify | NOT RUN |
| Interrupted temp write or publication | No destination writes before verified backup; incomplete artifacts not verified | NOT RUN |
| Destination changes after backup | Stale plan rejected/recomputed against new verified snapshot | NOT RUN |
| SQLite write or COMMIT failure | Entire merge rolled back; verified pre-merge backup retained | NOT RUN |
| Crash after commit before summary | Reload and idempotent retry; no duplicate data or misleading acknowledgement | NOT RUN |

`backup-scenarios.json` records these requirements as design fixtures, not test
execution evidence. Persistent activation requires independent contract, portable
module, backup/recovery and storage-adapter reviews, plus the Notes and Company
Directory gates. No success from the isolated schema suite clears these gates.
