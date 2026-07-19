# OddRoom Woo OrderOps

OddRoom Woo OrderOps is a recoverable WooCommerce order-operations integration. A custom WordPress plugin captures immutable order events, serializes delivery per order, and sends signed requests through a dedicated n8n adapter to HubSpot and Slack.

This repository is built from a separate non-Git implementation source by a deny-by-default public builder. It contains synthetic fixtures and public-safe evidence only. Protected raw evidence, credentials, runtime state, backups, and owner-machine paths are excluded.

## Delivered system

The protected acceptance run exercised the complete four-event path and its recovery boundaries:

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
- An authenticated on-demand HTTPS route exposed only the storefront and the exact signed webhook. WordPress administration and the n8n editor remained private; a 262145-byte chunked request was rejected at ingress before workflow execution.
- Dependency, activation, HPOS-off/on, migration, data-preserving uninstall, opt-in removal, and every required Action Scheduler failure branch were exercised in an isolated compatibility runtime.
- A quiesced formal backup was restored into a separate Compose project with fresh WordPress, database, application, and n8n volumes. Recreated HubSpot and Slack credentials passed smoke checks; one new restored order converged on one Deal and one payment notification, and duplicate replay produced no second notification.

The public case, exact proof scorecard, architecture, and claim boundaries are in [case-study/README.md](case-study/README.md). Public machine evidence is indexed by [evidence/public/acceptance-matrix.json](evidence/public/acceptance-matrix.json). Protected raw records, account identifiers, runtime state, backups, and credentials are deliberately absent from this repository.

## Local checks

```bash
./scripts/ci
./scripts/validate-public --pre-public
```

After the repository becomes public, an unauthenticated clone can establish the repository-only release state without depending on the separately deployed showcase. Once that showcase is live, the final mode also checks its case data, media, and browser-quality suite:

```bash
./scripts/validate-public --repository-public
./scripts/validate-public --post-public
```

The protected source owner can additionally validate raw-to-public lineage with:

```bash
./scripts/validate-all --pre-public
./scripts/validate-all --final
```

`validate-public` never reads protected raw evidence. `validate-all` is intentionally local-only and is not invoked by public CI.

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

This staging project uses synthetic data and a non-monetary checkout path. The runtime is available on demand, while the static public case is persistent. It does not claim production scale, real payment processing, formal exactly-once delivery, or elimination of the Slack accepted/response-lost window. See [docs/CLAIMS-BOUNDARY.md](docs/CLAIMS-BOUNDARY.md) for the complete boundary.
