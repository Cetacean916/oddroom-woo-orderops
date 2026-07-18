<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_State_Machine
{
    private const PHASES = [
        'created', 'deal_resolved', 'contact_upserted', 'deal_upserted',
        'associated', 'slack_pending', 'slack_posted', 'completed',
    ];

    public static function assertMonotonic(string $current, string $next): void
    {
        $currentRank = array_search($current, self::PHASES, true);
        $nextRank = array_search($next, self::PHASES, true);
        if ($currentRank === false || $nextRank === false || $nextRank < $currentRank) {
            throw new DomainException('Processing phase regression.');
        }
    }

    public static function checkpoint(?string $stored, ?string $returned): ?string
    {
        if ($stored !== null && $returned !== null && $stored !== $returned) {
            throw new DomainException('CHECKPOINT_CONFLICT');
        }
        return $stored ?? $returned;
    }
}

