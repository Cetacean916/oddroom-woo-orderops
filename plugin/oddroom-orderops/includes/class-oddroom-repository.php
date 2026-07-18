<?php

defined('ABSPATH') || exit;

final class OddRoom_Repository
{
    private const LEASE_SECONDS = 600;

    public static function insertOrderCreated(WC_Order $order): array
    {
        global $wpdb;
        $shopId = self::requiredConfig('ODDROOM_ORDEROPS_SHOP_INSTANCE_ID');
        $runId = self::requiredConfig('ODDROOM_ORDEROPS_RUN_ID');
        $orderId = (int) $order->get_id();
        $eventKey = "v1:{$shopId}:{$orderId}:ORDER_CREATED";
        $created = $order->get_date_created();
        if (!$created) {
            throw new DomainException('Order creation time is unavailable.');
        }

        $items = [];
        foreach ($order->get_items('line_item') as $itemId => $item) {
            $product = $item->get_product();
            $items[] = [
                'item_id' => (int) $itemId,
                'product_id' => (int) $item->get_product_id(),
                'variation_id' => (int) $item->get_variation_id(),
                'sku' => $product ? (string) $product->get_sku() : 'unknown-' . (int) $itemId,
                'name' => (string) $item->get_name(),
                'quantity' => (int) $item->get_quantity(),
                'line_total' => number_format((float) $item->get_total(), 2, '.', ''),
            ];
        }
        if ($items === []) {
            throw new DomainException('A qualifying order requires at least one line item.');
        }

        $payload = OddRoom_Canonical_Payload::encode([
            'event_key' => $eventKey,
            'shop_instance_id' => $shopId,
            'run_id' => $runId,
            'event_type' => 'ORDER_CREATED',
            'occurred_at_utc' => gmdate('Y-m-d\\TH:i:s\\Z', $created->getTimestamp()),
            'occurred_at_source' => 'date_created',
            'order' => [
                'id' => $orderId,
                'number' => (string) $order->get_order_number(),
                'currency' => strtoupper((string) $order->get_currency()),
                'total' => number_format((float) $order->get_total(), 2, '.', ''),
                'customer' => [
                    'email' => strtolower((string) $order->get_billing_email()),
                    'first_name' => (string) $order->get_billing_first_name(),
                    'last_name' => (string) $order->get_billing_last_name(),
                ],
                'items' => $items,
                'coupon_codes' => array_values(array_map('strval', $order->get_coupon_codes())),
            ],
        ]);

        $table = OddRoom_Installer::outboxTable();
        $inserted = $wpdb->query($wpdb->prepare(
            "INSERT IGNORE INTO {$table}
            (schema_version,shop_instance_id,run_id,event_key,order_id,event_type,occurred_at_utc,
             occurred_at_source,state_rank,payload_json,payload_hash,status,processing_phase,
             attempt_count,automatic_attempt_count,max_attempts,manual_retry_count,manual_attempt_pending,
             adapter_dispatch_state,slack_status,operator_wait_epoch,resolved_operator_wait_epoch,
             created_at,updated_at)
            VALUES (%s,%s,%s,%s,%d,'ORDER_CREATED',%s,'date_created',10,%s,%s,'pending','created',
                    0,0,6,0,0,'not_started','not_required',0,0,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
            OddRoom_Canonical_Payload::SCHEMA_VERSION,
            $shopId,
            $runId,
            $eventKey,
            $orderId,
            gmdate('Y-m-d H:i:s', $created->getTimestamp()),
            $payload,
            OddRoom_Canonical_Payload::hash($payload)
        ));
        if ($inserted === false) {
            throw new RuntimeException('Outbox insert failed.');
        }
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE event_key = %s", $eventKey));
        if (!$row) {
            throw new RuntimeException('Outbox row lookup failed.');
        }
        return ['row' => $row, 'inserted' => $inserted === 1];
    }

    public static function find(int $rowId): ?object
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE id = %d", $rowId));
        return is_object($row) ? $row : null;
    }

    public static function eligibleUnscheduledIds(int $limit): array
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        return array_map('intval', $wpdb->get_col($wpdb->prepare(
            "SELECT id FROM {$table}
             WHERE action_id IS NULL
               AND (status = 'pending' OR (status = 'retry_wait' AND next_attempt_at <= UTC_TIMESTAMP(6)))
               AND (error_code IS NULL OR error_code <> 'ACTION_ID_AMBIGUOUS')
             ORDER BY id ASC LIMIT %d",
            $limit
        )));
    }

    public static function linkAction(int $rowId, int $actionId): bool
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        $updated = $wpdb->query($wpdb->prepare(
            "UPDATE {$table} SET action_id = %d,
                    last_error = CASE WHEN error_code LIKE 'ACTION_%' THEN NULL ELSE last_error END,
                    error_code = CASE WHEN error_code LIKE 'ACTION_%' THEN NULL ELSE error_code END,
                    updated_at = UTC_TIMESTAMP(6)
             WHERE id = %d AND action_id IS NULL
               AND (status = 'pending' OR status = 'retry_wait')",
            $actionId,
            $rowId
        ));
        return $updated === 1;
    }

    public static function recordSchedulingError(int $rowId, string $code, bool $terminal): void
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        $status = $terminal ? 'failed' : null;
        if ($status !== null) {
            $wpdb->query($wpdb->prepare(
                "UPDATE {$table} SET status = %s, action_id = NULL, error_code = %s, retryable = 0,
                        last_error = %s, updated_at = UTC_TIMESTAMP(6)
                 WHERE id = %d AND lock_token IS NULL",
                $status,
                $code,
                self::sanitizeError($code),
                $rowId
            ));
            return;
        }
        $wpdb->query($wpdb->prepare(
            "UPDATE {$table} SET action_id = NULL, error_code = %s, retryable = 1,
                    last_error = %s, updated_at = UTC_TIMESTAMP(6)
             WHERE id = %d AND lock_token IS NULL AND (status = 'pending' OR status = 'retry_wait')",
            $code,
            self::sanitizeError($code),
            $rowId
        ));
    }

    public static function claim(int $rowId, int $actionId): ?array
    {
        global $wpdb;
        $outbox = OddRoom_Installer::outboxTable();
        $leases = OddRoom_Installer::leaseTable();
        $rowToken = bin2hex(random_bytes(32));
        $leaseToken = bin2hex(random_bytes(32));

        $wpdb->query('START TRANSACTION');
        try {
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$outbox} WHERE id = %d FOR UPDATE", $rowId));
            if (!$row || (int) $row->action_id !== $actionId || $row->lock_token !== null) {
                $wpdb->query('ROLLBACK');
                return null;
            }
            $eligible = $row->status === 'pending'
                || ($row->status === 'retry_wait' && self::isDue((string) $row->next_attempt_at));
            if (!$eligible) {
                $wpdb->query('ROLLBACK');
                return null;
            }

            $wpdb->query($wpdb->prepare(
                "DELETE FROM {$leases} WHERE shop_instance_id = %s AND order_id = %d
                 AND expires_at <= UTC_TIMESTAMP(6)",
                $row->shop_instance_id,
                (int) $row->order_id
            ));
            $leaseInserted = $wpdb->query($wpdb->prepare(
                "INSERT IGNORE INTO {$leases}
                 (shop_instance_id,order_id,lease_token,holder_outbox_id,holder_action_id,
                  holder_row_lock_token,acquired_at,expires_at)
                 VALUES (%s,%d,%s,%d,%d,%s,UTC_TIMESTAMP(6),
                         DATE_ADD(UTC_TIMESTAMP(6), INTERVAL %d SECOND))",
                $row->shop_instance_id,
                (int) $row->order_id,
                $leaseToken,
                $rowId,
                $actionId,
                $rowToken,
                self::LEASE_SECONDS
            ));
            if ($leaseInserted !== 1) {
                $wpdb->query('ROLLBACK');
                return null;
            }

            $manual = (int) $row->manual_attempt_pending === 1;
            $automaticIncrement = $manual ? 0 : 1;
            $updated = $wpdb->query($wpdb->prepare(
                "UPDATE {$outbox}
                 SET status = 'processing', lock_token = %s, locked_at = UTC_TIMESTAMP(6),
                     lock_expires_at = DATE_ADD(UTC_TIMESTAMP(6), INTERVAL %d SECOND),
                     last_attempt_at = UTC_TIMESTAMP(6), attempt_count = attempt_count + 1,
                     automatic_attempt_count = automatic_attempt_count + %d,
                     manual_attempt_pending = 0, adapter_dispatch_state = 'not_started',
                     adapter_dispatch_attempt = attempt_count, adapter_dispatched_at = NULL,
                     error_code = NULL, retryable = NULL, last_error = NULL,
                     updated_at = UTC_TIMESTAMP(6)
                 WHERE id = %d AND action_id = %d AND lock_token IS NULL
                   AND (status = 'pending' OR (status = 'retry_wait' AND next_attempt_at <= UTC_TIMESTAMP(6)))",
                $rowToken,
                self::LEASE_SECONDS,
                $automaticIncrement,
                $rowId,
                $actionId
            ));
            if ($updated !== 1) {
                $wpdb->query('ROLLBACK');
                return null;
            }
            $wpdb->query('COMMIT');
            $claimed = self::find($rowId);
            return $claimed ? ['row' => $claimed, 'row_token' => $rowToken, 'lease_token' => $leaseToken] : null;
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            throw $error;
        }
    }

    public static function markDispatched(object $row, string $rowToken, string $leaseToken): bool
    {
        global $wpdb;
        $outbox = OddRoom_Installer::outboxTable();
        $leases = OddRoom_Installer::leaseTable();
        $wpdb->query('START TRANSACTION');
        try {
            $leaseUpdated = $wpdb->query($wpdb->prepare(
                "UPDATE {$leases} SET expires_at = DATE_ADD(UTC_TIMESTAMP(6), INTERVAL %d SECOND)
                 WHERE shop_instance_id = %s AND order_id = %d AND lease_token = %s
                   AND holder_outbox_id = %d AND holder_action_id = %d AND holder_row_lock_token = %s",
                self::LEASE_SECONDS,
                $row->shop_instance_id,
                (int) $row->order_id,
                $leaseToken,
                (int) $row->id,
                (int) $row->action_id,
                $rowToken
            ));
            $rowUpdated = $wpdb->query($wpdb->prepare(
                "UPDATE {$outbox}
                 SET adapter_dispatch_state = 'in_flight', adapter_dispatched_at = UTC_TIMESTAMP(6),
                     lock_expires_at = DATE_ADD(UTC_TIMESTAMP(6), INTERVAL %d SECOND),
                     updated_at = UTC_TIMESTAMP(6)
                 WHERE id = %d AND lock_token = %s AND status = 'processing'
                   AND adapter_dispatch_state = 'not_started' AND adapter_dispatch_attempt = attempt_count",
                self::LEASE_SECONDS,
                (int) $row->id,
                $rowToken
            ));
            if ($leaseUpdated !== 1 || $rowUpdated !== 1) {
                $wpdb->query('ROLLBACK');
                return false;
            }
            $wpdb->query('COMMIT');
            return true;
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            throw $error;
        }
    }

    public static function finish(
        object $claimedRow,
        string $rowToken,
        string $leaseToken,
        array $result,
        ?int $httpStatus
    ): array {
        global $wpdb;
        $outbox = OddRoom_Installer::outboxTable();
        $leases = OddRoom_Installer::leaseTable();
        $wpdb->query('START TRANSACTION');
        try {
            $row = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM {$outbox} WHERE id = %d AND lock_token = %s FOR UPDATE",
                (int) $claimedRow->id,
                $rowToken
            ));
            if (!$row || $row->status !== 'processing') {
                $wpdb->query('ROLLBACK');
                throw new RuntimeException('LOCK_LOST');
            }

            $remoteContact = OddRoom_State_Machine::checkpoint(
                self::nullableString($row->remote_contact_id),
                self::nullableString($result['remote_contact_id'])
            );
            $remoteDeal = OddRoom_State_Machine::checkpoint(
                self::nullableString($row->remote_deal_id),
                self::nullableString($result['remote_deal_id'])
            );
            $slackTs = OddRoom_State_Machine::checkpoint(
                self::nullableString($row->slack_message_ts),
                self::nullableString($result['slack_message_ts'])
            );
            OddRoom_State_Machine::assertMonotonic((string) $row->processing_phase, (string) $result['processing_phase']);

            $transition = self::transitionFor($row, $result);
            $nextAttemptAt = $transition['delay'] !== null
                ? $wpdb->get_var($wpdb->prepare(
                    'SELECT DATE_ADD(UTC_TIMESTAMP(6), INTERVAL %d SECOND)',
                    $transition['delay']
                ))
                : null;

            $updated = $wpdb->query($wpdb->prepare(
                "UPDATE {$outbox}
                 SET status = %s, processing_phase = %s, remote_contact_id = NULLIF(%s,''),
                     remote_deal_id = NULLIF(%s,''), slack_status = %s, slack_message_ts = NULLIF(%s,''),
                     next_attempt_at = NULLIF(%s,''), action_id = NULL, last_http_status = NULLIF(%s,''),
                     error_code = NULLIF(%s,''), retryable = %d, last_error = NULLIF(%s,''),
                     operator_wait_reason = NULLIF(%s,''),
                     operator_wait_epoch = operator_wait_epoch + %d,
                     processed_at = NULLIF(%s,''), lock_token = NULL, locked_at = NULL,
                     lock_expires_at = NULL, updated_at = UTC_TIMESTAMP(6)
                 WHERE id = %d AND lock_token = %s AND status = 'processing'",
                $transition['status'],
                $transition['phase'],
                $remoteContact,
                $remoteDeal,
                $result['slack_status'],
                $slackTs,
                $nextAttemptAt,
                $httpStatus === null ? '' : (string) $httpStatus,
                $transition['error_code'] ?? '',
                $transition['retryable'] ? 1 : 0,
                self::sanitizeError((string) ($result['error_message'] ?? $transition['error_code'] ?? '')),
                $transition['operator_wait_reason'] ?? '',
                $transition['operator_wait_reason'] !== null ? 1 : 0,
                $transition['status'] === 'completed' ? gmdate('Y-m-d H:i:s') : null,
                (int) $row->id,
                $rowToken
            ));
            if ($updated !== 1) {
                $wpdb->query('ROLLBACK');
                throw new RuntimeException('LOCK_LOST');
            }

            $released = $wpdb->query($wpdb->prepare(
                "DELETE FROM {$leases}
                 WHERE shop_instance_id = %s AND order_id = %d AND lease_token = %s
                   AND holder_outbox_id = %d AND holder_action_id = %d AND holder_row_lock_token = %s",
                $row->shop_instance_id,
                (int) $row->order_id,
                $leaseToken,
                (int) $row->id,
                (int) $row->action_id,
                $rowToken
            ));
            if ($released !== 1) {
                $wpdb->query('ROLLBACK');
                throw new RuntimeException('LOCK_LOST');
            }
            $wpdb->query('COMMIT');
            return ['schedule_at' => $nextAttemptAt, 'status' => $transition['status']];
        } catch (DomainException $error) {
            $wpdb->query('ROLLBACK');
            self::moveCheckpointConflict((int) $claimedRow->id, $rowToken, $leaseToken, $claimedRow);
            return ['schedule_at' => null, 'status' => 'operator_wait'];
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            throw $error;
        }
    }

    public static function transportFailure(
        object $claimedRow,
        string $rowToken,
        string $leaseToken,
        string $code,
        string $message,
        ?int $httpStatus = null,
        ?int $retryAfter = null
    ): array {
        $result = [
            'schema_version' => '1',
            'event_key' => (string) $claimedRow->event_key,
            'result' => 'retryable_error',
            'processing_phase' => (string) $claimedRow->processing_phase,
            'remote_contact_id' => self::nullableString($claimedRow->remote_contact_id),
            'remote_deal_id' => self::nullableString($claimedRow->remote_deal_id),
            'slack_status' => (string) $claimedRow->slack_status,
            'slack_message_ts' => self::nullableString($claimedRow->slack_message_ts),
            'retryable' => true,
            'retry_after_seconds' => $retryAfter,
            'error_code' => $code,
            'error_message' => $message,
        ];
        return self::finish($claimedRow, $rowToken, $leaseToken, $result, $httpStatus);
    }

    public static function all(int $limit = 100): array
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        return $wpdb->get_results($wpdb->prepare("SELECT * FROM {$table} ORDER BY id DESC LIMIT %d", $limit));
    }

    public static function counts(): array
    {
        global $wpdb;
        $outbox = OddRoom_Installer::outboxTable();
        $leases = OddRoom_Installer::leaseTable();
        return [
            'outbox' => (int) $wpdb->get_var("SELECT COUNT(*) FROM {$outbox}"),
            'leases' => (int) $wpdb->get_var("SELECT COUNT(*) FROM {$leases}"),
        ];
    }

    public static function requiredConfig(string $constant): string
    {
        $value = defined($constant) ? constant($constant) : '';
        if ((!is_string($value) || $value === '') && str_starts_with($constant, 'ODDROOM_ORDEROPS_')) {
            $value = getenv('ODDROOM_' . substr($constant, strlen('ODDROOM_ORDEROPS_')));
        }
        if (!is_string($value) || $value === '') {
            throw new RuntimeException($constant . ' is not configured.');
        }
        return $value;
    }

    public static function testMode(): bool
    {
        if (defined('ODDROOM_ORDEROPS_TEST_MODE')) {
            return ODDROOM_ORDEROPS_TEST_MODE === true;
        }
        return filter_var(getenv('ODDROOM_TEST_MODE'), FILTER_VALIDATE_BOOLEAN);
    }

    private static function transitionFor(object $row, array $result): array
    {
        $kind = (string) $result['result'];
        if (in_array($kind, ['completed', 'duplicate_noop', 'stale_ignored'], true)) {
            return [
                'status' => 'completed', 'phase' => 'completed', 'delay' => null,
                'retryable' => false, 'error_code' => null, 'operator_wait_reason' => null,
            ];
        }
        if ($kind === 'operator_review') {
            return [
                'status' => 'operator_wait', 'phase' => (string) $result['processing_phase'], 'delay' => null,
                'retryable' => false, 'error_code' => (string) $result['error_code'],
                'operator_wait_reason' => (string) $result['error_code'],
            ];
        }
        if ($kind === 'terminal_error') {
            return [
                'status' => 'failed', 'phase' => (string) $result['processing_phase'], 'delay' => null,
                'retryable' => false, 'error_code' => (string) $result['error_code'], 'operator_wait_reason' => null,
            ];
        }

        $automatic = (int) $row->attempt_count === (int) $row->automatic_attempt_count;
        if (!$automatic) {
            return [
                'status' => 'failed', 'phase' => (string) $result['processing_phase'], 'delay' => null,
                'retryable' => false, 'error_code' => (string) $result['error_code'], 'operator_wait_reason' => null,
            ];
        }
        if ((int) $row->automatic_attempt_count >= (int) $row->max_attempts) {
            return [
                'status' => 'failed', 'phase' => (string) $result['processing_phase'], 'delay' => null,
                'retryable' => false, 'error_code' => 'ATTEMPTS_EXHAUSTED', 'operator_wait_reason' => null,
            ];
        }
        $delay = OddRoom_Retry_Policy::delayAfter(
            (int) $row->automatic_attempt_count,
            self::testMode()
        );
        if (is_int($result['retry_after_seconds'] ?? null)) {
            $delay = max($delay, (int) $result['retry_after_seconds']);
        }
        return [
            'status' => 'retry_wait', 'phase' => (string) $result['processing_phase'], 'delay' => $delay,
            'retryable' => true, 'error_code' => (string) ($result['error_code'] ?? 'ADAPTER_RESPONSE_INVALID'),
            'operator_wait_reason' => null,
        ];
    }

    private static function moveCheckpointConflict(
        int $rowId,
        string $rowToken,
        string $leaseToken,
        object $claimedRow
    ): void {
        global $wpdb;
        $outbox = OddRoom_Installer::outboxTable();
        $leases = OddRoom_Installer::leaseTable();
        $wpdb->query('START TRANSACTION');
        $updated = $wpdb->query($wpdb->prepare(
            "UPDATE {$outbox}
             SET status='operator_wait', error_code='CHECKPOINT_CONFLICT', retryable=0,
                 operator_wait_reason='CHECKPOINT_CONFLICT', operator_wait_epoch=operator_wait_epoch+1,
                 action_id=NULL, lock_token=NULL, locked_at=NULL, lock_expires_at=NULL,
                 last_error='CHECKPOINT_CONFLICT', updated_at=UTC_TIMESTAMP(6)
             WHERE id=%d AND lock_token=%s AND status='processing'",
            $rowId,
            $rowToken
        ));
        $released = $wpdb->query($wpdb->prepare(
            "DELETE FROM {$leases} WHERE shop_instance_id=%s AND order_id=%d AND lease_token=%s
             AND holder_outbox_id=%d AND holder_action_id=%d AND holder_row_lock_token=%s",
            $claimedRow->shop_instance_id,
            (int) $claimedRow->order_id,
            $leaseToken,
            $rowId,
            (int) $claimedRow->action_id,
            $rowToken
        ));
        if ($updated === 1 && $released === 1) {
            $wpdb->query('COMMIT');
        } else {
            $wpdb->query('ROLLBACK');
        }
    }

    private static function isDue(string $date): bool
    {
        global $wpdb;
        return (int) $wpdb->get_var($wpdb->prepare('SELECT %s <= UTC_TIMESTAMP(6)', $date)) === 1;
    }

    private static function nullableString(mixed $value): ?string
    {
        return is_string($value) && $value !== '' ? $value : null;
    }

    private static function sanitizeError(string $message): string
    {
        $clean = sanitize_text_field($message);
        return substr($clean, 0, 500);
    }
}
