# ADR 0011: Committed note snapshots before archive and shutdown

Status: Implemented candidate; independent review required.

Archive previously trusted an active debounce timer. Failed autosaves stop that
timer while retaining unsaved text. Explicit Quit removed recovery controls before
close could refuse shutdown, and HTML/image writes used independent transactions.

Use a repository-owned transaction for each HTML revision, referenced JPEG BLOBs
and ticket-scoped orphan cleanup. Reject missing image references and ambient
transactions. Keep SQL out of the UI and never nest independently committing CRUD
calls inside the save unit of work. No schema migration or production DB access is
needed. SaveReceipt contains ticket_id, attempted_revision, persisted_revision,
status and error_code; errors raise without a saved receipt. This follows the
application persistence requirement described in the candidate M365 architecture,
without approving or modifying that contract or connecting Notes to execution.

The UI snapshots the current monotonic in-session editor revision. Only its exact
committed acknowledgement clears dirty state and pending JPEGs. A later edit or
ambiguous receipt retains recovery state. One archive barrier serves direct,
prompted, secondary-pane and Close Other Tabs routes. Shutdown defers F8/tray
teardown and application quit until note/session persistence succeeds. Failure
restores visible Notes, keeps recovery controls and allows Ctrl+S Retry.

Per-ticket atomicity does not imply all-ticket or archive-batch atomicity. Archive
audit updates remain subsequent operations; completed saves are durable even if
archiving later fails. Forced OS termination while notes are unsaved still loses
RAM-only edits. No recovery journal or background persistence engine is introduced.

See [history and archive](../features/history-and-archive.md),
[tab lifecycle](../features/tab-lifecycle.md),
[editor save acknowledgement](../features/editor-and-formatting.md),
[database unit of work](../database/schema.md) and
[image cache ownership](../architecture/image-pipeline.md).

The concurrently modified system-overview.md is deliberately preserved. This ADR
records the Notes interaction change without editing the other task's document.
