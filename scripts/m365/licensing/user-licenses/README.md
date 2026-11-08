# M365.ENTRA.USER_LICENSES (`Get-UserLicenses.ps1`)

- **Contract Version:** `tnotes.m365 / 0.3.0`
- **Category:** `licensing`
- **Risk:** `read_only`
- **Execution Mode:** `isolated_worker`
- **Required Connection:** `Graph` (`LicenseAssignment.Read.All`, role `Directory.Readers`)
- **Accepted Target Kinds:** `object_id` (`requires_resolved_identity: true`)
- **Expected Output Schema:** `schemas/operation-data.schema.json#/$defs/user_licenses`

## Description

Retrieves assigned Microsoft 365 SKU licenses and service plan provisioning states for a resolved Entra user `object_id`. Supports both mocked `Get-MgUserLicenseDetail` cmdlet evaluation and deterministic offline synthetic evaluation.

