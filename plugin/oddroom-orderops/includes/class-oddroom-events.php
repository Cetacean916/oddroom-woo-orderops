<?php

defined('ABSPATH') || exit;

final class OddRoom_Events
{
    private const CANCELLED_AT_META = '_oddroom_orderops_cancelled_at_utc';

    public static function boot(): void
    {
        add_action('woocommerce_checkout_order_processed', [self::class, 'captureCheckout'], 100, 1);
        add_action('woocommerce_store_api_checkout_order_processed', [self::class, 'captureStoreApi'], 100, 1);
        add_action('oddroom_orderops_capture_order_created', [self::class, 'captureCheckout'], 10, 1);
        add_action('woocommerce_payment_complete', [self::class, 'capturePayment'], 100, 1);
        add_action('woocommerce_order_status_cancelled', [self::class, 'captureCancellation'], 1, 2);
        add_action('woocommerce_order_refunded', [self::class, 'captureRefund'], 100, 2);
    }

    public static function captureCheckout(int $orderId): ?int
    {
        if (!function_exists('wc_get_order')) {
            return null;
        }
        $order = wc_get_order($orderId);
        if (!$order instanceof WC_Order || in_array($order->get_status(), ['auto-draft', 'checkout-draft', 'trash'], true)) {
            return null;
        }
        if (OddRoom_Faults::isActiveForEvent(
            $orderId,
            'ORDER_CREATED',
            OddRoom_Faults::SUPPRESS_OUTBOX_INSERT
        )) {
            return null;
        }
        try {
            $created = OddRoom_Repository::insertOrderCreated($order);
        } catch (Throwable $error) {
            update_option('oddroom_orderops_health_error', 'PAYLOAD_INVALID', false);
            return null;
        }
        if ($created['inserted']) {
            if (OddRoom_Faults::isActiveForEvent(
                $orderId,
                'ORDER_CREATED',
                OddRoom_Faults::SUPPRESS_SCHEDULE
            )) {
                return null;
            }
            return OddRoom_Scheduler::scheduleBusiness((int) $created['row']->id);
        }
        return (int) ($created['row']->action_id ?? 0);
    }

    public static function captureStoreApi(WC_Order $order): ?int
    {
        return self::captureCheckout((int) $order->get_id());
    }

    public static function capturePayment(int $orderId): ?int
    {
        $order = wc_get_order($orderId);
        if (!$order instanceof WC_Order || !$order->is_paid()) {
            return null;
        }
        $paid = $order->get_date_paid();
        if (!$paid) {
            update_option('oddroom_orderops_health_error', 'PAYMENT_FACT_MISSING', false);
            return null;
        }
        return self::captureAndSchedule($order, 'PAYMENT_CONFIRMED', $paid, 'date_paid');
    }

    public static function captureCancellation(int $orderId, ?WC_Order $order = null): ?int
    {
        global $wpdb;
        $order = $order instanceof WC_Order ? $order : wc_get_order($orderId);
        if (!$order instanceof WC_Order || $order->get_status() !== 'cancelled') {
            return null;
        }

        $stored = (string) $order->get_meta(self::CANCELLED_AT_META, true);
        if ($stored === '') {
            $stored = (string) $wpdb->get_var(
                "SELECT DATE_FORMAT(UTC_TIMESTAMP(6), '%Y-%m-%dT%H:%i:%s.%fZ')"
            );
            if ($stored === '') {
                update_option('oddroom_orderops_health_error', 'CANCELLATION_FACT_MISSING', false);
                return null;
            }
            $order->update_meta_data(self::CANCELLED_AT_META, $stored);
            $order->save_meta_data();
        }

        try {
            $cancelledAt = OddRoom_Canonical_Payload::parseUtcTimestamp($stored);
        } catch (Throwable $error) {
            update_option('oddroom_orderops_health_error', 'CANCELLATION_FACT_INVALID', false);
            return null;
        }
        return self::captureAndSchedule(
            $order,
            'ORDER_CANCELLED',
            $cancelledAt,
            self::CANCELLED_AT_META
        );
    }

    public static function captureRefund(int $orderId, int $refundId): ?int
    {
        $order = wc_get_order($orderId);
        $refund = wc_get_order($refundId);
        if (!$order instanceof WC_Order || !$refund instanceof WC_Order_Refund) {
            return null;
        }
        try {
            $totalMinor = OddRoom_Canonical_Payload::toMinorUnits((string) $order->get_total());
            $refundedMinor = OddRoom_Canonical_Payload::toMinorUnits((string) $order->get_total_refunded());
        } catch (Throwable $error) {
            update_option('oddroom_orderops_health_error', 'PAYLOAD_INVALID', false);
            return null;
        }
        if ($totalMinor === '0'
            || OddRoom_Canonical_Payload::compareMinorUnits($refundedMinor, $totalMinor) < 0) {
            return null;
        }
        $created = $refund->get_date_created();
        if (!$created) {
            update_option('oddroom_orderops_health_error', 'REFUND_FACT_MISSING', false);
            return null;
        }
        return self::captureAndSchedule(
            $order,
            'ORDER_REFUNDED',
            $created,
            'full_refund_completion'
        );
    }

    private static function captureAndSchedule(
        WC_Order $order,
        string $eventType,
        DateTimeInterface $occurredAt,
        string $source
    ): ?int {
        if (OddRoom_Faults::isActiveForEvent(
            (int) $order->get_id(),
            $eventType,
            OddRoom_Faults::SUPPRESS_OUTBOX_INSERT
        )) {
            return null;
        }
        try {
            $created = OddRoom_Repository::insertEvent($order, $eventType, $occurredAt, $source);
        } catch (Throwable $error) {
            update_option('oddroom_orderops_health_error', 'PAYLOAD_INVALID', false);
            return null;
        }
        if ($created['inserted']) {
            if (OddRoom_Faults::isActiveForEvent(
                (int) $order->get_id(),
                $eventType,
                OddRoom_Faults::SUPPRESS_SCHEDULE
            )) {
                return null;
            }
            return OddRoom_Scheduler::scheduleBusiness((int) $created['row']->id);
        }
        return (int) ($created['row']->action_id ?? 0);
    }
}
