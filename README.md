# OddRoom Woo OrderOps

OddRoom Woo OrderOps is a recoverable WooCommerce order-operations integration. A custom WordPress plugin captures immutable order events, serializes delivery per order, and sends signed requests through a dedicated n8n adapter to HubSpot and Slack.

This repository is built from a separate non-Git implementation source by a deny-by-default public builder. It contains synthetic fixtures and public-safe evidence only. Protected raw evidence, credentials, runtime state, backups, and owner-machine paths are excluded.

## Current implementation order

1. Bootstrap the source-driven public builder and CI.
2. Deliver and prove the `ORDER_CREATED` vertical slice.
3. Add the complete four-event CRM and Slack lifecycle.
4. Add bounded retry, operator resolution, reconciliation, product surfaces, restore, and public evidence.

The project is complete only when the active PF07 contract records `FINAL_PASS`. A local tree, private CI run, or public repository does not by itself establish completion.

## Local checks

```bash
./scripts/ci
./scripts/validate-public --pre-public
```

## Claims boundary

This staging project uses synthetic data and a non-monetary checkout path. It does not claim production scale, real payment processing, formal exactly-once delivery, or elimination of the Slack accepted/response-lost window.

