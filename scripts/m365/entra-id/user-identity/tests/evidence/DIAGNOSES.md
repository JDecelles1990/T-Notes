# Retained attempt history

- attempt-01.log: **FAIL**. Nested fixture patch traversal assigned the result of
  an if-expression; PowerShell unwrapped a singleton connections array into its
  dictionary. Patching connections.0.* then indexed a nonexistent dictionary key.
  Diagnostic single-case/loop checks localized OfflineHarness.ps1 line 63. This
  was a test harness defect; no Graph command or application database was used.
- Correction: assign $cursor inside each conditional branch, preserving arrays.
- attempt-02.log: **PASS** at that source/fixture revision: Pester 3.4.0 reported
  55 tests passed, zero failed, and 53 standalone synthetic cases passed. It is
  retained evidence only. The subsequent provider-error-stream case changes the
  fixture inventory and requires fresh validation; it does not rewrite that log.
- validation-*.json: unique later PS7/Pester/schema attempts with exact command,
  input hashes, actual output and status. Use the final successful report matching
  SHA256SUMS.json. A prior failing report is never relabelled or overwritten.
- validation-20261103T004214Z-71b521c1.json: **FAIL**. The new synthetic
  nonterminating-error stub used Write-Error, which was unavailable in the fresh
  CreateDefault2 runspace with autoload disabled. CommandNotFoundException was
  correctly caught but misclassified as a pre-dispatch missing module. Corrected
  the stub to use PSCmdlet.WriteError directly, without loading a utility module.
  Also separated missing-command preflight (Get-Command -ListImported, no import)
  from a dependency failure after provider dispatch (INTERNAL_ERROR/unknown), so
  nested command failures cannot falsely claim the provider never started.
  The validator now records a failed runner directly rather than attempting to
  parse its empty stdout as JSON; the original failed report remains untouched.

All results are author-tested SYNTHETIC/OFFLINE evidence. Pester was already
installed; no dependency installation occurred. SDK/live-tenant behavior and
independent review remain NOT RUN.

After the 56-test/68-check PASS in validation-20261103T004548Z-77eabc15.json,
source review found that Get-ProviderField could unwrap a malformed singleton
array into a scalar. Preserve the property value as one pipeline object and add
array-valued ID/UPN/account-status rejection cases. Add a provider-internal missing
command case to exercise the post-dispatch classification correction. Restrict
HTTP status mapping to typed int/HttpStatusCode values. These new code/case bytes
require the subsequent validation report; the earlier PASS remains retained only.
