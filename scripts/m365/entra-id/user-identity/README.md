# M365.ENTRA.USER_IDENTITY (`Get-UserIdentity.ps1`)

- **Contract Version:** `tnotes.m365 / 0.3.0`
- **Category:** `entra-id`
- **Risk:** `read_only`
- **Execution Mode:** `isolated_worker`
- **Required Connection:** `Graph` (`User.Read.All`)
- **Accepted Target Kinds:** `upn`, `object_id`
- **Expected Output Schema:** `schemas/operation-data.schema.json#/$defs/user_identity`

## Description

Resolves a single Entra ID user identity by normalized UPN or object UUID, verifying canonical identity binding (`id` and `user_principal_name`) and returning `display_name`, `account_enabled`, and `user_type`. Supports both mocked `Get-MgUser` cmdlet evaluation and deterministic offline synthetic evaluation without live tenant connections.
