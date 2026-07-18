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

The exact initialized WordPress, WooCommerce, PHP, Action Scheduler version and loaded-source identity remain intentionally unclaimed until the project runtime exists. They must be recorded and pass the argument-aware uniqueness preflight before the first PF07 business action is scheduled.

No system-wide package was installed during bootstrap. Host passwordless sudo is unavailable and is not required by the selected container and user-scope path.

