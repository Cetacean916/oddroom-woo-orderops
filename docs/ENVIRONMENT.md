# Environment

## Bootstrap observations

- Docker Engine: `29.6.1`
- Docker Compose: `5.3.1`
- Git: `2.43.0`
- GitHub CLI: `2.45.0`
- WordPress CLI container: `2.12.0`
- n8n Community container selected for project creation: `2.25.7`
- nginx staging ingress image: `nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`
- ngrok agent: `3.39.9`, installed in the owner user executable path because host passwordless sudo is unavailable
- Queue runner mode: `FOREGROUND_WP_CLI`
- Hosting mode: `ON_DEMAND_HTTPS_TUNNEL`
- n8n restore mode: `REPROVISIONED_RESTORE`

The ingress exposes the storefront and the exact production webhook only. It keeps WordPress administration and the n8n editor off the public route, forwards the observed HTTPS scheme, and rejects request bodies above `262144` bytes before n8n executes. Host ports are parameterized so the original, compatibility, and restored Compose projects cannot collide.

## Initialized project runtime

Observed before the first PF07 business action was scheduled:

- WordPress: `7.0.2`
- WooCommerce: `10.9.4`
- PHP: `8.3.32`
- Initialized Action Scheduler: `4.0.0`
- Normalized loaded Action Scheduler source: `plugin:action-scheduler/`
- WordPress database schema: `61833`
- Outbox, order-lease, and fault-control engines: `InnoDB`
- Database clock: UTC with microsecond precision

Compatibility is satisfied: WooCommerce 10.9.4 requires WordPress 6.9 or later and PHP 7.4 or later; Action Scheduler 4.0.0 requires WordPress 6.8 or later and PHP 7.2 or later. The selected versions exceed each minimum.

The isolated argument-aware uniqueness preflight passed against this exact initialized version/source identity. Synthetic row IDs `101` and `102` received distinct non-zero action IDs with one exact pending/in-progress candidate each. A duplicate unique schedule for row `101` returned raw ID `0`, the exact resolver reused the original ID, and cancellation left zero candidates. It inserted or changed no business row and consumed no business attempt or lease. Any loaded version/source change invalidates this result and keeps business scheduling disabled until the preflight passes again.

No system-wide package was installed during bootstrap. Host passwordless sudo is unavailable and is not required by the selected container and user-scope path.

## Browser and accessibility validation pin

- Browser driver: Playwright `1.61.1`
- Browser executable: host Google Chrome, with its exact observed version recorded in each evidence run
- Accessibility engine and ruleset: axe-core `4.12.1`, default WCAG-impact rules
- Public/storefront mode: `full_document`
- PF07 administrator mode: `scoped`, root selector `.oddroom-orderops`, including every PF07-owned notice, details/action surface, and table inside that root
- Required viewports: `390`, `768`, and `1440` CSS pixels
- Failure threshold: zero `critical` or `serious` violations; no manual PF07-introduced reclassification

The validation also records document `scrollWidth` versus `clientWidth`, broken image responses, clipped primary actions, console errors, and keyboard reachability. The intentionally wide administrator data table must scroll only inside `.oddroom-table-wrap`; page-level horizontal overflow remains a failure.
