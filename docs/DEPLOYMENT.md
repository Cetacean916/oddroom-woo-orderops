# Deployment

## Availability model

The selected mode is `ON_DEMAND_HTTPS_TUNNEL` with `ON_DEMAND_ONLY` runtime availability. A pinned nginx ingress terminates the local tunnel target and exposes only the storefront plus `/webhook/oddroom-orderops-v1`. WordPress administration, login, XML-RPC, and the n8n editor remain outside the public route. The public case and evidence remain available independently through the static showcase and repository.

This is a staging delivery model, not an uptime or SLA claim.

## Runtime sequence

1. Materialize protected runtime values outside Git with `scripts/runtime-materialize`.
2. Start the pinned database, WordPress, n8n, task-runner, and nginx services in one dedicated Compose project.
3. Install WordPress and the plugin with `scripts/runtime-wp-install`.
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

## Replacement restore

The completed drill used a new Compose project, new WordPress/database/n8n volumes, a new n8n runtime, and a distinct restore-run identity. Outbound processing began disabled. The workflow credential references were remapped to recreated credential records before publication and activation. After credential smoke checks, one previously absent order key passed creation and payment through the restored webhook; duplicate payment replay converged without a second Slack post. The original outbound components remained stopped and the active runtime designation became exactly `RESTORED`.
