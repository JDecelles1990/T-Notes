# M365 categories and operation registration

The [company directory and identity preview](m365-company-directory.md) adds
session-only company and multiple administrator metadata, company confirmation,
separate synthetic Graph/Exchange states and client target input. It does not alter
the fourteen categories, provisional catalog pins, empty production registry or
execution prohibition. S1 now binds catalog validation to official v0.3.0;
the engine candidate remains disconnected and awaits independent review.

Status: category architecture candidate for independent review. The production
operation registry is empty. Contract compatibility targets
`tnotes.m365 / 0.3.0`, explicitly accepted by the user for S1 development on
2026-11-03 with the final contract independent-signoff limitation retained.
The S1 implementation is **not independently approved**. See
[S1 engine migration](m365-s1-engine.md) for authority and test boundaries.

## Taxonomy

The ordered source is `assets/m365/categories.json`. Stable IDs, labels,
descriptions, emoji/text icons, order and view kind are presentation data.
All fourteen entries are visible; no subcategories or Personal entry exist.

| ID | Label | Responsibility |
|---|---|---|
| dashboard | Dashboard | Status, shortcuts, recent activity, service overviews |
| companies | Companies | Company selection and verified tenant/connection context |
| general | General | Common reusable diagnostics across services |
| entra-id | Entra ID | Users, authentication, groups, apps, directory roles |
| exchange-online | Exchange Online | Mailboxes, mail flow, delegates and permissions |
| licensing | Licensing | Subscriptions, assignments, plans and usage |
| teams | Teams | Memberships, policies, meetings and diagnostics |
| sharepoint | SharePoint | Sites, sharing, storage and permissions |
| onedrive | OneDrive | User storage, sync information, sharing and permissions |
| intune | Intune | Devices, enrollment, compliance and configuration |
| security | Security | Defender, Purview, DLP, retention and sensitivity labels |
| reports | Reports | Read-only audits, exports and historical reports |
| workflows | Workflows | Guided orchestration with per-operation validation |
| other | Other | Approved miscellaneous M365 utilities without a suitable home |

Prefer a specific service category. Use General for frequently useful diagnostics
that span services; use Other only after review establishes that no primary
category fits. Reports is for report generation/audits; Workflows is for approved
multi-step orchestration. Local Windows and personal utilities stay outside this
library. Unknown or corrupt registrations are rejected; there is no fallback to
Other. Multiple category references point to one authoritative manifest.

## Registry and GUI boundary

`M365LauncherWidget` reads immutable presentation snapshots exclusively through
`M365CatalogService`. Navigation stores category IDs in Qt.UserRole and operation
lists store script IDs. Labels and icons never select executable paths. The
existing collapsible splitters and one/two-column reflow remain; viewport resizing,
including sidebar collapse, recalculates columns. The catalog is vertically
scrollable in narrow windows and keeps focusable navigation, named search/filter
controls, and selectable read-only plain-text details. Metadata cannot render HTML.

Dashboard retains a disconnected overview; Companies retains a company/context
view. Each service category shows its description, metadata list or useful empty
state. Search matches all entered words across title, description, script ID,
tags, categories, services, risk and module names. Risk filters and lifecycle
filters combine with search. Deprecated entries remain inspectable and unavailable;
archived entries require the archived/all filter. Search/filter state survives
category and workspace changes; details clear when selection disappears.

No Run control, dispatch signal, subprocess import, engine import, authentication,
tenant access, note insertion or second editable notes owner is introduced.
The remaining parameter, execution, result and ticket panels are explicitly
unimplemented placeholders. Existing Notes ownership and Alt+F8 routing are unchanged.

## File ownership and registration

Library layout/naming and future test directories are defined in
[the library README](../../scripts/m365/README.md). Application-owned
`assets/m365/catalog.json` is a presentation index, **not a script manifest or a
release trust anchor**. Its local format is:

```text
format_version: 1
operations: list of {
  manifest_path: canonical relative path below scripts/m365,
  manifest_sha256: exact raw manifest review identity,
  category_ids: ordered unique category IDs (primary first),
  lifecycle: active | deprecated | archived
}
```

No operation definitions, approval flags, permissions or executable commands are
embedded in that index. Each referenced manifest follows the existing contract
schema without extension. For newly authored manifests the contract's free-text
`category` field contains the primary stable category ID. Optional contract
subcategory metadata does not create nested navigation. Old proposal display
labels are not automatically mapped or rewritten; an explicitly reviewed manifest
must choose its primary ID. Dashboard/Companies and Workflows cannot register
PowerShell operations in this index. Declarative workflow registration is a future
separate contract decision.

Future registration procedure:

1. Obtain explicit task, approved architecture/contract and exact release review
   inputs. Follow root GEMINI.md for any operation implementation. The current
   catalog does not authorize creating or running scripts.
2. Assign a unique stable script ID and primary category. Add one implementation,
   co-located `operation.manifest.json`, README, Pester tests and synthetic fixtures.
3. Declare all contract-required script/version/SHA identity, PS7 and module
   dependencies, target policy, service connections, Graph scopes, service-qualified
   RBAC, parameters, result schema, risk, sensitivity and approval requirements.
4. Review the implementation, manifests, required modules, output schema and
   dependencies together. Establish approval in an external owner-approved release
   inventory. Manifest hashes and category membership never approve executable bytes.
5. Add an explicit presentation-index reference with raw manifest hash and primary
   category first; add optional secondary references without copying implementation.
   Validate the complete candidate and independently review it. No GUI edit is needed.
6. Execution remains unavailable until separately authorized adapter, external trust,
   target, tenant/account/service, RBAC and confirmation gates are implemented and
   revalidated at dispatch. This service never computes positive execution eligibility.

For retirement, set lifecycle to deprecated/archived; preserve historical version
and release evidence. Archives disappear from the default current filter. Changing
versions or script bytes requires fresh manifest/release review. Removing a
registration removes it from presentation; historical evidence is not deleted.

## Validation responsibility and limits

The service bounds JSON reads (64 KiB registry/manifest, 256 KiB per schema), rejects
duplicate keys, BOM, nonfinite numbers, excessive nesting, invalid category fields,
duplicate category IDs/orders/labels, unknown references and conflicting script IDs.
Every conflicting valid script ID is quarantined. Manifest paths must be canonical,
contained and free of symlink/reparse ancestors. Discovery reads only explicit
index references and never scans/imports scripts.

For nonempty indexes, `ManifestValidator` loads all seven **existing** Draft 2020-12
schemas from `docs/contracts/m365/`. `contract-review-pins.json` binds their raw
hashes for compatibility review; it is explicitly not approval. A nonempty index
fails closed if schemas/pins are unavailable or changed. The empty production
index does not require schema loading to start the application.

JSON Schema validation uses `jsonschema` with a local `referencing.Registry` and
no retrieval callback, following the library's
[local registry guidance](https://github.com/python-jsonschema/jsonschema/blob/main/docs/referencing.rst).
Unknown references cannot trigger network retrieval. Additional semantic checks
cover target output fields, required service/RBAC consistency, reserved and
case-insensitive parameter names, numeric/string/array bounds, exact default/enum
types and values. Output definitions are resolved through the local shared schema
references. Invalid manifests create no operation item; a safe catalog warning
reports rejected metadata. Valid unapproved metadata can be inspected as
Unavailable, with contract, trust, context/permission and disconnected-engine reasons.

This is a compatibility/presentation validator, not executable trust validation.
It does not open/hash scripts or modules, approve schemas, verify ACLs or mitigate
execution-time check/use races. Future release validation must pin every dependency,
verify actual runtime/module compatibility and owned tenant/service state, then
recheck at dispatch. Connection requirements currently support only the proposed
Graph and ExchangeOnline values; other service adapters need explicit contract
review. General does not invent tenant-wide target semantics: this proposal still
requires UPN/object-ID target policies. No incompatible operation types are fabricated.

## Future integration and references

Authorized future boundary:

```text
GUI -> application service -> catalog / eligibility
    -> separately approved Python adapter -> trusted PowerShell operation
```

The offline engine stays entirely disconnected. Future execution must run outside
the Qt main loop and separately establish external trust, runtime, immutable release
binding, verified target/context/connections, scopes, effective RBAC and explicit
authorization. Presentation metadata, favorites or a workflow cannot bypass gates.

- [Official implementation contract](../contracts/m365/CONTRACT.md)
- [Preserved predecessor proposal](../planning/m365/03_codex_reviews/architecture-contract-proposal-20261102/CONTRACT.md)
- [Correction handoff](../planning/m365/03_codex_reviews/architecture-contract-proposal-20261102/CONTRACT_CORRECTION_HANDOFF.md)
- [Offline engine](../planning/m365/offline-execution-engine-prototype/README.md)
- [Engine checkpoint](../planning/m365/offline-execution-engine-prototype/ENGINE_CHECKPOINT.md)
- [Category architecture decision](../decisions/0009-m365-metadata-catalog.md)
- [Review checkpoint and actual test evidence](../reviews/m365-category-architecture-20261102/CHECKPOINT.md)
