<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Signature
{
    public static function baseString(int $timestamp, string $eventKey, string $resumePhase, string $body): string
    {
        if ($timestamp < 1 || $eventKey === '' || !in_array($resumePhase, self::allowedPhases(), true)) {
            throw new InvalidArgumentException('Signature input is invalid.');
        }
        return $timestamp . '.' . $eventKey . '.' . $resumePhase . '.' . $body;
    }

    public static function sign(int $timestamp, string $eventKey, string $resumePhase, string $body, string $secret): string
    {
        if ($secret === '') {
            throw new InvalidArgumentException('Signing secret is empty.');
        }
        return 'v1=' . hash_hmac('sha256', self::baseString($timestamp, $eventKey, $resumePhase, $body), $secret);
    }

    public static function verify(string $provided, int $timestamp, string $eventKey, string $resumePhase, string $body, string $secret): bool
    {
        return hash_equals(self::sign($timestamp, $eventKey, $resumePhase, $body, $secret), $provided);
    }

    private static function allowedPhases(): array
    {
        return ['created', 'deal_resolved', 'contact_upserted', 'deal_upserted', 'associated', 'slack_pending'];
    }
}

