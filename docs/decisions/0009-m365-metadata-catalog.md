# ADR 0009 — M365 presentation registry and provisional catalog validation

- Date: 2026-11-02
- Status: implemented candidate; independent review pending
- Scope: categories, library conventions and read-only operation presentation

## Decision

Keep exactly fourteen flat categories in application-owned JSON with stable IDs.
Keep executable manifests in a separately owned script library and reference one
authoritative manifest per operation from an explicit presentation index. Do not
derive trust from folder/category membership or discover arbitrary dropped files.
Use a service boundary and frozen presentation records; Qt widgets never parse
manifests or dispatch operations. Reject invalid metadata and show valid unapproved
metadata only as unavailable. The shipped production index is empty.

Use the existing proposed 0.3.0-proposed.1 manifest schemas without modification.
Add `jsonschema>=4.23,<5` for Draft 2020-12 validation using its local registry API,
with seven hash-bound schema inputs and no network resolver. Maintain semantic
descriptor/service checks beyond schema shape. The review pins establish input
identity only and cannot approve the provisional contract or any executable.
No dependency is installed by the application at runtime.

## Consequences

Future operations can be registered without GUI edits. General/Other classification
and one-to-many display references are explicit. Empty categories accurately show
that no approved operations exist. Dashboard/Companies retain navigation views;
workflow orchestration and non-Graph/Exchange service contracts remain future work.
Production execution requires a separately authorized application adapter, external
release trust, runtime/context/permission/target checks and explicit intent.

The script tree currently contains only a README. Catalog validation and tests do
not adopt the offline prototype, authenticate, access tenants, migrate SQLite or
alter Notes persistence/shortcuts. See [the domain guide](../features/m365-catalog.md)
and [review checkpoint](../reviews/m365-category-architecture-20261102/CHECKPOINT.md).
