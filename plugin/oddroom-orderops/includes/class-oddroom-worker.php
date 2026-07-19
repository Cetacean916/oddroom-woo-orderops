<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Worker
{
    private const DEFAULT_TEST_PAUSE_SECONDS = 120;
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
            if (in_array((string) $row->processing_phase, ['slack_posted', 'completed'], true)) {
                OddRoom_Repository::recordSchedulingError($rowId, 'ADAPTER_RESPONSE_INVALID', true);
                return;
            }

            $claim = OddRoom_Repository::claim($rowId, $executionId);
            if (!$claim) {
                OddRoom_Scheduler::deferContentionRequeue($rowId, $executionId);
                return;
            }
            $claimed = $claim['row'];
            $rowToken = $claim['row_token'];
            $leaseToken = $claim['lease_token'];

            self::pauseForCrashFixture($claimed, OddRoom_Faults::PAUSE_AFTER_CLAIM);

            if (!OddRoom_Repository::markDispatched($claimed, $rowToken, $leaseToken)) {
                return;
            }

            self::pauseForCrashFixture($claimed, OddRoom_Faults::PAUSE_AFTER_DISPATCH);

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

            self::pauseForCrashFixture($claimed, OddRoom_Faults::PAUSE_AFTER_RESPONSE);

            if (is_wp_error($response)) {
                self::recordReachability('HOLD', null, 'TRANSPORT_ERROR');
                self::requiresSlack($claimed)
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
                return;
            }

            $httpStatus = (int) wp_remote_retrieve_response_code($response);
            self::recordReachability('REACHED', $httpStatus, null);
            $raw = (string) wp_remote_retrieve_body($response);
            try {
                $envelope = self::validateEnvelope(
                    $raw,
                    (string) $claimed->event_key,
                    $phase,
                    $httpStatus
                );
            } catch (Throwable $error) {
                $disposition = self::invalidResponseDisposition(
                    self::requiresSlack($claimed),
                    $httpStatus
                );
                if ($disposition === 'ambiguous_slack') {
                    OddRoom_Repository::ambiguousSlackFailure(
                        $claimed,
                        $rowToken,
                        $leaseToken,
                        'Adapter response did not establish the Slack outcome.',
                        $httpStatus
                    );
                } elseif ($disposition === 'terminal') {
                    OddRoom_Repository::terminalResponseFailure(
                        $claimed,
                        $rowToken,
                        $leaseToken,
                        'ADAPTER_RESPONSE_INVALID',
                        'Adapter returned a terminal HTTP response without a valid authenticated envelope.',
                        $httpStatus
                    );
                } else {
                    OddRoom_Repository::transportFailure(
                        $claimed,
                        $rowToken,
                        $leaseToken,
                        'ADAPTER_RESPONSE_INVALID',
                        'Adapter response did not satisfy the authenticated envelope.',
                        $httpStatus,
                        self::retryAfter($response)
                    );
                }
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
        } finally {
            OddRoom_Scheduler::clearExecution();
        }
    }

    public static function validateEnvelope(
        string $raw,
        string $eventKey,
        string $requestPhase,
        int $httpStatus
    ): array
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
        self::assertNullableString($value['remote_contact_id'], 128, 'remote_contact_id');
        self::assertNullableString($value['remote_deal_id'], 128, 'remote_deal_id');
        self::assertNullableString($value['slack_message_ts'], 64, 'slack_message_ts');
        self::assertNullableString($value['error_code'], 96, 'error_code');
        self::assertNullableString($value['error_message'], 500, 'error_message');
        self::assertPhaseCheckpointConsistency($value);
        if ($value['error_code'] !== null
            && preg_match('/\A[A-Z][A-Z0-9_]*\z/D', $value['error_code']) !== 1) {
            throw new UnexpectedValueException('Invalid stable error code.');
        }
        if (!is_bool($value['retryable'])
            || ($value['retry_after_seconds'] !== null
                && (!is_int($value['retry_after_seconds']) || $value['retry_after_seconds'] < 0))) {
            throw new UnexpectedValueException('Invalid retry fields.');
        }
        OddRoom_State_Machine::assertMonotonic($requestPhase, $value['processing_phase']);

        if ($value['slack_status'] === 'posted') {
            if ($value['slack_message_ts'] === null
                || !in_array($value['processing_phase'], ['slack_posted', 'completed'], true)) {
                throw new UnexpectedValueException('Invalid posted Slack invariant.');
            }
        } elseif ($value['slack_message_ts'] !== null) {
            throw new UnexpectedValueException('Slack timestamp requires posted state.');
        }
        if ($value['slack_status'] === 'failed_before_post'
            && ($value['processing_phase'] !== 'slack_pending'
                || !in_array($value['result'], ['retryable_error', 'terminal_error'], true))) {
            throw new UnexpectedValueException('Invalid pre-post failure invariant.');
        }
        if ($value['slack_status'] === 'outcome_unknown'
            && ($value['processing_phase'] !== 'slack_pending' || $value['result'] !== 'operator_review')) {
            throw new UnexpectedValueException('Invalid unknown Slack outcome invariant.');
        }

        $successful = in_array($value['result'], ['completed', 'duplicate_noop', 'stale_ignored'], true);
        if ($successful) {
            if ($httpStatus !== 200
                || $value['retryable']
                || $value['retry_after_seconds'] !== null
                || $value['processing_phase'] !== 'completed'
                || $value['remote_deal_id'] === null
                || !in_array($value['slack_status'], ['posted', 'not_required'], true)
                || $value['error_code'] !== null
                || $value['error_message'] !== null) {
                throw new UnexpectedValueException('Invalid successful response invariant.');
            }
            if (in_array($value['result'], ['duplicate_noop', 'stale_ignored'], true)
                && ($value['slack_status'] !== 'not_required' || $value['slack_message_ts'] !== null)) {
                throw new UnexpectedValueException('A no-op result cannot establish a new Slack post.');
            }
            if ($value['result'] === 'stale_ignored' && $value['remote_contact_id'] !== null) {
                throw new UnexpectedValueException('A stale short-circuit cannot establish a Contact checkpoint.');
            }
        } elseif ($value['result'] === 'retryable_error') {
            if ($httpStatus < 500 || $httpStatus > 599
                || !$value['retryable']
                || $value['error_code'] === null
                || in_array($value['slack_status'], ['posted', 'outcome_unknown'], true)) {
                throw new UnexpectedValueException('Invalid retryable response invariant.');
            }
        } elseif ($value['result'] === 'operator_review') {
            if ($httpStatus !== 409
                || $value['retryable']
                || $value['retry_after_seconds'] !== null
                || !in_array($value['error_code'], ['RESUME_PHASE_CONFLICT', 'SLACK_OUTCOME_UNKNOWN'], true)
                || ($value['error_code'] === 'SLACK_OUTCOME_UNKNOWN'
                    && $value['slack_status'] !== 'outcome_unknown')
                || ($value['error_code'] !== 'SLACK_OUTCOME_UNKNOWN'
                    && $value['slack_status'] === 'outcome_unknown')) {
                throw new UnexpectedValueException('Invalid operator-review response invariant.');
            }
        } elseif ($value['result'] === 'terminal_error') {
            if ($httpStatus < 400 || $httpStatus > 499 || $httpStatus === 409
                || $value['retryable']
                || $value['retry_after_seconds'] !== null
                || $value['error_code'] === null
                || in_array($value['slack_status'], ['posted', 'outcome_unknown'], true)) {
                throw new UnexpectedValueException('Invalid terminal response invariant.');
            }
        }
        return $value;
    }

    private static function assertNullableString(mixed $value, int $maxBytes, string $field): void
    {
        if ($value === null) {
            return;
        }
        if (!is_string($value)
            || $value === ''
            || strlen($value) > $maxBytes
            || trim($value) !== $value
            || preg_match('/[\x00-\x1F\x7F]/', $value) === 1) {
            throw new UnexpectedValueException('Invalid bounded response field: ' . $field . '.');
        }
    }

    private static function assertPhaseCheckpointConsistency(array $value): void
    {
        $phases = [
            'created', 'deal_resolved', 'contact_upserted', 'deal_upserted',
            'associated', 'slack_pending', 'slack_posted', 'completed',
        ];
        $rank = array_search($value['processing_phase'], $phases, true);
        if ($rank === false) {
            throw new UnexpectedValueException('Invalid response phase.');
        }
        if ($rank >= 2
            && $value['result'] !== 'stale_ignored'
            && $value['remote_contact_id'] === null) {
            throw new UnexpectedValueException('Response phase requires a Contact checkpoint.');
        }
        if ($rank >= 3 && $value['remote_deal_id'] === null) {
            throw new UnexpectedValueException('Response phase requires a Deal checkpoint.');
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
        $header = wp_remote_retrieve_header($response, 'retry-after');
        if (!is_string($header)) {
            return null;
        }
        $value = trim($header);
        if ($value === '') {
            return null;
        }
        if (preg_match('/\A[0-9]+\z/D', $value) === 1) {
            $normalized = ltrim($value, '0');
            $normalized = $normalized === '' ? '0' : $normalized;
            $maximum = (string) PHP_INT_MAX;
            if (strlen($normalized) > strlen($maximum)
                || (strlen($normalized) === strlen($maximum) && strcmp($normalized, $maximum) > 0)) {
                return null;
            }
            return (int) $normalized;
        }

        $format = 'D, d M Y H:i:s \\G\\M\\T';
        $date = DateTimeImmutable::createFromFormat($format, $value, new DateTimeZone('GMT'));
        $errors = DateTimeImmutable::getLastErrors();
        if (!$date
            || ($errors !== false && ($errors['warning_count'] !== 0 || $errors['error_count'] !== 0))
            || $date->format($format) !== $value) {
            return null;
        }
        return max(0, $date->getTimestamp() - time());
    }

    private static function invalidResponseDisposition(bool $requiresSlack, int $httpStatus): string
    {
        if ($requiresSlack && $httpStatus !== 429) {
            return 'ambiguous_slack';
        }
        if ($httpStatus >= 400 && $httpStatus <= 499 && $httpStatus !== 429) {
            return 'terminal';
        }
        return 'retryable';
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

    private static function pauseForCrashFixture(object $row, string $faultType): void
    {
        if (!OddRoom_Repository::testMode()) {
            return;
        }
        if (OddRoom_Faults::isActiveForEvent(
            (int) $row->order_id,
            (string) $row->event_type,
            $faultType
        )) {
            sleep(self::testPauseSeconds());
        }
    }

    private static function testPauseSeconds(): int
    {
        $raw = trim((string) getenv('ODDROOM_TEST_PAUSE_SECONDS'));
        if ($raw === '') {
            return self::DEFAULT_TEST_PAUSE_SECONDS;
        }
        if (preg_match('/\A(?:[1-9]|[1-9][0-9]|1[01][0-9]|120)\z/D', $raw) !== 1) {
            throw new RuntimeException('ODDROOM_TEST_PAUSE_SECONDS must be an integer from 1 through 120.');
        }
        return (int) $raw;
    }
}
