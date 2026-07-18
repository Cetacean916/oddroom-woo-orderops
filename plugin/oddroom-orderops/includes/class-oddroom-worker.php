<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Worker
{
    private const ALLOWED_RESULTS = [
        'completed', 'duplicate_noop', 'stale_ignored',
        'retryable_error', 'operator_review', 'terminal_error',
    ];
    private const ALLOWED_SLACK = [
        'not_required', 'pending', 'posted', 'failed_before_post', 'outcome_unknown',
    ];

    public static function process(int $rowId): void
    {
        $executionId = OddRoom_Scheduler::currentExecutionId();
        try {
            $row = OddRoom_Repository::find($rowId);
            $guard = OddRoom_Scheduler::guard(true);
            if (!$row || !$guard['ok'] || !$executionId || (int) $row->action_id !== $executionId) {
                return;
            }
            if (!OddRoom_Scheduler::actionMatches($executionId, $rowId)) {
                OddRoom_Repository::recordSchedulingError($rowId, 'ACTION_ID_MISMATCH', true);
                return;
            }
            if (!hash_equals((string) $row->payload_hash, hash('sha256', (string) $row->payload_json))) {
                OddRoom_Repository::recordSchedulingError($rowId, 'PAYLOAD_HASH_MISMATCH', true);
                return;
            }

            $claim = OddRoom_Repository::claim($rowId, $executionId);
            if (!$claim) {
                return;
            }
            $claimed = $claim['row'];
            $rowToken = $claim['row_token'];
            $leaseToken = $claim['lease_token'];

            if (!OddRoom_Repository::markDispatched($claimed, $rowToken, $leaseToken)) {
                return;
            }

            $timestamp = time();
            $secret = self::secret();
            $phase = (string) $claimed->processing_phase;
            $body = (string) $claimed->payload_json;
            $signature = OddRoom_Signature::sign(
                $timestamp,
                (string) $claimed->event_key,
                $phase,
                $body,
                $secret
            );
            $response = wp_remote_post(OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_WEBHOOK_URL'), [
                'timeout' => 300,
                'redirection' => 0,
                'httpversion' => '1.1',
                'blocking' => true,
                'headers' => [
                    'Content-Type' => 'application/json; charset=utf-8',
                    'X-OddRoom-Event-Key' => (string) $claimed->event_key,
                    'X-OddRoom-Timestamp' => (string) $timestamp,
                    'X-OddRoom-Resume-Phase' => $phase,
                    'X-OddRoom-Signature' => $signature,
                ],
                'body' => $body,
                'data_format' => 'body',
                'limit_response_size' => OddRoom_Canonical_Payload::MAX_BODY_BYTES,
                'user-agent' => 'OddRoom-OrderOps/0.2.0',
            ]);

            if (is_wp_error($response)) {
                self::recordReachability('HOLD', null, 'TRANSPORT_ERROR');
                $result = self::requiresSlack($claimed)
                    ? OddRoom_Repository::ambiguousSlackFailure(
                        $claimed,
                        $rowToken,
                        $leaseToken,
                        self::sanitizeTransportError($response->get_error_message())
                    )
                    : OddRoom_Repository::transportFailure(
                        $claimed,
                        $rowToken,
                        $leaseToken,
                        'HUBSPOT_RETRYABLE',
                        self::sanitizeTransportError($response->get_error_message())
                    );
                self::scheduleFollowup($rowId, $result);
                return;
            }

            $httpStatus = (int) wp_remote_retrieve_response_code($response);
            self::recordReachability('REACHED', $httpStatus, null);
            $raw = (string) wp_remote_retrieve_body($response);
            try {
                $envelope = self::validateEnvelope($raw, (string) $claimed->event_key, $phase);
            } catch (Throwable $error) {
                $result = self::requiresSlack($claimed)
                    ? OddRoom_Repository::ambiguousSlackFailure(
                        $claimed,
                        $rowToken,
                        $leaseToken,
                        'Adapter response did not establish the Slack outcome.',
                        $httpStatus
                    )
                    : OddRoom_Repository::transportFailure(
                        $claimed,
                        $rowToken,
                        $leaseToken,
                        'ADAPTER_RESPONSE_INVALID',
                        'Adapter response did not satisfy the authenticated envelope.',
                        $httpStatus,
                        self::retryAfter($response)
                    );
                self::scheduleFollowup($rowId, $result);
                return;
            }

            $result = OddRoom_Repository::finish(
                $claimed,
                $rowToken,
                $leaseToken,
                $envelope,
                $httpStatus
            );
            if (($result['status'] ?? null) === 'completed') {
                update_option('oddroom_orderops_last_successful_event', [
                    'outbox_id' => (int) $claimed->id,
                    'event_type' => (string) $claimed->event_type,
                    'observed_at_utc' => gmdate('c'),
                ], false);
            }
            self::scheduleFollowup($rowId, $result);
        } finally {
            OddRoom_Scheduler::clearExecution();
        }
    }

    public static function validateEnvelope(string $raw, string $eventKey, string $requestPhase): array
    {
        $value = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
        if (!is_array($value)) {
            throw new UnexpectedValueException('Envelope must be an object.');
        }
        $required = [
            'schema_version', 'event_key', 'result', 'processing_phase', 'remote_contact_id',
            'remote_deal_id', 'slack_status', 'slack_message_ts', 'retryable',
            'retry_after_seconds', 'error_code', 'error_message',
        ];
        foreach ($required as $key) {
            if (!array_key_exists($key, $value)) {
                throw new UnexpectedValueException('Missing response field.');
            }
        }
        if ($value['schema_version'] !== '1' || $value['event_key'] !== $eventKey) {
            throw new UnexpectedValueException('Response identity mismatch.');
        }
        if (!is_string($value['result']) || !in_array($value['result'], self::ALLOWED_RESULTS, true)) {
            throw new UnexpectedValueException('Invalid result.');
        }
        if (!is_string($value['processing_phase']) || !is_string($value['slack_status'])
            || !in_array($value['slack_status'], self::ALLOWED_SLACK, true)) {
            throw new UnexpectedValueException('Invalid response state.');
        }
        foreach (['remote_contact_id', 'remote_deal_id', 'slack_message_ts', 'error_code', 'error_message'] as $key) {
            if ($value[$key] !== null && !is_string($value[$key])) {
                throw new UnexpectedValueException('Invalid nullable string.');
            }
        }
        if (!is_bool($value['retryable'])
            || ($value['retry_after_seconds'] !== null
                && (!is_int($value['retry_after_seconds']) || $value['retry_after_seconds'] < 0))) {
            throw new UnexpectedValueException('Invalid retry fields.');
        }
        OddRoom_State_Machine::assertMonotonic($requestPhase, $value['processing_phase']);

        if ($value['result'] === 'completed') {
            if ($value['retryable'] || !$value['remote_deal_id']
                || !in_array($value['slack_status'], ['posted', 'not_required'], true)
                || ($value['slack_status'] === 'posted' && !$value['slack_message_ts'])) {
                throw new UnexpectedValueException('Invalid completion invariant.');
            }
        }
        if ($value['result'] === 'retryable_error'
            && (!$value['retryable'] || !$value['error_code'])) {
            throw new UnexpectedValueException('Invalid retryable invariant.');
        }
        if (in_array($value['result'], ['operator_review', 'terminal_error'], true)
            && ($value['retryable'] || !$value['error_code'])) {
            throw new UnexpectedValueException('Invalid non-retryable invariant.');
        }
        return $value;
    }

    private static function scheduleFollowup(int $rowId, array $result): void
    {
        if (!is_string($result['schedule_at'] ?? null) || $result['schedule_at'] === '') {
            return;
        }
        $timestamp = strtotime($result['schedule_at'] . ' UTC');
        if ($timestamp !== false) {
            OddRoom_Scheduler::scheduleBusiness($rowId, $timestamp);
        }
    }

    private static function secret(): string
    {
        $secret = trim((string) getenv('ODDROOM_WEBHOOK_HMAC_KEY'));
        if ($secret === '') {
            throw new RuntimeException('Webhook signing key is unavailable.');
        }
        return $secret;
    }

    private static function retryAfter(array $response): ?int
    {
        $value = wp_remote_retrieve_header($response, 'retry-after');
        return is_numeric($value) && (int) $value >= 0 ? (int) $value : null;
    }

    private static function sanitizeTransportError(string $message): string
    {
        return substr(sanitize_text_field($message), 0, 240);
    }

    private static function requiresSlack(object $row): bool
    {
        return in_array(
            (string) $row->event_type,
            ['PAYMENT_CONFIRMED', 'ORDER_CANCELLED', 'ORDER_REFUNDED'],
            true
        );
    }

    private static function recordReachability(string $status, ?int $httpStatus, ?string $errorCode): void
    {
        update_option('oddroom_orderops_last_reachability', [
            'status' => $status,
            'http_status' => $httpStatus,
            'error_code' => $errorCode,
            'observed_at_utc' => gmdate('c'),
        ], false);
    }
}
