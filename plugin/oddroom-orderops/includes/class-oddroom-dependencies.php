<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Dependencies
{
    public const MINIMUM_ACTION_SCHEDULER_VERSION = '4.0.0';
    public const SELECTED_CURRENCY = 'KRW';
    public const SELECTED_CURRENCY_PRECISION = 2;
    private const HEALTH_OPTION = 'oddroom_orderops_health_error';
    private const FAILURE_CODES = [
        'WOOCOMMERCE_UNAVAILABLE',
        'ACTION_SCHEDULER_NOT_READY',
        'ACTION_SCHEDULER_VERSION_UNSUPPORTED',
        'WOOCOMMERCE_CURRENCY_MISMATCH',
        'WOOCOMMERCE_CURRENCY_PRECISION_MISMATCH',
    ];

    public static function registerAdminNotice(): void
    {
        add_action('admin_notices', [self::class, 'renderAdminNotice']);
        add_action('network_admin_notices', [self::class, 'renderAdminNotice']);
    }

    public static function evaluate(
        bool $woocommerceReady,
        bool $actionSchedulerInitialized,
        ?string $actionSchedulerVersion,
        ?string $currency = self::SELECTED_CURRENCY,
        ?int $currencyPrecision = self::SELECTED_CURRENCY_PRECISION
    ): array {
        $code = null;
        if (!$woocommerceReady) {
            $code = 'WOOCOMMERCE_UNAVAILABLE';
        } elseif (!$actionSchedulerInitialized) {
            $code = 'ACTION_SCHEDULER_NOT_READY';
        } elseif ($actionSchedulerVersion === null
            || version_compare($actionSchedulerVersion, self::MINIMUM_ACTION_SCHEDULER_VERSION, '<')) {
            $code = 'ACTION_SCHEDULER_VERSION_UNSUPPORTED';
        } elseif ($currency !== self::SELECTED_CURRENCY) {
            $code = 'WOOCOMMERCE_CURRENCY_MISMATCH';
        } elseif ($currencyPrecision !== self::SELECTED_CURRENCY_PRECISION) {
            $code = 'WOOCOMMERCE_CURRENCY_PRECISION_MISMATCH';
        }

        return [
            'ok' => $code === null,
            'code' => $code,
            'woocommerce_ready' => $woocommerceReady,
            'action_scheduler_initialized' => $actionSchedulerInitialized,
            'action_scheduler_version' => $actionSchedulerVersion,
            'currency' => $currency,
            'currency_precision' => $currencyPrecision,
        ];
    }

    public static function status(): array
    {
        $woocommerceReady = class_exists('WooCommerce')
            && function_exists('WC')
            && defined('WC_VERSION');
        $initialized = false;
        if (class_exists('ActionScheduler') && method_exists('ActionScheduler', 'is_initialized')) {
            try {
                $initialized = ActionScheduler::is_initialized();
            } catch (Throwable $error) {
                $initialized = false;
            }
        }

        $version = null;
        if ($initialized && class_exists('ActionScheduler_Versions')) {
            try {
                $version = (string) ActionScheduler_Versions::instance()->latest_version();
            } catch (Throwable $error) {
                $version = null;
            }
        }

        $currency = null;
        $currencyPrecision = null;
        if ($woocommerceReady) {
            $currency = function_exists('get_woocommerce_currency')
                ? strtoupper((string) get_woocommerce_currency())
                : strtoupper((string) get_option('woocommerce_currency', ''));
            $currencyPrecision = function_exists('wc_get_price_decimals')
                ? (int) wc_get_price_decimals()
                : (int) get_option('woocommerce_price_num_decimals', -1);
        }

        $status = self::evaluate($woocommerceReady, $initialized, $version, $currency, $currencyPrecision);
        $status['woocommerce_version'] = defined('WC_VERSION') ? (string) WC_VERSION : null;
        return $status;
    }

    public static function assertActivationReady(): void
    {
        $status = self::status();
        self::persistHealth($status);
        if (!$status['ok']) {
            throw new RuntimeException(self::messageFor((string) $status['code']));
        }
    }

    public static function runtimeReady(): bool
    {
        $status = self::status();
        self::persistHealth($status);
        return (bool) $status['ok'];
    }

    public static function renderAdminNotice(): void
    {
        if (!current_user_can('activate_plugins')) {
            return;
        }
        $status = self::status();
        if ($status['ok']) {
            return;
        }

        echo '<div class="notice notice-error"><p><strong>OFFSET OrderOps is paused.</strong> '
            . esc_html(self::messageFor((string) $status['code']))
            . '</p></div>';
    }

    public static function messageFor(string $code): string
    {
        return match ($code) {
            'WOOCOMMERCE_UNAVAILABLE' => 'Install and activate WooCommerce, then reactivate OFFSET OrderOps. No order automation was started.',
            'ACTION_SCHEDULER_NOT_READY' => 'Action Scheduler did not initialize. Activate a supported WooCommerce or Action Scheduler distribution, then retry. No order automation was started.',
            'ACTION_SCHEDULER_VERSION_UNSUPPORTED' => 'Action Scheduler 4.0.0 or later is required. Update the loaded distribution, rerun the preflight, and then retry. No order automation was started.',
            'WOOCOMMERCE_CURRENCY_MISMATCH' => 'Set the WooCommerce currency to KRW, then retry. No order automation was started.',
            'WOOCOMMERCE_CURRENCY_PRECISION_MISMATCH' => 'Set the WooCommerce number of decimals to 2, then retry. No order automation was started.',
            default => 'Resolve the reported dependency failure before enabling order automation.',
        };
    }

    private static function persistHealth(array $status): void
    {
        $current = get_option(self::HEALTH_OPTION, '');
        if (!$status['ok']) {
            update_option(self::HEALTH_OPTION, (string) $status['code'], false);
        } elseif (in_array($current, self::FAILURE_CODES, true)) {
            update_option(self::HEALTH_OPTION, '', false);
        }
    }
}
