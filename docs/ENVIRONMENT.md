# Environment

## Bootstrap observations

- Docker Engine: `29.6.1`
- Docker Compose: `5.3.1`
- Git: `2.43.0`
- GitHub CLI: `2.45.0`
- WordPress CLI container: `2.12.0`
- n8n Community container selected for project creation: `2.25.7`
- Queue runner mode: `FOREGROUND_WP_CLI`
- Hosting mode: `ON_DEMAND_HTTPS_TUNNEL`
- n8n restore mode: `REPROVISIONED_RESTORE`

## Initialized project runtime

Observed before the first PF07 business action was scheduled:

- WordPress: `7.0.2`
- WooCommerce: `10.9.4`
- PHP: `8.3.32`
- Initialized Action Scheduler: `4.0.0`
- Normalized loaded Action Scheduler source: `plugin:action-scheduler/`
- WordPress database schema: `61833`
- Outbox and order-lease engines: `InnoDB`
- Database clock: UTC with microsecond precision

Compatibility is satisfied: WooCommerce 10.9.4 requires WordPress 6.9 or later and PHP 7.4 or later; Action Scheduler 4.0.0 requires WordPress 6.8 or later and PHP 7.2 or later. The selected versions exceed each minimum.

The isolated argument-aware uniqueness preflight passed against this exact initialized version/source identity. Synthetic row IDs `101` and `102` received distinct non-zero action IDs with one exact pending/in-progress candidate each. A duplicate unique schedule for row `101` returned raw ID `0`, the exact resolver reused the original ID, and cancellation left zero candidates. It inserted or changed no business row and consumed no business attempt or lease. Any loaded version/source change invalidates this result and keeps business scheduling disabled until the preflight passes again.

No system-wide package was installed during bootstrap. Host passwordless sudo is unavailable and is not required by the selected container and user-scope path.
