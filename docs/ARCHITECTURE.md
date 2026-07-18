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

The on-demand HTTPS route terminates at a pinned nginx ingress. Only the storefront and `/webhook/oddroom-orderops-v1` are routed; WordPress administration and the n8n editor remain private. nginx buffers and caps the raw request before proxying, while n8n verifies HMAC against the unchanged bytes before decoding JSON or reaching any external node.

Every external effect is fenced by the current outbox lock token and serialized by shop and order. Remote identifiers and Slack timestamps are write-once checkpoints. Ambiguous Slack transmission moves the row to protected operator review instead of automatic retry.

## Slack response-loss boundary

Slack is accepted only when `chat.postMessage` returns transport success, `ok: true`, the configured channel, and a non-empty `ts`. A proven failure immediately before the post is retryable from the persisted `slack_pending` phase. If transmission may have occurred but the response cannot establish acceptance or rejection, the row retains its known CRM checkpoints, records `SLACK_OUTCOME_UNKNOWN`, and enters `operator_wait` with no automatic follow-up action. A protected evidence-based resolution is required before any later post attempt.

This design does not eliminate the interval in which Slack may accept a message and the response is lost. It therefore does not claim formally exactly-once Slack delivery.

## Operator resolution and reconciliation

Every transition into `operator_wait` records a reason and increments an epoch. The protected administrator action compares and sets only that current unresolved epoch. It accepts four fixed evidence decisions rather than a free-form status: confirmed posted completes without scheduling; confirmed not posted creates one immediate manual resume; retry after due creates one action at the exact future database time; unresolved retains the wait and zero actions. Stored Contact, Deal, and Slack identifiers remain write-once.

Hourly and manual reconciliation invoke the same seven-day, 50-order-page implementation. It scans orders deterministically without filtering on order creation time, derives creation/payment/cancellation/full-refund events from their own WooCommerce fact timestamps, inserts only a missing immutable snapshot, and uses the normal unique Action Scheduler and order-lease path. It never rewrites an existing payload or invents a cancellation timestamp.

## Fault-control boundary

The third InnoDB table stores staging-only control authorization, not business events. Each control is keyed by protected run, fault type, and the event-key hash. Authorization requires `enabled=1` and database-UTC `expires_at` in the future at the instant of use. Cleanup is defense in depth; expiration itself is authoritative. The end-run transaction disables every control for the run and bounds all expiry times to the same database clock.

## Storefront boundary

The plugin supplies the OddRoom storefront composition without changing the read-only OddRoom reuse source or the active block theme. WooCommerce retains product, cart, checkout, account, and order semantics. The staging setup exposes two buyer-facing synthetic products and keeps integration fixtures hidden from the catalog, sets `noindex`, captures rather than sends transactional mail, rate-limits checkout, and offers only a relabelled no-funds synthetic gateway. Storefront activity can create real staging domain facts but cannot collect funds.
