# Validation, decisions and implementation roadmap

Status: **PROPOSED**, approval and implementation remain separate gates.

## Validation scope and procedure

Run `validation/validate_contract.py` with an available Python 3 interpreter and
PowerShell 7. It uses the JSON Schema engine already bundled with PowerShell:
no dependency installation and no import of T-Notes production modules. It loads
only this package's schemas into an offline registry, checks each against Draft
2020-12's built-in metaschema, enables format assertions, evaluates synthetic
positive/negative fixtures, checks semantic acceptance rules and local doc links,
and verifies source identities. [Test-Json reference](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/test-json?view=powershell-7.5),
[JSON Schema specification](https://json-schema.org/draft/2020-12/json-schema-core).

The harness is a design-validation tool, never a production parser, security
boundary, worker, redactor or real script-path authorization implementation.
It includes reference acceptance predicates only to demonstrate the proposed
rules against synthetic inputs. Future production implementations need independent
tests against those rules, not imports from this harness.

Correction executions save a unique correction-results attempt and current
correction-results.json; original results.json/results-*.json remain immutable.
Each execution records actual
environment/command/time/check outcomes and artifact hashes. Failed attempts remain
preserved; diagnose before a materially changed rerun. Python's WindowsApps `py`
alias was inaccessible during environment discovery; direct installed Python
3.14.5 worked. jsonschema was absent, so the installed PowerShell engine was
selected instead; no dependency or production behavior was changed. Initial
artifact-directory creation was denied in the sandbox; scoped access created
only this package's directories. These were environment/authoring issues, not
executed product test failures. See validation/correction-results.json for fresh
correction outcomes and validation/results.json for the original proposal only.

The correction adds exact callable ABI/return/release binding, metadata-driven
target/service/permission eligibility, complete notes save acknowledgements,
UTC/history coverage, descriptor consistency and explicit connection/trust records.
Seven schemas remain the inventory; application-only mock types are definitions
in common.schema.json. No production implementation is claimed by these predicates.
The shell's WindowsApps python alias was inaccessible again; the installed
interpreter path in historical evidence was verified and used. Initial shell
writes were sandbox-denied; scoped approved writes saved only this contract.

The first validator attempt failed before schema-engine execution because an
accidental leading `+` in the embedded PowerShell helper caused a parser error.
Its immutable failed result is retained. Source inspection identified the literal;
the helper was corrected before a changed rerun. This was a validation-tool defect,
not a production or tenant test outcome.

The second attempt exposed a stack overflow with automatic metaschema validation
enabled while explicitly evaluating the metaschema. A bounded diagnostic with
automatic checking disabled accepted a valid schema and rejected an invalid type.
The harness now performs explicit Draft 2020-12 checks for every schema without
recursive automatic validation. The failed attempt remains retained; this change
does not waive metaschema validation or format assertions.

The third attempt completed 280 checks successfully but failed the negative
February-30 fixture: bundled JsonSchema.Net 7.0.0.0 accepted an impossible calendar
date with format assertions enabled. A focused diagnostic accepted a valid date,
also accepted February 30, and rejected a non-date string. Explicit Python calendar
validation now supplements schema shape/format checks. Results retain the raw
engine outcome alongside the combined acceptance decision; the limitation is not
hidden by changing the fixture. Production parsers need their own calendar tests.

## Acceptance matrix

| Gate | Checks required | Evidence in this task |
|---|---|---|
| Schema/syntax | Strict JSON, metaschema validity, all refs offline, exact version, unknown fields, invalid types/dates/IDs/status/errors | Executed by design harness; see results |
| Positive/negative fixtures | Manifest, request, result, error, company and all four payloads; secret fields, paths, wrong version, partial/error semantics | Executed synthetic checks |
| Semantic binding | Correlation/company/actual tenant/script/generation/target, parameter types/bounds/defaults, counts, expiry/confirmation, outcomes/exit mapping | Reference acceptance checks; not runtime enforcement |
| Wire rejection | Duplicate/multiple/truncated/invalid UTF-8/BOM/nonfinite output, extra text, depth/byte caps, nonzero-success | Synthetic samples only |
| Catalog safety | Resolved containment, symlinks/reparse/ADS/device paths, immutable approved hashes, check/use race, manifest tampering | String rules checked; actual filesystem trust/signing NOT RUN |
| Pester | Mock exact provider calls/no calls on rejection, success/failure/partial/cancel and redaction | NOT RUN: no production scripts |
| Parser/application | Independent production strict parser, approved payload model, view escaping, raw JSON redaction, unavailable semantics | NOT RUN: no integration implemented |
| Existing regression | Existing database/image/scratchpad/stopwatch/UI suites plus M365 navigation matrix | Existing tests inspected; NOT RUN for documentation-only task |
| Native Windows | Actual Qt focus/F8/HUD/tray/DPI, PowerShell module/auth/session and owned worker containment | NOT RUN |
| Live service | Approved synthetic tenant, authorized account/roles, expiry/switch/isolation, actual read-only outputs | NOT RUN; no customer credentials used |

Future production tests must not equate schema-valid with authorized, correct or
secret-free. Validate allowlisted data construction and semantic truth separately.

## Required future UI and persistence regression

Run existing tests/test_database.py (migration/integrity/FK/FTS), test_image_service.py,
test_scratchpad_service.py, test_stopwatch_service.py and test_ui_integration.py
as applicable to the authorized slice. Review existing fixtures before execution:
UI fixtures instantiate MainWindow and register tray/hotkey behavior, so they are
not part of a harmless schema-only run. Use synthetic isolated DB/image fixtures.

Add meaningful regression cases for Notes↔M365 navigation during unsaved typing
and pending image capture, both split panes, archive/restore/reorder/duplicate,
cursor/undo/resources/formatting, stopwatch running/paused/idle, no duplicate
debouncers, read-only fallback, panel collapse/resize, history/opacity, F8 restore,
HUD enter/exit, modal Return/Space/Escape and tab shortcuts while M365 forms have
focus. Test tray hide versus explicit Quit during auth/run/cancel and save failure.
Assert actual HTML/image/cache identity and zero unintended provider calls.

Ticket insertion tests must change company, target, ticket and preview immediately
before Insert, use hostile HTML/control text, confirm one undo step and single-use
preview, and prove existing saves retain unsaved images. Database proposals need
forward migration, rollback/recovery limits, integrity_check=ok and zero FK errors.
Native acceptance includes 100% and alternate DPI/multiple display, focus and
accessibility checks; offscreen success does not establish these outcomes.

## Decisions and conflicts requiring approval

| ID | Issue | Proposed disposition / remaining gate |
|---|---|---|
| D01 | Competing 0.1/1.0 draft families | Official 0.3.0 baseline established (promoted from 0.3.0-proposed.1) |
| D02 | Module-function versus .ps1 output ownership | Exact Context/Parameters/CancellationToken ABI and operation_return now specified; independent ABI approval still precedes script work |
| D03 | Editable ticket panel | Exclusive whole-container transfer; regression spike required; read-only fallback leaves editable acceptance open |
| D04 | Global keyboard/focus and HUD policies | Approve workspace-aware routing and HUD return behavior; preserve Notes behavior |
| D05 | Auth/process model | Review proposed per-tenant/account/service isolation, interactive flows and process-scoped Graph; native spike before freeze |
| D06 | Contract integrity/trust | Approve external release inventory and immutable staging/signing mechanism; manifest self-hash not sufficient |
| D07 | Storage/retention | RAM-first profile fixtures/history, settings reuse; durable companies and retention need later schema/policy approval |
| D08 | Existing documentation drift | system-overview permits UI→repositories whereas AGENTS requires services; approve owner correction separately, do not weaken AGENTS |
| D09 | Existing implementation drift | editor.py and MainWindow duplicate-tab path call image_service.repo directly; preserve now, review service boundary separately |
| D10 | Save atomicity | B2 now requires durable current-revision HTML/image acknowledgement, retained dirty state and rejected Quit/transitions on failure; implementation and failure-injection acceptance remain future gates |
| D11 | Existing restore limit | Pane membership not persisted although docs broadly promise restore; preserve order/ID and define separate restoration requirements |
| D12 | Microsoft capabilities | Freeze exact PS/module versions, property permissions, Exchange size conversion and sign-in retention through authorized native tests |
| D13 | Confirmation policy | Approve write previews, expiry/single-use and unknown-outcome handling; high-impact stays disabled pending stronger policy |
| D14 | Limits | Approve 64KiB request, 1MiB stdout, 64KiB stderr, depth20, max300s + grace5s and operation caps |
| D15 | Separately requested full Gemini GUI | Treat any delivery as an implementation candidate; reconcile exact source against approved contracts and regression gates |

These are explicit proposed decisions and unverified areas, not silently adopted
architecture. The design can be reviewed while production implementation remains
blocked. No existing independent review is superseded by an author self-review.

## Small implementation sequence

| Slice | Scope and exit gate |
|---|---|
| 1 GUI acceptance/review | Inspect any Gemini delivery; classify visual demo versus backend; run Notes regressions and document exact adjustment list, no inferred acceptance |
| 2 Contract approval | Independent review then user approval of source/hash/version/decisions; separate canonical promotion authorization |
| 3 Validation harness | Integrate production-grade schema/semantic acceptance tests and strict parsing under approved contracts; no provider access |
| 4 Safe catalog | Manifest discovery/trust, path/integrity checks and typed forms; no live execution |
| 5 Company profile service | RAM/synthetic first, non-secret settings reuse; durable repository/migrations only if authorized |
| 6 Auth service spike | Isolated authorized test tenant; Graph and Exchange identity/expiry/switch tests; approve lifecycle before production connector |
| 7 Worker | Owned nonblocking process, typed dispatch, bounded streams, cancel/timeout/exit/unknown-outcome tests with fake workers |
| 8 User Identity | Gemini implements only Get-UserIdentity.ps1, manifest, Pester fixtures/docs; independent script review and approved test-tenant acceptance |
| 9 Other Snapshot operations | Licenses, sign-ins, mailbox in separate slices with least-privilege/module evidence |
| 10 Workflow | Serial aggregation, partial/missing/expiry/tenant-change behavior, retry only selected section |
| 11 Notes integration | Prove editable panel transfer or approve alternative, sanitized preview/insertion and Notes data preservation |
| 12 Controlled changes | Only separately approved write operations, bound confirmation and outcome verification; high-impact separate |
| 13 Hardening | Native lifecycle/DPI/accessibility, privacy/retention, signing/ACL, crash recovery and full affected regression |

Slice 1 may inspect/review a delivered GUI before contract approval, but cannot
declare compatibility with an unapproved contract. Required GUI corrections remain
future work; do not implement them here. No slice authorizes the next automatically.
