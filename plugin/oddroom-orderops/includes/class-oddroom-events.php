<?php

defined('ABSPATH') || exit;

final class OddRoom_Events
{
    public static function boot(): void
    {
        add_action('woocommerce_checkout_order_processed', [self::class, 'captureCheckout'], 100, 1);
        add_action('woocommerce_store_api_checkout_order_processed', [self::class, 'captureStoreApi'], 100, 1);
        add_action('oddroom_orderops_capture_order_created', [self::class, 'captureCheckout'], 10, 1);
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
        try {
            $created = OddRoom_Repository::insertOrderCreated($order);
        } catch (Throwable $error) {
            update_option('oddroom_orderops_health_error', 'PAYLOAD_INVALID', false);
            return null;
        }
        if ($created['inserted']) {
            return OddRoom_Scheduler::scheduleBusiness((int) $created['row']->id);
        }
        return (int) ($created['row']->action_id ?? 0);
    }

    public static function captureStoreApi(WC_Order $order): ?int
    {
        return self::captureCheckout((int) $order->get_id());
    }
}
