# Recovery Runbook

## Start with the row state

Use the protected WordPress event table or WP-CLI to identify a masked event alias, status, processing phase, attempt counters, dispatch state, next attempt, and current error. Never reconstruct the event body from current order data: retries must send the stored immutable bytes.

## Retryable outage

For a proven retryable failure, confirm that the row is `retry_wait`, its automatic counter is no greater than six, and the next delay follows `2, 5, 10, 20, 30` seconds after attempts one through five. The sixth automatic failure is terminal `ATTEMPTS_EXHAUSTED` and has no follow-up action. A manual attempt increments the manual counter but never resets or disguises the automatic counter.

## Stale lease

Recovery may clear only the exact expired row and order fencing tokens. If dispatch never started, it preserves consumed counters and schedules at most one same-row action after commit. A second sweep must be a no-op. If dispatch was `in_flight` for a Slack-producing event, recovery must move the row to `operator_wait/SLACK_OUTCOME_UNKNOWN` and schedule nothing.

## Ambiguous Slack outcome

Generic retry is forbidden while the unresolved operator epoch is open. Review the complete attempt-linked trace and remotely verified CRM state, then choose one protected decision:

- `CONFIRMED_POSTED(ts)` stores the verified timestamp and completes without another action.
- `CONFIRMED_NOT_POSTED` resumes once from the last verified safe phase.
- `RETRY_AFTER_DUE` schedules one manual action at the evidenced due time, never earlier.
- `UNRESOLVED` retains the wait and zero actions.

Repeating the same completed decision is a no-op; a conflicting second decision is `CHECKPOINT_CONFLICT`.

## Missed hook or missing action

Run the same reconciliation path used by the hourly job. It derives facts from WooCommerce creation, payment, protected first-cancellation, or full-refund times. The first scan inserts a missing immutable row or restores one missing eligible action. The second scan must not mutate the payload or create another row/action.

## End an acceptance run

Use the protected end-run action before declaring the run ended. It disables every run-scoped fault control in one database-UTC transaction. Confirm zero pending/running PF07 actions, zero active leases, zero enabled unexpired controls, and zero running PF07 n8n executions before a final backup or restore snapshot.

## Execute the replacement restore drill

Create a new runtime root and a UUIDv4 restore-run identity, materialize it from the canonical protected readiness file, and select a Compose project name with no existing containers, volumes, or network. Keep the verified formal backup outside both runtime roots. Then run the exact destructive staging probe with protected path aliases:

`wordpress-database.sql` must be a dump of the WordPress application database only. Do not include `mysql`, `sys`, `performance_schema`, account tables, or `CREATE DATABASE`/`USE` statements. The restore imports into the fresh runtime's configured application database, verifies both fresh root and application credentials, restarts MariaDB, and requires a healthy post-restart service before n8n or WordPress processing can start.

The caller may retain the acceptance `RUN_ID` for evidence correlation, but no inherited runtime secret or database setting may override either Compose project's own protected `runtime.env`. The restore probe rebinds each Compose call to the selected root's exact environment and switches the probe process to the replacement environment before target helper scripts or event processing run.

Because a repeated drill can restore the same local next-order sequence after an earlier synthetic attempt already created a remote Deal, order selection checks the exact HubSpot order key before any restored action runs. A colliding synthetic candidate is canceled and removed only from the new local runtime, with zero n8n, HubSpot, or Slack call, and selection advances within a fixed 20-candidate bound. The selected candidate must have zero preexisting Deals before its created/payment flow begins.

```bash
PF07_RUNTIME_ROOT=<NEW_RUNTIME_ROOT> \
PF07_COMPOSE_PROJECT=<NEW_COMPOSE_PROJECT> \
PF07_ORIGINAL_RUNTIME_ROOT=<ACTIVE_RUNTIME_ROOT> \
PF07_ORIGINAL_COMPOSE_PROJECT=<ACTIVE_COMPOSE_PROJECT> \
PF07_BACKUP_DIR=<VERIFIED_FORMAL_BACKUP> \
PF07_READINESS_FILE=<CANONICAL_READINESS_JSON> \
PF07_EVIDENCE_OUTPUT_DIR=<PROTECTED_RUN_ARTIFACT_DIR> \
PF07_SCRATCH_ROOT=<OWNER_SCRATCH_ROOT> \
scripts/probe-clean-restore
```

The probe refuses a non-empty target project. It rechecks WordPress and n8n quiescence, stops every original service before creating the replacement, restores fresh WordPress/database volumes, reprovisions a fresh n8n owner/workflow/credential set, restarts n8n so the published production webhook is registered, runs direct credential smokes, and only then starts WordPress event processing. Success leaves only the restored project running and emits `gate10_restore_trace.json`; failure leaves the original stopped so an operator can repair or deliberately select rollback without ever running both shop-identical environments.

Do not rerun against a partly created target. Inspect it first. If it is an explicitly failed disposable restore with no required state, remove only that exact Compose project and its volumes, then rerun from zero resources. Never remove the preserved original project or the formal backup.
