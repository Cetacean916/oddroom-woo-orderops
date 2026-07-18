<?php

defined('ABSPATH') || exit;

final class OddRoom_Recovery
{
    public static function sweep(int $limit = 50): array
    {
        global $wpdb;
        $outbox = OddRoom_Installer::outboxTable();
        $ids = array_map('intval', $wpdb->get_col($wpdb->prepare(
            "SELECT id FROM {$outbox}
             WHERE status='processing' AND lock_expires_at <= UTC_TIMESTAMP(6)
             ORDER BY lock_expires_at ASC, id ASC LIMIT %d",
            $limit
        )));
        $observations = [];
        foreach ($ids as $rowId) {
            $result = self::recoverOne($rowId);
            if ($result !== null) {
                $observations[] = $result;
            }
        }
        return $observations;
    }

    private static function recoverOne(int $rowId): ?array
    {
        global $wpdb;
        $outbox = OddRoom_Installer::outboxTable();
        $leases = OddRoom_Installer::leaseTable();
        $snapshot = OddRoom_Repository::find($rowId);
        if (!$snapshot || $snapshot->status !== 'processing' || !$snapshot->action_id) {
            return null;
        }
        if (OddRoom_Scheduler::exactCandidates(OddRoom_Scheduler::HOOK, $rowId) !== []) {
            return null;
        }

        $wpdb->query('START TRANSACTION');
        try {
            $row = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM {$outbox} WHERE id=%d AND status='processing'
                 AND lock_expires_at <= UTC_TIMESTAMP(6) FOR UPDATE",
                $rowId
            ));
            if (!$row || !$row->lock_token || (int) $row->adapter_dispatch_attempt !== (int) $row->attempt_count) {
                $wpdb->query('ROLLBACK');
                return null;
            }
            $lease = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM {$leases} WHERE shop_instance_id=%s AND order_id=%d FOR UPDATE",
                $row->shop_instance_id,
                (int) $row->order_id
            ));
            $holderMatches = $lease
                && hash_equals((string) $lease->holder_row_lock_token, (string) $row->lock_token)
                && (int) $lease->holder_outbox_id === $rowId
                && (int) $lease->holder_action_id === (int) $row->action_id
                && (string) $lease->lease_token !== ''
                && (int) $wpdb->get_var($wpdb->prepare('SELECT %s <= UTC_TIMESTAMP(6)', $lease->expires_at)) === 1;
            if (!$holderMatches) {
                $wpdb->query('ROLLBACK');
                return null;
            }

            $automatic = (int) $row->attempt_count === (int) $row->automatic_attempt_count;
            $isSlackEvent = $row->event_type !== 'ORDER_CREATED';
            $dispatch = (string) $row->adapter_dispatch_state;
            $schedule = false;
            $delay = null;
            $status = 'failed';
            $errorCode = $dispatch === 'not_started'
                ? 'WORKER_INTERRUPTED_BEFORE_DISPATCH'
                : 'WORKER_INTERRUPTED_IN_FLIGHT';
            $operatorWait = null;

            if ($dispatch === 'in_flight' && $isSlackEvent) {
                $status = 'operator_wait';
                $errorCode = 'SLACK_OUTCOME_UNKNOWN';
                $operatorWait = 'SLACK_OUTCOME_UNKNOWN';
            } elseif ($automatic && (int) $row->automatic_attempt_count < (int) $row->max_attempts) {
                $status = 'retry_wait';
                $delay = OddRoom_Retry_Policy::delayAfter(
                    (int) $row->automatic_attempt_count,
                    OddRoom_Repository::testMode()
                );
                $schedule = true;
            } elseif ($automatic) {
                $errorCode = 'ATTEMPTS_EXHAUSTED';
            }

            $nextAttempt = $delay === null ? null : $wpdb->get_var($wpdb->prepare(
                'SELECT DATE_ADD(UTC_TIMESTAMP(6), INTERVAL %d SECOND)',
                $delay
            ));
            $updated = $wpdb->query($wpdb->prepare(
                "UPDATE {$outbox}
                 SET status=%s, action_id=NULL, next_attempt_at=NULLIF(%s,''), error_code=%s,
                     retryable=%d, last_error=%s, operator_wait_reason=NULLIF(%s,''),
                     operator_wait_epoch=operator_wait_epoch+%d,
                     lock_token=NULL, locked_at=NULL, lock_expires_at=NULL,
                     updated_at=UTC_TIMESTAMP(6)
                 WHERE id=%d AND status='processing' AND lock_token=%s
                   AND action_id=%d AND adapter_dispatch_attempt=attempt_count",
                $status,
                $nextAttempt ?? '',
                $errorCode,
                $schedule ? 1 : 0,
                $errorCode,
                $operatorWait ?? '',
                $operatorWait === null ? 0 : 1,
                $rowId,
                $row->lock_token,
                (int) $row->action_id
            ));
            $released = $wpdb->query($wpdb->prepare(
                "DELETE FROM {$leases}
                 WHERE shop_instance_id=%s AND order_id=%d AND lease_token=%s
                   AND holder_outbox_id=%d AND holder_action_id=%d AND holder_row_lock_token=%s",
                $row->shop_instance_id,
                (int) $row->order_id,
                $lease->lease_token,
                $rowId,
                (int) $row->action_id,
                $row->lock_token
            ));
            if ($updated !== 1 || $released !== 1) {
                $wpdb->query('ROLLBACK');
                return null;
            }
            $wpdb->query('COMMIT');

            $newActionId = 0;
            if ($schedule && is_string($nextAttempt)) {
                $timestamp = strtotime($nextAttempt . ' UTC');
                if ($timestamp !== false) {
                    $newActionId = OddRoom_Scheduler::scheduleBusiness($rowId, $timestamp);
                }
            }
            return [
                'row_id' => $rowId,
                'prior_action_id' => (int) $row->action_id,
                'status' => $status,
                'error_code' => $errorCode,
                'attempt_count' => (int) $row->attempt_count,
                'automatic_attempt_count' => (int) $row->automatic_attempt_count,
                'new_action_id' => $newActionId ?: null,
                'next_attempt_at' => $nextAttempt,
            ];
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            throw $error;
        }
    }
}
