<?php

defined('ABSPATH') || exit;

final class OddRoom_Package
{
    public const DEMO_MODE = 'DEMO_MODE';
    public const CONNECTED_MODE = 'CONNECTED_MODE';
    private const MODE_OPTION = 'oddroom_orderops_package_mode';
    private const SCENARIO_OPTION = 'oddroom_orderops_demo_scenario';
    private const SETUP_OPTION = 'oddroom_orderops_package_setup';
    private const ADAPTER_STATE_OPTION = 'oddroom_orderops_demo_adapter_state';
    private const LAST_RESET_OPTION = 'oddroom_orderops_last_demo_reset';
    private const RESET_CONFIRMATION = 'RESET PF07 DEMO';

    public static function boot(): void
    {
        add_action('rest_api_init', static function (): void {
            register_rest_route('oddroom-orderops/v1', '/demo-adapter', [
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => [self::class, 'handleDemoAdapter'],
                'permission_callback' => '__return_true',
            ]);
        });
    }

    public static function mode(): string
    {
        $value = (string) get_option(self::MODE_OPTION, self::DEMO_MODE);
        return in_array($value, [self::DEMO_MODE, self::CONNECTED_MODE], true)
            ? $value
            : self::DEMO_MODE;
    }

    public static function scenario(): string
    {
        $value = (string) get_option(self::SCENARIO_OPTION, 'normal');
        return in_array($value, ['normal', 'fail_once', 'terminal', 'operator_review'], true)
            ? $value
            : 'normal';
    }

    public static function setupState(): array
    {
        $stored = get_option(self::SETUP_OPTION, []);
        if (!is_array($stored)) {
            $stored = [];
        }
        $remote = self::adapterState();
        return [
            'mode' => self::mode(),
            'scenario' => self::scenario(),
            'hubspot_alias' => self::boundedAlias($stored['hubspot_alias'] ?? 'PF07HubSpotRuntime1'),
            'slack_alias' => self::boundedAlias($stored['slack_alias'] ?? 'PF07SlackRuntime1'),
            'hubspot_configured' => filter_var(getenv('PF07_HUBSPOT_CONFIGURED'), FILTER_VALIDATE_BOOLEAN),
            'slack_configured' => filter_var(getenv('PF07_SLACK_CONFIGURED'), FILTER_VALIDATE_BOOLEAN),
            'demo_contacts' => count($remote['contacts']),
            'demo_deals' => count($remote['deals']),
            'demo_slack_messages' => count($remote['slack']),
            'demo_executions' => (int) $remote['executions'],
            'last_demo_event_ref' => (string) ($remote['last_event_ref'] ?? ''),
            'last_reset' => get_option(self::LAST_RESET_OPTION, null),
        ];
    }

    public static function updateSetup(string $mode, string $hubspotAlias, string $slackAlias): array
    {
        if (!in_array($mode, [self::DEMO_MODE, self::CONNECTED_MODE], true)) {
            throw new InvalidArgumentException('PACKAGE_MODE_INVALID');
        }
        $hubspotAlias = self::boundedAlias($hubspotAlias);
        $slackAlias = self::boundedAlias($slackAlias);
        if ($hubspotAlias === '' || $slackAlias === '') {
            throw new InvalidArgumentException('CREDENTIAL_ALIAS_REQUIRED');
        }
        update_option(self::MODE_OPTION, $mode, false);
        update_option(self::SETUP_OPTION, [
            'hubspot_alias' => $hubspotAlias,
            'slack_alias' => $slackAlias,
            'updated_at_utc' => gmdate('c'),
        ], false);
        return self::setupState();
    }

    public static function setScenario(string $scenario): string
    {
        if (!in_array($scenario, ['normal', 'fail_once', 'terminal', 'operator_review'], true)) {
            throw new InvalidArgumentException('DEMO_SCENARIO_INVALID');
        }
        if (self::mode() !== self::DEMO_MODE || !OddRoom_Repository::testMode()) {
            throw new RuntimeException('DEMO_SCENARIO_UNAVAILABLE');
        }
        update_option(self::SCENARIO_OPTION, $scenario, false);
        return $scenario;
    }

    public static function controlSignature(
        int $timestamp,
        string $eventKey,
        string $scenario,
        int $attempt,
        string $secret
    ): string {
        return 'v1=' . hash_hmac(
            'sha256',
            'demo.' . $timestamp . '.' . $eventKey . '.' . $scenario . '.' . $attempt,
            $secret
        );
    }

    public static function handleDemoAdapter(WP_REST_Request $request): WP_REST_Response
    {
        if (self::mode() !== self::DEMO_MODE || !OddRoom_Repository::testMode()) {
            return new WP_REST_Response(['error_code' => 'DEMO_MODE_DISABLED'], 409);
        }
        $raw = (string) $request->get_body();
        $eventKey = trim((string) $request->get_header('x-oddroom-event-key'));
        $phase = trim((string) $request->get_header('x-oddroom-resume-phase'));
        $timestampText = trim((string) $request->get_header('x-oddroom-timestamp'));
        $signature = trim((string) $request->get_header('x-oddroom-signature'));
        $scenario = trim((string) $request->get_header('x-pf07-demo-scenario'));
        $attemptText = trim((string) $request->get_header('x-pf07-demo-attempt'));
        $controlSignature = trim((string) $request->get_header('x-pf07-demo-control-signature'));

        if (preg_match('/\A[1-9][0-9]{0,10}\z/D', $timestampText) !== 1
            || preg_match('/\A[1-9][0-9]{0,5}\z/D', $attemptText) !== 1) {
            return new WP_REST_Response(['error_code' => 'SIGNATURE_INVALID'], 401);
        }
        $timestamp = (int) $timestampText;
        $attempt = (int) $attemptText;
        if (abs(time() - $timestamp) > 300) {
            return new WP_REST_Response(['error_code' => 'TIMESTAMP_EXPIRED'], 401);
        }
        if (!in_array($scenario, ['normal', 'fail_once', 'terminal', 'operator_review'], true)) {
            return new WP_REST_Response(['error_code' => 'DEMO_SCENARIO_INVALID'], 400);
        }
        try {
            $secret = OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_WEBHOOK_HMAC_KEY');
        } catch (Throwable $error) {
            return new WP_REST_Response(['error_code' => 'SIGNATURE_CONFIG_UNAVAILABLE'], 503);
        }
        if (!OddRoom_Signature::verify($signature, $timestamp, $eventKey, $phase, $raw, $secret)
            || !hash_equals(
                self::controlSignature($timestamp, $eventKey, $scenario, $attempt, $secret),
                $controlSignature
            )) {
            return new WP_REST_Response(['error_code' => 'SIGNATURE_INVALID'], 401);
        }

        try {
            $decoded = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
            if (!is_array($decoded)) {
                throw new UnexpectedValueException('Payload must be an object.');
            }
            $canonical = OddRoom_Canonical_Payload::encode([
                'event_key' => $decoded['event_key'] ?? null,
                'shop_instance_id' => $decoded['shop_instance_id'] ?? null,
                'run_id' => $decoded['run_id'] ?? null,
                'event_type' => $decoded['event_type'] ?? null,
                'occurred_at_utc' => $decoded['occurred_at_utc'] ?? null,
                'occurred_at_source' => $decoded['occurred_at_source'] ?? null,
                'order' => $decoded['order'] ?? null,
            ]);
            if (!hash_equals($canonical, $raw) || ($decoded['event_key'] ?? null) !== $eventKey) {
                throw new UnexpectedValueException('Canonical payload mismatch.');
            }
        } catch (Throwable $error) {
            return new WP_REST_Response(['error_code' => 'PAYLOAD_INVALID'], 400);
        }

        if ($scenario === 'fail_once' && $attempt === 1) {
            return self::adapterResponse($eventKey, 503, [
                'result' => 'retryable_error',
                'processing_phase' => $phase,
                'remote_contact_id' => null,
                'remote_deal_id' => null,
                'slack_status' => 'not_required',
                'slack_message_ts' => null,
                'retryable' => true,
                'retry_after_seconds' => 8,
                'error_code' => 'DEMO_ADAPTER_RETRYABLE',
                'error_message' => 'Deterministic demo adapter failure before external-edge acceptance.',
            ]);
        }
        if ($scenario === 'terminal') {
            return self::adapterResponse($eventKey, 422, [
                'result' => 'terminal_error',
                'processing_phase' => $phase,
                'remote_contact_id' => null,
                'remote_deal_id' => null,
                'slack_status' => 'not_required',
                'slack_message_ts' => null,
                'retryable' => false,
                'retry_after_seconds' => null,
                'error_code' => 'DEMO_TERMINAL_FIXTURE',
                'error_message' => 'Deterministic demo terminal state; select Normal before manual retry.',
            ]);
        }
        if ($scenario === 'operator_review') {
            return self::adapterResponse($eventKey, 409, [
                'result' => 'operator_review',
                'processing_phase' => $phase,
                'remote_contact_id' => null,
                'remote_deal_id' => null,
                'slack_status' => 'not_required',
                'slack_message_ts' => null,
                'retryable' => false,
                'retry_after_seconds' => null,
                'error_code' => 'RESUME_PHASE_CONFLICT',
                'error_message' => 'Deterministic demo checkpoint conflict requiring an operator decision.',
            ]);
        }

        return self::completeDemoEdge($decoded, $eventKey);
    }

    public static function resetDemo(string $confirmation, int $administratorId): array
    {
        if (!OddRoom_Repository::testMode() || self::mode() !== self::DEMO_MODE) {
            throw new RuntimeException('DEMO_RESET_UNAVAILABLE');
        }
        if (!hash_equals(self::RESET_CONFIRMATION, trim($confirmation))) {
            throw new InvalidArgumentException('DEMO_RESET_CONFIRMATION_INVALID');
        }

        if (function_exists('as_unschedule_all_actions')) {
            as_unschedule_all_actions(OddRoom_Scheduler::HOOK, [], OddRoom_Scheduler::GROUP);
        }
        $deletedOrders = 0;
        if (function_exists('wc_get_orders')) {
            $orderIds = wc_get_orders([
                'limit' => -1,
                'return' => 'ids',
                'type' => 'shop_order',
                'status' => array_keys(wc_get_order_statuses()),
            ]);
            foreach ($orderIds as $orderId) {
                $order = wc_get_order((int) $orderId);
                if ($order instanceof WC_Order && $order->delete(true)) {
                    $deletedOrders++;
                }
            }
        }

        global $wpdb;
        foreach ([
            OddRoom_Installer::leaseTable(),
            OddRoom_Installer::faultTable(),
            OddRoom_Installer::outboxTable(),
        ] as $table) {
            $wpdb->query("DELETE FROM {$table}");
        }
        $wpdb->query($wpdb->prepare(
            "DELETE FROM {$wpdb->options} WHERE option_name LIKE %s",
            $wpdb->esc_like(OddRoom_Storefront::checkoutRateOptionPrefix()) . '%'
        ));
        foreach ([
            self::ADAPTER_STATE_OPTION,
            'oddroom_orderops_health_error',
            'oddroom_orderops_last_reachability',
            'oddroom_orderops_last_successful_event',
            'oddroom_orderops_last_reconciliation',
            'oddroom_orderops_mail_capture',
        ] as $option) {
            delete_option($option);
        }
        update_option(self::SCENARIO_OPTION, 'normal', false);
        $record = [
            'status' => 'PASS',
            'scope' => 'PACKAGE_DEMO_BUSINESS_DATA_ONLY',
            'deleted_orders' => $deletedOrders,
            'administrator_id' => $administratorId,
            'shop_instance_preserved' => true,
            'runtime_identity_preserved' => true,
            'reset_at_utc' => gmdate('c'),
        ];
        update_option(self::LAST_RESET_OPTION, $record, false);
        return $record;
    }

    private static function completeDemoEdge(array $payload, string $eventKey): WP_REST_Response
    {
        $state = self::adapterState();
        $order = $payload['order'];
        $emailHash = hash('sha256', (string) $order['customer']['email']);
        $orderHash = hash('sha256', (string) $payload['shop_instance_id'] . ':' . (string) $order['id']);
        $eventHash = hash('sha256', $eventKey);
        $contactId = 'demo-contact-' . substr($emailHash, 0, 16);
        $dealId = 'demo-deal-' . substr($orderHash, 0, 16);
        $eventType = (string) $payload['event_type'];
        $stateRank = (int) $payload['state_rank'];
        $existingRank = (int) ($state['deals'][$orderHash]['state_rank'] ?? 0);

        if (isset($state['events'][$eventHash])) {
            $state['executions']++;
            $state['last_event_ref'] = substr($eventHash, -12);
            self::saveAdapterState($state);
            return self::adapterResponse($eventKey, 200, [
                'result' => 'duplicate_noop',
                'processing_phase' => 'completed',
                'remote_contact_id' => $contactId,
                'remote_deal_id' => $dealId,
                'slack_status' => 'not_required',
                'slack_message_ts' => null,
                'retryable' => false,
                'retry_after_seconds' => null,
                'error_code' => null,
                'error_message' => null,
            ]);
        }
        if ($stateRank < $existingRank) {
            $state['executions']++;
            $state['events'][$eventHash] = ['result' => 'stale_ignored', 'observed_at_utc' => gmdate('c')];
            $state['last_event_ref'] = substr($eventHash, -12);
            self::saveAdapterState($state);
            return self::adapterResponse($eventKey, 200, [
                'result' => 'stale_ignored',
                'processing_phase' => 'completed',
                'remote_contact_id' => null,
                'remote_deal_id' => $dealId,
                'slack_status' => 'not_required',
                'slack_message_ts' => null,
                'retryable' => false,
                'retry_after_seconds' => null,
                'error_code' => null,
                'error_message' => null,
            ]);
        }

        $slackRequired = in_array($eventType, ['PAYMENT_CONFIRMED', 'ORDER_CANCELLED', 'ORDER_REFUNDED'], true);
        $slackTs = $slackRequired ? 'demo.' . substr($eventHash, 0, 20) : null;
        $state['contacts'][$emailHash] = ['id' => $contactId];
        $state['deals'][$orderHash] = ['id' => $dealId, 'state_rank' => $stateRank, 'event_type' => $eventType];
        if ($slackRequired) {
            $state['slack'][$eventHash] = ['ts' => $slackTs];
        }
        $state['events'][$eventHash] = ['result' => 'completed', 'observed_at_utc' => gmdate('c')];
        $state['executions']++;
        $state['last_event_ref'] = substr($eventHash, -12);
        self::saveAdapterState($state);
        return self::adapterResponse($eventKey, 200, [
            'result' => 'completed',
            'processing_phase' => 'completed',
            'remote_contact_id' => $contactId,
            'remote_deal_id' => $dealId,
            'slack_status' => $slackRequired ? 'posted' : 'not_required',
            'slack_message_ts' => $slackTs,
            'retryable' => false,
            'retry_after_seconds' => null,
            'error_code' => null,
            'error_message' => null,
        ]);
    }

    private static function adapterResponse(string $eventKey, int $status, array $fields): WP_REST_Response
    {
        return new WP_REST_Response([
            'schema_version' => '1',
            'event_key' => $eventKey,
            ...$fields,
        ], $status);
    }

    private static function adapterState(): array
    {
        $state = get_option(self::ADAPTER_STATE_OPTION, []);
        if (!is_array($state)) {
            $state = [];
        }
        return [
            'contacts' => is_array($state['contacts'] ?? null) ? $state['contacts'] : [],
            'deals' => is_array($state['deals'] ?? null) ? $state['deals'] : [],
            'slack' => is_array($state['slack'] ?? null) ? $state['slack'] : [],
            'events' => is_array($state['events'] ?? null) ? $state['events'] : [],
            'executions' => max(0, (int) ($state['executions'] ?? 0)),
            'last_event_ref' => is_string($state['last_event_ref'] ?? null) ? $state['last_event_ref'] : '',
        ];
    }

    private static function saveAdapterState(array $state): void
    {
        foreach (['events', 'slack'] as $key) {
            if (count($state[$key]) > 200) {
                $state[$key] = array_slice($state[$key], -200, null, true);
            }
        }
        update_option(self::ADAPTER_STATE_OPTION, $state, false);
    }

    private static function boundedAlias(mixed $value): string
    {
        if (!is_string($value)) {
            return '';
        }
        $value = trim(sanitize_text_field($value));
        return preg_match('/\A[A-Za-z][A-Za-z0-9._-]{2,63}\z/D', $value) === 1 ? $value : '';
    }
}
