<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Canonical_Payload
{
    public const SCHEMA_VERSION = '1';
    public const MAX_BODY_BYTES = 262144;

    private const EVENT_RANKS = [
        'ORDER_CREATED' => 10,
        'PAYMENT_CONFIRMED' => 20,
        'ORDER_CANCELLED' => 30,
        'ORDER_REFUNDED' => 40,
    ];

    public static function rankFor(string $eventType): int
    {
        if (!isset(self::EVENT_RANKS[$eventType])) {
            throw new InvalidArgumentException('Unsupported event type.');
        }
        return self::EVENT_RANKS[$eventType];
    }

    public static function encode(array $input): string
    {
        self::requireKeys($input, [
            'event_key', 'shop_instance_id', 'run_id', 'event_type',
            'occurred_at_utc', 'occurred_at_source', 'order',
        ]);

        $eventType = (string) $input['event_type'];
        $stateRank = self::rankFor($eventType);

        $order = self::normalizeOrder($input['order']);
        $payload = [
            'schema_version' => self::SCHEMA_VERSION,
            'event_key' => (string) $input['event_key'],
            'shop_instance_id' => (string) $input['shop_instance_id'],
            'run_id' => (string) $input['run_id'],
            'event_type' => $eventType,
            'occurred_at_utc' => (string) $input['occurred_at_utc'],
            'occurred_at_source' => (string) $input['occurred_at_source'],
            'state_rank' => $stateRank,
            'order' => $order,
        ];

        $flags = JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION;
        $json = function_exists('wp_json_encode')
            ? wp_json_encode($payload, $flags)
            : json_encode($payload, $flags | JSON_THROW_ON_ERROR);

        if (!is_string($json) || $json === '' || strlen($json) > self::MAX_BODY_BYTES) {
            throw new LengthException('Canonical payload size is invalid.');
        }

        return $json;
    }

    public static function hash(string $json): string
    {
        return hash('sha256', $json);
    }

    private static function normalizeOrder(mixed $value): array
    {
        if (!is_array($value)) {
            throw new InvalidArgumentException('Order must be an object.');
        }

        self::requireKeys($value, ['id', 'number', 'currency', 'total', 'customer', 'items', 'coupon_codes']);
        if (!is_array($value['customer']) || !is_array($value['items']) || !is_array($value['coupon_codes'])) {
            throw new InvalidArgumentException('Order child types are invalid.');
        }
        self::requireKeys($value['customer'], ['email', 'first_name', 'last_name']);
        if (count($value['items']) < 1 || count($value['items']) > 100 || count($value['coupon_codes']) > 50) {
            throw new LengthException('Order array bounds are invalid.');
        }

        $items = [];
        foreach ($value['items'] as $item) {
            if (!is_array($item)) {
                throw new InvalidArgumentException('Order item must be an object.');
            }
            self::requireKeys($item, ['item_id', 'product_id', 'variation_id', 'sku', 'name', 'quantity', 'line_total']);
            $items[] = [
                'item_id' => self::nonNegativeInt($item['item_id']),
                'product_id' => self::nonNegativeInt($item['product_id']),
                'variation_id' => self::nonNegativeInt($item['variation_id']),
                'sku' => self::boundedString($item['sku'], 255),
                'name' => self::boundedString($item['name'], 255),
                'quantity' => self::positiveInt($item['quantity'], 1000000),
                'line_total' => self::money($item['line_total']),
            ];
        }
        usort($items, static fn(array $a, array $b): int => $a['item_id'] <=> $b['item_id']);

        $coupons = array_map(static fn(mixed $code): string => self::boundedString($code, 255), $value['coupon_codes']);
        sort($coupons, SORT_STRING);

        $currency = (string) $value['currency'];
        if (!preg_match('/^[A-Z]{3}$/', $currency)) {
            throw new InvalidArgumentException('Currency is invalid.');
        }

        return [
            'id' => self::nonNegativeInt($value['id']),
            'number' => self::boundedString($value['number'], 255),
            'currency' => $currency,
            'total' => self::money($value['total']),
            'customer' => [
                'email' => self::boundedString(strtolower((string) $value['customer']['email']), 254),
                'first_name' => self::boundedString($value['customer']['first_name'], 255),
                'last_name' => self::boundedString($value['customer']['last_name'], 255),
            ],
            'items' => $items,
            'coupon_codes' => $coupons,
        ];
    }

    private static function requireKeys(array $value, array $keys): void
    {
        foreach ($keys as $key) {
            if (!array_key_exists($key, $value)) {
                throw new InvalidArgumentException('Missing required field: ' . $key);
            }
        }
    }

    private static function nonNegativeInt(mixed $value): int
    {
        if (!is_int($value) || $value < 0) {
            throw new InvalidArgumentException('Expected non-negative integer.');
        }
        return $value;
    }

    private static function positiveInt(mixed $value, int $max): int
    {
        if (!is_int($value) || $value < 1 || $value > $max) {
            throw new InvalidArgumentException('Expected bounded positive integer.');
        }
        return $value;
    }

    private static function boundedString(mixed $value, int $max): string
    {
        if (!is_string($value) || $value === '' || self::length($value) > $max) {
            throw new InvalidArgumentException('String bound is invalid.');
        }
        return $value;
    }

    private static function money(mixed $value): string
    {
        if (!is_string($value) || !preg_match('/^(?:0|[1-9][0-9]{0,17})\.[0-9]{2}$/', $value)) {
            throw new InvalidArgumentException('Money must be a two-decimal non-negative string.');
        }
        return $value;
    }

    private static function length(string $value): int
    {
        return function_exists('mb_strlen') ? mb_strlen($value, 'UTF-8') : strlen($value);
    }
}
