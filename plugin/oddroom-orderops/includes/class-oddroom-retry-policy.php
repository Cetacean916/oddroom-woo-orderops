<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Retry_Policy
{
    private const PRODUCTION_DELAYS = [1 => 60, 2 => 300, 3 => 900, 4 => 3600, 5 => 21600];
    private const TEST_DELAYS = [1 => 2, 2 => 5, 3 => 10, 4 => 20, 5 => 30];

    public static function delayAfter(int $automaticAttempt, bool $testMode = false): int
    {
        $delays = $testMode ? self::TEST_DELAYS : self::PRODUCTION_DELAYS;
        if (!isset($delays[$automaticAttempt])) {
            throw new OutOfRangeException('No follow-up delay for this attempt.');
        }
        return $delays[$automaticAttempt];
    }

    public static function attemptKind(int $attemptCount, int $automaticAttemptCount): string
    {
        if ($attemptCount < 1 || $automaticAttemptCount < 0 || $automaticAttemptCount > $attemptCount) {
            throw new InvalidArgumentException('Attempt counters are invalid.');
        }
        return $attemptCount === $automaticAttemptCount ? 'automatic' : 'manual';
    }
}

