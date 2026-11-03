# Retained validation attempts

The initial canonical proposed-contract validation invocation used
`--attempt-name proposed-preflight-01.json`. It exited 1 at argument validation:
`attempt-name must be a new safe correction-results UTC filename`.
No contract checks ran and no historical evidence was rewritten. This is a
retained NOT RUN contract-test attempt, with a failed CLI invocation.
Any rerun must use the documented correction-results filename convention or
omit the optional attempt name and retain its generated unique output.
