<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Canonical_Payload
{
    public const SCHEMA_VERSION = '1';
    public const MAX_BODY_BYTES = 262144;
    public const SELECTED_CURRENCY = 'KRW';
    public const SELECTED_CURRENCY_PRECISION = 2;

    private const EVENT_RANKS = [
        'ORDER_CREATED' => 10,
        'PAYMENT_CONFIRMED' => 20,
        'ORDER_CANCELLED' => 30,
        'ORDER_REFUNDED' => 40,
    ];

    private const EVENT_SOURCES = [
        'ORDER_CREATED' => 'date_created',
        'PAYMENT_CONFIRMED' => 'date_paid',
        'ORDER_CANCELLED' => '_oddroom_orderops_cancelled_at_utc',
        'ORDER_REFUNDED' => 'full_refund_completion',
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
        self::requireExactKeys($input, [
            'event_key', 'shop_instance_id', 'run_id', 'event_type',
            'occurred_at_utc', 'occurred_at_source', 'order',
        ]);

        $eventType = (string) $input['event_type'];
        $stateRank = self::rankFor($eventType);
        $order = self::normalizeOrder($input['order']);

        $shopInstanceId = self::boundedString($input['shop_instance_id'], 64);
        if (!preg_match('/^pf07-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D', $shopInstanceId)) {
            throw new InvalidArgumentException('Shop instance ID is invalid.');
        }
        $runId = self::boundedString($input['run_id'], 36);
        if (!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D', $runId)) {
            throw new InvalidArgumentException('Run ID is invalid.');
        }
        $occurredAtUtc = self::utcSecond($input['occurred_at_utc']);
        $occurredAtSource = self::boundedString($input['occurred_at_source'], 64);
        if ($occurredAtSource !== self::EVENT_SOURCES[$eventType]) {
            throw new InvalidArgumentException('Event occurrence source is invalid.');
        }
        $eventKey = self::boundedString($input['event_key'], 255);
        if ($eventKey !== "v1:{$shopInstanceId}:{$order['id']}:{$eventType}") {
            throw new InvalidArgumentException('Event key is invalid.');
        }

        $payload = [
            'schema_version' => self::SCHEMA_VERSION,
            'event_key' => $eventKey,
            'shop_instance_id' => $shopInstanceId,
            'run_id' => $runId,
            'event_type' => $eventType,
            'occurred_at_utc' => $occurredAtUtc,
            'occurred_at_source' => $occurredAtSource,
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

    public static function normalizeMoney(mixed $value): string
    {
        if (!is_string($value) && !is_int($value)) {
            throw new InvalidArgumentException('Money must be a decimal string or integer.');
        }
        $raw = (string) $value;
        if (!preg_match('/^(0|[1-9][0-9]{0,17})(?:\.([0-9]+))?$/D', $raw, $matches)) {
            throw new InvalidArgumentException('Money is not a non-negative decimal.');
        }
        $fraction = $matches[2] ?? '';
        $excess = substr($fraction, self::SELECTED_CURRENCY_PRECISION);
        if ($excess !== '' && trim($excess, '0') !== '') {
            throw new InvalidArgumentException('Money exceeds the selected WooCommerce currency precision.');
        }
        $fraction = str_pad(
            substr($fraction, 0, self::SELECTED_CURRENCY_PRECISION),
            self::SELECTED_CURRENCY_PRECISION,
            '0'
        );
        return $matches[1] . '.' . $fraction;
    }

    public static function toMinorUnits(mixed $value): string
    {
        $normalized = self::normalizeMoney($value);
        $minor = ltrim(str_replace('.', '', $normalized), '0');
        return $minor === '' ? '0' : $minor;
    }

    public static function addMinorUnits(string $left, string $right): string
    {
        self::assertMinorUnits($left);
        self::assertMinorUnits($right);
        $leftIndex = strlen($left) - 1;
        $rightIndex = strlen($right) - 1;
        $carry = 0;
        $result = '';
        while ($leftIndex >= 0 || $rightIndex >= 0 || $carry !== 0) {
            $sum = $carry;
            if ($leftIndex >= 0) {
                $sum += ord($left[$leftIndex--]) - 48;
            }
            if ($rightIndex >= 0) {
                $sum += ord($right[$rightIndex--]) - 48;
            }
            $result = (string) ($sum % 10) . $result;
            $carry = intdiv($sum, 10);
        }
        $result = ltrim($result, '0');
        return $result === '' ? '0' : $result;
    }

    public static function compareMinorUnits(string $left, string $right): int
    {
        self::assertMinorUnits($left);
        self::assertMinorUnits($right);
        $left = ltrim($left, '0');
        $right = ltrim($right, '0');
        $left = $left === '' ? '0' : $left;
        $right = $right === '' ? '0' : $right;
        $lengthComparison = strlen($left) <=> strlen($right);
        return $lengthComparison !== 0 ? $lengthComparison : strcmp($left, $right);
    }

    public static function parseUtcTimestamp(mixed $value): DateTimeImmutable
    {
        if (!is_string($value)
            || !preg_match(
                '/^[1-9][0-9]{3}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.([0-9]{1,6}))?Z$/D',
                $value,
                $matches
            )) {
            throw new InvalidArgumentException('UTC timestamp is invalid.');
        }
        $fraction = isset($matches[1]) && $matches[1] !== '' ? $matches[1] : null;
        $parseValue = $fraction === null
            ? $value
            : substr($value, 0, -(strlen($fraction) + 2)) . '.' . str_pad($fraction, 6, '0') . 'Z';
        $parseFormat = $fraction === null ? '!Y-m-d\\TH:i:s\\Z' : '!Y-m-d\\TH:i:s.u\\Z';
        $outputFormat = $fraction === null ? 'Y-m-d\\TH:i:s\\Z' : 'Y-m-d\\TH:i:s.u\\Z';
        $parsed = DateTimeImmutable::createFromFormat($parseFormat, $parseValue, new DateTimeZone('UTC'));
        $errors = DateTimeImmutable::getLastErrors();
        if ($parsed === false
            || ($errors !== false && ($errors['warning_count'] !== 0 || $errors['error_count'] !== 0))
            || $parsed->format($outputFormat) !== $parseValue) {
            throw new InvalidArgumentException('UTC timestamp is invalid.');
        }
        return $parsed;
    }

    private static function normalizeOrder(mixed $value): array
    {
        if (!is_array($value)) {
            throw new InvalidArgumentException('Order must be an object.');
        }

        self::requireExactKeys($value, ['id', 'number', 'currency', 'total', 'customer', 'items', 'coupon_codes']);
        if (!is_array($value['customer']) || !is_array($value['items']) || !is_array($value['coupon_codes'])) {
            throw new InvalidArgumentException('Order child types are invalid.');
        }
        self::requireExactKeys($value['customer'], ['email', 'first_name', 'last_name']);
        if (count($value['items']) < 1 || count($value['items']) > 100 || count($value['coupon_codes']) > 50) {
            throw new LengthException('Order array bounds are invalid.');
        }

        $items = [];
        foreach ($value['items'] as $item) {
            if (!is_array($item)) {
                throw new InvalidArgumentException('Order item must be an object.');
            }
            self::requireExactKeys($item, ['item_id', 'product_id', 'variation_id', 'sku', 'name', 'quantity', 'line_total']);
            $items[] = [
                'item_id' => self::nonNegativeInt($item['item_id']),
                'product_id' => self::nonNegativeInt($item['product_id']),
                'variation_id' => self::nonNegativeInt($item['variation_id']),
                'sku' => self::boundedString($item['sku'], 255, 0),
                'name' => self::boundedString($item['name'], 255),
                'quantity' => self::positiveInt($item['quantity'], 1000000),
                'line_total' => self::money($item['line_total']),
            ];
        }
        usort($items, static fn(array $a, array $b): int => $a['item_id'] <=> $b['item_id']);

        $coupons = array_map(static fn(mixed $code): string => self::boundedString($code, 255), $value['coupon_codes']);
        sort($coupons, SORT_STRING);

        $currency = (string) $value['currency'];
        if (!preg_match('/^[A-Z]{3}$/', $currency) || $currency !== self::SELECTED_CURRENCY) {
            throw new InvalidArgumentException('Currency is invalid.');
        }

        $email = self::boundedString(strtolower((string) $value['customer']['email']), 254);
        if (!preg_match('/^[^@\s]+@example\.com$/D', $email)) {
            throw new InvalidArgumentException('Synthetic email is invalid.');
        }

        return [
            'id' => self::nonNegativeInt($value['id']),
            'number' => self::boundedString($value['number'], 255),
            'currency' => $currency,
            'total' => self::money($value['total']),
            'customer' => [
                'email' => $email,
                'first_name' => self::boundedString($value['customer']['first_name'], 255),
                'last_name' => self::boundedString($value['customer']['last_name'], 255),
            ],
            'items' => $items,
            'coupon_codes' => $coupons,
        ];
    }

    private static function requireExactKeys(array $value, array $keys): void
    {
        foreach ($keys as $key) {
            if (!array_key_exists($key, $value)) {
                throw new InvalidArgumentException('Missing required field: ' . $key);
            }
        }
        if (count($value) !== count($keys)) {
            throw new InvalidArgumentException('Unexpected object field.');
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

    private static function boundedString(mixed $value, int $max, int $min = 1): string
    {
        if (!is_string($value)) {
            throw new InvalidArgumentException('String bound is invalid.');
        }
        $length = self::length($value);
        if ($length < $min || $length > $max) {
            throw new InvalidArgumentException('String bound is invalid.');
        }
        return $value;
    }

    private static function utcSecond(mixed $value): string
    {
        if (!is_string($value)
            || !preg_match('/^[1-9][0-9]{3}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/D', $value)) {
            throw new InvalidArgumentException('UTC occurrence timestamp is invalid.');
        }
        self::parseUtcTimestamp($value);
        return $value;
    }

    private static function money(mixed $value): string
    {
        return self::normalizeMoney($value);
    }

    private static function assertMinorUnits(string $value): void
    {
        if (!preg_match('/^(?:0|[1-9][0-9]*)$/D', $value)) {
            throw new InvalidArgumentException('Minor-unit integer is invalid.');
        }
    }

    private static function length(string $value): int
    {
        if (preg_match('//u', $value) !== 1) {
            throw new InvalidArgumentException('String is not valid UTF-8.');
        }
        $length = preg_match_all('/./us', $value);
        if (!is_int($length)) {
            throw new InvalidArgumentException('String length is unavailable.');
        }
        return $length;
    }
}
