<?php

defined('WP_UNINSTALL_PLUGIN') || exit;

if (!defined('ODDROOM_ORDEROPS_REMOVE_DATA') || ODDROOM_ORDEROPS_REMOVE_DATA !== true) {
    return;
}

global $wpdb;

if (function_exists('as_unschedule_all_actions')) {
    as_unschedule_all_actions('oddroom_orderops_process', [], 'oddroom-orderops');
}
wp_clear_scheduled_hook('oddroom_orderops_reconcile_hourly');
wp_clear_scheduled_hook('oddroom_orderops_fault_cleanup');

foreach ([
    $wpdb->prefix . 'oddroom_orderops_order_leases',
    $wpdb->prefix . 'oddroom_orderops_fault_controls',
    $wpdb->prefix . 'oddroom_orderops_outbox',
] as $table) {
    $wpdb->query("DROP TABLE IF EXISTS {$table}");
}

foreach ([
    'oddroom_orderops_schema_version',
    'oddroom_orderops_health_error',
    'oddroom_orderops_as_preflight',
    'oddroom_orderops_last_reconciliation',
    'oddroom_orderops_last_reachability',
    'oddroom_orderops_last_successful_event',
    'oddroom_orderops_mail_capture',
    'oddroom_orderops_checkout_control_mode',
    'oddroom_orderops_store_image_id',
] as $option) {
    delete_option($option);
}
