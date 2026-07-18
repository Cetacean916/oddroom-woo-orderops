<?php

defined('ABSPATH') || exit;

final class OddRoom_Repository
{
    private const LEASE_SECONDS = 600;

    public static function insertOrderCreated(WC_Order $order): array
    {
        $created = $order->get_date_created();
        if (!$created) {
            throw new DomainException('Order creation time is unavailable.');
        }
        return self::insertEvent($order, 'ORDER_CREATED', $created, 'date_created');
    }

    public static function insertEvent(
        WC_Order $order,
        string $eventType,
        DateTimeInterface $occurredAt,
        string $occurredAtSource
    ): array {
        global $wpdb;
        $allowedSources = [
            'ORDER_CREATED' => 'date_created',
            'PAYMENT_CONFIRMED' => 'date_paid',
            'ORDER_CANCELLED' => '_oddroom_orderops_cancelled_at_utc',
            'ORDER_REFUNDED' => 'full_refund_completion',
        ];
        if (($allowedSources[$eventType] ?? null) !== $occurredAtSource) {
            throw new DomainException('Event occurrence source is invalid.');
        }

        $shopId = self::requiredConfig('ODDROOM_ORDEROPS_SHOP_INSTANCE_ID');
        $runId = self::requiredConfig('ODDROOM_ORDEROPS_RUN_ID');
        $orderId = (int) $order->get_id();
        $eventKey = "v1:{$shopId}:{$orderId}:{$eventType}";
        $stateRank = OddRoom_Canonical_Payload::rankFor($eventType);
        $occurredTimestamp = $occurredAt->getTimestamp();

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
            'event_type' => $eventType,
            'occurred_at_utc' => gmdate('Y-m-d\\TH:i:s\\Z', $occurredTimestamp),
            'occurred_at_source' => $occurredAtSource,
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
            VALUES (%s,%s,%s,%s,%d,%s,%s,%s,%d,%s,%s,'pending','created',
                    0,0,6,0,0,'not_started',%s,0,0,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
            OddRoom_Canonical_Payload::SCHEMA_VERSION,
            $shopId,
            $runId,
            $eventKey,
            $orderId,
            $eventType,
            gmdate('Y-m-d H:i:s', $occurredTimestamp),
            $occurredAtSource,
            $stateRank,
            $payload,
            OddRoom_Canonical_Payload::hash($payload),
            $eventType === 'ORDER_CREATED' ? 'not_required' : 'pending'
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

    public static function findEvent(int $orderId, string $eventType): ?object
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        $row = $wpdb->get_row($wpdb->prepare(
            "SELECT * FROM {$table} WHERE shop_instance_id = %s AND order_id = %d AND event_type = %s",
            self::requiredConfig('ODDROOM_ORDEROPS_SHOP_INSTANCE_ID'),
            $orderId,
            $eventType
        ));
        return is_object($row) ? $row : null;
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

    public static function unlinkCompletedAction(int $rowId, int $actionId): bool
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        $updated = $wpdb->query($wpdb->prepare(
            "UPDATE {$table} SET action_id = NULL, updated_at = UTC_TIMESTAMP(6)
             WHERE id = %d AND action_id = %d AND lock_token IS NULL
               AND (status = 'pending' OR (status = 'retry_wait' AND next_attempt_at <= UTC_TIMESTAMP(6)))",
            $rowId,
            $actionId
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

    public static function ambiguousSlackFailure(
        object $claimedRow,
        string $rowToken,
        string $leaseToken,
        string $message,
        ?int $httpStatus = null
    ): array {
        $result = [
            'schema_version' => '1',
            'event_key' => (string) $claimedRow->event_key,
            'result' => 'operator_review',
            'processing_phase' => (string) $claimedRow->processing_phase,
            'remote_contact_id' => self::nullableString($claimedRow->remote_contact_id),
            'remote_deal_id' => self::nullableString($claimedRow->remote_deal_id),
            'slack_status' => 'outcome_unknown',
            'slack_message_ts' => self::nullableString($claimedRow->slack_message_ts),
            'retryable' => false,
            'retry_after_seconds' => null,
            'error_code' => 'SLACK_OUTCOME_UNKNOWN',
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

    public static function queryForAdmin(array $filters): array
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        [$whereSql, $whereArgs] = self::adminWhere($filters);
        $sorts = [
            'id' => 'id',
            'order_id' => 'order_id',
            'event_type' => 'event_type',
            'status' => 'status',
            'occurred_at_utc' => 'occurred_at_utc',
            'updated_at' => 'updated_at',
        ];
        $sort = $sorts[(string) ($filters['sort'] ?? 'id')] ?? 'id';
        $direction = strtoupper((string) ($filters['direction'] ?? 'DESC')) === 'ASC' ? 'ASC' : 'DESC';
        $page = max(1, (int) ($filters['page'] ?? 1));
        $perPage = min(100, max(1, (int) ($filters['per_page'] ?? 50)));
        $offset = ($page - 1) * $perPage;
        $sql = "SELECT *,
                    CASE WHEN locked_at IS NULL THEN NULL
                         ELSE TIMESTAMPDIFF(SECOND,locked_at,UTC_TIMESTAMP(6)) END AS lock_age_seconds
                FROM {$table} WHERE {$whereSql}
                ORDER BY {$sort} {$direction}, id {$direction} LIMIT %d OFFSET %d";
        return $wpdb->get_results($wpdb->prepare($sql, ...array_merge($whereArgs, [$perPage, $offset])));
    }

    public static function countForAdmin(array $filters): int
    {
        global $wpdb;
        $table = OddRoom_Installer::outboxTable();
        [$whereSql, $whereArgs] = self::adminWhere($filters);
        $sql = "SELECT COUNT(*) FROM {$table} WHERE {$whereSql}";
        return $whereArgs === []
            ? (int) $wpdb->get_var($sql)
            : (int) $wpdb->get_var($wpdb->prepare($sql, ...$whereArgs));
    }

    public static function shouldSchedule(object $row): bool
    {
        if ($row->action_id !== null || $row->lock_token !== null) {
            return false;
        }
        if ((string) $row->status === 'pending') {
            return true;
        }
        return (string) $row->status === 'retry_wait'
            && is_string($row->next_attempt_at)
            && $row->next_attempt_at !== ''
            && self::isDue($row->next_attempt_at);
    }

    public static function manualRetry(int $rowId, int $administratorId): array
    {
        global $wpdb;
        if ($rowId < 1 || $administratorId < 1) {
            throw new InvalidArgumentException('Manual retry input is invalid.');
        }
        if (OddRoom_Scheduler::exactCandidates(OddRoom_Scheduler::HOOK, $rowId) !== []) {
            throw new RuntimeException('ACTION_CONFLICT');
        }
        $table = OddRoom_Installer::outboxTable();
        $wpdb->query('START TRANSACTION');
        try {
            $row = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM {$table} WHERE id=%d FOR UPDATE",
                $rowId
            ));
            if (!$row) {
                throw new RuntimeException('ROW_NOT_FOUND');
            }
            if ((string) $row->status === 'operator_wait') {
                throw new RuntimeException('OPERATOR_WAIT_REQUIRES_RESOLVE_OUTCOME');
            }
            if ((string) $row->status !== 'failed'
                || $row->action_id !== null
                || $row->lock_token !== null) {
                throw new RuntimeException('ROW_NOT_MANUALLY_RETRYABLE');
            }
            $updated = $wpdb->query($wpdb->prepare(
                "UPDATE {$table}
                 SET status='pending', manual_retry_count=manual_retry_count+1,
                     manual_attempt_pending=1, next_attempt_at=NULL, action_id=NULL,
                     error_code=NULL, retryable=1, last_error=NULL,
                     updated_at=UTC_TIMESTAMP(6)
                 WHERE id=%d AND status='failed' AND action_id IS NULL AND lock_token IS NULL",
                $rowId
            ));
            if ($updated !== 1) {
                throw new RuntimeException('MANUAL_RETRY_CONFLICT');
            }
            $wpdb->query('COMMIT');
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            throw $error;
        }

        $actionId = OddRoom_Scheduler::scheduleBusiness($rowId);
        if ($actionId < 1
            || OddRoom_Scheduler::exactCandidates(OddRoom_Scheduler::HOOK, $rowId) !== [$actionId]) {
            throw new RuntimeException('MANUAL_RETRY_SCHEDULE_FAILED');
        }
        return ['status' => 'scheduled', 'action_id' => $actionId, 'idempotent' => false];
    }

    public static function resolveOutcome(array $input): array
    {
        global $wpdb;
        $rowId = (int) ($input['row_id'] ?? 0);
        $epoch = (int) ($input['epoch'] ?? 0);
        $administratorId = (int) ($input['administrator_id'] ?? 0);
        $decision = strtoupper((string) ($input['decision'] ?? ''));
        $evidenceRef = self::validateEvidenceRef((string) ($input['evidence_ref'] ?? ''));
        $decisions = ['CONFIRMED_POSTED', 'CONFIRMED_NOT_POSTED', 'RETRY_AFTER_DUE', 'UNRESOLVED'];
        if ($rowId < 1 || $epoch < 1 || $administratorId < 1 || !in_array($decision, $decisions, true)) {
            throw new InvalidArgumentException('Resolve Outcome input is invalid.');
        }
        $table = OddRoom_Installer::outboxTable();
        $scheduleAt = null;
        $wpdb->query('START TRANSACTION');
        try {
            $row = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM {$table} WHERE id=%d FOR UPDATE",
                $rowId
            ));
            if (!$row) {
                throw new RuntimeException('ROW_NOT_FOUND');
            }
            if ((int) $row->resolved_operator_wait_epoch === $epoch) {
                if ((string) $row->last_operator_resolution === $decision) {
                    $wpdb->query('COMMIT');
                    return [
                        'status' => (string) $row->status,
                        'action_id' => (int) ($row->action_id ?? 0),
                        'idempotent' => true,
                    ];
                }
                throw new DomainException('CHECKPOINT_CONFLICT');
            }
            if (OddRoom_Scheduler::exactCandidates(OddRoom_Scheduler::HOOK, $rowId) !== []) {
                throw new RuntimeException('ACTION_CONFLICT');
            }
            if ((string) $row->status !== 'operator_wait'
                || (int) $row->operator_wait_epoch !== $epoch
                || (int) $row->resolved_operator_wait_epoch >= $epoch
                || $row->action_id !== null
                || $row->lock_token !== null) {
                throw new RuntimeException('OPERATOR_WAIT_EPOCH_CONFLICT');
            }

            $reason = (string) $row->operator_wait_reason;
            if ($decision !== 'UNRESOLVED'
                && !in_array($reason, ['SLACK_OUTCOME_UNKNOWN', 'RESUME_PHASE_CONFLICT'], true)) {
                throw new RuntimeException('RESOLUTION_NOT_ALLOWED_FOR_REASON');
            }
            if ($decision === 'UNRESOLVED') {
                $updated = $wpdb->query($wpdb->prepare(
                    "UPDATE {$table}
                     SET last_operator_resolution='UNRESOLVED', operator_evidence_ref=%s,
                         operator_resolved_at=UTC_TIMESTAMP(6), operator_resolved_by=%d,
                         updated_at=UTC_TIMESTAMP(6)
                     WHERE id=%d AND status='operator_wait' AND operator_wait_epoch=%d
                       AND resolved_operator_wait_epoch<%d AND action_id IS NULL AND lock_token IS NULL",
                    $evidenceRef,
                    $administratorId,
                    $rowId,
                    $epoch,
                    $epoch
                ));
                if ($updated !== 1) {
                    throw new RuntimeException('OPERATOR_WAIT_EPOCH_CONFLICT');
                }
                $wpdb->query('COMMIT');
                return ['status' => 'operator_wait', 'action_id' => 0, 'idempotent' => false];
            }

            $contactId = OddRoom_State_Machine::checkpoint(
                self::nullableString($row->remote_contact_id),
                self::validateIdentifier($input['remote_contact_id'] ?? null, 'remote_contact_id')
            );
            $dealId = OddRoom_State_Machine::checkpoint(
                self::nullableString($row->remote_deal_id),
                self::validateIdentifier($input['remote_deal_id'] ?? null, 'remote_deal_id')
            );
            $slackTs = self::nullableString($row->slack_message_ts);
            $phase = 'completed';
            $status = 'completed';
            $slackStatus = 'posted';
            $nextAttempt = null;
            $manualPending = 0;
            $manualIncrement = 0;
            $processed = true;
            $retryable = 0;

            if ($decision === 'CONFIRMED_POSTED') {
                $slackTs = OddRoom_State_Machine::checkpoint(
                    $slackTs,
                    self::validateIdentifier($input['slack_message_ts'] ?? null, 'slack_message_ts')
                );
                if ($contactId === null || $dealId === null || $slackTs === null) {
                    throw new InvalidArgumentException('Confirmed posted requires Contact, Deal, and Slack identifiers.');
                }
            } else {
                $phase = self::validateResumePhase((string) ($input['verified_phase'] ?? ''));
                self::assertResumeCheckpoints($phase, $contactId, $dealId);
                $status = $decision === 'RETRY_AFTER_DUE' ? 'retry_wait' : 'pending';
                $slackStatus = 'pending';
                $manualPending = 1;
                $manualIncrement = 1;
                $processed = false;
                $retryable = 1;
                if ($decision === 'RETRY_AFTER_DUE') {
                    $nextAttempt = self::normalizeFutureDue((string) ($input['due_at_utc'] ?? ''));
                    $scheduleAt = strtotime($nextAttempt . ' UTC');
                }
            }

            $updated = $wpdb->query($wpdb->prepare(
                "UPDATE {$table}
                 SET status=%s, processing_phase=%s,
                     remote_contact_id=NULLIF(%s,''), remote_deal_id=NULLIF(%s,''),
                     slack_status=%s, slack_message_ts=NULLIF(%s,''),
                     next_attempt_at=NULLIF(%s,''), action_id=NULL,
                     manual_attempt_pending=%d,
                     manual_retry_count=manual_retry_count+%d,
                     error_code=NULL, retryable=%d, last_error=NULL,
                     operator_wait_reason=NULL, resolved_operator_wait_epoch=%d,
                     last_operator_resolution=%s, operator_evidence_ref=%s,
                     operator_resolved_at=UTC_TIMESTAMP(6), operator_resolved_by=%d,
                     processed_at=CASE WHEN %d=1 THEN UTC_TIMESTAMP(6) ELSE NULL END,
                     updated_at=UTC_TIMESTAMP(6)
                 WHERE id=%d AND status='operator_wait' AND operator_wait_epoch=%d
                   AND resolved_operator_wait_epoch<%d AND action_id IS NULL AND lock_token IS NULL",
                $status,
                $phase,
                $contactId ?? '',
                $dealId ?? '',
                $slackStatus,
                $slackTs ?? '',
                $nextAttempt ?? '',
                $manualPending,
                $manualIncrement,
                $retryable,
                $epoch,
                $decision,
                $evidenceRef,
                $administratorId,
                $processed ? 1 : 0,
                $rowId,
                $epoch,
                $epoch
            ));
            if ($updated !== 1) {
                throw new RuntimeException('OPERATOR_WAIT_EPOCH_CONFLICT');
            }
            $wpdb->query('COMMIT');
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            throw $error;
        }

        if ($decision === 'CONFIRMED_POSTED') {
            return ['status' => 'completed', 'action_id' => 0, 'idempotent' => false];
        }
        $actionId = OddRoom_Scheduler::scheduleBusiness($rowId, $scheduleAt);
        if ($actionId < 1
            || OddRoom_Scheduler::exactCandidates(OddRoom_Scheduler::HOOK, $rowId) !== [$actionId]) {
            throw new RuntimeException('RESOLUTION_SCHEDULE_FAILED');
        }
        return ['status' => $status, 'action_id' => $actionId, 'idempotent' => false];
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

    private static function adminWhere(array $filters): array
    {
        global $wpdb;
        $where = ['1=1'];
        $args = [];
        $statuses = ['pending', 'processing', 'retry_wait', 'operator_wait', 'failed', 'completed'];
        $events = ['ORDER_CREATED', 'PAYMENT_CONFIRMED', 'ORDER_CANCELLED', 'ORDER_REFUNDED'];
        $status = (string) ($filters['status'] ?? '');
        $event = (string) ($filters['event_type'] ?? '');
        if (in_array($status, $statuses, true)) {
            $where[] = 'status=%s';
            $args[] = $status;
        }
        if (in_array($event, $events, true)) {
            $where[] = 'event_type=%s';
            $args[] = $event;
        }
        $search = trim((string) ($filters['search'] ?? ''));
        if ($search !== '') {
            $like = '%' . $wpdb->esc_like(substr($search, 0, 191)) . '%';
            $where[] = '(event_key LIKE %s OR CAST(order_id AS CHAR) LIKE %s)';
            $args[] = $like;
            $args[] = $like;
        }
        return [implode(' AND ', $where), $args];
    }

    private static function validateEvidenceRef(string $value): string
    {
        $value = trim(sanitize_text_field($value));
        if ($value === '' || strlen($value) > 255) {
            throw new InvalidArgumentException('A bounded execution-evidence reference is required.');
        }
        return $value;
    }

    private static function validateIdentifier(mixed $value, string $field): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }
        if (!is_string($value)) {
            throw new InvalidArgumentException($field . ' is invalid.');
        }
        $value = trim($value);
        $max = $field === 'slack_message_ts' ? 64 : 128;
        if ($value === '' || strlen($value) > $max || preg_match('/[\x00-\x1F\x7F]/', $value)) {
            throw new InvalidArgumentException($field . ' is invalid.');
        }
        return $value;
    }

    private static function validateResumePhase(string $phase): string
    {
        $allowed = ['created', 'deal_resolved', 'contact_upserted', 'deal_upserted', 'associated', 'slack_pending'];
        if (!in_array($phase, $allowed, true)) {
            throw new InvalidArgumentException('Verified resume phase is invalid.');
        }
        return $phase;
    }

    private static function assertResumeCheckpoints(string $phase, ?string $contactId, ?string $dealId): void
    {
        $rank = array_search($phase, [
            'created', 'deal_resolved', 'contact_upserted', 'deal_upserted', 'associated', 'slack_pending',
        ], true);
        if ($rank >= 2 && $contactId === null) {
            throw new InvalidArgumentException('Verified phase requires a Contact identifier.');
        }
        if ($rank >= 3 && $dealId === null) {
            throw new InvalidArgumentException('Verified phase requires a Deal identifier.');
        }
    }

    private static function normalizeFutureDue(string $value): string
    {
        global $wpdb;
        if (!preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/', $value)) {
            throw new InvalidArgumentException('Service due time must be an exact UTC timestamp.');
        }
        $date = DateTimeImmutable::createFromFormat('!Y-m-d\\TH:i:s\\Z', $value, new DateTimeZone('UTC'));
        if (!$date || $date->format('Y-m-d\\TH:i:s\\Z') !== $value) {
            throw new InvalidArgumentException('Service due time is invalid.');
        }
        $database = $date->format('Y-m-d H:i:s');
        if ((int) $wpdb->get_var($wpdb->prepare('SELECT %s > UTC_TIMESTAMP(6)', $database)) !== 1) {
            throw new InvalidArgumentException('Service due time must be in the future.');
        }
        return $database;
    }
}
