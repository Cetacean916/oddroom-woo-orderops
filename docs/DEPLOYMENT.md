# Deployment

## Availability model

The selected mode is `ON_DEMAND_HTTPS_TUNNEL` with `ON_DEMAND_ONLY` runtime availability. A pinned nginx ingress terminates the local tunnel target and exposes only the storefront plus `/webhook/oddroom-orderops-v1`. WordPress administration, login, XML-RPC, and the n8n editor remain outside the public route. The public case and evidence remain available independently through the static showcase and repository.

This is a staging delivery model, not an uptime or SLA claim.

## Runtime sequence

1. Materialize protected runtime values outside Git with `scripts/runtime-materialize`.
2. Start the pinned database, WordPress, n8n, task-runner, and nginx services in one dedicated Compose project.
3. Install WordPress and the plugin with `scripts/runtime-wp-install <COMPOSE_PROJECT>`; it pins the selected WooCommerce currency to `KRW` and the decimal precision to exactly `2` before plugin activation.
4. Recreate n8n credential records from protected locators with `scripts/runtime-import-credentials`, import the credential-free workflow, and publish that exact workflow.
5. Run the Action Scheduler version/source preflight before any business row is scheduled.
6. Verify HubSpot and Slack credentials with no-business-effect smoke probes.
7. Start the foreground WP-CLI queue runner only after the webhook and credentials pass.
8. Start the authenticated HTTPS tunnel to the loopback-bound nginx port when an observation window is required.

Every container image in `infra/compose.yaml` is digest-pinned. Host ports are parameterized so an original, compatibility, and replacement-restore project cannot collide.

## Public route controls

- nginx buffers the raw body and rejects more than 262144 bytes before n8n execution.
- n8n verifies the timestamped HMAC over the unchanged bytes before JSON decoding or any external node.
- The storefront sends `noindex` and uses a no-funds synthetic checkout method.
- Runtime secrets and account identifiers stay in protected files or n8n credential storage; they are not Compose defaults, workflow literals, evidence-public values, or Git content.

## Private administrator observation

The direct WordPress host port is bound to loopback only and is not part of the public tunnel. The official browser suite uses that loopback origin for login and administrator observations and sends `X-OddRoom-Private-Admin: loopback`. The plugin accepts this mode only when the request host is `127.0.0.1`, `localhost`, or `[::1]`; it then rewrites WordPress-generated canonical URLs to the current loopback origin for that request.

The public nginx route independently strips the private-observation header and returns `404` for `/wp-admin`, `/wp-login.php`, and XML-RPC. Do not publish, tunnel, or bind the direct WordPress port beyond loopback.

Run the complete storefront and administrator browser suite with protected aliases rather than literal credentials:

```bash
PF07_BASE_URL=<STAGING_URL> \
PF07_ADMIN_BASE_URL=http://127.0.0.1:<LOOPBACK_WORDPRESS_PORT> \
PF07_ADMIN_USER=<SYNTHETIC_ADMIN_ALIAS> \
PF07_ADMIN_PASSWORD_FILE=<PROTECTED_SECRET_FILE> \
./scripts/validate-ui
```

## Replacement restore

The completed drill used `scripts/probe-clean-restore` with a zero-resource Compose project, new WordPress/database/n8n volumes, a new n8n runtime, and a distinct restore-run identity. Outbound processing began disabled. The workflow credential references were remapped to two recreated credential records before publication and activation, and the n8n runtime was restarted to register that published webhook before WordPress was started. After direct HubSpot and Slack credential smokes, one previously absent order key passed creation and payment through the restored webhook; duplicate payment replay produced zero additional n8n executions, Slack posts, or Deals. The original outbound components remained stopped, its execution counter did not change, HTTPS returned `200` with normal TLS verification, and the active runtime designation became exactly `RESTORED`.
