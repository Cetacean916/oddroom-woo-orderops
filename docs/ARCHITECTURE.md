# Architecture

```text
WooCommerce order fact
  -> immutable WordPress outbox snapshot
  -> Action Scheduler action with exact row identity
  -> row claim and order-scoped lease
  -> exact-byte HMAC request
  -> dedicated n8n webhook adapter
  -> monotonic HubSpot Contact/Deal state
  -> guarded Slack notification
  -> validated checkpoints in the outbox row
```

WordPress owns retry and recovery state. n8n has no independent retry loop. The outbox is the only business delivery ledger, while the order lease table stores coordination state only.

Every external effect is fenced by the current outbox lock token and serialized by shop and order. Remote identifiers and Slack timestamps are write-once checkpoints. Ambiguous Slack transmission moves the row to protected operator review instead of automatic retry.

