# Microsoft 365 operation library

This is the reserved root for reviewed M365 operations. It currently contains
documentation only. There are no administrative scripts or executable examples.
The GUI's production operation registry is empty.

An operation owner will add one directory only when authorized content exists:

```text
scripts/m365/<primary-category-id>/<operation-slug>/
  <Verb>-<Noun>.ps1
  operation.manifest.json
  README.md
```

The permitted primary folder IDs are `general`, `entra-id`, `exchange-online`,
`licensing`, `teams`, `sharepoint`, `onedrive`, `intune`, `security`, `reports`,
and `other`. Do not create empty folders for symmetry. Dashboard and Companies
are application views. Future declarative workflows belong in an independently
approved `workflows/m365/<workflow-id>.json` design; no workflow schema or runner
is introduced here.

Use a lowercase kebab-case operation slug and a reviewed PowerShell Verb-Noun
filename. Assign a stable `M365.<SERVICE>.<OPERATION>` ID, independent of the
filename, title and navigation labels. Keep one implementation and one manifest;
additional category references never copy the script.

Paths in manifests resolve from **this library root**. For example, a future
script_path has the shape `<primary-category-id>/<operation-slug>/<Verb>-<Noun>.ps1`.
Registry manifest_path also resolves from this root. Output schema references
resolve from the separately reviewed contract root, never from the script folder.

Operation owners maintain their implementation, manifest, documentation, Pester
tests and synthetic fixtures. The application owner maintains category metadata,
registration validation and GUI services. Shared schema changes require separate
contract authority. Operation tests will live under
`tests/powershell/m365/<operation-id>/`; synthetic data under
`tests/fixtures/m365/<operation-id>/`. These future directories are created with
their first real content. Current Python catalog fixtures live in
`tests/fixtures/m365/` and supply no script or trust approval.

See [catalog architecture and registration](../../docs/features/m365-catalog.md)
for ownership, validation, retirement and approval requirements. The governing
contract and offline engine remain provisional and disconnected from this GUI.
