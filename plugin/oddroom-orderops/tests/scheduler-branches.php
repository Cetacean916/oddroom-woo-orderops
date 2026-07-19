<?php

define('ABSPATH', '/wordpress/');
define('WP_PLUGIN_DIR', '/plugins');
define('ODDROOM_ORDEROPS_TESTING', true);

$GLOBALS['pf07_options'] = [];
$GLOBALS['pf07_initialized'] = false;
$GLOBALS['pf07_version'] = null;
$GLOBALS['pf07_schedule_return'] = 0;
$GLOBALS['pf07_schedule_calls'] = 0;
$GLOBALS['pf07_candidates'] = [];

function update_option(string $name, mixed $value, bool $autoload = false): bool
{
    $GLOBALS['pf07_options'][$name] = $value;
    return true;
}

function get_option(string $name, mixed $default = false): mixed
{
    return $GLOBALS['pf07_options'][$name] ?? $default;
}

function wp_normalize_path(string $path): string
{
    return str_replace('\\', '/', $path);
}

function trailingslashit(string $path): string
{
    return rtrim($path, '/') . '/';
}

function untrailingslashit(string $path): string
{
    return rtrim($path, '/');
}

function as_schedule_single_action(int $timestamp, string $hook, array $args, string $group, bool $unique): int
{
    $GLOBALS['pf07_schedule_calls']++;
    return (int) $GLOBALS['pf07_schedule_return'];
}

function as_get_scheduled_actions(array $query, string $returnFormat): array
{
    $rowId = (int) (($query['args'][0] ?? 0));
    return $GLOBALS['pf07_candidates'][$rowId] ?? [];
}

final class PF07_Fake_Action
{
    public function __construct(private int $rowId)
    {
    }

    public function get_hook(): string
    {
        return OddRoom_Scheduler::HOOK;
    }

    public function get_args(): array
    {
        return [$this->rowId];
    }

    public function get_group(): string
    {
        return OddRoom_Scheduler::GROUP;
    }
}

final class PF07_Fake_Store
{
    public function fetch_action(int $actionId): PF07_Fake_Action
    {
        $rowId = (int) ($GLOBALS['pf07_action_rows'][$actionId] ?? 0);
        return new PF07_Fake_Action($rowId);
    }
}

final class ActionScheduler
{
    public static function is_initialized(): bool
    {
        return (bool) $GLOBALS['pf07_initialized'];
    }

    public static function store(): PF07_Fake_Store
    {
        return new PF07_Fake_Store();
    }
}

final class ActionScheduler_Versions
{
    public static function instance(): self
    {
        return new self();
    }

    public function latest_version(): ?string
    {
        return $GLOBALS['pf07_version'];
    }
}

final class ActionScheduler_SystemInformation
{
    public static function active_source_path(): string
    {
        return '/plugins/action-scheduler/';
    }
}

final class OddRoom_Repository
{
    public static array $rows = [];
    public static int $claimCalls = 0;

    public static function row(int $id, ?int $actionId = null): object
    {
        self::$rows[$id] = (object) [
            'id' => $id,
            'status' => 'pending',
            'action_id' => $actionId,
            'attempt_count' => 0,
            'automatic_attempt_count' => 0,
            'lock_token' => null,
            'error_code' => null,
        ];
        if ($actionId !== null) {
            $GLOBALS['pf07_action_rows'][$actionId] = $id;
        }
        return self::$rows[$id];
    }

    public static function find(int $id): ?object
    {
        return self::$rows[$id] ?? null;
    }

    public static function recordSchedulingError(int $id, string $code, bool $terminal): void
    {
        $row = self::$rows[$id];
        $row->error_code = $code;
        if ($terminal) {
            $row->status = 'failed';
        }
    }

    public static function linkAction(int $id, int $actionId): bool
    {
        $row = self::$rows[$id];
        if ($row->action_id !== null && $row->action_id !== $actionId) {
            return false;
        }
        $row->action_id = $actionId;
        $GLOBALS['pf07_action_rows'][$actionId] = $id;
        return true;
    }

    public static function claim(int $rowId, int $actionId): ?array
    {
        self::$claimCalls++;
        return null;
    }

    public static function testMode(): bool
    {
        return true;
    }
}

require_once __DIR__ . '/../includes/class-oddroom-scheduler.php';
require_once __DIR__ . '/../includes/class-oddroom-worker.php';

$tests = 0;
$failures = [];
$assert = static function (bool $condition, string $message) use (&$tests, &$failures): void {
    $tests++;
    if (!$condition) {
        $failures[] = $message;
    }
};
$resetSchedule = static function (): void {
    $GLOBALS['pf07_schedule_calls'] = 0;
    $GLOBALS['pf07_schedule_return'] = 0;
    $GLOBALS['pf07_candidates'] = [];
};
$supportedPreflight = static function (): void {
    $GLOBALS['pf07_options']['oddroom_orderops_as_preflight'] = [
        'status' => 'PASS',
        'version' => '4.0.0',
        'source' => 'plugin:action-scheduler/',
    ];
};

$resetSchedule();
$GLOBALS['pf07_initialized'] = false;
$GLOBALS['pf07_version'] = null;
$row = OddRoom_Repository::row(1);
$returned = OddRoom_Scheduler::scheduleBusiness(1);
$assert($returned === 0, 'uninitialized scheduling returned an action');
$assert($GLOBALS['pf07_schedule_calls'] === 0, 'uninitialized scheduling called the scheduler API');
$assert($row->status === 'pending' && $row->action_id === null && $row->attempt_count === 0 && $row->lock_token === null, 'uninitialized scheduling mutated delivery state');
$assert($row->error_code === 'ACTION_SCHEDULER_NOT_READY', 'uninitialized scheduling health code differs');

$resetSchedule();
$GLOBALS['pf07_initialized'] = true;
$GLOBALS['pf07_version'] = '3.9.9';
$row = OddRoom_Repository::row(2);
$returned = OddRoom_Scheduler::scheduleBusiness(2);
$assert($returned === 0 && $GLOBALS['pf07_schedule_calls'] === 0, 'unsupported scheduling called or returned an action');
$assert($row->status === 'pending' && $row->action_id === null && $row->attempt_count === 0, 'unsupported scheduling mutated delivery state');
$assert($row->error_code === 'ACTION_SCHEDULER_VERSION_UNSUPPORTED', 'unsupported scheduling health code differs');
$linked = OddRoom_Repository::row(20, 200);
$claimsBefore = OddRoom_Repository::$claimCalls;
OddRoom_Scheduler::captureExecution(200, 'fixture');
OddRoom_Worker::process(20);
$assert(OddRoom_Repository::$claimCalls === $claimsBefore, 'unsupported linked callback acquired a claim');
$assert($linked->status === 'pending' && $linked->action_id === 200 && $linked->attempt_count === 0 && $linked->lock_token === null, 'unsupported linked callback mutated delivery state');

$resetSchedule();
$GLOBALS['pf07_initialized'] = true;
$GLOBALS['pf07_version'] = '4.0.0';
$GLOBALS['pf07_options']['oddroom_orderops_as_preflight'] = [
    'status' => 'PASS', 'version' => '4.0.0', 'source' => 'plugin:other-source',
];
$row = OddRoom_Repository::row(3);
$returned = OddRoom_Scheduler::scheduleBusiness(3);
$assert($returned === 0 && $GLOBALS['pf07_schedule_calls'] === 0, 'stale preflight scheduling called or returned an action');
$assert($row->status === 'pending' && $row->action_id === null && $row->attempt_count === 0, 'stale preflight scheduling mutated delivery state');
$assert($row->error_code === 'ACTION_SCHEDULER_PREFLIGHT_REQUIRED', 'stale preflight health code differs');
$linked = OddRoom_Repository::row(30, 300);
$claimsBefore = OddRoom_Repository::$claimCalls;
OddRoom_Scheduler::captureExecution(300, 'fixture');
OddRoom_Worker::process(30);
$assert(OddRoom_Repository::$claimCalls === $claimsBefore, 'stale-preflight linked callback acquired a claim');
$assert($linked->status === 'pending' && $linked->action_id === 300 && $linked->attempt_count === 0 && $linked->lock_token === null, 'stale-preflight linked callback mutated delivery state');

$resetSchedule();
$supportedPreflight();
$row = OddRoom_Repository::row(4);
$GLOBALS['pf07_schedule_return'] = 404;
$returned = OddRoom_Scheduler::scheduleBusiness(4);
$assert($returned === 404 && $row->action_id === 404 && $GLOBALS['pf07_schedule_calls'] === 1, 'positive scheduler ID was not stored');

$resetSchedule();
$supportedPreflight();
$row = OddRoom_Repository::row(5);
$GLOBALS['pf07_candidates'][5] = [505];
$returned = OddRoom_Scheduler::scheduleBusiness(5);
$assert($returned === 505 && $row->action_id === 505, 'one exact candidate was not reused');

$resetSchedule();
$supportedPreflight();
$row = OddRoom_Repository::row(6);
$returned = OddRoom_Scheduler::scheduleBusiness(6);
$assert($returned === 0 && $row->status === 'pending' && $row->action_id === null && $row->error_code === 'ACTION_SCHEDULE_FAILED' && $row->attempt_count === 0, 'zero-candidate failure branch differs');

$resetSchedule();
$supportedPreflight();
$row = OddRoom_Repository::row(7);
$GLOBALS['pf07_candidates'][7] = [701, 702];
$returned = OddRoom_Scheduler::scheduleBusiness(7);
$assert($returned === 0 && $row->status === 'failed' && $row->action_id === null && $row->error_code === 'ACTION_ID_AMBIGUOUS' && $row->attempt_count === 0, 'multiple-candidate failure branch differs');

$resetSchedule();
$supportedPreflight();
$row = OddRoom_Repository::row(8, 808);
$claimsBefore = OddRoom_Repository::$claimCalls;
OddRoom_Scheduler::clearExecution();
OddRoom_Worker::process(8);
$assert(OddRoom_Repository::$claimCalls === $claimsBefore, 'missing begin-execute ID acquired a claim');
$assert($row->status === 'pending' && $row->action_id === 808 && $row->attempt_count === 0 && $row->lock_token === null, 'missing begin-execute ID mutated delivery state');
OddRoom_Scheduler::captureExecution(809, 'fixture');
OddRoom_Worker::process(8);
$assert(OddRoom_Repository::$claimCalls === $claimsBefore, 'mismatched begin-execute ID acquired a claim');
$assert($row->status === 'pending' && $row->action_id === 808 && $row->attempt_count === 0 && $row->lock_token === null, 'mismatched begin-execute ID mutated delivery state');
$assert($GLOBALS['pf07_schedule_calls'] === 0 && OddRoom_Repository::$claimCalls === 0, 'failure branches consumed a scheduler call, lease, or external-effect path');

$record = [
    'exit_code' => $failures === [] ? 0 : 1,
    'assertion_count' => $tests,
    'failure_count' => count($failures),
    'failures' => $failures,
];
fwrite(STDOUT, json_encode($record, JSON_UNESCAPED_SLASHES) . PHP_EOL);
exit($record['exit_code']);
