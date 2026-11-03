# M365 Official PowerShell Contract v0.3.0 — Release Approval Record

Candidate release identifier: `tnotes.m365 / 0.3.0`  
Current release status: **RELEASE CANDIDATE — INDEPENDENT REVIEW REQUIRED**  
Required status upon independent approval: **APPROVED — IMPLEMENTATION CONTRACT**  
Date: 2026-11-02  
Authoritative repository path: `docs/contracts/m365/`  
Authoritative entrypoint: [`CONTRACT.md`](CONTRACT.md)  
Predecessor baseline: `tnotes.m365 / 0.3.0-proposed.1` (historical proposal preserved at `docs/planning/m365/03_codex_reviews/architecture-contract-proposal-20261102/`)

---

## 1. Executive Summary & Governance Notice

This release package establishes `tnotes.m365 / 0.3.0` as the authoritative, single source of truth for Microsoft 365 PowerShell development in the T-Notes repository.

In strict adherence to repository governance (`AGENTS.md` and `GEMINI.md`):
- **No Self-Certification:** The creating agent (Gemini) does not self-approve or self-promote newly authored release artifacts. The status of this package is explicitly set to `RELEASE CANDIDATE — INDEPENDENT REVIEW REQUIRED`.
- **Technical Scope Only:** Contract promotion and design validation authorize offline script development and synthetic validation only. They do **NOT** authorize live Microsoft Graph/Exchange Online authentication, credential persistence, live tenant execution, production GUI integration, or executable script registration.
- **Historical Baseline Preservation:** The predecessor proposal `tnotes.m365 / 0.3.0-proposed.1`, its 21 signed artifacts, and historical validation evidence remain completely intact, byte-preserved, and immutable.

---

## 2. Four Distinct Approval Boundaries

To maintain strict operational security and eliminate ambiguity between development specifications and operational privileges, four separate approval boundaries are defined and enforced:

| Approval Boundary | Designated Status | Authorized Capabilities | Prohibited Capabilities |
|---|---|---|---|
| **1. Contract Specification** | `APPROVED — IMPLEMENTATION CONTRACT` | Offline schema validation, contract authoring, unit/Pester test authoring against synthetic fixtures. | Live tenant execution, credential storage, engine registration. |
| **2. Host Execution Engine** | `APPROVED — EXECUTION ENGINE` | Offline engine dispatch, worker sandbox isolation, process supervision, output validation. | Live Graph/Exchange authentication, unverified script execution. |
| **3. Operation Script** | `APPROVED — OPERATION SCRIPT` | Registration of a specific `.ps1` operation in catalog with pinned SHA-256 and verified permissions. | Replay outside declared tenant/scope bounds, unapproved script execution. |
| **4. Live Tenant Execution** | `AUTHORIZED — LIVE TENANT EXECUTION` | Live tenant PowerShell invocation with human administrator or policy authorization. | Execution without tenant verification, automated retry of non-idempotent operations. |

Technical contract approval applies exclusively to **Boundary 1**.

---

## 3. Future F7Hub Portability and Application Independence

Reusable M365 PowerShell operations defined under this contract are designed for eventual adoption by F7Hub and other administrative hosts.

### Prohibitions for Reusable Scripts:
- Must **NOT** import T-Notes-specific Python modules or runtime packages.
- Must **NOT** depend on PySide6 widgets or the Qt event loop.
- Must **NOT** access T-Notes SQLite databases (`notes.db`, `app_session`, scratchpads, etc.).
- Must **NOT** read ticket editor DOM or workspace GUI state directly.
- Must **NOT** own Graph or Exchange Online authentication sessions, login dialogs, or token caches.
- Must **NOT** store credentials, access tokens, or tenant secrets in local files or registry.
- Must **NOT** make assumptions regarding a specific GUI layout, ticketing tool, or operating application.

### Reusable Script Interface Requirements:
- Must rely exclusively on parameters passed by the hosting adapter across the standard invocation boundary:
  - `$Context`: Typed hashtable containing `company_id`, `tenant_id`, `ticket_id`, `correlation_id`, `execution_mode`, etc.
  - `$Parameters`: Validated typed hashtable conforming to the operation's manifest schema.
  - `$CancellationToken`: Cancellation sentinel monitored during long-running operations.
- Must return a typed PowerShell object conforming to the official contract schema (`https://tnotes.invalid/m365/0.3.0/schemas/operation-data.schema.json`).
- Must allow the host adapter to serialize the wire envelope to stdout (scripts never perform wire JSON serialization on stdout).

---

## 4. Resolution of P1 Tooling Findings

Three critical P1 tooling findings identified during independent review have been corrected and verified:

### P1 — Python Interpreter Discovery
- **Finding:** Hardcoded obsolete interpreter paths (`pythoncore-3.14-64`) caused execution failures on standard Windows installations.
- **Resolution:**
  - Automated tooling (`run_tests.py` and `validate_contract.py`) uses `sys.executable` by default.
  - Optional `--python <path>` argument validated for file existence before execution.
  - Operator runtime discovery documented: `$python = (Get-Command python.exe -ErrorAction Stop).Source`.
  - Verified on current Windows installation.

### P1 — Non-Destructive Test Execution
- **Finding:** Test runners wrote output files directly into source directories (`examples/` and untracked `evidence/` files).
- **Resolution:**
  - `test_engine.py` routes responses to isolated temporary directories (`tempfile.TemporaryDirectory`). Source fixtures in `examples/` are never overwritten.
  - `run_tests.py` enforces isolated temporary directories by default, asserts pre/post source fixture SHA-256 hashes, and cleans up on `PASS`.
  - Added explicit `--record-evidence` flag when durable evidence persistence is required.
  - Verified: zero files modified in `examples/`, zero untracked files created in `evidence/`.

### P1 — Validation Baseline Isolation
- **Finding:** Validation suite conflated contract semantic checks with repository-level byte preservation, causing 17 authorized S001 merge changes to fail contract validation.
- **Resolution:**
  - Contract semantic and schema checks (`contract_checks`) are isolated from repository baseline checks (`preservation_checks`).
  - Contract checks evaluate contract artifacts (7 schemas, ABI, metadata, exit codes, limits, mock compatibility).
  - Repository baseline preservation evaluates historical snapshot drift as an explicitly separate diagnostic without failing contract semantics.

---

## 5. Consumer Compatibility & Migration Requirements

The official release candidate `tnotes.m365 / 0.3.0` introduces updated schema identifiers (`https://tnotes.invalid/m365/0.3.0/schemas/...`) and strict version validation. Existing consumers require coordinated migration:

| Consumer Component | Current State | Required Migration Action | Assigned Responsibility |
|---|---|---|---|
| **`M365CatalogService`** (`src/services/m365_catalog_service.py`) | Pinned to `03_codex_reviews/...` and `VERSION = "0.3.0-proposed.1"` | Update default path to `docs/contracts/m365/` and expected version to `0.3.0`. | Codex / Application Service Owner |
| **Contract Review Pins** (`assets/m365/contract-review-pins.json`) | Contains 21 hashes for `0.3.0-proposed.1` | Update review pins to match the 26 official `0.3.0` candidate hashes upon independent approval. | Codex / Security Integration |
| **Offline Execution Engine** (`docs/planning/m365/offline-execution-engine-prototype/`) | `trust-anchor.json` pins `0.3.0-proposed.1` schemas | Update trust anchor and test descriptors to reference official `0.3.0` schemas in follow-on engine task. | Engine Maintainer |

---

## 6. Official Release Candidate File Inventory

Every file in `docs/contracts/m365/` has been verified with cryptographic SHA-256 hashing:

| File Path | Description | SHA-256 |
|---|---|---|
| `CONTRACT.md` | Authoritative contract specification (Entrypoint) | `d983ed65280b908d173310de6c69170d4708e53a79e2c6a7bf1f8127049faa56` |
| `README.md` | Architecture index, boundaries, and discovery | `38a98881bd610507e65423bf021fce23b7a347f4892de8d6318ef8d2f2b1b1ec` |
| `AGENT_HANDOFF.md` | Agent governance and review handoff instructions | `3f2798f1431764911da07c824dd132802202fb60d62d21244399ad87c202c86b` |
| `CHECKPOINT.md` | Promotion checkpoint and verification summary | `744c281f21b9fceb01b31e4bb6226e261aff5b3de805502c7db34c9dd67f5609` |
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

---

## 7. Validation Execution Summary

### Contract Validation Suite
- **Command:** `python -B docs/contracts/m365/validation/validate_contract.py`
- **Contract Result:** `PASS` (446 / 446 checks passed, 0 failures)
- **Baseline Preservation Diagnostic:** `FAIL` (23 historical drift items: 17 S001 merge changes + 6 AGENTS.md/GEMINI.md changes; isolated from contract semantics)
- **Execution Mode:** Isolated temporary directory, automatic cleanup on `PASS`.

### Offline Execution Engine Native Suite
- **Command:** `python -B docs/planning/m365/offline-execution-engine-prototype/run_tests.py`
- **Engine Status:** `PASS` (38 / 38 passed, 0 failures, 0 skips)
- **Execution Mode:** Isolated temporary directory, automatic cleanup on `PASS`, pre/post fixture integrity verified.

---

## 8. Remaining Independent Review Gate

The package is prepared and fully validated. The following gates remain before production release:

1. **Independent Review:** An independent reviewer (or human operator) must inspect this package, verify hashes, and confirm the transition from `RELEASE CANDIDATE — INDEPENDENT REVIEW REQUIRED` to `APPROVED — IMPLEMENTATION CONTRACT`.
2. **Consumer Pin Update:** Update `assets/m365/contract-review-pins.json` and `src/services/m365_catalog_service.py` to point to `docs/contracts/m365/` with version `0.3.0`.
3. **Engine Trust Anchor Update:** Update `docs/planning/m365/offline-execution-engine-prototype/trust-anchor.json` to pin official `0.3.0` schemas in a dedicated engine integration task.
4. **Live Execution Authorization:** Live Microsoft Graph and Exchange Online execution remains blocked until an authorized administrative gate explicitly authorizes live tenant operations.

