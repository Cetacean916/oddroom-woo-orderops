# OddRoom Woo OrderOps

OddRoom Woo OrderOps is a recoverable WooCommerce order-operations integration. A custom WordPress plugin captures immutable order events, serializes delivery per order, and sends signed requests through a dedicated n8n adapter to HubSpot and Slack.

This repository is built from a separate non-Git implementation source by a deny-by-default public builder. It contains synthetic fixtures and public-safe evidence only. Protected raw evidence, credentials, runtime state, backups, and owner-machine paths are excluded.

## Current implementation order

1. Bootstrap the source-driven public builder and CI.
2. Deliver and prove the `ORDER_CREATED` vertical slice.
3. Add the complete four-event CRM and Slack lifecycle.
4. Add bounded retry, operator resolution, reconciliation, product surfaces, restore, and public evidence.

The project is complete only when the active PF07 contract records `FINAL_PASS`. A local tree, private CI run, or public repository does not by itself establish completion.

## Vertical slice status

The protected staging acceptance run has reached `VSL_PASS` for `ORDER_CREATED`:

- WooCommerce creates immutable, hash-checked outbox snapshots.
- Action Scheduler 4.0.0 passes the isolated argument-aware uniqueness preflight before business scheduling.
- A database row claim and order-scoped InnoDB lease fence concurrent workers.
- WordPress signs the exact stored bytes and a dedicated n8n 2.25.7 adapter verifies the raw body before side effects.
- n8n uses only fixed HubSpot `2026-03` Deal batch read/upsert endpoints for this slice.
- WordPress persists the returned Deal checkpoint and complete envelope under the row fencing token.
- Endpoint outage retains the immutable snapshot and bounded retry state; the foreground WP-CLI runner recovers without an administrator page load.

This is a milestone, not final project completion. Contact association, the remaining event types, Slack, full reconciliation/operator controls, clean restore, public case deployment, and release gates remain later ordered work.

## Local checks

```bash
./scripts/ci
./scripts/validate-public --pre-public
```

During an authorized on-demand acceptance window, the foreground queue process is:

```bash
./scripts/queue-runner --loop
```

## Claims boundary

This staging project uses synthetic data and a non-monetary checkout path. It does not claim production scale, real payment processing, formal exactly-once delivery, or elimination of the Slack accepted/response-lost window.
