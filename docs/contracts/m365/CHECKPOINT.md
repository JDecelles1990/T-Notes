# M365 Official Contract v0.3.0 Release Preparation Checkpoint

Final disposition: **OFFICIAL CONTRACT v0.3.0 — RELEASE CANDIDATE READY FOR INDEPENDENT REVIEW**

Date: 2026-11-02  
Repository: `C:\Dev\T-Notes`  
Branch: `main` (HEAD: `30eef02` - Merge branch 'feature/m365-workspace-foundation-s001')  
Authoritative contract path: `docs/contracts/m365/`  
Authoritative contract entrypoint: [`CONTRACT.md`](CONTRACT.md)  
Official contract version: `tnotes.m365 / 0.3.0`  
Predecessor baseline: `tnotes.m365 / 0.3.0-proposed.1` (preserved in `docs/planning/m365/03_codex_reviews/architecture-contract-proposal-20261102/`)

---

## 1. Executive Summary and Authority Rules

- **Authoritative Location:** The official Microsoft 365 PowerShell shared contract candidate is established in canonical repository path `docs/contracts/m365/`.
- **Target Release:** `tnotes.m365 / 0.3.0` (promoted from `0.3.0-proposed.1`).
- **Review Boundary:** The creating agent (Gemini) does not self-approve newly authored artifacts. In compliance with repository governance, this release candidate is marked **`RELEASE CANDIDATE — INDEPENDENT REVIEW REQUIRED`**. The required status upon independent approval is **`APPROVED — IMPLEMENTATION CONTRACT`**.
- **Live Tenant Execution Strictly Prohibited:** Contract preparation and design validation authorize offline script development and testing against synthetic fixtures. They do **NOT** authorize live Microsoft Graph or Exchange Online authentication, credential storage, real tenant execution, or production GUI integration.
- **Predecessor Baseline Immutability:** Historical proposal `0.3.0-proposed.1` (21 signed files) and engine prototype trust anchors remain completely unchanged and byte-preserved.

---

## 2. Four Distinct Approval Boundaries

Operational security and governance mandate four explicitly separated approval gates:

1. **Contract Approved (`APPROVED — IMPLEMENTATION CONTRACT`):**
   - Contract specification, JSON schemas, manifests, ABI, and validation test suite are verified and approved for implementation.
   - Authorizes offline script development and synthetic test execution.
   - *Does NOT authorize live tenant execution, credential storage, or executable registration.*
2. **Engine Approved (`APPROVED — EXECUTION ENGINE`):**
   - Host execution engine, process supervisor, isolation boundaries, cancellation mechanics, and output parsers are independently tested and approved.
   - Verifies sandbox isolation and non-destructive execution.
3. **Operation Approved (`APPROVED — OPERATION SCRIPT`):**
   - A specific PowerShell operation script, manifest, SHA-256 hash, and Pester tests are reviewed and cryptographically pinned in host catalog.
   - Authorizes the host engine to register and invoke the script in offline/mock modes.
4. **Live Tenant Execution Authorized (`AUTHORIZED — LIVE TENANT EXECUTION`):**
   - Human administrator or explicit enterprise authorization policy grants permission to execute an approved operation against a verified, specific Microsoft 365 tenant using host-owned credentials.
   - Requires live tenant verification, scope consent verification, and RBAC validation.
   - *Strictly separate from technical contract or engine approval.*

---

## 3. Future F7Hub Portability & Application Independence

To ensure reusable M365 PowerShell operations can be adopted by F7Hub and other administrative hosts:

- **Strict Application Independence:** Reusable scripts must NOT import T-Notes Python modules, depend on PySide6/Qt widgets, access T-Notes SQLite databases (`notes.db`, `app_session`), read ticket editor state directly, or own Graph/Exchange authentication sessions.
- **Pure PowerShell 7 ABI:** Operations rely strictly on host-supplied parameters passed across the invocation boundary: `$Context` (hashtable), `$Parameters` (hashtable), and `$CancellationToken`.
- **Host Output Ownership:** Operations return typed PowerShell objects; the host adapter serializes the wire JSON envelope.

---

## 4. Resolution of Three P1 Tooling Findings

1. **P1 — Python Interpreter Discovery:**
   - Automated tooling (`run_tests.py` and `validate_contract.py`) uses `sys.executable` by default.
   - Added optional `--python <path>` argument with path resolution and existence validation.
   - Documented operator runtime discovery: `$python = (Get-Command python.exe -ErrorAction Stop).Source`.
   - Verified on current Windows installation (`Python 3.14`).

2. **P1 — Non-Destructive Test Execution:**
   - `test_engine.py` routes output response files to isolated temporary directories (`tempfile.TemporaryDirectory`). Source fixtures in `examples/` are never overwritten.
   - `run_tests.py` runs non-destructively in an isolated temporary directory by default, asserts pre/post source fixture hashes, and cleans up on `PASS`.
   - Added explicit `--record-evidence` flag when durable evidence persistence is required.
   - Verified: zero files modified in `examples/`, zero untracked files in `evidence/`.

3. **P1 — Validation Baseline Isolation:**
   - Separated contract semantic and schema checks (`contract_checks`) from repository-level baseline preservation checks (`preservation_checks`).
   - Contract checks evaluate contract artifacts (7 schemas, metaschema validation, offline refs, ABI, format, parameter binding, result binding, exit codes, limits, mock compatibility).
   - Baseline preservation checks evaluate repository drift (17 S001 files + 6 AGENTS.md/GEMINI.md files) as a separate diagnostic without failing contract semantics.

---

## 5. Actual Test and Validation Results

### Contract Validation Suite (`docs/contracts/m365/validation/validate_contract.py`)
- **Command:** `python -B docs/contracts/m365/validation/validate_contract.py`
- **Contract Result:** `PASS`
- **Contract Checks Passed:** 446 / 446 (0 failures)
- **Baseline Preservation Diagnostic:** `FAIL` (23 historical drift items isolated from contract semantics)
- **Execution Mode:** Isolated temporary directory, automatic cleanup on `PASS`.

### Offline Engine Native Suite (`docs/planning/m365/offline-execution-engine-prototype/run_tests.py`)
- **Command:** `python -B docs/planning/m365/offline-execution-engine-prototype/run_tests.py`
- **Engine Status:** `PASS`
- **Tests Passed:** 38 / 38 (0 engine failures, 0 skips)
- **Execution Mode:** Isolated temporary directory, automatic cleanup on `PASS`, pre/post fixture integrity verified.

---

## 6. Consumer Compatibility & Migration Requirements

| Consumer Component | Current State | Required Migration Action | Assigned Responsibility |
|---|---|---|---|
| **`M365CatalogService`** (`src/services/m365_catalog_service.py`) | Pinned to `03_codex_reviews/...` and `VERSION = "0.3.0-proposed.1"` | Update default path to `docs/contracts/m365/` and expected version to `0.3.0`. | Codex / Application Service Owner |
| **Contract Review Pins** (`assets/m365/contract-review-pins.json`) | Contains 21 hashes for `0.3.0-proposed.1` | Update review pins to match the 26 official `0.3.0` candidate hashes upon independent approval. | Codex / Security Integration |
| **Offline Execution Engine** (`docs/planning/m365/offline-execution-engine-prototype/`) | `trust-anchor.json` pins `0.3.0-proposed.1` schemas | Update trust anchor and test descriptors to reference official `0.3.0` schemas in follow-on engine task. | Engine Maintainer |

---

## 7. Official Candidate File Inventory

Authoritative candidate files in `docs/contracts/m365/`:

| Path | Status | SHA-256 |
|---|---|---|
| `CONTRACT.md` | Authoritative Entrypoint (0.3.0, F7Hub portability, 4 approval gates) | `d983ed65280b908d173310de6c69170d4708e53a79e2c6a7bf1f8127049faa56` |
| `README.md` | Architecture Index & Discovery | `38a98881bd610507e65423bf021fce23b7a347f4892de8d6318ef8d2f2b1b1ec` |
| `RELEASE_APPROVAL.md` | Formal release approval record and candidate inventory | (Generated in release preparation) |
| `CHECKPOINT.md` | Promotion checkpoint and verification summary | (This document) |
| `AGENT_HANDOFF.md` | Agent governance and review handoff instructions | `3f2798f1431764911da07c824dd132802202fb60d62d21244399ad87c202c86b` |
| `CONTRACT_CORRECTION_HANDOFF.md` | Historical record of independent review corrections | `3569c2ce3460ed2708ce97d55ea0fa01bcc7719264f8e429e10aed1cc62d27f9` |
| `GEMINI.md` | Reference copy of script development rules | `3d4f901235904ba86f2147342d71c56c641ed05c8fd1878197af34fdce7b6e26` |
| `security-and-execution.md` | Security model, catalog, and worker lifecycle | `28a68b4590193400f80b526e12b283fe2ef2fd696932bcf61296276b60131ebe` |
| `user-snapshot.md` | User Snapshot four-operation specification | `598f2b64afcad6c41dad6879b2a94a548131be9e2ec215d0b9a513101bfc7c80` |
| `validation-and-roadmap.md` | Test matrix and roadmap | `dcf5b712141f5512192a05ef2733124a71d60dafd13a43e94d0ec74e467a0b30` |
| `workspace-architecture.md` | Workspace, UI, and notes architecture | `7075b0d697556deca3dd030bc1c6fda0d660662cb7fde9220705da493cf29ee3` |
| `schemas/common.schema.json` | Shared JSON types, ABI, and return types | `e718b3bc83e3562deb9e743e99823a785a7839a2a1a4ae895afc38def8200ae6` |
| `schemas/company-profile.schema.json` | Company profile schema | `b2e2628634fec9289e75fbcaa8b942acd39e60588dc0d307a291c4fc3753247d` |
| `schemas/error.schema.json` | Bounded error response schema | `0d9a5d81efca5486e7dd5ff6f9735f5f51a75d43c60ea97d3882fd0386a94a20` |
| `schemas/execution-request.schema.json` | Worker execution request schema | `c86e2c508afec1d358d12f3f83602c5e456c3807513a7db1e4b88ac8d8eda963` |
| `schemas/execution-result.schema.json` | Worker execution result envelope schema | `a3ab4200c5a303559fb301688d48ce1d45d493185c44281e35b1d6873b5234d6` |
| `schemas/operation-data.schema.json` | User Snapshot typed data schemas | `eac11af0432f19d0ff6b8c424d99383dd4ae87a64810a6990272418a446273fe` |
| `schemas/script-manifest.schema.json` | Script manifest metadata schema | `2f13a3c3f98dba6b5cfbfa2a7b9c9032acdf2665b522c7cc3a446d2654ad9e7c` |
| `examples/fixtures.json` | Synthetic positive and negative test fixtures | `11c77c1793db38631c2c461d007fe1277bce688c1adefefd61dcd6c2f44971fb` |
| `examples/mock-compatibility.json` | Mock compatibility instances | `dd2fb96848a327e5fcb9e6e550a506a759f3a1c41e2a4427d4161cbf1eefffeb` |
| `validation/validate_contract.py` | Contract validation harness | `7ef6eaf6dcfaa3f064d5264cd6458c5d800f30729e6841bb28b25196fc2d237f` |
| `validation/correction_checks.py` | Contract check definitions | `7ae4eb81694dcccc5c9ab54433c70f8194da7fc6043684b64e8601ca02163b7b` |
| `validation/correction-baseline.json` | Repository baseline verification hashes | `7687bae19cdb97ebd93623ec21d257173f4c59f97fa5edaedd86deaff10094a1` |
| `validation/source-snapshot.json` | Preserved source snapshot metadata | `e1cd2831e0f824c435fd4217f21b5eee4f953cd3bafaed431a631ac4e6b6e5b6` |
| `validation/correction-results.json` | Active validation results summary | `87ba06d99dc2542ddcae1d3572627c13a935110559df645a02fcf90630ffa7bc` |
| `validation/correction-results-20261103T010141-0a261cf4.json` | Historical correction evidence | `5f8a74acd096dc962b1a3664901c20ba15b2e31f4455f7282e94a0b994665901` |
| `validation/correction-results-20261103T012008-67c2c2fe.json` | Official v0.3.0 validation evidence | `87ba06d99dc2542ddcae1d3572627c13a935110559df645a02fcf90630ffa7bc` |
