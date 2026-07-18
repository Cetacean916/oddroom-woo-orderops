# OddRoom Woo OrderOps

OddRoom Woo OrderOps is a recoverable WooCommerce order-operations integration. A custom WordPress plugin captures immutable order events, serializes delivery per order, and sends signed requests through a dedicated n8n adapter to HubSpot and Slack.

This repository is built from a separate non-Git implementation source by a deny-by-default public builder. It contains synthetic fixtures and public-safe evidence only. Protected raw evidence, credentials, runtime state, backups, and owner-machine paths are excluded.

## Ordered delivery state

1. Source-driven public builder, private CI, and the `ORDER_CREATED` vertical slice: implemented and observed.
2. Complete four-event CRM/Slack lifecycle and bounded recovery: implemented and observed in protected staging.
3. Operator resolution, reconciliation, fault controls, and minimum OddRoom storefront: implemented and observed in protected staging.
4. Security/compatibility closure, HTTPS replacement restore, public evidence/case, repository publication, and showcase release: still ordered work.

The project is complete only when the active PF07 contract records `FINAL_PASS`. A local tree, private CI run, or public repository does not by itself establish completion.

## Implemented through STEP-070

The protected staging acceptance run has reached `VSL_PASS` for `ORDER_CREATED`:

- WooCommerce creates immutable, hash-checked outbox snapshots.
- Action Scheduler 4.0.0 passes the isolated argument-aware uniqueness preflight before business scheduling.
- A database row claim and order-scoped InnoDB lease fence concurrent workers.
- WordPress signs the exact stored bytes and a dedicated n8n 2.25.7 adapter verifies the raw body before side effects.
- n8n uses only fixed HubSpot `2026-03` HTTP endpoints for Deal comparison/upsert/read-back, full-set email Contact upsert/read-back, and default Contact-Deal association/read-back.
- WordPress persists returned Contact, Deal, phase, Slack status, and Slack `ts` checkpoints under the row fencing token.
- Endpoint outage retains the immutable snapshot and bounded retry state; the foreground WP-CLI runner recovers without an administrator page load.
- Actual synthetic `PAYMENT_CONFIRMED`, `ORDER_CANCELLED`, and full `ORDER_REFUNDED` facts each follow the guarded CRM path and issue at most one `chat.postMessage` call per adapter execution.
- A deterministic pre-post failure retains the same immutable payload and CRM checkpoints; the due retry resumes at `slack_pending` and converges on one accepted Slack message.
- Protected Resolve Outcome supports only `CONFIRMED_POSTED`, `CONFIRMED_NOT_POSTED`, `RETRY_AFTER_DUE`, and `UNRESOLVED`, bound to the current unresolved epoch. Generic retry cannot bypass `operator_wait`.
- Seven-day, 50-order reconciliation derives expected events only from WooCommerce fact times. Controlled insert and schedule suppression fixtures were repaired on the first scan and became no-ops on the second.
- Staging-only fault controls are tied to the protected run, expire by database UTC within 30 minutes, and can be disabled together by the protected end-run transaction.
- The administrator surface provides deterministic filters, sorting, 50-row pagination, contained table overflow, masked identifiers, protected reveal/actions, and passed an isolated 500-row usability observation.
- The OddRoom storefront includes a branded home, shop, simple product, two-variation product, coupon, cart, checkout, and account surface. Staging is `noindex`; outbound mail is captured; checkout exposes only a relabelled no-funds synthetic method.
- Playwright 1.61.1 and axe-core 4.12.1 passed 18 full-document storefront observations and three scoped administrator observations across 390, 768, and 1440 CSS pixels with zero serious/critical violations, page overflow, broken assets, clipped actions, or console errors.

This remains a staging milestone, not final project completion. Security/compatibility closure, HTTPS deployment, clean replacement restore, public evidence, public case deployment, repository visibility change, showcase integration, and final release gates remain ordered work.

## Local checks

```bash
./scripts/ci
./scripts/validate-public --pre-public
```

With the protected staging runtime available, the pinned browser suite is:

```bash
PF07_BASE_URL=<STAGING_URL> \
PF07_ADMIN_USER=<SYNTHETIC_ADMIN_ALIAS> \
PF07_ADMIN_PASSWORD_FILE=<PROTECTED_SECRET_FILE> \
./scripts/validate-ui
```

During an authorized on-demand acceptance window, the foreground queue process is:

```bash
./scripts/queue-runner --loop
```

## Claims boundary

This staging project uses synthetic data and a non-monetary checkout path. It does not claim production scale, real payment processing, formal exactly-once delivery, or elimination of the Slack accepted/response-lost window.
