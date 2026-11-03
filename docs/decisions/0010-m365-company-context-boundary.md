# ADR 0010: Session-only company metadata and synthetic identity context

Status: Implemented for synthetic Phase A; independent review required.

Multiple administrator records are needed before Notes integrity corrections and
contract/engine approvals are complete. Keep immutable metadata in a Qt-independent
RAM directory, using stable UUIDs and deriving preferred UPN from a default record.
Version metadata exchange independently from the PowerShell wire contract.
Defer storage until verified backup/restore/migration gates. F7Hub can provide its
own adapter without sharing a live database.

A context service owns selection, confirmation, generation and target. The fixture
manager tracks Graph and Exchange separately and cannot create verified state.
Eligibility remains false and has no dispatch method. Future runtime evidence
belongs to an approved host adapter, never entered UPNs, labels or domains.

Restarts intentionally discard metadata. The multi-admin model does not silently
extend shared schemas. See the [directory guide](../features/m365-company-directory.md)
for fields, lifecycle, remaining authorization gates and migration requirements.
