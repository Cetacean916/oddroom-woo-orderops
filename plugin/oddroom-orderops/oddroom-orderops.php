<?php
/**
 * Plugin Name: OddRoom OrderOps
 * Description: Recoverable WooCommerce order delivery to a signed n8n adapter.
 * Version: 0.2.0
 * Requires PHP: 8.1
 * Requires Plugins: woocommerce
 * License: GPL-2.0-or-later
 */

defined('ABSPATH') || exit;

require_once __DIR__ . '/includes/class-oddroom-canonical-payload.php';
require_once __DIR__ . '/includes/class-oddroom-signature.php';
require_once __DIR__ . '/includes/class-oddroom-state-machine.php';
require_once __DIR__ . '/includes/class-oddroom-retry-policy.php';
require_once __DIR__ . '/includes/class-oddroom-dependencies.php';
require_once __DIR__ . '/includes/class-oddroom-installer.php';
require_once __DIR__ . '/includes/class-oddroom-repository.php';
require_once __DIR__ . '/includes/class-oddroom-scheduler.php';
require_once __DIR__ . '/includes/class-oddroom-worker.php';
require_once __DIR__ . '/includes/class-oddroom-recovery.php';
require_once __DIR__ . '/includes/class-oddroom-faults.php';
require_once __DIR__ . '/includes/class-oddroom-events.php';
require_once __DIR__ . '/includes/class-oddroom-reconciliation.php';
require_once __DIR__ . '/includes/class-oddroom-storefront.php';
require_once __DIR__ . '/includes/class-oddroom-admin.php';
require_once __DIR__ . '/includes/class-oddroom-private-admin.php';
require_once __DIR__ . '/includes/class-oddroom-cli.php';

OddRoom_Dependencies::registerAdminNotice();

register_activation_hook(__FILE__, ['OddRoom_Installer', 'activate']);

add_action('before_woocommerce_init', static function (): void {
    if (class_exists('Automattic\\WooCommerce\\Utilities\\FeaturesUtil')) {
        Automattic\WooCommerce\Utilities\FeaturesUtil::declare_compatibility(
            'custom_order_tables',
            __FILE__,
            true
        );
    }
});

$oddroomOrderOpsBoot = static function (): void {
    static $booted = false;
    if ($booted || !OddRoom_Dependencies::runtimeReady()) {
        return;
    }
    $booted = true;
    OddRoom_Installer::maybeUpgrade();
    OddRoom_Private_Admin::boot();
    OddRoom_Scheduler::boot();
    OddRoom_Events::boot();
    OddRoom_Faults::boot();
    OddRoom_Reconciliation::boot();
    OddRoom_Storefront::boot();
    OddRoom_Admin::boot();
    OddRoom_CLI::boot();
};
add_action('action_scheduler_init', $oddroomOrderOpsBoot, 20);
add_action('init', $oddroomOrderOpsBoot, 20);

register_deactivation_hook(__FILE__, static function (): void {
    OddRoom_Reconciliation::unschedule();
    wp_clear_scheduled_hook('oddroom_orderops_fault_cleanup');
});
