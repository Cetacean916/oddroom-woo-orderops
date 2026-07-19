<?php

defined('ABSPATH') || exit;

final class OddRoom_Scheduler
{
    public const HOOK = 'oddroom_orderops_process';
    public const PREFLIGHT_HOOK = 'oddroom_orderops_preflight_noop';
    public const GROUP = 'oddroom-orderops';
    private const PREFLIGHT_OPTION = 'oddroom_orderops_as_preflight';
    private static ?int $executionId = null;

    public static function boot(): void
    {
        add_action('action_scheduler_begin_execute', [self::class, 'captureExecution'], 1, 2);
        add_action('action_scheduler_after_execute', [self::class, 'clearExecution'], PHP_INT_MAX, 1);
        add_action('action_scheduler_failed_execution', [self::class, 'clearExecution'], PHP_INT_MAX, 1);
        add_action('action_scheduler_completed_action', [self::class, 'handleCompletedBusinessAction'], 10, 1);
        add_action(self::HOOK, [OddRoom_Worker::class, 'process'], 10, 1);
        add_action(self::PREFLIGHT_HOOK, '__return_null', 10, 1);
        add_action('action_scheduler_init', [self::class, 'scheduleEligibleRows'], 50);
        add_action('init', [self::class, 'scheduleEligibleRows'], 50);
    }

    public static function captureExecution(int $actionId, string $context = ''): void
    {
        self::$executionId = $actionId > 0 ? $actionId : null;
    }

    public static function clearExecution(int $actionId = 0): void
    {
        self::$executionId = null;
    }

    public static function currentExecutionId(): ?int
    {
        return self::$executionId;
    }

    public static function runtimeIdentity(): array
    {
        $initialized = class_exists('ActionScheduler') && ActionScheduler::is_initialized();
        $version = $initialized && class_exists('ActionScheduler_Versions')
            ? (string) ActionScheduler_Versions::instance()->latest_version()
            : null;
        $source = null;
        if ($initialized && class_exists('ActionScheduler_SystemInformation')) {
            $path = wp_normalize_path(ActionScheduler_SystemInformation::active_source_path());
            $pluginRoot = trailingslashit(wp_normalize_path(WP_PLUGIN_DIR));
            $source = str_starts_with($path, $pluginRoot)
                ? 'plugin:' . ltrim(substr($path, strlen($pluginRoot)), '/')
                : 'non-plugin:' . basename(untrailingslashit($path));
        }
        return ['initialized' => $initialized, 'version' => $version, 'source' => $source];
    }

    public static function guard(bool $requirePreflight = true): array
    {
        $identity = self::runtimeIdentity();
        if (!$identity['initialized']) {
            return self::healthFailure('ACTION_SCHEDULER_NOT_READY', $identity);
        }
        if ($identity['version'] === null || version_compare($identity['version'], '4.0.0', '<')) {
            return self::healthFailure('ACTION_SCHEDULER_VERSION_UNSUPPORTED', $identity);
        }
        if ($requirePreflight) {
            $record = get_option(self::PREFLIGHT_OPTION);
            $matches = is_array($record)
                && ($record['status'] ?? null) === 'PASS'
                && ($record['version'] ?? null) === $identity['version']
                && ($record['source'] ?? null) === $identity['source'];
            if (!$matches) {
                return self::healthFailure('ACTION_SCHEDULER_PREFLIGHT_REQUIRED', $identity);
            }
        }
        self::clearSchedulerHealth();
        return ['ok' => true, 'code' => null] + $identity;
    }

    private static function healthFailure(string $code, array $identity): array
    {
        update_option('oddroom_orderops_health_error', $code, false);
        return ['ok' => false, 'code' => $code] + $identity;
    }

    private static function clearSchedulerHealth(): void
    {
        $current = get_option('oddroom_orderops_health_error');
        if (in_array($current, [
            'ACTION_SCHEDULER_NOT_READY',
            'ACTION_SCHEDULER_VERSION_UNSUPPORTED',
            'ACTION_SCHEDULER_PREFLIGHT_REQUIRED',
        ], true)) {
            update_option('oddroom_orderops_health_error', '', false);
        }
    }

    public static function runPreflight(): array
    {
        $guard = self::guard(false);
        if (!$guard['ok']) {
            update_option('oddroom_orderops_health_error', $guard['code'], false);
            return ['status' => 'HOLD', 'error_code' => $guard['code']] + $guard;
        }

        self::cancelExact(self::PREFLIGHT_HOOK, 101);
        self::cancelExact(self::PREFLIGHT_HOOK, 102);
        $when = time() + DAY_IN_SECONDS;
        $id101 = (int) as_schedule_single_action($when, self::PREFLIGHT_HOOK, [101], self::GROUP, true);
        $id102 = (int) as_schedule_single_action($when, self::PREFLIGHT_HOOK, [102], self::GROUP, true);
        $duplicateRaw = (int) as_schedule_single_action($when, self::PREFLIGHT_HOOK, [101], self::GROUP, true);
        $candidates101 = self::exactCandidates(self::PREFLIGHT_HOOK, 101);
        $candidates102 = self::exactCandidates(self::PREFLIGHT_HOOK, 102);
        $resolved101 = count($candidates101) === 1 ? (int) $candidates101[0] : 0;

        $pass = $id101 > 0
            && $id102 > 0
            && $id101 !== $id102
            && $duplicateRaw === 0
            && $candidates101 === [$id101]
            && $candidates102 === [$id102]
            && $resolved101 === $id101;

        $record = [
            'status' => $pass ? 'PASS' : 'HOLD',
            'version' => $guard['version'],
            'source' => $guard['source'],
            'observed_at_utc' => gmdate('c'),
            'row_101' => ['action_id' => $id101, 'candidate_ids' => $candidates101],
            'row_102' => ['action_id' => $id102, 'candidate_ids' => $candidates102],
            'duplicate_row_101_raw_id' => $duplicateRaw,
            'resolved_row_101_id' => $resolved101,
            'business_rows_mutated' => 0,
            'business_attempts_consumed' => 0,
            'business_leases_consumed' => 0,
        ];

        self::cancelIds(array_values(array_unique(array_merge($candidates101, $candidates102))));
        $record['remaining_candidate_count'] = count(self::exactCandidates(self::PREFLIGHT_HOOK, 101))
            + count(self::exactCandidates(self::PREFLIGHT_HOOK, 102));
        if ($record['remaining_candidate_count'] !== 0) {
            $record['status'] = 'HOLD';
        }

        update_option(self::PREFLIGHT_OPTION, $record, false);
        update_option(
            'oddroom_orderops_health_error',
            $record['status'] === 'PASS' ? '' : 'ACTION_SCHEDULER_PREFLIGHT_REQUIRED',
            false
        );
        return $record;
    }

    public static function scheduleEligibleRows(): void
    {
        if (!self::guard(true)['ok']) {
            return;
        }
        self::repairFinishedEligibleLinks();
        foreach (OddRoom_Repository::eligibleUnscheduledIds(50) as $rowId) {
            $row = OddRoom_Repository::find((int) $rowId);
            if ($row) {
                self::scheduleEligibleRow($row);
            }
        }
    }

    public static function scheduleBusiness(int $rowId, ?int $timestamp = null): int
    {
        $guard = self::guard(true);
        if (!$guard['ok']) {
            OddRoom_Repository::recordSchedulingError($rowId, $guard['code'], false);
            return 0;
        }

        $timestamp ??= time();
        $actionId = (int) as_schedule_single_action($timestamp, self::HOOK, [$rowId], self::GROUP, true);
        $createdAction = $actionId > 0;
        if ($actionId === 0) {
            $candidates = self::exactCandidates(self::HOOK, $rowId);
            if (count($candidates) === 1) {
                $actionId = (int) $candidates[0];
            } elseif (count($candidates) > 1) {
                OddRoom_Repository::recordSchedulingError($rowId, 'ACTION_ID_AMBIGUOUS', true);
                return 0;
            } else {
                OddRoom_Repository::recordSchedulingError($rowId, 'ACTION_SCHEDULE_FAILED', false);
                return 0;
            }
        }

        if (!OddRoom_Repository::linkAction($rowId, $actionId)) {
            $row = OddRoom_Repository::find($rowId);
            if (!$row || (int) ($row->action_id ?? 0) !== $actionId) {
                if ($createdAction) {
                    self::cancelIds([$actionId]);
                }
                return 0;
            }
        }
        return $actionId;
    }

    public static function handleCompletedBusinessAction(int $actionId): void
    {
        $rowId = self::completedBusinessRowId($actionId);
        if ($rowId === null) {
            return;
        }
        $row = OddRoom_Repository::find($rowId);
        if (!$row || $row->lock_token !== null
            || !in_array((string) $row->status, ['pending', 'retry_wait'], true)) {
            return;
        }

        $linkedActionId = (int) ($row->action_id ?? 0);
        if ($linkedActionId === $actionId) {
            if (!OddRoom_Repository::unlinkFinishedEligibleAction($rowId, $actionId)) {
                return;
            }
            $row = OddRoom_Repository::find($rowId);
        } elseif ($linkedActionId !== 0) {
            return;
        }

        if ($row) {
            self::scheduleEligibleRow($row);
        }
    }

    private static function completedBusinessRowId(int $actionId): ?int
    {
        if ($actionId < 1 || !class_exists('ActionScheduler')) {
            return null;
        }
        try {
            $action = ActionScheduler::store()->fetch_action($actionId);
            if (!is_object($action)
                || $action->get_hook() !== self::HOOK
                || $action->get_group() !== self::GROUP) {
                return null;
            }
            $args = $action->get_args();
            if (!is_array($args) || count($args) !== 1 || !is_int($args[0]) || $args[0] < 1) {
                return null;
            }
            return self::actionMatches($actionId, $args[0]) ? $args[0] : null;
        } catch (Throwable $error) {
            return null;
        }
    }

    private static function repairFinishedEligibleLinks(): void
    {
        foreach (OddRoom_Repository::linkedEligibleRows(50) as $row) {
            $rowId = (int) $row->id;
            $actionId = (int) $row->action_id;
            if ($rowId < 1 || $actionId < 1) {
                continue;
            }
            $candidates = self::exactCandidates(self::HOOK, $rowId);
            if (count($candidates) > 1) {
                OddRoom_Repository::recordSchedulingError($rowId, 'ACTION_ID_AMBIGUOUS', true);
                continue;
            }
            if ($candidates === [$actionId]) {
                continue;
            }
            if (!OddRoom_Repository::unlinkFinishedEligibleAction($rowId, $actionId)) {
                continue;
            }
            $current = OddRoom_Repository::find($rowId);
            if ($current) {
                self::scheduleEligibleRow($current);
            }
        }
    }

    private static function scheduleEligibleRow(object $row, int $notBefore = 0): void
    {
        if ($row->lock_token !== null
            || $row->action_id !== null
            || self::schedulingSuppressed($row)) {
            return;
        }
        $rowId = (int) $row->id;
        if ($rowId < 1 || (string) $row->status === 'pending') {
            if ($rowId > 0 && (string) $row->status === 'pending') {
                self::scheduleBusiness($rowId, max(time(), $notBefore));
            }
            return;
        }
        if ((string) $row->status !== 'retry_wait'
            || !is_string($row->next_attempt_at)
            || $row->next_attempt_at === '') {
            return;
        }
        $timestamp = strtotime($row->next_attempt_at . ' UTC');
        self::scheduleBusiness(
            $rowId,
            max(time(), $notBefore, $timestamp === false ? time() : $timestamp)
        );
    }

    private static function schedulingSuppressed(object $row): bool
    {
        return OddRoom_Repository::testMode()
            && isset($row->order_id, $row->event_type)
            && OddRoom_Faults::isActiveForEvent(
                (int) $row->order_id,
                (string) $row->event_type,
                OddRoom_Faults::SUPPRESS_SCHEDULE
            );
    }

    public static function deferContentionRequeue(int $rowId, int $actionId): void
    {
        if ($rowId < 1 || $actionId < 1) {
            return;
        }
        register_shutdown_function(static function () use ($rowId, $actionId): void {
            $row = OddRoom_Repository::find($rowId);
            if (!$row
                || (int) ($row->action_id ?? 0) !== $actionId
                || $row->lock_token !== null
                || !in_array((string) $row->status, ['pending', 'retry_wait'], true)
                || self::exactCandidates(self::HOOK, $rowId) !== []) {
                return;
            }
            if (!OddRoom_Repository::unlinkFinishedEligibleAction($rowId, $actionId)) {
                return;
            }
            $current = OddRoom_Repository::find($rowId);
            if ($current) {
                self::scheduleEligibleRow($current, time() + 2);
            }
        });
    }

    public static function exactCandidates(string $hook, int $rowId): array
    {
        return self::exactCandidatesForStatuses($hook, $rowId, ['pending', 'in-progress']);
    }

    private static function exactCandidatesForStatuses(string $hook, int $rowId, array $statuses): array
    {
        if (!self::runtimeIdentity()['initialized'] || !function_exists('as_get_scheduled_actions')) {
            return [];
        }
        $ids = [];
        foreach ($statuses as $status) {
            $found = as_get_scheduled_actions([
                'hook' => $hook,
                'args' => [$rowId],
                'group' => self::GROUP,
                'status' => $status,
                'per_page' => -1,
                'orderby' => 'none',
            ], 'ids');
            foreach ($found as $id) {
                $ids[(int) $id] = true;
            }
        }
        $result = array_keys($ids);
        sort($result, SORT_NUMERIC);
        return $result;
    }

    public static function actionMatches(int $actionId, int $rowId): bool
    {
        if ($actionId < 1 || !class_exists('ActionScheduler')) {
            return false;
        }
        try {
            $action = ActionScheduler::store()->fetch_action($actionId);
            return is_object($action)
                && $action->get_hook() === self::HOOK
                && $action->get_args() === [$rowId]
                && $action->get_group() === self::GROUP;
        } catch (Throwable $error) {
            return false;
        }
    }

    private static function cancelExact(string $hook, int $rowId): void
    {
        self::cancelIds(self::exactCandidates($hook, $rowId));
    }

    private static function cancelIds(array $ids): void
    {
        if (!class_exists('ActionScheduler')) {
            return;
        }
        foreach ($ids as $id) {
            try {
                ActionScheduler::store()->cancel_action((int) $id);
            } catch (Throwable $error) {
                // The final candidate-count check decides the preflight result.
            }
        }
    }
}
