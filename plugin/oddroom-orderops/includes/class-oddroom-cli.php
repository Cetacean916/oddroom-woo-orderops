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
            WP_CLI::add_command('oddroom-orderops emit-event', [self::class, 'emitEvent']);
            WP_CLI::add_command('oddroom-orderops rows', [self::class, 'rows']);
            WP_CLI::add_command('oddroom-orderops recover', [self::class, 'recover']);
            WP_CLI::add_command('oddroom-orderops setup-storefront', [self::class, 'setupStorefront']);
            WP_CLI::add_command('oddroom-orderops reset-checkout-limit', [self::class, 'resetCheckoutLimit']);
            WP_CLI::add_command('oddroom-orderops reconcile', [self::class, 'reconcile']);
            WP_CLI::add_command('oddroom-orderops package-status', [self::class, 'packageStatus']);
            WP_CLI::add_command('oddroom-orderops demo-scenario', [self::class, 'demoScenario']);
            WP_CLI::add_command('oddroom-orderops reset-demo', [self::class, 'resetDemo']);
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
        $shape = sanitize_key((string) ($assocArgs['shape'] ?? 'simple'));
        if (!preg_match('/^[1-9][0-9]{0,7}\\.[0-9]{2}$/', $amount)) {
            WP_CLI::error('Use --amount with two decimal places.');
        }
        if (!in_array($shape, ['simple', 'variable', 'coupon'], true)) {
            WP_CLI::error('Use --shape=simple, variable, or coupon.');
        }

        $fixture = self::createProductFixture($shape, $alias, $amount);
        $product = $fixture['product'];
        $productId = (int) $fixture['product_id'];

        $order = wc_create_order(['status' => 'pending', 'created_via' => 'oddroom-orderops-cli']);
        $order->set_currency('KRW');
        $order->set_billing_email('pf07+' . $alias . '@example.com');
        $order->set_billing_first_name('Synthetic-' . strtoupper($alias));
        $order->set_billing_last_name('Buyer');
        $order->add_product($product, 1);
        if (is_string($fixture['coupon_code'])) {
            $applied = $order->apply_coupon($fixture['coupon_code']);
            if (is_wp_error($applied)) {
                WP_CLI::error('Synthetic coupon application failed.');
            }
        }
        $order->calculate_totals();
        $order->save();
        do_action('oddroom_orderops_capture_order_created', (int) $order->get_id());

        $row = OddRoom_Repository::findEvent((int) $order->get_id(), 'ORDER_CREATED');
        if (!$row) {
            WP_CLI::error('ORDER_CREATED outbox row was not created.');
        }
        WP_CLI::line(wp_json_encode([
            'order_id' => (int) $order->get_id(),
            'product_id' => (int) $productId,
            'variation_id' => (int) $fixture['variation_id'],
            'shape' => $shape,
            'coupon_applied' => is_string($fixture['coupon_code']),
            'outbox_id' => (int) $row->id,
            'payload_hash' => (string) $row->payload_hash,
            'action_id' => $row->action_id === null ? null : (int) $row->action_id,
        ], JSON_UNESCAPED_SLASHES));
    }

    public static function emitEvent(array $args, array $assocArgs): void
    {
        $orderId = (int) ($args[0] ?? 0);
        $eventType = strtoupper((string) ($args[1] ?? ''));
        $order = wc_get_order($orderId);
        if (!$order instanceof WC_Order) {
            WP_CLI::error('A valid WooCommerce order ID is required.');
        }
        if (!in_array($eventType, ['PAYMENT_CONFIRMED', 'ORDER_CANCELLED', 'ORDER_REFUNDED'], true)) {
            WP_CLI::error('Use PAYMENT_CONFIRMED, ORDER_CANCELLED, or ORDER_REFUNDED.');
        }

        if ($eventType === 'PAYMENT_CONFIRMED') {
            $order->payment_complete('pf07-synthetic-' . wp_generate_uuid4());
        } elseif ($eventType === 'ORDER_CANCELLED') {
            $order->update_status('cancelled', 'PF07 synthetic cancellation fixture.', true);
        } else {
            if (!$order->is_paid()) {
                $order->payment_complete('pf07-synthetic-' . wp_generate_uuid4());
                $order = wc_get_order($orderId);
            }
            $refund = wc_create_refund([
                'order_id' => $orderId,
                'amount' => (string) $order->get_total(),
                'reason' => 'PF07 synthetic full-refund fixture.',
                'refund_payment' => false,
                'restock_items' => false,
            ]);
            if (is_wp_error($refund)) {
                WP_CLI::error('Synthetic full refund failed: ' . $refund->get_error_code());
            }
        }

        $row = OddRoom_Repository::findEvent($orderId, $eventType);
        if (!$row) {
            WP_CLI::error($eventType . ' outbox row was not created.');
        }
        WP_CLI::line(wp_json_encode([
            'order_id' => $orderId,
            'event_type' => $eventType,
            'outbox_id' => (int) $row->id,
            'state_rank' => (int) $row->state_rank,
            'occurred_at_source' => (string) $row->occurred_at_source,
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

    public static function setupStorefront(array $args, array $assocArgs): void
    {
        $result = OddRoom_Storefront::installDemoStore();
        WP_CLI::line(wp_json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    }

    public static function resetCheckoutLimit(array $args, array $assocArgs): void
    {
        if (!OddRoom_Repository::testMode()
            || get_option('oddroom_orderops_checkout_control_mode') !== 'ON_DEMAND_ONLY') {
            WP_CLI::error('Synthetic checkout reset is unavailable outside ON_DEMAND_ONLY test mode.');
        }

        global $wpdb;
        $deleted = $wpdb->query($wpdb->prepare(
            "DELETE FROM {$wpdb->options} WHERE option_name LIKE %s",
            $wpdb->esc_like(OddRoom_Storefront::checkoutRateOptionPrefix()) . '%'
        ));
        if ($deleted === false) {
            WP_CLI::error('Synthetic checkout rate-limit reset failed.');
        }

        WP_CLI::line(wp_json_encode([
            'status' => 'PASS',
            'scope' => 'SYNTHETIC_CHECKOUT_RATE_LIMIT_ONLY',
            'deleted_option_count' => $deleted,
        ], JSON_UNESCAPED_SLASHES));
    }

    public static function reconcile(array $args, array $assocArgs): void
    {
        $result = OddRoom_Reconciliation::run();
        WP_CLI::line(wp_json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
        if (($result['status'] ?? null) !== 'PASS') {
            WP_CLI::error('Reconciliation reported a fact failure.');
        }
    }

    public static function packageStatus(array $args, array $assocArgs): void
    {
        WP_CLI::line(wp_json_encode(OddRoom_Package::setupState(), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    }

    public static function demoScenario(array $args, array $assocArgs): void
    {
        $scenario = OddRoom_Package::setScenario(sanitize_key((string) ($args[0] ?? '')));
        WP_CLI::line(wp_json_encode([
            'status' => 'PASS',
            'mode' => OddRoom_Package::mode(),
            'scenario' => $scenario,
        ], JSON_UNESCAPED_SLASHES));
    }

    public static function resetDemo(array $args, array $assocArgs): void
    {
        $confirmation = (string) ($assocArgs['confirm'] ?? '');
        $administratorId = 0;
        $administratorLogin = getenv('PF07_ADMIN_USER');
        if (is_string($administratorLogin) && $administratorLogin !== '') {
            $administrator = get_user_by('login', $administratorLogin);
            if ($administrator instanceof WP_User) {
                $administratorId = (int) $administrator->ID;
            }
        }
        $record = OddRoom_Package::resetDemo($confirmation, $administratorId);
        WP_CLI::line(wp_json_encode($record, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    }

    private static function databaseUtc(): string
    {
        global $wpdb;
        return (string) $wpdb->get_var('SELECT DATE_FORMAT(UTC_TIMESTAMP(6), "%Y-%m-%dT%H:%i:%s.%fZ")');
    }

    private static function createProductFixture(string $shape, string $alias, string $amount): array
    {
        $name = 'OFFSET Synthetic ' . strtoupper($alias);
        $sku = 'PF07-' . strtoupper($alias) . '-' . wp_rand(1000, 9999);
        $couponCode = null;
        $variationId = 0;

        if ($shape === 'variable') {
            $parent = new WC_Product_Variable();
            $parent->set_name($name);
            $parent->set_sku($sku);
            $parent->set_status('publish');
            $parent->set_catalog_visibility('hidden');
            $attribute = new WC_Product_Attribute();
            $attribute->set_name('Format');
            $attribute->set_options(['Standard', 'Plus']);
            $attribute->set_visible(true);
            $attribute->set_variation(true);
            $parent->set_attributes([$attribute]);
            $productId = (int) $parent->save();

            $variation = new WC_Product_Variation();
            $variation->set_parent_id($productId);
            $variation->set_attributes(['format' => 'Standard']);
            $variation->set_regular_price($amount);
            $variation->set_status('publish');
            $variationId = (int) $variation->save();
            $product = wc_get_product($variationId);
        } else {
            $product = new WC_Product_Simple();
            $product->set_name($name);
            $product->set_sku($sku);
            $product->set_regular_price($amount);
            $product->set_status('publish');
            $product->set_catalog_visibility('hidden');
            $productId = (int) $product->save();
        }

        if (!$product instanceof WC_Product || $productId <= 0) {
            WP_CLI::error('Synthetic product fixture failed.');
        }
        if ($shape === 'coupon') {
            $couponCode = 'pf07-' . $alias . '-' . wp_rand(1000, 9999);
            $coupon = new WC_Coupon();
            $coupon->set_code($couponCode);
            $coupon->set_discount_type('fixed_cart');
            $coupon->set_amount('1000.00');
            $coupon->set_individual_use(true);
            if ((int) $coupon->save() <= 0) {
                WP_CLI::error('Synthetic coupon fixture failed.');
            }
        }

        return [
            'product' => $product,
            'product_id' => $productId,
            'variation_id' => $variationId,
            'coupon_code' => $couponCode,
        ];
    }
}
