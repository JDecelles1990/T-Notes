# T-Notes Gemini CLI instructions (proposed)

Read and obey the repository's `AGENTS.md` and `ARCHITECTURE.md` first.
For M365 PowerShell tasks, also read the following authoritative contract and schemas **from the current repository checkout** before writing code:

@./docs/contracts/m365/CONTRACT.md

Do not claim to have read a file that is inaccessible. If the file is missing or contradictory, STOP and report the blocker.

You must repeat the contract version, script ID, required inputs, allowed outputs, authorization requirements and validation commands before proposing a script. Never change the contract or existing T-Notes core files while implementing an individual PowerShell script. Generate only the assigned script, tests and narrowly scoped documentation. All changes require review; never merge/push without explicit authorization.

Never read, echo, save, upload or log customer passwords, tokens, private keys, password-manager vault contents or real customer data. No real tenant operations without explicit authorization.
