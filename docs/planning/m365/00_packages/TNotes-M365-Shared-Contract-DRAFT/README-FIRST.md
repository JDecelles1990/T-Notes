# T-Notes M365 PowerShell Contract Kit — PROPOSAL ONLY

Status: `DRAFT — NOT YET APPROVED OR IMPLEMENTED` (2026-11-02).

This kit is prepared for review, **not committed to GitHub**. Repository filenames below are proposed, not files already present in your live T-Notes repository.

## Install after review

1. Copy `docs/contracts/m365/` into the T-Notes repository at the same relative path.
2. Add the included `GEMINI.md` to the repository root for Gemini CLI (review conflicts with any existing file first).
3. Keep existing root `AGENTS.md` intact; append the small canonical contract directive given in the contract section `Agent governance`, if you approve it.
4. Read the role-specific prompts in `docs/contracts/m365/prompts/`.
5. First authorize Codex **analysis only**, then approve the contract, then authorize one small GUI slice. The Gemini script work should begin only after the contract is approved.
6. For Gemini web chat, upload the canonical contract, schemas, relevant example files and the specific task prompt each time; do **not** assume the web chat reads the repository automatically.
7. For Gemini CLI, check `/memory show` and quote the version and acceptance criteria before it starts implementation.
8. Run `python -m pip install jsonschema` only in a development/test environment if not installed; then `python docs/contracts/m365/tests/validate_examples.py` from the repo root.

There is intentionally **no PowerShell runner, no login integration, no database migration and no active tenant connection** in this package.
