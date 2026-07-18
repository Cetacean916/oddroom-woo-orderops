<?php

defined('ABSPATH') || exit;

final class OddRoom_Faults
{
    public const BEFORE_SLACK_POST = 'BEFORE_SLACK_POST';
    public const SUPPRESS_OUTBOX_INSERT = 'SUPPRESS_OUTBOX_INSERT';
    public const SUPPRESS_SCHEDULE = 'SUPPRESS_SCHEDULE';
    private const TYPES = [
        self::BEFORE_SLACK_POST,
        self::SUPPRESS_OUTBOX_INSERT,
        self::SUPPRESS_SCHEDULE,
    ];

    public static function boot(): void
    {
        add_action('rest_api_init', [self::class, 'registerRest']);
        add_action('oddroom_orderops_fault_cleanup', [self::class, 'cleanupExpired']);
        if (!wp_next_scheduled('oddroom_orderops_fault_cleanup')) {
            wp_schedule_event(time() + HOUR_IN_SECONDS, 'hourly', 'oddroom_orderops_fault_cleanup');
        }
    }

    public static function registerRest(): void
    {
        register_rest_route('oddroom-orderops/v1', '/fault-before-slack', [
            'methods' => WP_REST_Server::CREATABLE,
            'permission_callback' => '__return_true',
            'callback' => [self::class, 'restStatus'],
        ]);
    }

    public static function restStatus(WP_REST_Request $request): WP_REST_Response
    {
        $params = $request->get_json_params();
        $eventKey = is_array($params) && is_string($params['event_key'] ?? null)
            ? $params['event_key']
            : '';
        $runId = is_array($params) && is_string($params['run_id'] ?? null)
            ? $params['run_id']
            : '';
        $timestamp = (string) $request->get_header('x-oddroom-timestamp');
        $signature = (string) $request->get_header('x-oddroom-fault-signature');
        if (!self::validRestSignature($timestamp, $eventKey, $runId, $signature)) {
            return new WP_REST_Response(['authorized' => false, 'active' => false], 401);
        }
        return new WP_REST_Response([
            'authorized' => true,
            'active' => self::isActive($eventKey, $runId, self::BEFORE_SLACK_POST),
        ], 200);
    }

    public static function enable(
        int $orderId,
        string $eventType,
        string $faultType,
        int $minutes,
        int $administratorId
    ): array {
        global $wpdb;
        if (!OddRoom_Repository::testMode()) {
            throw new RuntimeException('Fault controls are staging-only.');
        }
        if (!in_array($faultType, self::TYPES, true)) {
            throw new InvalidArgumentException('Unsupported fault type.');
        }
        OddRoom_Canonical_Payload::rankFor($eventType);
        if ($orderId <= 0 || $administratorId <= 0 || $minutes < 1 || $minutes > 30) {
            throw new InvalidArgumentException('Fault control bounds are invalid.');
        }
        $runId = OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_RUN_ID');
        $eventKey = self::eventKey($orderId, $eventType);
        $hash = hash('sha256', $eventKey);
        $table = OddRoom_Installer::faultTable();
        $written = $wpdb->query($wpdb->prepare(
            "INSERT INTO {$table}
             (run_id,fault_type,event_key_sha256,enabled,expires_at,created_by,created_at,disabled_at)
             VALUES (%s,%s,%s,1,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL %d MINUTE),%d,UTC_TIMESTAMP(6),NULL)
             ON DUPLICATE KEY UPDATE enabled=1,
                 expires_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL %d MINUTE),
                 created_by=VALUES(created_by),created_at=UTC_TIMESTAMP(6),disabled_at=NULL",
            $runId,
            $faultType,
            $hash,
            $minutes,
            $administratorId,
            $minutes
        ));
        if ($written === false) {
            throw new RuntimeException('Fault control write failed.');
        }
        $row = $wpdb->get_row($wpdb->prepare(
            "SELECT id,fault_type,enabled,expires_at FROM {$table}
             WHERE run_id=%s AND fault_type=%s AND event_key_sha256=%s",
            $runId,
            $faultType,
            $hash
        ));
        if (!$row || (int) $row->enabled !== 1) {
            throw new RuntimeException('Fault control read-back failed.');
        }
        return [
            'id' => (int) $row->id,
            'fault_type' => (string) $row->fault_type,
            'event_key_sha256' => $hash,
            'expires_at' => (string) $row->expires_at,
        ];
    }

    public static function isActive(string $eventKey, string $runId, string $faultType): bool
    {
        global $wpdb;
        if (!in_array($faultType, self::TYPES, true) || !hash_equals(
            OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_RUN_ID'),
            $runId
        )) {
            return false;
        }
        $table = OddRoom_Installer::faultTable();
        return (int) $wpdb->get_var($wpdb->prepare(
            "SELECT COUNT(*) FROM {$table}
             WHERE run_id=%s AND fault_type=%s AND event_key_sha256=%s
               AND enabled=1 AND expires_at>UTC_TIMESTAMP(6)",
            $runId,
            $faultType,
            hash('sha256', $eventKey)
        )) === 1;
    }

    public static function isActiveForEvent(int $orderId, string $eventType, string $faultType): bool
    {
        return self::isActive(
            self::eventKey($orderId, $eventType),
            OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_RUN_ID'),
            $faultType
        );
    }

    public static function endRun(string $runId): int
    {
        global $wpdb;
        $expected = OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_RUN_ID');
        if (!hash_equals($expected, $runId)) {
            throw new InvalidArgumentException('RUN_ID mismatch.');
        }
        $table = OddRoom_Installer::faultTable();
        $wpdb->query('START TRANSACTION');
        try {
            $updated = $wpdb->query($wpdb->prepare(
                "UPDATE {$table} SET enabled=0,
                     expires_at=LEAST(expires_at,UTC_TIMESTAMP(6)),disabled_at=UTC_TIMESTAMP(6)
                 WHERE run_id=%s AND enabled=1",
                $runId
            ));
            if ($updated === false) {
                throw new RuntimeException('Fault-control end-run update failed.');
            }
            $remaining = (int) $wpdb->get_var($wpdb->prepare(
                "SELECT COUNT(*) FROM {$table}
                 WHERE run_id=%s AND enabled=1 AND expires_at>UTC_TIMESTAMP(6)",
                $runId
            ));
            if ($remaining !== 0) {
                throw new RuntimeException('Fault controls remain active.');
            }
            $wpdb->query('COMMIT');
            return (int) $updated;
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            throw $error;
        }
    }

    public static function cleanupExpired(): int
    {
        global $wpdb;
        $table = OddRoom_Installer::faultTable();
        $updated = $wpdb->query(
            "UPDATE {$table} SET enabled=0,disabled_at=COALESCE(disabled_at,UTC_TIMESTAMP(6))
             WHERE enabled=1 AND expires_at<=UTC_TIMESTAMP(6)"
        );
        return $updated === false ? 0 : (int) $updated;
    }

    public static function activeRows(): array
    {
        global $wpdb;
        $table = OddRoom_Installer::faultTable();
        return $wpdb->get_results(
            "SELECT id,fault_type,event_key_sha256,expires_at
             FROM {$table} WHERE enabled=1 AND expires_at>UTC_TIMESTAMP(6)
             ORDER BY expires_at ASC,id ASC"
        );
    }

    private static function eventKey(int $orderId, string $eventType): string
    {
        $shopId = OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_SHOP_INSTANCE_ID');
        return "v1:{$shopId}:{$orderId}:{$eventType}";
    }

    private static function validRestSignature(
        string $timestamp,
        string $eventKey,
        string $runId,
        string $signature
    ): bool {
        if (!preg_match('/^[1-9][0-9]{0,10}$/', $timestamp)
            || abs(time() - (int) $timestamp) > 60
            || !preg_match('/^v1=[0-9a-f]{64}$/', $signature)
            || !preg_match('/^[0-9a-f-]{36}$/', $runId)
            || strlen($eventKey) > 255) {
            return false;
        }
        $secret = trim((string) getenv('ODDROOM_WEBHOOK_HMAC_KEY'));
        if ($secret === '') {
            return false;
        }
        $base = "fault-status.{$timestamp}.{$eventKey}.{$runId}";
        $expected = 'v1=' . hash_hmac('sha256', $base, $secret);
        return hash_equals($expected, $signature);
    }
}
