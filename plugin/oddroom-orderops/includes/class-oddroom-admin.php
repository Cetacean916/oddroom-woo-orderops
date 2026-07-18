<?php

defined('ABSPATH') || exit;

final class OddRoom_Admin
{
    private const PAGE = 'oddroom-orderops';

    public static function boot(): void
    {
        add_action('admin_menu', [self::class, 'menu']);
        add_action('admin_post_oddroom_orderops_retry', [self::class, 'handleRetry']);
        add_action('admin_post_oddroom_orderops_resolve', [self::class, 'handleResolve']);
        add_action('admin_post_oddroom_orderops_reconcile', [self::class, 'handleReconcile']);
        add_action('admin_post_oddroom_orderops_fault_enable', [self::class, 'handleFaultEnable']);
        add_action('admin_post_oddroom_orderops_fault_end_run', [self::class, 'handleFaultEndRun']);
        add_action('admin_post_oddroom_orderops_reveal', [self::class, 'handleReveal']);
    }

    public static function menu(): void
    {
        add_submenu_page(
            'woocommerce',
            'OddRoom OrderOps',
            'OrderOps',
            'manage_woocommerce',
            self::PAGE,
            [self::class, 'render']
        );
    }

    public static function render(): void
    {
        self::requireCapability();
        $filters = self::filters();
        $rows = OddRoom_Repository::queryForAdmin($filters);
        $total = OddRoom_Repository::countForAdmin($filters);
        $pages = max(1, (int) ceil($total / $filters['per_page']));
        $identity = OddRoom_Scheduler::runtimeIdentity();
        $health = (string) get_option('oddroom_orderops_health_error', '');
        $counts = OddRoom_Repository::counts();
        $lastReconciliation = OddRoom_Reconciliation::lastResult();
        $reachability = get_option('oddroom_orderops_last_reachability');
        $lastSuccess = get_option('oddroom_orderops_last_successful_event');

        echo '<div class="wrap oddroom-orderops"><h1>OddRoom OrderOps</h1>';
        self::renderNotice();
        self::renderReveal();
        echo '<style>
            .oddroom-orderops .oddroom-health{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:16px 0}
            .oddroom-orderops .oddroom-card{background:#fff;border:1px solid #c3c4c7;padding:14px;box-sizing:border-box}
            .oddroom-orderops .oddroom-table-wrap{max-width:100%;overflow-x:auto;border:1px solid #c3c4c7;background:#fff}
            .oddroom-orderops table{min-width:2500px;border:0}.oddroom-orderops td,.oddroom-orderops th{vertical-align:top;overflow-wrap:anywhere}
            .oddroom-orderops .oddroom-actions{min-width:310px}.oddroom-orderops .oddroom-inline{display:inline-block;margin:0 6px 6px 0}
            .oddroom-orderops .oddroom-resolve{border:1px solid #c3c4c7;padding:8px}.oddroom-orderops .oddroom-resolve label{display:block;margin:6px 0}
            .oddroom-orderops .oddroom-resolve input,.oddroom-orderops .oddroom-resolve select{width:100%;max-width:290px}
            .oddroom-orderops .tablenav-pages{margin:12px 0}.oddroom-orderops code{overflow-wrap:anywhere}
        </style>';
        echo '<div class="oddroom-health">';
        self::card('Schema', OddRoom_Installer::SCHEMA_VERSION);
        self::card('Queue runner', 'FOREGROUND_WP_CLI · operator-driven');
        self::card('Action Scheduler', ($identity['version'] ?? 'unavailable') . ' · ' . ($identity['source'] ?? 'unavailable'));
        self::card('Database', OddRoom_Installer::tablesAreTransactional() ? 'InnoDB PASS' : 'HOLD');
        self::card('Health', $health === '' ? 'PASS' : $health);
        self::card('Rows / leases', $counts['outbox'] . ' / ' . $counts['leases']);
        self::card('Test mode', OddRoom_Repository::testMode() ? 'STAGING-ONLY' : 'disabled');
        self::card('Webhook alias', 'private-n8n / oddroom-orderops-v1');
        self::card('Credential aliases', 'PF07HubSpotRuntime1 · PF07SlackRuntime1');
        self::card(
            'Last reachability',
            is_array($reachability)
                ? (string) ($reachability['status'] ?? 'unknown') . ' / HTTP ' . (string) ($reachability['http_status'] ?? '—')
                : 'not yet observed'
        );
        self::card(
            'Last successful event',
            is_array($lastSuccess)
                ? (string) ($lastSuccess['event_type'] ?? 'unknown') . ' · ' . (string) ($lastSuccess['observed_at_utc'] ?? 'unknown')
                : 'not yet observed'
        );
        self::card(
            'Last reconciliation',
            is_array($lastReconciliation)
                ? (string) ($lastReconciliation['status'] ?? 'unknown') . ' · ' . (string) ($lastReconciliation['observed_at_utc'] ?? 'unknown')
                : 'not yet run'
        );
        echo '</div>';

        self::renderControls();
        self::renderFilters($filters);
        echo '<p>' . esc_html(sprintf('Showing %d rows; %d matched.', count($rows), $total)) . '</p>';
        echo '<div class="oddroom-table-wrap"><table class="widefat striped"><thead><tr>';
        $headings = [
            'ID', 'Event key', 'Order', 'Event', 'Status', 'Phase', 'Attempts total/automatic',
            'Max automatic', 'Manual retries', 'HTTP', 'Error code', 'Sanitized error',
            'Operator wait reason/epoch', 'Contact ID', 'Deal ID', 'Slack state/timestamp',
            'Next retry', 'Action ID', 'Dispatch state/attempt', 'Lock age',
            'Occurred UTC', 'Created UTC', 'Updated UTC', 'Actions',
        ];
        foreach ($headings as $heading) {
            echo '<th scope="col">' . esc_html($heading) . '</th>';
        }
        echo '</tr></thead><tbody>';
        if ($rows === []) {
            echo '<tr><td colspan="24">No matching events.</td></tr>';
        }
        foreach ($rows as $row) {
            echo '<tr>';
            $values = [
                $row->id,
                $row->event_key,
                $row->order_id,
                $row->event_type,
                $row->status,
                $row->processing_phase,
                $row->attempt_count . ' / ' . $row->automatic_attempt_count,
                $row->max_attempts,
                $row->manual_retry_count,
                $row->last_http_status ?? '—',
                $row->error_code ?? '—',
                $row->last_error ?? '—',
                ($row->operator_wait_reason ?? '—') . ' / ' . $row->operator_wait_epoch,
                self::maskIdentifier($row->remote_contact_id),
                self::maskIdentifier($row->remote_deal_id),
                $row->slack_status . ' / ' . self::maskIdentifier($row->slack_message_ts),
                $row->next_attempt_at ?? '—',
                $row->action_id ?? '—',
                $row->adapter_dispatch_state . ' / ' . ($row->adapter_dispatch_attempt ?? '—'),
                $row->lock_age_seconds === null ? 'free' : ((int) $row->lock_age_seconds . 's'),
                $row->occurred_at_utc,
                $row->created_at,
                $row->updated_at,
            ];
            foreach ($values as $value) {
                echo '<td>' . esc_html((string) $value) . '</td>';
            }
            echo '<td class="oddroom-actions">';
            self::renderRowActions($row);
            echo '</td></tr>';
        }
        echo '</tbody></table></div>';
        self::renderPagination($filters, $pages);
        echo '</div>';
    }

    public static function handleRetry(): void
    {
        $rowId = self::postedInt('row_id');
        self::authorize('oddroom_orderops_retry_' . $rowId);
        try {
            $result = OddRoom_Repository::manualRetry($rowId, get_current_user_id());
            self::redirectNotice('MANUAL_RETRY_SCHEDULED_' . (int) $result['action_id'], true);
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false);
        }
    }

    public static function handleResolve(): void
    {
        $rowId = self::postedInt('row_id');
        $epoch = self::postedInt('epoch');
        self::authorize('oddroom_orderops_resolve_' . $rowId . '_' . $epoch);
        try {
            $result = OddRoom_Repository::resolveOutcome([
                'row_id' => $rowId,
                'epoch' => $epoch,
                'administrator_id' => get_current_user_id(),
                'decision' => self::postedText('decision'),
                'evidence_ref' => self::postedText('evidence_ref'),
                'verified_phase' => self::postedText('verified_phase'),
                'remote_contact_id' => self::postedText('remote_contact_id'),
                'remote_deal_id' => self::postedText('remote_deal_id'),
                'slack_message_ts' => self::postedText('slack_message_ts'),
                'due_at_utc' => self::postedText('due_at_utc'),
            ]);
            $suffix = $result['idempotent'] ? '_IDEMPOTENT' : '';
            self::redirectNotice('OUTCOME_' . strtoupper((string) $result['status']) . $suffix, true);
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false);
        }
    }

    public static function handleReconcile(): void
    {
        self::authorize('oddroom_orderops_reconcile');
        try {
            $result = OddRoom_Reconciliation::run();
            self::redirectNotice(
                'RECONCILIATION_' . (string) $result['status']
                . '_INSERTED_' . (int) $result['inserted_rows']
                . '_SCHEDULED_' . (int) $result['scheduled_rows'],
                $result['status'] === 'PASS'
            );
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false);
        }
    }

    public static function handleFaultEnable(): void
    {
        self::authorize('oddroom_orderops_fault_enable');
        try {
            OddRoom_Faults::enable(
                self::postedInt('order_id'),
                self::postedText('event_type'),
                self::postedText('fault_type'),
                self::postedInt('minutes'),
                get_current_user_id()
            );
            self::redirectNotice('STAGING_FAULT_ENABLED', true);
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false);
        }
    }

    public static function handleFaultEndRun(): void
    {
        self::authorize('oddroom_orderops_fault_end_run');
        try {
            $disabled = OddRoom_Faults::endRun(
                OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_RUN_ID')
            );
            self::redirectNotice('RUN_FAULTS_DISABLED_' . $disabled, true);
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false);
        }
    }

    public static function handleReveal(): void
    {
        $rowId = self::postedInt('row_id');
        self::authorize('oddroom_orderops_reveal_' . $rowId);
        try {
            if (!OddRoom_Repository::testMode()) {
                throw new RuntimeException('SYNTHETIC_IDENTIFIER_REVEAL_DISABLED');
            }
            $row = OddRoom_Repository::find($rowId);
            if (!$row) {
                throw new RuntimeException('ROW_NOT_FOUND');
            }
            set_transient(self::revealKey($rowId), [
                'row_id' => $rowId,
                'remote_contact_id' => $row->remote_contact_id,
                'remote_deal_id' => $row->remote_deal_id,
                'slack_message_ts' => $row->slack_message_ts,
                'operator_evidence_ref' => $row->operator_evidence_ref,
            ], 120);
            wp_safe_redirect(add_query_arg(['page' => self::PAGE, 'reveal' => $rowId], admin_url('admin.php')));
            exit;
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false);
        }
    }

    private static function renderControls(): void
    {
        echo '<div class="oddroom-health"><section class="oddroom-card"><h2>Reconciliation</h2>';
        echo '<p>Seven-day fact window · deterministic 50-order pages · same hourly/manual code path.</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
        echo '<input type="hidden" name="action" value="oddroom_orderops_reconcile">';
        wp_nonce_field('oddroom_orderops_reconcile');
        submit_button('Run reconciliation', 'secondary', 'submit', false);
        echo '</form></section>';

        echo '<section class="oddroom-card"><h2>Staging-only fault control</h2>';
        if (!OddRoom_Repository::testMode()) {
            echo '<p>Disabled outside test mode.</p></section></div>';
            return;
        }
        echo '<p>Disabled by default, bound to the active run, and authorized by database UTC for at most 30 minutes.</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
        echo '<input type="hidden" name="action" value="oddroom_orderops_fault_enable">';
        wp_nonce_field('oddroom_orderops_fault_enable');
        echo '<p><label>Order ID <input required type="number" min="1" name="order_id"></label></p>';
        echo '<p><label>Event <select name="event_type">';
        foreach (['ORDER_CREATED', 'PAYMENT_CONFIRMED', 'ORDER_CANCELLED', 'ORDER_REFUNDED'] as $event) {
            echo '<option value="' . esc_attr($event) . '">' . esc_html($event) . '</option>';
        }
        echo '</select></label></p><p><label>Fault <select name="fault_type">';
        foreach ([OddRoom_Faults::BEFORE_SLACK_POST, OddRoom_Faults::SUPPRESS_OUTBOX_INSERT, OddRoom_Faults::SUPPRESS_SCHEDULE] as $fault) {
            echo '<option value="' . esc_attr($fault) . '">' . esc_html($fault) . '</option>';
        }
        echo '</select></label></p><p><label>Minutes <input required type="number" min="1" max="30" value="5" name="minutes"></label></p>';
        submit_button('Enable staging fault', 'secondary', 'submit', false);
        echo '</form><hr><h3>Active controls</h3>';
        $active = OddRoom_Faults::activeRows();
        if ($active === []) {
            echo '<p>None.</p>';
        } else {
            echo '<ul>';
            foreach ($active as $fault) {
                echo '<li>' . esc_html($fault->fault_type . ' · ' . self::maskIdentifier($fault->event_key_sha256) . ' · ' . $fault->expires_at) . '</li>';
            }
            echo '</ul>';
        }
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
        echo '<input type="hidden" name="action" value="oddroom_orderops_fault_end_run">';
        wp_nonce_field('oddroom_orderops_fault_end_run');
        submit_button('End run and disable all controls', 'delete', 'submit', false);
        echo '</form></section></div>';
    }

    private static function renderFilters(array $filters): void
    {
        echo '<form method="get"><input type="hidden" name="page" value="' . esc_attr(self::PAGE) . '">';
        echo '<label>Status <select name="status"><option value="">All</option>';
        foreach (['pending', 'processing', 'retry_wait', 'operator_wait', 'failed', 'completed'] as $status) {
            echo '<option value="' . esc_attr($status) . '"' . selected($filters['status'], $status, false) . '>' . esc_html($status) . '</option>';
        }
        echo '</select></label> <label>Event <select name="event_type"><option value="">All</option>';
        foreach (['ORDER_CREATED', 'PAYMENT_CONFIRMED', 'ORDER_CANCELLED', 'ORDER_REFUNDED'] as $event) {
            echo '<option value="' . esc_attr($event) . '"' . selected($filters['event_type'], $event, false) . '>' . esc_html($event) . '</option>';
        }
        echo '</select></label> <label>Order or event <input type="search" maxlength="191" name="search" value="' . esc_attr($filters['search']) . '"></label>';
        echo ' <label>Sort <select name="sort">';
        foreach (['id', 'order_id', 'event_type', 'status', 'occurred_at_utc', 'updated_at'] as $sort) {
            echo '<option value="' . esc_attr($sort) . '"' . selected($filters['sort'], $sort, false) . '>' . esc_html($sort) . '</option>';
        }
        echo '</select></label> <label>Direction <select name="direction">';
        foreach (['DESC', 'ASC'] as $direction) {
            echo '<option value="' . esc_attr($direction) . '"' . selected($filters['direction'], $direction, false) . '>' . esc_html($direction) . '</option>';
        }
        echo '</select></label> ';
        submit_button('Filter', 'secondary', 'submit', false);
        echo '</form>';
    }

    private static function renderRowActions(object $row): void
    {
        if ((string) $row->status === 'failed') {
            echo '<form class="oddroom-inline" method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
            echo '<input type="hidden" name="action" value="oddroom_orderops_retry"><input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '">';
            wp_nonce_field('oddroom_orderops_retry_' . (int) $row->id);
            submit_button('Manual Retry', 'secondary small', 'submit', false);
            echo '</form>';
        }
        if ((string) $row->status === 'operator_wait'
            && (int) $row->resolved_operator_wait_epoch < (int) $row->operator_wait_epoch) {
            echo '<details class="oddroom-resolve"><summary>Resolve Outcome</summary>';
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
            echo '<input type="hidden" name="action" value="oddroom_orderops_resolve">';
            echo '<input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '">';
            echo '<input type="hidden" name="epoch" value="' . esc_attr((string) $row->operator_wait_epoch) . '">';
            wp_nonce_field('oddroom_orderops_resolve_' . (int) $row->id . '_' . (int) $row->operator_wait_epoch);
            echo '<label>Decision <select name="decision">';
            foreach (['UNRESOLVED', 'CONFIRMED_POSTED', 'CONFIRMED_NOT_POSTED', 'RETRY_AFTER_DUE'] as $decision) {
                echo '<option value="' . esc_attr($decision) . '">' . esc_html($decision) . '</option>';
            }
            echo '</select></label>';
            echo '<label>Protected evidence reference <input required maxlength="255" name="evidence_ref"></label>';
            echo '<label>Verified resume phase <select name="verified_phase"><option value="">Not applicable</option>';
            foreach (['created', 'deal_resolved', 'contact_upserted', 'deal_upserted', 'associated', 'slack_pending'] as $phase) {
                echo '<option value="' . esc_attr($phase) . '">' . esc_html($phase) . '</option>';
            }
            echo '</select></label>';
            echo '<label>Verified Contact ID <input maxlength="128" name="remote_contact_id"></label>';
            echo '<label>Verified Deal ID <input maxlength="128" name="remote_deal_id"></label>';
            echo '<label>Verified Slack timestamp <input maxlength="64" name="slack_message_ts"></label>';
            echo '<label>Service due UTC <input maxlength="20" placeholder="YYYY-MM-DDTHH:MM:SSZ" name="due_at_utc"></label>';
            submit_button('Apply Resolve Outcome', 'primary', 'submit', false);
            echo '</form></details>';
        }
        echo '<form class="oddroom-inline" method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
        echo '<input type="hidden" name="action" value="oddroom_orderops_reveal"><input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '">';
        wp_nonce_field('oddroom_orderops_reveal_' . (int) $row->id);
        submit_button('Reveal synthetic IDs', 'secondary small', 'submit', false);
        echo '</form>';
    }

    private static function renderPagination(array $filters, int $pages): void
    {
        if ($pages <= 1) {
            return;
        }
        $base = add_query_arg([
            'page' => self::PAGE,
            'status' => $filters['status'],
            'event_type' => $filters['event_type'],
            'search' => $filters['search'],
            'sort' => $filters['sort'],
            'direction' => $filters['direction'],
            'paged' => '%#%',
        ], admin_url('admin.php'));
        echo '<div class="tablenav-pages">' . wp_kses_post(paginate_links([
            'base' => $base,
            'format' => '',
            'current' => $filters['page'],
            'total' => $pages,
            'type' => 'plain',
        ])) . '</div>';
    }

    private static function renderNotice(): void
    {
        $notice = get_transient(self::noticeKey());
        if (!is_array($notice)) {
            return;
        }
        delete_transient(self::noticeKey());
        $class = !empty($notice['success']) ? 'notice-success' : 'notice-error';
        echo '<div class="notice ' . esc_attr($class) . ' is-dismissible"><p>'
            . esc_html((string) ($notice['code'] ?? 'UNKNOWN')) . '</p></div>';
    }

    private static function renderReveal(): void
    {
        $rowId = isset($_GET['reveal']) ? absint(wp_unslash($_GET['reveal'])) : 0;
        if ($rowId < 1) {
            return;
        }
        $values = get_transient(self::revealKey($rowId));
        if (!is_array($values)) {
            return;
        }
        delete_transient(self::revealKey($rowId));
        echo '<div class="notice notice-info"><p><strong>Protected synthetic identifiers for row '
            . esc_html((string) $rowId) . '</strong></p><ul>';
        foreach (['remote_contact_id', 'remote_deal_id', 'slack_message_ts', 'operator_evidence_ref'] as $field) {
            echo '<li>' . esc_html($field) . ': <code>' . esc_html((string) ($values[$field] ?? '—')) . '</code></li>';
        }
        echo '</ul></div>';
    }

    private static function filters(): array
    {
        $status = isset($_GET['status']) ? sanitize_key(wp_unslash($_GET['status'])) : '';
        $event = isset($_GET['event_type']) ? strtoupper(sanitize_key(wp_unslash($_GET['event_type']))) : '';
        $search = isset($_GET['search']) ? sanitize_text_field(wp_unslash($_GET['search'])) : '';
        $sort = isset($_GET['sort']) ? sanitize_key(wp_unslash($_GET['sort'])) : 'id';
        $direction = isset($_GET['direction']) ? strtoupper(sanitize_key(wp_unslash($_GET['direction']))) : 'DESC';
        return [
            'status' => $status,
            'event_type' => $event,
            'search' => substr($search, 0, 191),
            'sort' => $sort,
            'direction' => $direction === 'ASC' ? 'ASC' : 'DESC',
            'page' => isset($_GET['paged']) ? max(1, absint(wp_unslash($_GET['paged']))) : 1,
            'per_page' => 50,
        ];
    }

    private static function card(string $label, string $value): void
    {
        echo '<section class="oddroom-card"><strong>' . esc_html($label) . '</strong><br>' . esc_html($value) . '</section>';
    }

    private static function maskIdentifier(mixed $value): string
    {
        if (!is_string($value) || $value === '') {
            return '—';
        }
        return '••••••' . substr($value, -6);
    }

    private static function authorize(string $nonceAction): void
    {
        self::requireCapability();
        check_admin_referer($nonceAction);
    }

    private static function requireCapability(): void
    {
        if (!current_user_can('manage_woocommerce')) {
            wp_die(esc_html__('You do not have permission to manage OrderOps.', 'oddroom-orderops'), '', ['response' => 403]);
        }
    }

    private static function postedInt(string $key): int
    {
        return isset($_POST[$key]) ? absint(wp_unslash($_POST[$key])) : 0;
    }

    private static function postedText(string $key): string
    {
        return isset($_POST[$key]) ? sanitize_text_field(wp_unslash($_POST[$key])) : '';
    }

    private static function redirectNotice(string $code, bool $success): never
    {
        set_transient(self::noticeKey(), [
            'code' => strtoupper(substr(sanitize_key($code), 0, 160)),
            'success' => $success,
        ], 120);
        wp_safe_redirect(add_query_arg('page', self::PAGE, admin_url('admin.php')));
        exit;
    }

    private static function errorCode(Throwable $error): string
    {
        $code = strtoupper(sanitize_key($error->getMessage()));
        return $code !== '' ? substr($code, 0, 96) : 'ORDEROPS_ACTION_FAILED';
    }

    private static function noticeKey(): string
    {
        return 'oddroom_orderops_notice_' . get_current_user_id();
    }

    private static function revealKey(int $rowId): string
    {
        return 'oddroom_orderops_reveal_' . get_current_user_id() . '_' . $rowId;
    }
}
