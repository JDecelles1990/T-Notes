# M365.ENTRA.USER_SIGNINS (`Get-UserSignIns.ps1`)

- **Contract Version:** `tnotes.m365 / 0.3.0`
- **Category:** `entra-id`
- **Risk:** `read_only`
- **Execution Mode:** `isolated_worker`
- **Required Connection:** `Graph` (`AuditLog.Read.All`, role `Reports.Reader`)
- **Accepted Target Kinds:** `object_id` (`requires_resolved_identity: true`)
- **Parameters:** `LookbackDays` (1–30, default 7), `MaxRecords` (1–50, default 20)
- **Expected Output Schema:** `schemas/operation-data.schema.json#/$defs/user_signins`

## Description

Queries bounded recent Entra ID sign-in events for a resolved user `object_id` using a fixed OData filter over `userId` and `createdDateTime`. Excludes IP/location/Conditional Access payloads for privacy and reports `OUTPUT_LIMIT` partial truncation when `MaxRecords` is reached.

