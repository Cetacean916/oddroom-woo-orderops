<?php

defined('ABSPATH') || exit;

final class OddRoom_Reconciliation
{
    public const HOOK = 'oddroom_orderops_reconcile_hourly';
    public const DEFAULT_WINDOW_DAYS = 7;
    public const PAGE_SIZE = 50;
    private const LAST_RESULT_OPTION = 'oddroom_orderops_last_reconciliation';
    private const LOCK_NAME = 'oddroom_orderops_reconcile_v1';

    public static function boot(): void
    {
        add_action(self::HOOK, [self::class, 'scheduledRun']);
        if (!wp_next_scheduled(self::HOOK)) {
            wp_schedule_event(time() + HOUR_IN_SECONDS, 'hourly', self::HOOK);
        }
    }

    public static function scheduledRun(): void
    {
        self::run();
    }

    public static function run(
        int $windowDays = self::DEFAULT_WINDOW_DAYS,
        int $pageSize = self::PAGE_SIZE
    ): array {
        global $wpdb;
        if (!function_exists('wc_get_orders')) {
            throw new RuntimeException('WooCommerce order query is unavailable.');
        }
        if ($windowDays < 1 || $windowDays > 30 || $pageSize !== self::PAGE_SIZE) {
            throw new InvalidArgumentException('Reconciliation bounds are invalid.');
        }
        $locked = (int) $wpdb->get_var($wpdb->prepare('SELECT GET_LOCK(%s,0)', self::LOCK_NAME));
        if ($locked !== 1) {
            throw new RuntimeException('RECONCILIATION_ALREADY_RUNNING');
        }

        try {
            $cutoff = (string) $wpdb->get_var($wpdb->prepare(
                'SELECT DATE_SUB(UTC_TIMESTAMP(6),INTERVAL %d DAY)',
                $windowDays
            ));
            if ($cutoff === '') {
                throw new RuntimeException('Database UTC cutoff is unavailable.');
            }
            $result = [
                'status' => 'PASS',
                'window_days' => $windowDays,
                'page_size' => $pageSize,
                'cutoff_utc' => $cutoff,
                'scanned_orders' => 0,
                'eligible_facts' => 0,
                'inserted_rows' => 0,
                'scheduled_rows' => 0,
                'noops' => 0,
                'failures' => [],
                'observed_at_utc' => gmdate('c'),
            ];

            $page = 1;
            do {
                $query = wc_get_orders([
                    'type' => 'shop_order',
                    'status' => array_keys(wc_get_order_statuses()),
                    'limit' => $pageSize,
                    'page' => $page,
                    'paginate' => true,
                    'orderby' => 'ID',
                    'order' => 'ASC',
                    'return' => 'objects',
                ]);
                $orders = is_object($query) && is_array($query->orders ?? null)
                    ? $query->orders
                    : [];
                $maxPages = is_object($query) ? max(1, (int) ($query->max_num_pages ?? 1)) : 1;
                foreach ($orders as $order) {
                    if (!$order instanceof WC_Order) {
                        continue;
                    }
                    $result['scanned_orders']++;
                    self::reconcileOrder($order, $cutoff, $result);
                }
                $page++;
            } while ($page <= $maxPages);

            if ($result['failures'] !== []) {
                $result['status'] = 'HOLD';
                update_option('oddroom_orderops_health_error', 'RECONCILIATION_FACT_FAILURE', false);
            }
            update_option(self::LAST_RESULT_OPTION, $result, false);
            return $result;
        } finally {
            $wpdb->get_var($wpdb->prepare('SELECT RELEASE_LOCK(%s)', self::LOCK_NAME));
        }
    }

    public static function lastResult(): ?array
    {
        $result = get_option(self::LAST_RESULT_OPTION);
        return is_array($result) ? $result : null;
    }

    public static function unschedule(): void
    {
        $timestamp = wp_next_scheduled(self::HOOK);
        while ($timestamp !== false) {
            wp_unschedule_event($timestamp, self::HOOK);
            $timestamp = wp_next_scheduled(self::HOOK);
        }
    }

    private static function reconcileOrder(WC_Order $order, string $cutoff, array &$result): void
    {
        $facts = [];
        $created = $order->get_date_created();
        if ($created) {
            $facts[] = ['ORDER_CREATED', $created, 'date_created'];
        }

        $paid = $order->get_date_paid();
        if ($paid) {
            $facts[] = ['PAYMENT_CONFIRMED', $paid, 'date_paid'];
        }

        $cancelledRaw = (string) $order->get_meta('_oddroom_orderops_cancelled_at_utc', true);
        if ($cancelledRaw !== '') {
            try {
                $facts[] = [
                    'ORDER_CANCELLED',
                    OddRoom_Canonical_Payload::parseUtcTimestamp($cancelledRaw),
                    '_oddroom_orderops_cancelled_at_utc',
                ];
            } catch (Throwable $error) {
                self::failure($result, (int) $order->get_id(), 'ORDER_CANCELLED', 'CANCELLATION_FACT_INVALID');
            }
        } elseif ((string) $order->get_status() === 'cancelled') {
            self::failure($result, (int) $order->get_id(), 'ORDER_CANCELLED', 'CANCELLATION_FACT_MISSING');
        }

        $refundFact = self::fullRefundCompletion($order);
        if ($refundFact instanceof DateTimeInterface) {
            $facts[] = ['ORDER_REFUNDED', $refundFact, 'full_refund_completion'];
        } elseif ($refundFact === false) {
            self::failure($result, (int) $order->get_id(), 'ORDER_REFUNDED', 'REFUND_FACT_MISSING');
        }

        foreach ($facts as [$eventType, $occurredAt, $source]) {
            $occurredDatabase = gmdate('Y-m-d H:i:s', $occurredAt->getTimestamp());
            if ($occurredDatabase < $cutoff) {
                continue;
            }
            $result['eligible_facts']++;
            try {
                $createdEvent = OddRoom_Repository::insertEvent($order, $eventType, $occurredAt, $source);
                $row = $createdEvent['row'];
                if ($createdEvent['inserted']) {
                    $result['inserted_rows']++;
                }
                if (OddRoom_Repository::shouldSchedule($row)) {
                    $actionId = OddRoom_Scheduler::scheduleBusiness((int) $row->id);
                    if ($actionId < 1) {
                        throw new RuntimeException('ACTION_SCHEDULE_FAILED');
                    }
                    $result['scheduled_rows']++;
                } else {
                    $result['noops']++;
                }
            } catch (Throwable $error) {
                self::failure(
                    $result,
                    (int) $order->get_id(),
                    $eventType,
                    sanitize_key($error->getMessage()) ?: 'reconciliation_failed'
                );
            }
        }
    }

    private static function fullRefundCompletion(WC_Order $order): DateTimeInterface|false|null
    {
        try {
            $totalMinor = OddRoom_Canonical_Payload::toMinorUnits((string) $order->get_total());
            $refundedMinor = OddRoom_Canonical_Payload::toMinorUnits((string) $order->get_total_refunded());
        } catch (Throwable $error) {
            return false;
        }
        if ($totalMinor === '0'
            || OddRoom_Canonical_Payload::compareMinorUnits($refundedMinor, $totalMinor) < 0) {
            return null;
        }
        $refunds = $order->get_refunds();
        usort($refunds, static function (WC_Order_Refund $left, WC_Order_Refund $right): int {
            $leftDate = $left->get_date_created();
            $rightDate = $right->get_date_created();
            $leftTime = $leftDate ? $leftDate->getTimestamp() : PHP_INT_MAX;
            $rightTime = $rightDate ? $rightDate->getTimestamp() : PHP_INT_MAX;
            return [$leftTime, (int) $left->get_id()] <=> [$rightTime, (int) $right->get_id()];
        });
        $runningMinor = '0';
        foreach ($refunds as $refund) {
            if (!$refund instanceof WC_Order_Refund) {
                continue;
            }
            $amount = (string) $refund->get_amount();
            if (str_starts_with($amount, '-')) {
                $amount = substr($amount, 1);
            }
            try {
                $runningMinor = OddRoom_Canonical_Payload::addMinorUnits(
                    $runningMinor,
                    OddRoom_Canonical_Payload::toMinorUnits($amount)
                );
            } catch (Throwable $error) {
                return false;
            }
            if (OddRoom_Canonical_Payload::compareMinorUnits($runningMinor, $totalMinor) >= 0) {
                return $refund->get_date_created() ?: false;
            }
        }
        return false;
    }

    private static function failure(array &$result, int $orderId, string $eventType, string $code): void
    {
        $result['status'] = 'HOLD';
        if (count($result['failures']) < 50) {
            $result['failures'][] = [
                'order_id' => $orderId,
                'event_type' => $eventType,
                'error_code' => strtoupper(substr(sanitize_key($code), 0, 96)),
            ];
        }
    }
}
