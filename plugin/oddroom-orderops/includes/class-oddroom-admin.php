<?php

defined('ABSPATH') || exit;

final class OddRoom_Admin
{
    private const PAGE = 'oddroom-orderops';

    public static function boot(): void
    {
        add_action('admin_menu', [self::class, 'menu']);
        add_action('admin_enqueue_scripts', [self::class, 'enqueue']);
        add_action('admin_post_oddroom_orderops_retry', [self::class, 'handleRetry']);
        add_action('admin_post_oddroom_orderops_resolve', [self::class, 'handleResolve']);
        add_action('admin_post_oddroom_orderops_reconcile', [self::class, 'handleReconcile']);
        add_action('admin_post_oddroom_orderops_setup', [self::class, 'handleSetup']);
        add_action('admin_post_oddroom_orderops_scenario', [self::class, 'handleScenario']);
        add_action('admin_post_oddroom_orderops_reset', [self::class, 'handleReset']);
        add_action('admin_post_oddroom_orderops_fault_enable', [self::class, 'handleFaultEnable']);
        add_action('admin_post_oddroom_orderops_fault_end_run', [self::class, 'handleFaultEndRun']);
        add_action('admin_post_oddroom_orderops_reveal', [self::class, 'handleReveal']);
    }

    public static function menu(): void
    {
        add_submenu_page(
            'woocommerce',
            'OFFSET OrderOps',
            'OFFSET OrderOps',
            'manage_woocommerce',
            self::PAGE,
            [self::class, 'render']
        );
    }

    public static function enqueue(string $hook): void
    {
        if ($hook !== 'woocommerce_page_' . self::PAGE) {
            return;
        }
        wp_enqueue_style(
            'oddroom-orderops-admin',
            plugins_url('../assets/css/admin.css', __FILE__),
            [],
            '0.4.0'
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
        $setup = OddRoom_Package::setupState();

        echo '<div class="wrap oddroom-orderops">';
        self::renderHero($setup);
        self::renderNotice();
        self::renderReveal();

        echo '<section id="overview" class="oddroom-stat-grid" aria-label="' . esc_attr(self::text('운영 상태', 'Operations status')) . '">';
        self::card(self::text('패키지 모드', 'Package mode'), (string) $setup['mode'], 'mode');
        self::card(self::text('전달 건강', 'Delivery health'), $health === '' ? 'PASS' : $health, $health === '' ? 'pass' : 'hold');
        self::card(self::text('이벤트 / 임대', 'Events / leases'), $counts['outbox'] . ' / ' . $counts['leases'], 'neutral');
        self::card('Action Scheduler', ($identity['version'] ?? 'unavailable') . ' · ' . ($identity['source'] ?? 'unavailable'), ($identity['initialized'] ?? false) ? 'pass' : 'hold');
        self::card('n8n', is_array($reachability) ? (string) ($reachability['status'] ?? 'unknown') : self::text('첫 전달 대기', 'Awaiting first delivery'), is_array($reachability) && ($reachability['status'] ?? null) === 'REACHED' ? 'pass' : 'neutral');
        self::card(self::text('최근 성공', 'Latest success'), is_array($lastSuccess) ? (string) ($lastSuccess['event_type'] ?? 'unknown') : self::text('아직 없음', 'Not yet observed'), is_array($lastSuccess) ? 'pass' : 'neutral');
        self::card(self::text('재조정', 'Reconciliation'), is_array($lastReconciliation) ? (string) ($lastReconciliation['status'] ?? 'unknown') : self::text('실행 전', 'Not yet run'), is_array($lastReconciliation) && ($lastReconciliation['status'] ?? null) === 'PASS' ? 'pass' : 'neutral');
        self::card(self::text('데모 외부 효과', 'Demo service edges'), sprintf('%d / %d / %d', $setup['demo_contacts'], $setup['demo_deals'], $setup['demo_slack_messages']), 'neutral');
        echo '</section>';

        echo '<div class="oddroom-two-column">';
        self::renderSetup($setup);
        self::renderRecovery($lastReconciliation);
        echo '</div>';

        echo '<section id="events" class="oddroom-panel oddroom-events-panel">';
        echo '<div class="oddroom-section-heading"><div><p class="oddroom-eyebrow">EVENT LEDGER</p><h2>'
            . esc_html(self::text('전달 이벤트', 'Delivery events')) . '</h2><p>'
            . esc_html(self::text(
                'WooCommerce 주문에서 n8n·CRM·Slack 효과까지 같은 마스킹 식별자로 추적합니다.',
                'Trace one masked identity from the WooCommerce order through n8n, CRM, and Slack effects.'
            )) . '</p></div><span class="oddroom-count">' . esc_html(sprintf(self::text('%d건', '%d matched'), $total)) . '</span></div>';
        self::renderFilters($filters);
        echo '<div class="oddroom-event-list">';
        if ($rows === []) {
            echo '<div class="oddroom-empty"><strong>' . esc_html(self::text('표시할 이벤트가 없습니다.', 'No events match these filters.')) . '</strong><p>'
                . esc_html(self::text('합성 주문을 만들거나 필터를 초기화하세요.', 'Create a synthetic order or clear the filters.')) . '</p></div>';
        }
        foreach ($rows as $row) {
            self::renderEvent($row);
        }
        echo '</div>';
        self::renderPagination($filters, $pages);
        echo '</section></div>';
    }

    public static function handleRetry(): void
    {
        $rowId = self::postedInt('row_id');
        self::authorize('oddroom_orderops_retry_' . $rowId);
        try {
            $result = OddRoom_Repository::manualRetry($rowId, get_current_user_id());
            self::redirectNotice('MANUAL_RETRY_SCHEDULED_' . (int) $result['action_id'], true, 'events');
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'events');
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
            self::redirectNotice('OUTCOME_' . strtoupper((string) $result['status']) . $suffix, true, 'events');
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'events');
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
                $result['status'] === 'PASS',
                'recovery'
            );
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'recovery');
        }
    }

    public static function handleSetup(): void
    {
        self::authorize('oddroom_orderops_setup');
        try {
            OddRoom_Package::updateSetup(
                OddRoom_Package::mode(),
                self::postedText('hubspot_alias'),
                self::postedText('slack_alias')
            );
            self::redirectNotice('PACKAGE_SETUP_SAVED', true, 'setup');
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'setup');
        }
    }

    public static function handleScenario(): void
    {
        self::authorize('oddroom_orderops_scenario');
        try {
            $scenario = OddRoom_Package::setScenario(self::postedText('scenario'));
            self::redirectNotice('DEMO_SCENARIO_' . strtoupper($scenario), true, 'recovery');
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'recovery');
        }
    }

    public static function handleReset(): void
    {
        self::authorize('oddroom_orderops_reset');
        try {
            $result = OddRoom_Package::resetDemo(self::postedText('confirmation'), get_current_user_id());
            self::redirectNotice('DEMO_RESET_' . (string) $result['status'], true, 'setup');
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'setup');
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
            self::redirectNotice('STAGING_FAULT_ENABLED', true, 'recovery');
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'recovery');
        }
    }

    public static function handleFaultEndRun(): void
    {
        self::authorize('oddroom_orderops_fault_end_run');
        try {
            $disabled = OddRoom_Faults::endRun(OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_RUN_ID'));
            self::redirectNotice('RUN_FAULTS_DISABLED_' . $disabled, true, 'recovery');
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'recovery');
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
            wp_safe_redirect(add_query_arg(['page' => self::PAGE, 'reveal' => $rowId], admin_url('admin.php')) . '#events');
            exit;
        } catch (Throwable $error) {
            self::redirectNotice(self::errorCode($error), false, 'events');
        }
    }

    private static function renderHero(array $setup): void
    {
        echo '<header class="oddroom-hero"><div class="oddroom-brand"><span>OFFSET / ORDEROPS</span><small>OPERATOR CONSOLE</small></div>';
        echo '<div class="oddroom-hero-copy"><p class="oddroom-eyebrow">ORDER OPERATIONS / LIVE STATE</p><h1>'
            . esc_html(self::text('주문 운영', 'Order operations'))
            . '</h1><p>' . esc_html(self::text(
                '주문 사실부터 n8n 실행, CRM·Slack 전달, 실패 복구까지 한 화면에서 추적하고 조치합니다.',
                'Trace and act on order facts, n8n execution, CRM and Slack delivery, and failure recovery from one surface.'
            )) . '</p></div>';
        echo '<div class="oddroom-hero-meta"><span class="oddroom-mode-pill">' . esc_html((string) $setup['mode']) . '</span><span>0 KRW</span><span>'
            . esc_html(self::text('합성 데이터 전용', 'Synthetic data only')) . '</span></div>';
        echo '<nav aria-label="' . esc_attr(self::text('운영 영역', 'Operator sections')) . '"><a href="#overview">'
            . esc_html(self::text('현황', 'Overview')) . '</a><a href="#setup">'
            . esc_html(self::text('설정', 'Setup')) . '</a><a href="#recovery">'
            . esc_html(self::text('복구', 'Recovery')) . '</a><a href="#events">'
            . esc_html(self::text('이벤트', 'Events')) . '</a></nav></header>';
    }

    private static function renderSetup(array $setup): void
    {
        echo '<section id="setup" class="oddroom-panel"><div class="oddroom-section-heading"><div><p class="oddroom-eyebrow">SETUP &amp; HEALTH</p><h2>'
            . esc_html(self::text('연결은 보이고, 비밀은 보이지 않게.', 'Visible connections, hidden secrets.')) . '</h2></div></div>';
        echo '<ol class="oddroom-setup-steps"><li class="is-pass"><span>01</span><div><strong>'
            . esc_html(self::text('패키지 관리자', 'Package administrator')) . '</strong><p>'
            . esc_html(self::text('패키지에서 생성되었고 WordPress 로그인이 필요합니다.', 'Generated inside the package; WordPress authentication remains required.')) . '</p></div></li>';
        echo '<li class="is-pass"><span>02</span><div><strong>DEMO_MODE</strong><p>'
            . esc_html(self::text('실제 WooCommerce·PF07 outbox·n8n을 사용하고 HubSpot·Slack 가장자리만 결정적 데모 어댑터로 처리합니다.', 'Uses real WooCommerce, PF07 outbox, and n8n; only HubSpot and Slack edges use deterministic demo adapters.')) . '</p></div></li>';
        echo '<li class="' . ($setup['hubspot_configured'] && $setup['slack_configured'] ? 'is-pass' : 'is-wait') . '"><span>03</span><div><strong>CONNECTED_MODE</strong><p>'
            . esc_html($setup['hubspot_configured'] && $setup['slack_configured']
                ? self::text('보호된 자격 증명이 설정되었습니다. 비파괴 연결 테스트 결과를 확인하세요.', 'Protected credentials are configured. Review the non-destructive connection-test results.')
                : self::text('런처 허브에서 수신자 자격 증명을 입력하고 비파괴 연결 테스트를 통과해야 합니다.', 'Enter recipient credentials in the launch hub and pass non-destructive connection tests.')) . '</p></div></li></ol>';

        echo '<form class="oddroom-form" method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_setup">';
        wp_nonce_field('oddroom_orderops_setup');
        echo '<div class="oddroom-fields"><div class="oddroom-readonly-field"><span>' . esc_html(self::text('운영 모드', 'Operating mode')) . '</span><strong>' . esc_html((string) $setup['mode']) . '</strong></div><label>HubSpot alias<input required maxlength="64" name="hubspot_alias" value="' . esc_attr((string) $setup['hubspot_alias']) . '"></label><label>Slack alias<input required maxlength="64" name="slack_alias" value="' . esc_attr((string) $setup['slack_alias']) . '"></label></div>';
        submit_button(self::text('설정 저장', 'Save setup'), 'primary', 'submit', false);
        echo '<p class="oddroom-boundary">' . esc_html(self::text(
            '이 화면은 alias와 준비 상태만 보여줍니다. 토큰·비밀·원격 ID 전체값은 표시하지 않습니다.',
            'This surface shows aliases and readiness only. Tokens, secrets, and full remote identifiers are never displayed.'
        )) . '</p></form>';

        echo '<details class="oddroom-danger"><summary>' . esc_html(self::text('확인 후 데모 초기화', 'Confirmed Reset Demo')) . '</summary><p>'
            . esc_html(self::text('주문·outbox·데모 어댑터 효과만 삭제합니다. 관리자·상품·런타임 식별자·볼륨은 보존합니다.', 'Deletes orders, outbox rows, and demo-adapter effects only. Administrator, catalog, runtime identity, and volumes remain.')) . '</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_reset">';
        wp_nonce_field('oddroom_orderops_reset');
        echo '<label>' . esc_html(self::text('확인 문구', 'Confirmation phrase')) . '<input required autocomplete="off" name="confirmation" placeholder="RESET PF07 DEMO"></label> ';
        if ($setup['mode'] === OddRoom_Package::DEMO_MODE) {
            submit_button(self::text('데모 데이터 초기화', 'Reset demo data'), 'delete', 'submit', false);
        } else {
            echo '<button class="button button-link-delete" type="button" disabled>' . esc_html(self::text('DEMO_MODE에서 사용', 'Available in DEMO_MODE')) . '</button>';
        }
        echo '</form></details></section>';
    }

    private static function renderRecovery(?array $lastReconciliation): void
    {
        $setup = OddRoom_Package::setupState();
        echo '<section id="recovery" class="oddroom-panel"><div class="oddroom-section-heading"><div><p class="oddroom-eyebrow">FAILURE → RETRY → RECOVERY</p><h2>'
            . esc_html(self::text('실제 상태를 만들고 복구하세요.', 'Create and recover real states.')) . '</h2><p>'
            . esc_html(self::text('다음 전달에 적용할 결정적 데모 시나리오입니다. 결과는 outbox에 실제로 기록됩니다.', 'Choose a deterministic scenario for the next delivery. Its result is written to the real outbox.')) . '</p></div></div>';
        echo '<form class="oddroom-form" method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_scenario">';
        wp_nonce_field('oddroom_orderops_scenario');
        $demoMode = $setup['mode'] === OddRoom_Package::DEMO_MODE;
        echo '<label>' . esc_html(self::text('다음 전달 시나리오', 'Next-delivery scenario')) . '<select name="scenario"' . ($demoMode ? '' : ' disabled') . '>';
        $scenarios = [
            'normal' => self::text('정상 완료', 'Normal completion'),
            'fail_once' => self::text('1회 실패 후 자동 복구', 'Fail once, then auto-recover'),
            'terminal' => self::text('수동 재시도가 필요한 실패', 'Terminal failure requiring manual retry'),
            'operator_review' => self::text('운영자 결과 확정 대기', 'Operator outcome resolution'),
        ];
        foreach ($scenarios as $value => $label) {
            echo '<option value="' . esc_attr($value) . '"' . selected($setup['scenario'], $value, false) . '>' . esc_html($label) . '</option>';
        }
        echo '</select></label> ';
        if ($demoMode) {
            submit_button(self::text('시나리오 적용', 'Apply scenario'), 'secondary', 'submit', false);
        } else {
            echo '<button class="button button-secondary" type="button" disabled>' . esc_html(self::text('DEMO_MODE에서 사용', 'Available in DEMO_MODE')) . '</button>';
        }
        echo '</form><div class="oddroom-scenario-key"><span><i class="is-normal"></i>' . esc_html(self::text('정상', 'Normal')) . '</span><span><i class="is-retrying"></i>' . esc_html(self::text('재시도', 'Retrying')) . '</span><span><i class="is-failed"></i>' . esc_html(self::text('실패', 'Failed')) . '</span><span><i class="is-recovered"></i>' . esc_html(self::text('복구', 'Recovered')) . '</span></div>';
        echo '<hr><h3>' . esc_html(self::text('사실 재조정', 'Fact reconciliation')) . '</h3><p>'
            . esc_html(self::text('7일 주문 사실을 50개 단위로 검사하고 누락 이벤트만 복구합니다.', 'Scans seven days of order facts in deterministic 50-order pages and repairs only missing events.')) . '</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_reconcile">';
        wp_nonce_field('oddroom_orderops_reconcile');
        submit_button(self::text('재조정 실행', 'Run reconciliation'), 'secondary', 'submit', false);
        echo '</form><p class="oddroom-boundary">' . esc_html(is_array($lastReconciliation)
            ? sprintf(self::text('최근 결과: %s · %s', 'Latest result: %s · %s'), (string) ($lastReconciliation['status'] ?? 'unknown'), (string) ($lastReconciliation['observed_at_utc'] ?? 'unknown'))
            : self::text('아직 재조정을 실행하지 않았습니다.', 'Reconciliation has not run yet.')) . '</p></section>';
    }

    private static function renderEvent(object $row): void
    {
        $status = self::displayStatus($row);
        echo '<article class="oddroom-event-card status-' . esc_attr($status['class']) . '"><header><div><span class="oddroom-event-type">'
            . esc_html((string) $row->event_type) . '</span><h3>'
            . esc_html(sprintf(self::text('주문 #%d · 이벤트 #%d', 'Order #%d · Event #%d'), (int) $row->order_id, (int) $row->id))
            . '</h3><p><code>' . esc_html(self::maskIdentifier($row->event_key)) . '</code> · '
            . esc_html((string) $row->occurred_at_utc) . '</p></div><span class="oddroom-status">' . esc_html($status['label']) . '</span></header>';
        echo '<div class="oddroom-event-metrics">';
        self::metric(self::text('단계', 'Phase'), (string) $row->processing_phase);
        self::metric(self::text('시도', 'Attempts'), $row->attempt_count . ' / ' . $row->max_attempts);
        self::metric(self::text('다음 재시도', 'Next retry'), $row->next_attempt_at ?? '—');
        self::metric('HTTP', $row->last_http_status ?? '—');
        echo '</div><details class="oddroom-event-details"><summary>' . esc_html(self::text('상세 흐름과 조치', 'Flow details and actions')) . '</summary>';
        echo '<div class="oddroom-correlation"><span>Woo <b>#' . esc_html((string) $row->order_id) . '</b></span><i>→</i><span>PF07 <b>#' . esc_html((string) $row->id) . '</b></span><i>→</i><span>n8n <b>'
            . esc_html($row->adapter_dispatch_state . '/' . ($row->adapter_dispatch_attempt ?? '—')) . '</b></span><i>→</i><span>CRM <b>'
            . esc_html(self::maskIdentifier($row->remote_deal_id)) . '</b></span><i>→</i><span>Slack <b>'
            . esc_html($row->slack_status) . '</b></span></div>';
        $facts = [
            self::text('상태 / 단계', 'Status / phase') => $row->status . ' / ' . $row->processing_phase,
            self::text('전체 / 자동 / 수동', 'Total / automatic / manual') => $row->attempt_count . ' / ' . $row->automatic_attempt_count . ' / ' . $row->manual_retry_count,
            self::text('액션 ID', 'Action ID') => $row->action_id ?? '—',
            self::text('잠금 나이', 'Lock age') => $row->lock_age_seconds === null ? self::text('없음', 'free') : ((int) $row->lock_age_seconds . 's'),
            self::text('오류 코드', 'Error code') => $row->error_code ?? '—',
            self::text('정제된 오류', 'Sanitized error') => $row->last_error ?? '—',
            'Contact' => self::maskIdentifier($row->remote_contact_id),
            'Deal' => self::maskIdentifier($row->remote_deal_id),
            'Slack' => $row->slack_status . ' / ' . self::maskIdentifier($row->slack_message_ts),
            self::text('업데이트 UTC', 'Updated UTC') => $row->updated_at,
        ];
        echo '<dl class="oddroom-fact-grid">';
        foreach ($facts as $label => $value) {
            echo '<div><dt>' . esc_html((string) $label) . '</dt><dd>' . esc_html((string) $value) . '</dd></div>';
        }
        echo '</dl><div class="oddroom-row-actions">';
        self::renderRowActions($row);
        echo '</div></details></article>';
    }

    private static function renderFilters(array $filters): void
    {
        echo '<form class="oddroom-filter" method="get"><input type="hidden" name="page" value="' . esc_attr(self::PAGE) . '">';
        echo '<label>' . esc_html(self::text('상태', 'Status')) . '<select name="status"><option value="">' . esc_html(self::text('전체', 'All')) . '</option>';
        foreach (['pending', 'processing', 'retry_wait', 'operator_wait', 'failed', 'completed'] as $status) {
            echo '<option value="' . esc_attr($status) . '"' . selected($filters['status'], $status, false) . '>' . esc_html($status) . '</option>';
        }
        echo '</select></label><label>' . esc_html(self::text('이벤트', 'Event')) . '<select name="event_type"><option value="">' . esc_html(self::text('전체', 'All')) . '</option>';
        foreach (['ORDER_CREATED', 'PAYMENT_CONFIRMED', 'ORDER_CANCELLED', 'ORDER_REFUNDED'] as $event) {
            echo '<option value="' . esc_attr($event) . '"' . selected($filters['event_type'], $event, false) . '>' . esc_html($event) . '</option>';
        }
        echo '</select></label><label>' . esc_html(self::text('주문 또는 이벤트', 'Order or event')) . '<input type="search" maxlength="191" name="search" value="' . esc_attr($filters['search']) . '"></label>';
        echo '<label>' . esc_html(self::text('정렬', 'Sort')) . '<select name="sort">';
        foreach (['id', 'order_id', 'event_type', 'status', 'occurred_at_utc', 'updated_at'] as $sort) {
            echo '<option value="' . esc_attr($sort) . '"' . selected($filters['sort'], $sort, false) . '>' . esc_html($sort) . '</option>';
        }
        echo '</select></label><label>' . esc_html(self::text('방향', 'Direction')) . '<select name="direction">';
        foreach (['DESC', 'ASC'] as $direction) {
            echo '<option value="' . esc_attr($direction) . '"' . selected($filters['direction'], $direction, false) . '>' . esc_html($direction) . '</option>';
        }
        echo '</select></label>';
        submit_button(self::text('필터 적용', 'Apply filters'), 'secondary', 'submit', false);
        echo '</form>';
    }

    private static function renderRowActions(object $row): void
    {
        if ((string) $row->status === 'failed') {
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_retry"><input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '">';
            wp_nonce_field('oddroom_orderops_retry_' . (int) $row->id);
            submit_button(self::text('수동 재시도', 'Manual retry'), 'primary small', 'submit', false);
            echo '</form>';
        }
        if ((string) $row->status === 'operator_wait'
            && (int) $row->resolved_operator_wait_epoch < (int) $row->operator_wait_epoch) {
            echo '<details class="oddroom-resolve"><summary>' . esc_html(self::text('결과 확정', 'Resolve outcome')) . '</summary><form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
            echo '<input type="hidden" name="action" value="oddroom_orderops_resolve"><input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '"><input type="hidden" name="epoch" value="' . esc_attr((string) $row->operator_wait_epoch) . '">';
            wp_nonce_field('oddroom_orderops_resolve_' . (int) $row->id . '_' . (int) $row->operator_wait_epoch);
            echo '<label>Decision<select name="decision">';
            foreach (['UNRESOLVED', 'CONFIRMED_POSTED', 'CONFIRMED_NOT_POSTED', 'RETRY_AFTER_DUE'] as $decision) {
                echo '<option value="' . esc_attr($decision) . '">' . esc_html($decision) . '</option>';
            }
            echo '</select></label><label>' . esc_html(self::text('보호된 증거 참조', 'Protected evidence reference')) . '<input required maxlength="255" name="evidence_ref"></label><label>' . esc_html(self::text('확인한 재개 단계', 'Verified resume phase')) . '<select name="verified_phase"><option value="">' . esc_html(self::text('해당 없음', 'Not applicable')) . '</option>';
            foreach (['created', 'deal_resolved', 'contact_upserted', 'deal_upserted', 'associated', 'slack_pending'] as $phase) {
                echo '<option value="' . esc_attr($phase) . '">' . esc_html($phase) . '</option>';
            }
            echo '</select></label><label>Contact ID<input maxlength="128" name="remote_contact_id"></label><label>Deal ID<input maxlength="128" name="remote_deal_id"></label><label>Slack timestamp<input maxlength="64" name="slack_message_ts"></label><label>Service due UTC<input maxlength="20" placeholder="YYYY-MM-DDTHH:MM:SSZ" name="due_at_utc"></label>';
            submit_button(self::text('확정 적용', 'Apply resolution'), 'primary', 'submit', false);
            echo '</form></details>';
        }
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_reveal"><input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '">';
        wp_nonce_field('oddroom_orderops_reveal_' . (int) $row->id);
        submit_button(self::text('합성 ID 2분간 표시', 'Reveal synthetic IDs for 2 minutes'), 'secondary small', 'submit', false);
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
        echo '<nav class="oddroom-pagination">' . wp_kses_post(paginate_links([
            'base' => $base,
            'format' => '',
            'current' => $filters['page'],
            'total' => $pages,
            'type' => 'plain',
        ])) . '</nav>';
    }

    private static function renderNotice(): void
    {
        $notice = get_transient(self::noticeKey());
        if (!is_array($notice)) {
            return;
        }
        delete_transient(self::noticeKey());
        $class = !empty($notice['success']) ? 'is-success' : 'is-error';
        echo '<div class="oddroom-notice ' . esc_attr($class) . '" role="status"><strong>'
            . esc_html(!empty($notice['success']) ? self::text('작업 완료', 'Action completed') : self::text('조치 필요', 'Action required'))
            . '</strong><code>' . esc_html((string) ($notice['code'] ?? 'UNKNOWN')) . '</code></div>';
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
        echo '<div class="oddroom-notice is-info"><strong>' . esc_html(sprintf(self::text('이벤트 #%d 합성 식별자', 'Synthetic identifiers for event #%d'), $rowId)) . '</strong><ul>';
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

    private static function card(string $label, string $value, string $tone): void
    {
        echo '<article class="oddroom-stat tone-' . esc_attr($tone) . '"><span>' . esc_html($label) . '</span><strong>' . esc_html($value) . '</strong></article>';
    }

    private static function metric(string $label, mixed $value): void
    {
        echo '<div><span>' . esc_html($label) . '</span><strong>' . esc_html((string) $value) . '</strong></div>';
    }

    private static function displayStatus(object $row): array
    {
        if ((string) $row->status === 'completed' && (int) $row->attempt_count > 1) {
            return ['class' => 'recovered', 'label' => self::text('복구됨', 'Recovered')];
        }
        return match ((string) $row->status) {
            'completed' => ['class' => 'normal', 'label' => self::text('완료', 'Completed')],
            'retry_wait', 'processing' => ['class' => 'retrying', 'label' => self::text('재시도 중', 'Retrying')],
            'failed' => ['class' => 'failed', 'label' => self::text('실패', 'Failed')],
            'operator_wait' => ['class' => 'operator', 'label' => self::text('결과 확정 대기', 'Operator review')],
            default => ['class' => 'queued', 'label' => self::text('대기', 'Queued')],
        };
    }

    private static function maskIdentifier(mixed $value): string
    {
        if (!is_string($value) || $value === '') {
            return '—';
        }
        return '••••••' . substr($value, -6);
    }

    private static function text(string $korean, string $english): string
    {
        return str_starts_with(determine_locale(), 'en_') ? $english : $korean;
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

    private static function redirectNotice(string $code, bool $success, string $anchor = ''): never
    {
        set_transient(self::noticeKey(), [
            'code' => strtoupper(substr(sanitize_key($code), 0, 160)),
            'success' => $success,
        ], 120);
        $url = add_query_arg('page', self::PAGE, admin_url('admin.php'));
        wp_safe_redirect($anchor === '' ? $url : $url . '#' . $anchor);
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
