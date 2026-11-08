# M365 S1 official contract engine migration

Status: author implementation candidate, independent review required.

The user explicitly accepted `tnotes.m365 / 0.3.0` for S1 implementation on
2026-11-03, retaining the corrected contract's final independent-signoff
limitation. This acceptance permits development against the exact accepted
bytes; it does not approve this implementation or authorize live execution.
The exact authorization and accepted identities are retained in the external
S1 checkpoint; `accepted-contract.json` records the authorization digest.

## Implementation boundary

`prototypes/m365_official_engine/` is the migrated copy of the existing offline
engine. Its host, schema validators, protocol, worker and Windows supervisor
reuse the predecessor implementation. The historical proposal and prototype
remain byte-preserved in `docs/planning/m365/`; there is no automatic fallback
or version negotiation. Keeping a separate candidate directory allows review
without rewriting historical trust evidence. There is no new execution design.

The package uses official seven-schema request, result, error, operation-return
and selected data validation. `Context`, `Parameters`, `CancellationToken` are
passed by the existing worker; context includes correlation and release identity.
Nullable `ticket_context` is accepted; an object requires a valid non-null
`ticket_id`. Native ABI tests exercise string, Int64, double, Boolean and immutable
string-array parameters. Invalid or mixed versions fail closed.

### Native return validation correction

The S1 P2 and array-ETS corrections validate native return values in
`Assert-NativeOperationReturn` before any operation return is passed to JSON
conversion. The outer return and non-null `data` must have the exact
`System.Management.Automation.PSCustomObject` runtime type. Plain note
properties represent JSON objects; one-dimensional, zero-based CLR arrays
represent JSON arrays, and warnings/errors must be object arrays. Leaves are
strings, Booleans, finite CLR integer/floating/decimal numbers, or null. Enum,
DateTime/DateTimeOffset, Hashtable/dictionary, arbitrary collections/provider
objects and executable properties are rejected without conversion or getter
evaluation. The compiled CLR helper `TNotesNativeReturnTypes` unwraps `PSObject`
layers, verifies that `PSCustomObject` instances carry only `PSNoteProperty` and
non-script CLR methods while arrays and primitives carry only non-script CLR
adapter members, and inspects array dimensions (`System.Array.Rank`), lower
bounds (`System.Array.GetLowerBound(0)`), lengths (`System.Array.Length`),
elements (`System.Array.GetValue(i)`) and note-property values directly via CLR
without invoking PowerShell ETS member dispatch (`Rank`, `GetLowerBound`,
`GetUpperBound`, `Length`, `Count`, `GetValue`, `GetEnumerator`, `GetType`).
The worker compiles that helper in memory from its pinned protocol source using
the bundled PowerShell utility before starting operation code; no new library or
external executable is installed. These are the existing callable ABI's
JSON-compatible values, not additional payload fields or schemas. The official
schemas still decide allowed fields, bounds, null locations and status semantics
in a separate mandatory step.

Traversal tracks canonical reference targets (`PSObject` wrapper for
`PSCustomObject`, unwrapped CLR reference for `System.Array`), rejects reference
cycles, permits repeated acyclic references, and uses the host parser's existing
depth limit of 20 with a node budget of 1,048,576 (the wire byte ceiling).
Native failures become a worker `CONTRACT_VIOLATION` return with null data; the
host adapter continues to own envelope serialization/output. Real worker tests
cover the original Hashtable and DateTime defects, numeric Enum serialization,
nested objects/arrays, cycles, depth, nullability, unsupported containers,
multidimensional and non-zero-lower-bound arrays, object getters, and array ETS
script members (`Rank`, `GetLowerBound`, `GetType`, `Length`, `Count`,
`GetUpperBound`, `GetValue`, `GetEnumerator`) with isolated side-effect counters
proving zero malicious member execution during validation, plus valid nested data
using an existing official schema. The nested fixture is test-only and does not
deliver an S2 operation.

The synchronous engine stays independent of Qt, SQLite and application state.
No GUI service imports or dispatches it. The production catalog remains empty,
all presentation eligibility stays false, and Settings Merge stays disabled.
S2 operation delivery and S3 asynchronous GUI integration are separate gates.

## Trust inventories

The catalog's seven schema-review pins are separate from executable trust.
The candidate engine pins the release inventory's 26 unique artifacts plus the
release record itself, for 27 contract artifacts. The release inventory excludes
its containing record, avoiding circular hashing. The candidate anchor binds
this accepted snapshot, catalog, worker, scripts and protocol helpers. A caller
must independently provide the expected anchor digest; reading a colocated pin
file never grants production trust.

PowerShell 7.6.9 executable and all 306 dependency records match the historical
runtime pins. The unchanged Windows supervisor retains pinned-file read locks,
structured arguments, suspended launch into an owned Job Object, bounded pipes,
bounded cancellation and process-tree cleanup. This is an integrity boundary
for trusted executable code, not a hostile-code sandbox.

Candidate worker/protocol and fixture hashes change for this correction. Only
their dependent candidate manifests/catalogs/anchors/request pins are refreshed
from verified bytes; the accepted contract record, its 27 artifact pins, seven
catalog schema pins, runtime identities and historical engine are preserved.
Previous candidate identities and failed-review evidence remain external and
unchanged. Historical gate1/entry-preservation records are retained snapshots;
the correction checkpoint records current scope and any authorized documentation
differences rather than rewriting those records.

`prepare_fixtures.py` is an explicit authoring tool that creates only candidate
synthetic fixtures and anchors. It is never invoked at dispatch. Generated pins
are author candidate identities pending independent review, not approvals.
Only the inherited offline ABI and fault fixtures can run; production modules,
connections and tenant execution remain unavailable.

## Validation and rollback

Run `.venv/Scripts/python.exe -B prototypes/m365_official_engine/run_tests.py
--output-dir <external-directory>` for the real-process S1 suite. Run the
historical prototype's runner separately for its unchanged 38-test baseline.
Run `python -B -m pytest` for application regression and the official contract
validator with external evidence output. Each suite reports its own preservation
scope. The contract validator's historical application baseline drift must not
be conflated with fresh contract failures or current S1 preservation.

Rollback requires no database recovery: remove only the new S1 candidate and test
files and restore the four explicitly backed-up catalog/service/fixture/topic
files to their S1 entry bytes. Do not reset the dirty checkout. External
`ENTRY.json`, byte-verified backups and final inventory identify this boundary.
Independent review must verify those exact identities before any later slice.
