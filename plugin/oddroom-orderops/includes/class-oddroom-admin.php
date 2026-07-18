<?php

defined('ABSPATH') || exit;

final class OddRoom_Admin
{
    public static function boot(): void
    {
        add_action('admin_menu', [self::class, 'menu']);
    }

    public static function menu(): void
    {
        add_submenu_page(
            'woocommerce',
            'OddRoom OrderOps',
            'OrderOps',
            'manage_woocommerce',
            'oddroom-orderops',
            [self::class, 'render']
        );
    }

    public static function render(): void
    {
        if (!current_user_can('manage_woocommerce')) {
            wp_die(esc_html__('You do not have permission to view this page.', 'oddroom-orderops'));
        }
        $identity = OddRoom_Scheduler::runtimeIdentity();
        $health = (string) get_option('oddroom_orderops_health_error', '');
        echo '<div class="wrap"><h1>OddRoom OrderOps</h1>';
        echo '<p><strong>Schema:</strong> ' . esc_html(OddRoom_Installer::SCHEMA_VERSION) . ' · ';
        echo '<strong>Queue:</strong> FOREGROUND_WP_CLI · ';
        echo '<strong>Action Scheduler:</strong> ' . esc_html((string) ($identity['version'] ?? 'unavailable')) . ' · ';
        echo '<strong>Health:</strong> ' . esc_html($health === '' ? 'PASS' : $health) . '</p>';
        echo '<div style="overflow-x:auto"><table class="widefat striped"><thead><tr>';
        foreach (['ID','Event','Order','Status','Phase','Attempts','HTTP','Error Code','Sanitized Error','Action','Dispatch','Lock','Deal','Updated'] as $heading) {
            echo '<th>' . esc_html($heading) . '</th>';
        }
        echo '</tr></thead><tbody>';
        foreach (OddRoom_Repository::all(100) as $row) {
            $deal = $row->remote_deal_id ? '…' . substr((string) $row->remote_deal_id, -6) : '—';
            $lock = $row->lock_token ? 'locked' : 'free';
            echo '<tr>';
            foreach ([
                $row->id, $row->event_type, $row->order_id, $row->status, $row->processing_phase,
                $row->attempt_count . '/' . $row->automatic_attempt_count . '/' . $row->max_attempts,
                $row->last_http_status ?? '—', $row->error_code ?? '—', $row->last_error ?? '—',
                $row->action_id ?? '—',
                $row->adapter_dispatch_state . '/' . ($row->adapter_dispatch_attempt ?? '—'),
                $lock, $deal, $row->updated_at,
            ] as $value) {
                echo '<td>' . esc_html((string) $value) . '</td>';
            }
            echo '</tr>';
        }
        echo '</tbody></table></div></div>';
    }
}
