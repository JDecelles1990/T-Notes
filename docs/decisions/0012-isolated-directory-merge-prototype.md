# ADR 0012: Isolate draft merge planning from persistence

Status: Candidate implementation; independent review required.

The exchange schema/policy, Notes corrections and company GUI corrections have
pending approval/review gates. Company profiles remain session-only. The current
implementation authorization explicitly permits isolated non-production work and a
disabled Settings control while durable persistence is unavailable.

Keep the merge planner in a self-contained prototype module outside `src/`, with
explicit pinned draft schema/policy inputs and no GUI, host-service, SQLite,
authentication or execution imports. Return detached non-durable plans; do not
register a production adapter, migrate a database or stamp timestamps during planning.

Add one disabled Merge button and a visible reason in the existing Settings dialog.
There is no picker or runtime path to the prototype. Defer optional workspace mode
and Department rather than extend company/context UI ownership during rereview.
Future reusable packaging and per-application adapters require independent review
and approval; exact draft hashes alone never supply those approvals.

The existing system-overview.md is concurrently modified by the company-directory
task and is preserved. This ADR and the Merge feature topic document the limited
Settings/prototype boundary without editing that shared architecture document.
