# M365.EXCHANGE.MAILBOX_SUMMARY (`Get-MailboxSummary.ps1`)

- **Contract Version:** `tnotes.m365 / 0.3.0`
- **Category:** `exchange-online`
- **Risk:** `read_only`
- **Execution Mode:** `isolated_worker`
- **Required Connection:** `ExchangeOnline` (`cmdlet.Get-EXOMailbox`, `cmdlet.Get-EXOMailboxStatistics`)
- **Accepted Target Kinds:** `object_id` (`requires_resolved_identity: true`)
- **Expected Output Schema:** `schemas/operation-data.schema.json#/$defs/mailbox_summary`

## Description

Resolves an Exchange Online mailbox by `ExternalDirectoryObjectId` and retrieves `recipient_type_details`, `primary_smtp_address`, `total_item_size_bytes`, and `prohibit_send_quota_bytes`. Distinguishes `MAILBOX_NOT_FOUND` from `ACCESS_DENIED` and reports `PROPERTY_UNAVAILABLE` partial status when statistics or quota bytes are unavailable.

