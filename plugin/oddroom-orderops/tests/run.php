<?php

define('ODDROOM_ORDEROPS_TESTING', true);
require_once __DIR__ . '/../includes/class-oddroom-canonical-payload.php';
require_once __DIR__ . '/../includes/class-oddroom-signature.php';
require_once __DIR__ . '/../includes/class-oddroom-state-machine.php';
require_once __DIR__ . '/../includes/class-oddroom-retry-policy.php';

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

$signature = OddRoom_Signature::sign(1784390400, $input['event_key'], 'created', $json, 'synthetic-test-secret');
$assert(OddRoom_Signature::verify($signature, 1784390400, $input['event_key'], 'created', $json, 'synthetic-test-secret'), 'Valid signature failed.');
$assert(!OddRoom_Signature::verify($signature, 1784390400, $input['event_key'], 'created', $json . ' ', 'synthetic-test-secret'), 'Mutated body passed.');

OddRoom_State_Machine::assertMonotonic('deal_resolved', 'deal_upserted');
$assert(OddRoom_State_Machine::checkpoint(null, 'remote-1') === 'remote-1', 'Checkpoint insert failed.');
$assert(OddRoom_State_Machine::checkpoint('remote-1', 'remote-1') === 'remote-1', 'Checkpoint replay failed.');

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

fwrite(STDOUT, "PASS: {$tests} bootstrap unit assertions\n");

