<?php

defined('ABSPATH') || exit;

final class OddRoom_CLI
{
    public static function boot(): void
    {
        if (defined('WP_CLI') && WP_CLI) {
            WP_CLI::add_command('oddroom-orderops preflight', [self::class, 'preflight']);
            WP_CLI::add_command('oddroom-orderops environment', [self::class, 'environment']);
            WP_CLI::add_command('oddroom-orderops create-order', [self::class, 'createOrder']);
            WP_CLI::add_command('oddroom-orderops rows', [self::class, 'rows']);
            WP_CLI::add_command('oddroom-orderops recover', [self::class, 'recover']);
        }
    }

    public static function preflight(array $args, array $assocArgs): void
    {
        $record = OddRoom_Scheduler::runPreflight();
        WP_CLI::line(wp_json_encode($record, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
        if (($record['status'] ?? null) !== 'PASS') {
            WP_CLI::error('Action Scheduler preflight failed.');
        }
    }

    public static function environment(array $args, array $assocArgs): void
    {
        $woocommerce = defined('WC_VERSION') ? WC_VERSION : null;
        $identity = OddRoom_Scheduler::runtimeIdentity();
        $record = [
            'wordpress' => get_bloginfo('version'),
            'woocommerce' => $woocommerce,
            'php' => PHP_VERSION,
            'action_scheduler' => $identity,
            'tables_transactional' => OddRoom_Installer::tablesAreTransactional(),
            'database_utc' => self::databaseUtc(),
        ];
        WP_CLI::line(wp_json_encode($record, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    }

    public static function createOrder(array $args, array $assocArgs): void
    {
        if (!class_exists('WC_Order')) {
            WP_CLI::error('WooCommerce is unavailable.');
        }
        $alias = sanitize_key((string) ($assocArgs['alias'] ?? 'alpha'));
        $amount = (string) ($assocArgs['amount'] ?? '15000.00');
        if (!preg_match('/^[1-9][0-9]{0,7}\\.[0-9]{2}$/', $amount)) {
            WP_CLI::error('Use --amount with two decimal places.');
        }

        $product = new WC_Product_Simple();
        $product->set_name('OddRoom Synthetic ' . strtoupper($alias));
        $product->set_sku('PF07-' . strtoupper($alias) . '-' . wp_rand(1000, 9999));
        $product->set_regular_price($amount);
        $product->set_status('publish');
        $productId = $product->save();

        $order = wc_create_order(['status' => 'pending', 'created_via' => 'oddroom-orderops-cli']);
        $order->set_currency('KRW');
        $order->set_billing_email('pf07+' . $alias . '@example.com');
        $order->set_billing_first_name('Synthetic-' . strtoupper($alias));
        $order->set_billing_last_name('Buyer');
        $order->add_product(wc_get_product($productId), 1);
        $order->calculate_totals();
        $order->save();
        do_action('oddroom_orderops_capture_order_created', (int) $order->get_id());

        $row = OddRoom_Repository::insertOrderCreated($order)['row'];
        WP_CLI::line(wp_json_encode([
            'order_id' => (int) $order->get_id(),
            'product_id' => (int) $productId,
            'outbox_id' => (int) $row->id,
            'payload_hash' => (string) $row->payload_hash,
            'action_id' => $row->action_id === null ? null : (int) $row->action_id,
        ], JSON_UNESCAPED_SLASHES));
    }

    public static function rows(array $args, array $assocArgs): void
    {
        $rows = array_map(static function (object $row): array {
            return [
                'id' => (int) $row->id,
                'order_id' => (int) $row->order_id,
                'event_type' => (string) $row->event_type,
                'payload_hash' => (string) $row->payload_hash,
                'status' => (string) $row->status,
                'phase' => (string) $row->processing_phase,
                'attempt_count' => (int) $row->attempt_count,
                'automatic_attempt_count' => (int) $row->automatic_attempt_count,
                'action_id' => $row->action_id === null ? null : (int) $row->action_id,
                'dispatch_state' => (string) $row->adapter_dispatch_state,
                'http_status' => $row->last_http_status === null ? null : (int) $row->last_http_status,
                'error_code' => $row->error_code,
                'deal_id_masked' => $row->remote_deal_id ? '…' . substr((string) $row->remote_deal_id, -6) : null,
            ];
        }, OddRoom_Repository::all(500));
        WP_CLI::line(wp_json_encode($rows, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    }

    public static function recover(array $args, array $assocArgs): void
    {
        $results = OddRoom_Recovery::sweep((int) ($assocArgs['limit'] ?? 50));
        WP_CLI::line(wp_json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    }

    private static function databaseUtc(): string
    {
        global $wpdb;
        return (string) $wpdb->get_var('SELECT DATE_FORMAT(UTC_TIMESTAMP(6), "%Y-%m-%dT%H:%i:%s.%fZ")');
    }
}
