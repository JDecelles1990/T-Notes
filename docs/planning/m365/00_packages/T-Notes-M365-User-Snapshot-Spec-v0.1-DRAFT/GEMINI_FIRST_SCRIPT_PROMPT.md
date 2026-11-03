# Gemini Flash — first task for User Diagnostic Snapshot

Read these files from the *same branch/workspace* before producing any code:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `contracts/m365/CONTRACT.md`
4. `contracts/m365/result.schema.json`
5. `contracts/m365/USER_SNAPSHOT_SPEC.md`

**Task mode: @ANALYZE ONLY until the user approves this specification and resolves the contract version mismatch.**

Your first implementation proposal must be limited to `M365.ENTRA.USER_IDENTITY`, the read-only `Get-UserIdentity.ps1` operation. Do not combine identity, licenses, sign-ins and Exchange into a monolithic script. Those are separate scripts in a GUI-orchestrated workflow.

Respond with:
- Contract version actually read; verify it agrees across files.
- Precise input/output schema proposal and permissions.
- Existing repo conventions that you will reuse.
- Proposed file paths, Pester mock tests, JSON success/error fixtures and test commands.
- Authentication boundary: no `Connect-MgGraph` inside script and no password handling.
- Failure modes and privacy constraints.
- Any contradictions or missing specification; STOP rather than inventing shared contracts.

After separate authorization to implement: generate only the selected `.ps1`, its manifest, its tests, fixtures and the short script documentation. Do not edit GUI, database, shared contracts or other scripts. Do not claim tests passed unless executed. Output PASS / FAIL / NOT RUN / BLOCKED.
