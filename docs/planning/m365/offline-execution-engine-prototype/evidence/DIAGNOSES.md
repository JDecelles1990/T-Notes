# Retained native attempt diagnoses

- `tests-20261102T233428Z-14fb1d3d.json`: FAIL. Catalog and Windows file
  pinning succeeded. The pinned schema helper emitted CRLF via Console.WriteLine;
  strict framing correctly rejected it. Changed protocol.ps1 to emit LF.
- The owned-job diagnostic identified the second process as Windows conhost.exe,
  launched alongside pwsh even with CREATE_NO_WINDOW. Job accounting therefore
  includes the hidden console host; the engine must not interpret count=2 as a
  script-created child. Child cleanup tests require at least three owned processes.
- `tests-20261102T233603Z-b772e9df.json`: FAIL, bounded TIMEOUT; owned job drained
  to zero. Console.In.ReadLineAsync used SyncTextReader's blocking implementation
  and stalled control/completion polling. Changed to a dedicated .NET Task with a
  bound TextReader.ReadLine delegate. Added safe worker stage/type diagnostics.

These failures remain FAIL. Later passing attempts do not rewrite this evidence.

- `tests-20261102T233710Z-aae96c3a.json`: the changed native smoke case PASS;
  aggregate preservation FAIL because eight unrelated canonical files changed
  after the task-entry snapshot. Neither LF nor CRLF normalization explains the
  differences. Their origin is unverified; no engine tool wrote or reverted them.
- `tests-20261102T234037Z-fb968547.json`: full initial engine suite PASS 34/34;
  `tests-20261102T234518Z-73311df2.json`: expanded suite PASS 38/38. Both retain
  the separate full-entry preservation FAIL.
- Final review tightened credential-like request rejection, result-validation
  deadline budgeting and mandatory nonempty well-formed SHA-256 identities.
  Missing/None/empty/malformed expected trust hashes now fail closed.
- `tests-20261102T234813Z-52f6c56b.json`: final implementation PASS 38/38,
  including actual native process exchange/cleanup. Full-entry preservation still
  FAIL for the same eight observations; 21 contract artifacts remain unchanged.
