<?php

define('ODDROOM_ORDEROPS_TESTING', true);
if (!function_exists('wp_remote_retrieve_header')) {
    function wp_remote_retrieve_header(array $response, string $header): mixed
    {
        return $response['headers'][strtolower($header)] ?? null;
    }
}
require_once __DIR__ . '/../includes/class-oddroom-canonical-payload.php';
require_once __DIR__ . '/../includes/class-oddroom-signature.php';
require_once __DIR__ . '/../includes/class-oddroom-state-machine.php';
require_once __DIR__ . '/../includes/class-oddroom-retry-policy.php';
require_once __DIR__ . '/../includes/class-oddroom-dependencies.php';
require_once __DIR__ . '/../includes/class-oddroom-worker.php';
require_once __DIR__ . '/../includes/class-oddroom-storefront.php';

$tests = 0;
$assert = static function (bool $condition, string $message) use (&$tests): void {
    $tests++;
    if (!$condition) {
        throw new RuntimeException($message);
    }
};

$input = [
    'event_key' => 'v1:pf07-00000000-0000-4000-8000-000000000000:42:ORDER_CREATED',
    'shop_instance_id' => 'pf07-00000000-0000-4000-8000-000000000000',
    'run_id' => '00000000-0000-4000-8000-000000000001',
    'event_type' => 'ORDER_CREATED',
    'occurred_at_utc' => '2026-07-19T00:00:00Z',
    'occurred_at_source' => 'date_created',
    'order' => [
        'id' => 42,
        'number' => '42',
        'currency' => 'KRW',
        'total' => '15000.00',
        'customer' => ['email' => 'BUYER@example.com', 'first_name' => 'Synthetic', 'last_name' => 'Buyer'],
        'items' => [
            ['item_id' => 2, 'product_id' => 8, 'variation_id' => 1, 'sku' => 'B', 'name' => 'Variation', 'quantity' => 1, 'line_total' => '10000.00'],
            ['item_id' => 1, 'product_id' => 7, 'variation_id' => 0, 'sku' => 'A', 'name' => 'Simple', 'quantity' => 1, 'line_total' => '5000.00'],
        ],
        'coupon_codes' => ['WELCOME', 'ODDROOM'],
    ],
];

$json = OddRoom_Canonical_Payload::encode($input);
$decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
$assert(array_keys($decoded) === ['schema_version', 'event_key', 'shop_instance_id', 'run_id', 'event_type', 'occurred_at_utc', 'occurred_at_source', 'state_rank', 'order'], 'Top-level order changed.');
$assert($decoded['order']['items'][0]['item_id'] === 1, 'Items were not sorted.');
$assert($decoded['order']['coupon_codes'] === ['ODDROOM', 'WELCOME'], 'Coupons were not sorted.');
$assert($decoded['order']['customer']['email'] === 'buyer@example.com', 'Email was not normalized.');
$assert(strlen(OddRoom_Canonical_Payload::hash($json)) === 64, 'Payload hash is invalid.');
$currencyInput = $input;
$currencyInput['order']['currency'] = 'USD';
$currencyRejected = false;
try {
    OddRoom_Canonical_Payload::encode($currencyInput);
} catch (InvalidArgumentException $error) {
    $currencyRejected = true;
}
$assert($currencyRejected, 'A non-selected currency was accepted.');
$precisionInput = $input;
$precisionInput['order']['total'] = '15000.0';
$precisionDecoded = json_decode(
    OddRoom_Canonical_Payload::encode($precisionInput),
    true,
    512,
    JSON_THROW_ON_ERROR
);
$assert($precisionDecoded['order']['total'] === '15000.00', 'A safely normalizable money value was not canonicalized.');
$excessPrecisionInput = $input;
$excessPrecisionInput['order']['total'] = '15000.001';
$excessPrecisionRejected = false;
try {
    OddRoom_Canonical_Payload::encode($excessPrecisionInput);
} catch (InvalidArgumentException $error) {
    $excessPrecisionRejected = true;
}
$assert($excessPrecisionRejected, 'A non-zero excess currency fraction was accepted.');
$assert(
    OddRoom_Canonical_Payload::normalizeMoney('999999999999999999.99') === '999999999999999999.99',
    'The maximum 18-digit money boundary lost precision.'
);
$assert(
    OddRoom_Canonical_Payload::toMinorUnits('999999999999999999.99') === '99999999999999999999',
    'Money-to-minor-units conversion lost precision.'
);
$assert(
    OddRoom_Canonical_Payload::addMinorUnits('99999999999999999999', '1') === '100000000000000000000',
    'Arbitrary-length minor-unit addition lost precision.'
);
$assert(
    OddRoom_Canonical_Payload::compareMinorUnits('100000000000000000000', '99999999999999999999') === 1,
    'Arbitrary-length minor-unit comparison failed.'
);
$assert(
    OddRoom_Canonical_Payload::normalizeMoney('15000.0000') === '15000.00',
    'Trailing zero precision was not normalized safely.'
);
$invalidMoneyValues = ['1e3', '-1.00', '+1.00', '01.00', '1000000000000000000.00'];
foreach ($invalidMoneyValues as $invalidMoneyValue) {
    $moneyRejected = false;
    try {
        OddRoom_Canonical_Payload::normalizeMoney($invalidMoneyValue);
    } catch (InvalidArgumentException $error) {
        $moneyRejected = true;
    }
    $assert($moneyRejected, 'An invalid money representation was accepted: ' . $invalidMoneyValue);
}
$assert(
    OddRoom_Canonical_Payload::parseUtcTimestamp('2026-07-19T01:02:03Z')->format('Y-m-d\\TH:i:s\\Z')
        === '2026-07-19T01:02:03Z',
    'A valid second-precision UTC timestamp was rejected.'
);
$assert(
    OddRoom_Canonical_Payload::parseUtcTimestamp('2026-07-19T01:02:03.1Z')->format('Y-m-d\\TH:i:s.u\\Z')
        === '2026-07-19T01:02:03.100000Z',
    'A valid fractional UTC timestamp was not parsed exactly.'
);
$invalidProtectedTimestampRejected = false;
try {
    OddRoom_Canonical_Payload::parseUtcTimestamp('2026-02-30T00:00:00.000001Z');
} catch (InvalidArgumentException $error) {
    $invalidProtectedTimestampRejected = true;
}
$assert($invalidProtectedTimestampRejected, 'An invalid protected-fact calendar timestamp was normalized and accepted.');

$emptySkuInput = $input;
$emptySkuInput['order']['items'][0]['sku'] = '';
$assert(OddRoom_Canonical_Payload::encode($emptySkuInput) !== '', 'A valid empty WooCommerce SKU was rejected.');

$unicodeBoundaryInput = $input;
$unicodeBoundaryInput['order']['customer']['first_name'] = str_repeat('😀', 255);
$assert(OddRoom_Canonical_Payload::encode($unicodeBoundaryInput) !== '', 'A 255-code-point astral string was rejected.');

$canonicalRejected = static function (array $candidate): bool {
    try {
        OddRoom_Canonical_Payload::encode($candidate);
    } catch (InvalidArgumentException|LengthException $error) {
        return true;
    }
    return false;
};
$unicodeOverflowInput = $unicodeBoundaryInput;
$unicodeOverflowInput['order']['customer']['first_name'] .= '😀';
$assert($canonicalRejected($unicodeOverflowInput), 'A 256-code-point string was accepted.');
$invalidUtf8Input = $input;
$invalidUtf8Input['order']['customer']['first_name'] = "\xFF";
$assert($canonicalRejected($invalidUtf8Input), 'Invalid UTF-8 was accepted.');
$invalidDateInput = $input;
$invalidDateInput['occurred_at_utc'] = '2026-02-30T00:00:00Z';
$assert($canonicalRejected($invalidDateInput), 'An invalid calendar timestamp was accepted.');
$realEmailInput = $input;
$realEmailInput['order']['customer']['email'] = 'buyer@real.invalid';
$assert($canonicalRejected($realEmailInput), 'A non-synthetic email domain was accepted.');
$extraFieldInput = $input;
$extraFieldInput['order']['unexpected'] = true;
$assert($canonicalRejected($extraFieldInput), 'An additional order property was accepted.');

$assert(OddRoom_Storefront::isSyntheticIdentity([
    'first_name' => 'Synthetic',
    'last_name' => 'Buyer',
    'email' => 'pf07-checkout@example.com',
]), 'The documented synthetic checkout identity was rejected.');
$assert(!OddRoom_Storefront::isSyntheticIdentity([
    'first_name' => 'Real',
    'last_name' => 'Customer',
    'email' => 'person@example.com',
]), 'A real-name checkout identity was accepted.');
$assert(!OddRoom_Storefront::isSyntheticIdentity([
    'first_name' => 'Synthetic',
    'last_name' => 'Buyer',
    'email' => 'PF07@example.com',
]), 'A non-lowercase synthetic email was accepted.');
$assert(OddRoom_Canonical_Payload::rankFor('ORDER_CREATED') === 10, 'Created rank changed.');
$assert(OddRoom_Canonical_Payload::rankFor('PAYMENT_CONFIRMED') === 20, 'Payment rank changed.');
$assert(OddRoom_Canonical_Payload::rankFor('ORDER_CANCELLED') === 30, 'Cancellation rank changed.');
$assert(OddRoom_Canonical_Payload::rankFor('ORDER_REFUNDED') === 40, 'Refund rank changed.');

$signature = OddRoom_Signature::sign(1784390400, $input['event_key'], 'created', $json, 'synthetic-test-secret');
$assert(OddRoom_Signature::verify($signature, 1784390400, $input['event_key'], 'created', $json, 'synthetic-test-secret'), 'Valid signature failed.');
$assert(!OddRoom_Signature::verify($signature, 1784390400, $input['event_key'], 'created', $json . ' ', 'synthetic-test-secret'), 'Mutated body passed.');

OddRoom_State_Machine::assertMonotonic('deal_resolved', 'deal_upserted');
$assert(OddRoom_State_Machine::checkpoint(null, 'remote-1') === 'remote-1', 'Checkpoint insert failed.');
$assert(OddRoom_State_Machine::checkpoint('remote-1', 'remote-1') === 'remote-1', 'Checkpoint replay failed.');

$nullConflict = false;
try {
    OddRoom_State_Machine::checkpoint('remote-1', null);
} catch (DomainException $error) {
    $nullConflict = $error->getMessage() === 'CHECKPOINT_CONFLICT';
}
$assert($nullConflict, 'Checkpoint deletion was not rejected.');

$conflict = false;
try {
    OddRoom_State_Machine::checkpoint('remote-1', 'remote-2');
} catch (DomainException $error) {
    $conflict = $error->getMessage() === 'CHECKPOINT_CONFLICT';
}
$assert($conflict, 'Checkpoint conflict was not rejected.');
$assert(OddRoom_Retry_Policy::delayAfter(5) === 21600, 'Production retry schedule changed.');
$assert(OddRoom_Retry_Policy::attemptKind(6, 6) === 'automatic', 'Automatic attempt classification failed.');
$assert(OddRoom_Retry_Policy::attemptKind(7, 6) === 'manual', 'Manual attempt classification failed.');

$missingWoo = OddRoom_Dependencies::evaluate(false, false, null);
$assert($missingWoo['ok'] === false && $missingWoo['code'] === 'WOOCOMMERCE_UNAVAILABLE', 'Missing WooCommerce was not blocked first.');
$missingScheduler = OddRoom_Dependencies::evaluate(true, false, null);
$assert($missingScheduler['ok'] === false && $missingScheduler['code'] === 'ACTION_SCHEDULER_NOT_READY', 'Uninitialized Action Scheduler was not blocked.');
$oldScheduler = OddRoom_Dependencies::evaluate(true, true, '3.9.9');
$assert($oldScheduler['ok'] === false && $oldScheduler['code'] === 'ACTION_SCHEDULER_VERSION_UNSUPPORTED', 'Old Action Scheduler was not blocked.');
$readyDependencies = OddRoom_Dependencies::evaluate(true, true, '4.0.0');
$assert($readyDependencies['ok'] === true && $readyDependencies['code'] === null, 'Minimum supported dependencies did not pass.');
$currencyMismatch = OddRoom_Dependencies::evaluate(true, true, '4.0.0', 'USD', 2);
$assert($currencyMismatch['code'] === 'WOOCOMMERCE_CURRENCY_MISMATCH', 'Currency drift was not blocked.');
$precisionMismatch = OddRoom_Dependencies::evaluate(true, true, '4.0.0', 'KRW', 0);
$assert($precisionMismatch['code'] === 'WOOCOMMERCE_CURRENCY_PRECISION_MISMATCH', 'Currency precision drift was not blocked.');
$assert(str_contains(OddRoom_Dependencies::messageFor('WOOCOMMERCE_UNAVAILABLE'), 'Install and activate WooCommerce'), 'Dependency notice is not actionable.');

$envelope = [
    'schema_version' => '1',
    'event_key' => $input['event_key'],
    'result' => 'completed',
    'processing_phase' => 'completed',
    'remote_contact_id' => 'synthetic-contact-1',
    'remote_deal_id' => 'synthetic-deal-1',
    'slack_status' => 'not_required',
    'slack_message_ts' => null,
    'retryable' => false,
    'retry_after_seconds' => null,
    'error_code' => null,
    'error_message' => null,
];
$validated = OddRoom_Worker::validateEnvelope(
    json_encode($envelope, JSON_THROW_ON_ERROR),
    $input['event_key'],
    'created',
    200
);
$assert($validated['remote_deal_id'] === 'synthetic-deal-1', 'Valid complete-path VSL envelope failed.');

$rejected = static function (array $candidate, int $httpStatus) use ($input): bool {
    try {
        OddRoom_Worker::validateEnvelope(
            json_encode($candidate, JSON_THROW_ON_ERROR),
            $input['event_key'],
            'created',
            $httpStatus
        );
        return false;
    } catch (Throwable $error) {
        return true;
    }
};

$badEnvelope = $envelope;
$badEnvelope['event_key'] = 'wrong-event';
$assert($rejected($badEnvelope, 200), 'Mismatched response event key was accepted.');
$assert($rejected($envelope, 201), 'Successful result accepted a non-200 status.');

$retryEnvelope = $envelope;
$retryEnvelope['result'] = 'retryable_error';
$retryEnvelope['processing_phase'] = 'slack_pending';
$retryEnvelope['slack_status'] = 'failed_before_post';
$retryEnvelope['retryable'] = true;
$retryEnvelope['retry_after_seconds'] = 90001;
$retryEnvelope['error_code'] = 'SLACK_RETRYABLE_BEFORE_POST';
$retryEnvelope['error_message'] = 'Synthetic pre-post failure.';
$validatedRetry = OddRoom_Worker::validateEnvelope(
    json_encode($retryEnvelope, JSON_THROW_ON_ERROR),
    $input['event_key'],
    'created',
    503
);
$assert($validatedRetry['retry_after_seconds'] === 90001, 'Valid Retry-After was capped or lost.');
$assert($rejected($retryEnvelope, 429), 'Retryable result accepted a non-5xx status.');

$operatorEnvelope = $envelope;
$operatorEnvelope['result'] = 'operator_review';
$operatorEnvelope['processing_phase'] = 'created';
$operatorEnvelope['remote_deal_id'] = null;
$operatorEnvelope['retryable'] = false;
$operatorEnvelope['error_code'] = 'RESUME_PHASE_CONFLICT';
$operatorEnvelope['error_message'] = 'Synthetic resume conflict.';
$validatedOperator = OddRoom_Worker::validateEnvelope(
    json_encode($operatorEnvelope, JSON_THROW_ON_ERROR),
    $input['event_key'],
    'created',
    409
);
$assert($validatedOperator['result'] === 'operator_review', 'Valid operator-review result failed.');
$badOperator = $operatorEnvelope;
$badOperator['error_code'] = 'ARBITRARY_REVIEW';
$assert($rejected($badOperator, 409), 'Undocumented operator-review code was accepted.');

$terminalEnvelope = $operatorEnvelope;
$terminalEnvelope['result'] = 'terminal_error';
$terminalEnvelope['error_code'] = 'PAYLOAD_INVALID';
$validatedTerminal = OddRoom_Worker::validateEnvelope(
    json_encode($terminalEnvelope, JSON_THROW_ON_ERROR),
    $input['event_key'],
    'created',
    422
);
$assert($validatedTerminal['result'] === 'terminal_error', 'Valid terminal result failed.');
$assert($rejected($terminalEnvelope, 409), 'Terminal result accepted operator-review status 409.');
$terminalSlackEnvelope = $terminalEnvelope;
$terminalSlackEnvelope['processing_phase'] = 'slack_pending';
$terminalSlackEnvelope['remote_contact_id'] = 'synthetic-contact-1';
$terminalSlackEnvelope['remote_deal_id'] = 'synthetic-deal-1';
$terminalSlackEnvelope['slack_status'] = 'failed_before_post';
$terminalSlackEnvelope['error_code'] = 'SLACK_AUTH';
$validatedTerminalSlack = OddRoom_Worker::validateEnvelope(
    json_encode($terminalSlackEnvelope, JSON_THROW_ON_ERROR),
    $input['event_key'],
    'created',
    422
);
$assert($validatedTerminalSlack['slack_status'] === 'failed_before_post', 'Definite terminal Slack rejection failed.');

$badDuplicate = $envelope;
$badDuplicate['result'] = 'duplicate_noop';
$badDuplicate['retryable'] = true;
$assert($rejected($badDuplicate, 200), 'Retryable duplicate_noop was accepted.');
$badSlackPhase = $retryEnvelope;
$badSlackPhase['processing_phase'] = 'associated';
$assert($rejected($badSlackPhase, 503), 'failed_before_post accepted a non-slack_pending phase.');
$missingContactCheckpoint = $retryEnvelope;
$missingContactCheckpoint['processing_phase'] = 'contact_upserted';
$missingContactCheckpoint['remote_contact_id'] = null;
$missingContactCheckpoint['remote_deal_id'] = null;
$missingContactCheckpoint['slack_status'] = 'pending';
$assert($rejected($missingContactCheckpoint, 503), 'A contact_upserted phase without its Contact checkpoint was accepted.');
$missingDealCheckpoint = $retryEnvelope;
$missingDealCheckpoint['processing_phase'] = 'deal_upserted';
$missingDealCheckpoint['remote_deal_id'] = null;
$missingDealCheckpoint['slack_status'] = 'pending';
$assert($rejected($missingDealCheckpoint, 503), 'A deal_upserted phase without its Deal checkpoint was accepted.');
$validStale = $envelope;
$validStale['result'] = 'stale_ignored';
$validStale['remote_contact_id'] = null;
$validatedStale = OddRoom_Worker::validateEnvelope(
    json_encode($validStale, JSON_THROW_ON_ERROR),
    $input['event_key'],
    'created',
    200
);
$assert($validatedStale['remote_deal_id'] === 'synthetic-deal-1', 'A stale short-circuit with its authoritative Deal checkpoint was rejected.');
$badStaleContact = $validStale;
$badStaleContact['remote_contact_id'] = 'synthetic-contact-1';
$assert($rejected($badStaleContact, 200), 'A stale short-circuit established a Contact checkpoint.');
$badStaleSlack = $validStale;
$badStaleSlack['slack_status'] = 'posted';
$badStaleSlack['slack_message_ts'] = '123.456';
$assert($rejected($badStaleSlack, 200), 'A stale short-circuit claimed a Slack post.');
$badDuplicateSlack = $envelope;
$badDuplicateSlack['result'] = 'duplicate_noop';
$badDuplicateSlack['slack_status'] = 'posted';
$badDuplicateSlack['slack_message_ts'] = '123.456';
$assert($rejected($badDuplicateSlack, 200), 'A duplicate no-op claimed a new Slack post.');
$oversizedCheckpoint = $envelope;
$oversizedCheckpoint['remote_deal_id'] = str_repeat('x', 129);
$assert($rejected($oversizedCheckpoint, 200), 'Oversized response checkpoint was accepted.');
$badErrorCode = $terminalEnvelope;
$badErrorCode['error_code'] = 'not-stable';
$assert($rejected($badErrorCode, 422), 'Malformed stable error code was accepted.');

$retryAfterMethod = new ReflectionMethod(OddRoom_Worker::class, 'retryAfter');
$assert(
    $retryAfterMethod->invoke(null, ['headers' => ['retry-after' => '00090001']]) === 90001,
    'Strict delta-seconds Retry-After parsing failed.'
);
$assert(
    $retryAfterMethod->invoke(null, ['headers' => ['retry-after' => '1e5']]) === null,
    'Scientific-notation Retry-After was accepted.'
);
$assert(
    $retryAfterMethod->invoke(null, ['headers' => ['retry-after' => '1.5']]) === null,
    'Fractional Retry-After was accepted.'
);
$futureRetryAfter = gmdate('D, d M Y H:i:s \\G\\M\\T', time() + 120);
$parsedFutureRetryAfter = $retryAfterMethod->invoke(null, ['headers' => ['retry-after' => $futureRetryAfter]]);
$assert(
    is_int($parsedFutureRetryAfter) && $parsedFutureRetryAfter >= 118 && $parsedFutureRetryAfter <= 120,
    'RFC 7231 date Retry-After parsing failed.'
);

$invalidDisposition = new ReflectionMethod(OddRoom_Worker::class, 'invalidResponseDisposition');
$assert(
    $invalidDisposition->invoke(null, true, 422) === 'ambiguous_slack',
    'A malformed Slack-event 4xx response was treated as terminal.'
);
$assert(
    $invalidDisposition->invoke(null, true, 429) === 'retryable',
    'A Slack-event 429 response was not retained as retryable.'
);
$assert(
    $invalidDisposition->invoke(null, false, 422) === 'terminal',
    'A malformed non-Slack terminal 4xx response was not terminal.'
);
$assert(
    $invalidDisposition->invoke(null, false, 503) === 'retryable',
    'A malformed non-Slack 5xx response was not retryable.'
);

fwrite(STDOUT, "PASS: {$tests} bootstrap unit assertions\n");
