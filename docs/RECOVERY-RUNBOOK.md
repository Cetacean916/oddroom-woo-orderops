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
