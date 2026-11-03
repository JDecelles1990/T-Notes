# PROVISIONAL OFFLINE ENGINE

Contract: `tnotes.m365 / 0.3.0-proposed.1`. Pending independent contract and engine
review. No application integration, database access, Microsoft authentication or
real diagnostic operations. `M365.TEST.ABI` and Fixture-Operation.ps1 are test
fixtures, not a User Identity diagnostic implementation.

## Run the tests

From the canonical repository, using runtime-discovered Python and PowerShell 7:

```powershell
$python = (Get-Command python.exe -ErrorAction Stop).Source
& $python -B 'docs/planning/m365/offline-execution-engine-prototype/run_tests.py'
```

Automated runs execute non-destructively: response artifacts and test evidence reports
use isolated temporary directories and automatically clean up on PASS. If any test fails,
diagnostics are retained in the temporary directory and its path is reported. Source fixtures
in `examples/` are verified unchanged.
To explicitly persist a durable evidence artifact into `evidence/`, pass `--record-evidence`.
Use `--case test_success` for a focused test. Old failed attempts remain immutable.

`prepare_fixtures.py` is an explicit development authoring utility. It generated
the synthetic catalogs/anchors and pinned the installed executable, 306 selected
PowerShell runtime files, all engine script assets and the 21 contract artifacts.
Do not run it to bypass a failed integrity gate. It is never called by Engine.
The fixture anchors are author-generated test trust data, not independent approval.

## Interface and boundaries

Future authorized architecture:

```text
GUI -> application service -> Engine -> pinned local Catalog -> owned pwsh worker
```

`Engine(prototype_root, expected_anchor_sha256, anchor_name='trust-anchor.json')`
requires the caller's expected anchor digest. `execute(request, cancellation)`
accepts a JSON-compatible request dictionary and an optional threading.Event.
No request argument can choose an executable, script path, worker or trust anchor.
Those choices come exclusively from externally pinned configuration.

`Execution.response` is the contract execution-result object. `Execution` itself
is an application-local result wrapper, not a new wire envelope. An invalid input
that cannot establish a schema-valid request is a local rejection with
response=None and a safe error code. Validated requests rejected at later gates
produce host-origin contract errors with no fabricated verified tenant/data.
Process exit is `process_exit_code`; the result's operation_exit_code carries the
logical operation outcome. Structured worker errors can have process exit 0.
Execution.error_code identifies host rejection/transport failure; always inspect
response.status and response.errors for a schema-valid worker operation error.

The Python host normalizes and schema-validates the request, independently binds
manifest descriptors/defaults, checks context/target/risk/release metadata, and
starts pwsh with an argument array and shell=False. Every service lease is an
explicitly simulated fixture; only the pinned synthetic company/account/generation
is eligible. Real auth, required Microsoft modules, resolved-identity workflows,
write and high-impact operations are unsupported and blocked.

The fixed PowerShell adapter passes deeply read-only Context and Parameters plus
a CancellationToken using the exact ABI. It invokes the allowlisted .ps1 through
AddCommand/AddParameter. It captures pipeline/errors and validates operation_return
and selected payload before writing one UTF-8 LF-terminated envelope. The Python
host independently validates strict framing, schema, real calendar validity,
binding and logical exit, sanitizes the result and validates it again.

## Controls and implementation limits

| Control | Implementation / limit |
|---|---|
| Script allowlist and identity | Externally pinned anchor -> raw catalog hash -> explicit asset hashes -> raw manifest, script, payload-schema binding; no trust by filename or repository location |
| Paths / check-use races | Canonical relative path restrictions, resolved handle identity, reparse rejection, files pinned against write/delete and ancestor directories pinned against rename for the complete invocation |
| Executable | Explicit absolute pwsh.exe and SHA-256; no PATH search, download, dependency install or shell interpolation |
| Dependencies | All 7 schemas and 21 contract artifacts, engine PS assets, root PS installation DLL/JSON files and Utility module manifest pinned. OS trust and every possible dynamically loaded system component are outside this prototype's proof |
| Parameters | Schema type applicability plus independent default/enum/bounds/duplicate/reserved-name checks; integer excludes bool; typed immutable PS arguments |
| Limits | 64 KiB effective request, 1 MiB stdout, 64 KiB stderr, depth 20, manifest deadline <=300 seconds, five-second cooperative cleanup grace |
| Schema checks | Pinned local JsonSchema.Net Draft 2020-12 engine through an owned helper process; local refs only, real Python calendar checks; no network resolver or Python dependency installation |
| Timeout / cancel | Bounded asynchronous pipe IO, matching cancel_control frame, first committed terminal cause, no automatic retry, unknown effects after dispatch |
| Windows cleanup | Create suspended -> assign non-breakaway kill-on-close Job Object -> resume exact owned thread; terminate the owned job after grace and verify active process count zero |
| Errors and privacy | No raw stderr retained or logged. Stable allowlisted messages replace worker warning/error messages. Unknown fields reject; selected string credential patterns redact and revalidate. This is not a universal secret detector or a safe sandbox for arbitrary code |

Normal Windows jobs include a hidden conhost process. The native child test
requires a larger observed process count and verifies the whole owned job drains
to zero. The job controls descendants created through normal process APIs; it is
not a security boundary against deliberately hostile approved code using external
brokers or already-running services.

There is one fresh worker per execute call and one active operation per Engine
instance. Persistent worker/session reuse is explicitly unsupported. The worker
handles matching cancel frames while its invocation runs, then performs normal
idle-EOF shutdown. No app-wide singleton or production auth/session registry exists.

Schema helper checks have a separate 15-second bound; operational output must be
validated and committed before the operation deadline. Startup/preflight overhead
is bounded separately. A UI must call the synchronous Engine API outside Qt's
main loop in any separately authorized integration.

## Independent review and integration

Read ENGINE_CHECKPOINT.md and evidence/DIAGNOSES.md before evaluating the latest
native attempt. Recompute artifact/anchor hashes and the 21 contract hashes.
Run tests without regenerating trust data. Review all Windows ownership and
failure paths, strict parser, parameter binder, output schemas and redaction.

Gemini review is read-only and independent. Save any review in a new artifact;
do not rewrite original contract reviews, contract bytes or test attempts.
No review outcome alone authorizes production integration. After explicit user
approval, an application service may wrap the adapter behind an asynchronous API;
keep authentication, company/profile state, notes insertion and SQLite services
outside this module. Graph and Exchange require separate future verified auth
adapters; replace the synthetic context only through a separately approved design.
