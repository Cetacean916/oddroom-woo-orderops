<?php

defined('ABSPATH') || exit;

final class OddRoom_Installer
{
    public const SCHEMA_VERSION = '1.1.0';
    private const OPTION = 'oddroom_orderops_schema_version';

    public static function activate(): void
    {
        OddRoom_Dependencies::assertActivationReady();
        self::install();
    }

    public static function maybeUpgrade(): void
    {
        if (get_option(self::OPTION) !== self::SCHEMA_VERSION) {
            self::install();
        }
    }

    public static function install(): void
    {
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';

        $charset = $wpdb->get_charset_collate();
        $outbox = self::outboxTable();
        $leases = self::leaseTable();
        $faults = self::faultTable();

        $outboxSql = "CREATE TABLE {$outbox} (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            schema_version varchar(16) NOT NULL,
            shop_instance_id varchar(64) NOT NULL,
            run_id char(36) NOT NULL,
            event_key varchar(255) NOT NULL,
            order_id bigint(20) unsigned NOT NULL,
            event_type varchar(32) NOT NULL,
            occurred_at_utc datetime(6) NOT NULL,
            occurred_at_source varchar(64) NOT NULL,
            state_rank smallint(5) unsigned NOT NULL,
            payload_json longtext NOT NULL,
            payload_hash char(64) NOT NULL,
            status varchar(32) NOT NULL,
            processing_phase varchar(32) NOT NULL,
            attempt_count int(10) unsigned NOT NULL DEFAULT 0,
            automatic_attempt_count int(10) unsigned NOT NULL DEFAULT 0,
            max_attempts int(10) unsigned NOT NULL DEFAULT 6,
            manual_retry_count int(10) unsigned NOT NULL DEFAULT 0,
            manual_attempt_pending tinyint(1) unsigned NOT NULL DEFAULT 0,
            next_attempt_at datetime(6) NULL,
            action_id bigint(20) unsigned NULL,
            adapter_dispatch_state varchar(32) NOT NULL DEFAULT 'not_started',
            adapter_dispatch_attempt int(10) unsigned NULL,
            adapter_dispatched_at datetime(6) NULL,
            lock_token char(64) NULL,
            locked_at datetime(6) NULL,
            lock_expires_at datetime(6) NULL,
            last_attempt_at datetime(6) NULL,
            last_http_status smallint(5) unsigned NULL,
            error_code varchar(96) NULL,
            retryable tinyint(1) unsigned NULL,
            last_error varchar(500) NULL,
            remote_contact_id varchar(128) NULL,
            remote_deal_id varchar(128) NULL,
            slack_status varchar(32) NOT NULL,
            slack_message_ts varchar(64) NULL,
            operator_wait_reason varchar(96) NULL,
            operator_wait_epoch int(10) unsigned NOT NULL DEFAULT 0,
            resolved_operator_wait_epoch int(10) unsigned NOT NULL DEFAULT 0,
            last_operator_resolution varchar(64) NULL,
            operator_evidence_ref varchar(255) NULL,
            operator_resolved_at datetime(6) NULL,
            operator_resolved_by bigint(20) unsigned NULL,
            created_at datetime(6) NOT NULL,
            updated_at datetime(6) NOT NULL,
            processed_at datetime(6) NULL,
            PRIMARY KEY  (id),
            UNIQUE KEY event_key (event_key(191)),
            KEY order_events (shop_instance_id,order_id,state_rank),
            KEY queue_due (status,next_attempt_at),
            KEY action_id (action_id)
        ) ENGINE=InnoDB {$charset};";

        $leaseSql = "CREATE TABLE {$leases} (
            shop_instance_id varchar(64) NOT NULL,
            order_id bigint(20) unsigned NOT NULL,
            lease_token char(64) NOT NULL,
            holder_outbox_id bigint(20) unsigned NOT NULL,
            holder_action_id bigint(20) unsigned NOT NULL,
            holder_row_lock_token char(64) NOT NULL,
            acquired_at datetime(6) NOT NULL,
            expires_at datetime(6) NOT NULL,
            PRIMARY KEY  (shop_instance_id,order_id),
            KEY expires_at (expires_at),
            KEY holder_outbox (holder_outbox_id)
        ) ENGINE=InnoDB {$charset};";

        $faultSql = "CREATE TABLE {$faults} (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            run_id char(36) NOT NULL,
            fault_type varchar(64) NOT NULL,
            event_key_sha256 char(64) NOT NULL,
            enabled tinyint(1) unsigned NOT NULL DEFAULT 0,
            expires_at datetime(6) NOT NULL,
            created_by bigint(20) unsigned NOT NULL,
            created_at datetime(6) NOT NULL,
            disabled_at datetime(6) NULL,
            PRIMARY KEY  (id),
            UNIQUE KEY exact_fault (run_id,fault_type,event_key_sha256),
            KEY active_expiry (run_id,enabled,expires_at)
        ) ENGINE=InnoDB {$charset};";

        dbDelta($outboxSql);
        dbDelta($leaseSql);
        dbDelta($faultSql);

        if (!self::tablesAreTransactional()) {
            update_option('oddroom_orderops_health_error', 'DATABASE_ENGINE_UNSUPPORTED', false);
            throw new RuntimeException('OddRoom OrderOps requires transactional InnoDB tables.');
        }

        update_option(self::OPTION, self::SCHEMA_VERSION, false);
    }

    public static function outboxTable(): string
    {
        global $wpdb;
        return $wpdb->prefix . 'oddroom_orderops_outbox';
    }

    public static function leaseTable(): string
    {
        global $wpdb;
        return $wpdb->prefix . 'oddroom_orderops_order_leases';
    }

    public static function faultTable(): string
    {
        global $wpdb;
        return $wpdb->prefix . 'oddroom_orderops_fault_controls';
    }

    public static function tablesAreTransactional(): bool
    {
        global $wpdb;
        foreach ([self::outboxTable(), self::leaseTable(), self::faultTable()] as $table) {
            $engine = $wpdb->get_var($wpdb->prepare(
                'SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s',
                $table
            ));
            if (!is_string($engine) || strtoupper($engine) !== 'INNODB') {
                return false;
            }
        }
        return true;
    }
}
