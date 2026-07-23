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

        $schedulerReady = (bool) ($identity['initialized'] ?? false);
        $automationReady = is_array($reachability) && ($reachability['status'] ?? null) === 'REACHED';
        $reconciliationPassed = is_array($lastReconciliation) && ($lastReconciliation['status'] ?? null) === 'PASS';
        echo '<section id="overview" class="oddroom-stat-grid" aria-label="' . esc_attr(self::text('운영 상태', 'Operations status')) . '">';
        self::card(self::text('현재 운영', 'Current operation'), self::modeLabel((string) $setup['mode']), 'mode');
        self::card(
            self::text('주문 전달 상태', 'Order delivery'),
            $health === '' ? self::text('정상', 'Healthy') : self::text('확인 필요', 'Needs attention'),
            $health === '' ? 'pass' : 'hold'
        );
        self::card(
            self::text('주문 기록 · 진행 중', 'Order records · in progress'),
            sprintf(self::text('%d건 · %d건', '%d · %d'), $counts['outbox'], $counts['leases']),
            'neutral'
        );
        self::card(
            self::text('백그라운드 작업', 'Background jobs'),
            $schedulerReady ? self::text('준비됨', 'Ready') : self::text('확인 필요', 'Needs attention'),
            $schedulerReady ? 'pass' : 'hold'
        );
        self::card(
            self::text('자동화 연결', 'Automation connection'),
            $automationReady ? self::text('연결됨', 'Connected') : self::text('첫 주문 대기', 'Awaiting first order'),
            $automationReady ? 'pass' : 'neutral'
        );
        self::card(
            self::text('최근 완료', 'Latest completion'),
            is_array($lastSuccess)
                ? self::eventTypeLabel((string) ($lastSuccess['event_type'] ?? ''))
                : self::text('아직 없음', 'None yet'),
            is_array($lastSuccess) ? 'pass' : 'neutral'
        );
        self::card(
            self::text('주문 기록 점검', 'Order record check'),
            is_array($lastReconciliation)
                ? ($reconciliationPassed ? self::text('정상', 'Healthy') : self::text('확인 필요', 'Needs attention'))
                : self::text('점검 전', 'Not checked'),
            $reconciliationPassed ? 'pass' : 'neutral'
        );
        self::card(
            self::text('외부 반영 · 연락처/거래/알림', 'External records · contacts/deals/alerts'),
            sprintf('%d · %d · %d', $setup['demo_contacts'], $setup['demo_deals'], $setup['demo_slack_messages']),
            'neutral'
        );
        echo '</section>';

        echo '<div class="oddroom-two-column">';
        self::renderSetup($setup);
        self::renderRecovery($lastReconciliation);
        echo '</div>';

        echo '<section id="events" class="oddroom-panel oddroom-events-panel">';
        echo '<div class="oddroom-section-heading"><div><p class="oddroom-eyebrow">ORDER ACTIVITY</p><h2>'
            . esc_html(self::text('주문 처리 내역', 'Order activity')) . '</h2><p>'
            . esc_html(self::text(
                '주문이 접수된 뒤 연락처와 거래, 알림이 어디까지 반영됐는지 한눈에 확인하세요.',
                'See how far contacts, deals, and notifications have been updated for each order.'
            )) . '</p></div><span class="oddroom-count">' . esc_html(sprintf(self::text('%d건', '%d matched'), $total)) . '</span></div>';
        self::renderFilters($filters);
        echo '<div class="oddroom-event-list">';
        if ($rows === []) {
            echo '<div class="oddroom-empty"><strong>' . esc_html(self::text('조건에 맞는 주문 처리 내역이 없습니다.', 'No order activity matches these filters.')) . '</strong><p>'
                . esc_html(self::text('새 데모 주문을 만들거나 조회 조건을 초기화해 보세요.', 'Create a new demo order or clear the search filters.')) . '</p></div>';
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
        echo '<div class="oddroom-hero"><div class="oddroom-brand"><span>OFFSET / ORDEROPS</span><small>OPERATOR CONSOLE</small></div>';
        echo '<div class="oddroom-hero-copy"><p class="oddroom-eyebrow">ORDER CONTROL / CURRENT STATUS</p><h1>'
            . esc_html(self::text('주문 운영 센터', 'Order operations center'))
            . '</h1><p>' . esc_html(self::text(
                '주문이 어디까지 처리됐는지 확인하고, 멈춘 작업을 다시 시작하거나 결과를 확정할 수 있습니다.',
                'See how far each order has progressed, restart interrupted work, and confirm outcomes from one place.'
            )) . '</p></div>';
        echo '<div class="oddroom-hero-meta"><span class="oddroom-mode-pill">' . esc_html(self::modeLabel((string) $setup['mode'])) . '</span><span>0 KRW</span><span>'
            . esc_html(self::text('데모 주문 전용', 'Demo orders only')) . '</span></div>';
        echo '<nav aria-label="' . esc_attr(self::text('운영 영역', 'Operator sections')) . '"><a href="#overview">'
            . esc_html(self::text('현황', 'Overview')) . '</a><a href="#setup">'
            . esc_html(self::text('연동', 'Connections')) . '</a><a href="#recovery">'
            . esc_html(self::text('처리 설정', 'Processing')) . '</a><a href="#events">'
            . esc_html(self::text('처리 내역', 'Activity')) . '</a></nav></div>';
    }

    private static function renderSetup(array $setup): void
    {
        echo '<section id="setup" class="oddroom-panel"><div class="oddroom-section-heading"><div><p class="oddroom-eyebrow">CONNECTIONS &amp; ACCESS</p><h2>'
            . esc_html(self::text('연동 상태와 표시 이름', 'Connections and display names')) . '</h2><p>'
            . esc_html(self::text(
                '현재 운영 방식과 외부 서비스의 연결 상태를 확인하고, 화면에 표시할 이름을 관리합니다.',
                'Review how orders are operating and whether external services are connected, then manage their display names.'
            )) . '</p></div></div>';
        echo '<ol class="oddroom-setup-steps"><li class="is-pass"><span>01</span><div><strong>'
            . esc_html(self::text('관리자 접근', 'Administrator access')) . '</strong><p>'
            . esc_html(self::text('이 화면은 로그인한 관리자만 열고 변경할 수 있습니다.', 'Only signed-in administrators can open this screen or make changes.')) . '</p></div></li>';
        echo '<li class="is-pass"><span>02</span><div><strong>' . esc_html(self::text('데모 운영', 'Demo operation')) . '</strong><p>'
            . esc_html(self::text('실제 고객 정보나 외부 메시지 없이 주문 처리 과정을 안전하게 확인할 수 있습니다.', 'Review the complete order process without using real customer information or sending external messages.')) . '</p></div></li>';
        echo '<li class="' . ($setup['hubspot_configured'] && $setup['slack_configured'] ? 'is-pass' : 'is-wait') . '"><span>03</span><div><strong>' . esc_html(self::text('외부 서비스 연결', 'External service connections')) . '</strong><p>'
            . esc_html($setup['hubspot_configured'] && $setup['slack_configured']
                ? self::text('HubSpot과 Slack 연결 정보가 준비되었습니다. 런처 허브에서 연결 상태를 확인할 수 있습니다.', 'HubSpot and Slack connection details are ready. Their status is available in the launch hub.')
                : self::text('HubSpot과 Slack을 사용하려면 런처 허브에서 연결 정보를 입력해 주세요.', 'To use HubSpot and Slack, enter their connection details in the launch hub.')) . '</p></div></li></ol>';

        echo '<form class="oddroom-form" method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_setup">';
        wp_nonce_field('oddroom_orderops_setup');
        echo '<div class="oddroom-fields"><div class="oddroom-readonly-field"><span>' . esc_html(self::text('현재 운영', 'Current operation')) . '</span><strong>' . esc_html(self::modeLabel((string) $setup['mode'])) . '</strong></div><label>' . esc_html(self::text('HubSpot 표시 이름', 'HubSpot display name')) . '<input required maxlength="64" name="hubspot_alias" value="' . esc_attr((string) $setup['hubspot_alias']) . '"></label><label>' . esc_html(self::text('Slack 표시 이름', 'Slack display name')) . '<input required maxlength="64" name="slack_alias" value="' . esc_attr((string) $setup['slack_alias']) . '"></label></div>';
        submit_button(self::text('표시 이름 저장', 'Save display names'), 'primary', 'submit', false);
        echo '<p class="oddroom-boundary">' . esc_html(self::text(
            '이 화면에는 표시 이름과 준비 상태만 나타납니다. 토큰과 비밀번호, 전체 연동 ID는 표시하지 않습니다.',
            'This screen shows display names and readiness only. Tokens, passwords, and full connection IDs remain hidden.'
        )) . '</p></form>';

        echo '<details class="oddroom-danger"><summary>' . esc_html(self::text('데모 주문 데이터 비우기', 'Clear demo order data')) . '</summary><p>'
            . esc_html(self::text('데모 주문과 처리 내역, 전송 결과만 삭제합니다. 관리자 계정과 상품, 시스템 설정은 그대로 유지됩니다.', 'Removes demo orders, processing history, and delivery results. The administrator account, products, and system settings remain.')) . '</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_reset">';
        wp_nonce_field('oddroom_orderops_reset');
        echo '<label>' . esc_html(self::text('확인 문구', 'Confirmation phrase')) . '<input required autocomplete="off" name="confirmation" placeholder="RESET PF07 DEMO"></label> ';
        if ($setup['mode'] === OddRoom_Package::DEMO_MODE) {
            submit_button(self::text('데모 데이터 초기화', 'Reset demo data'), 'delete', 'submit', false);
        } else {
            echo '<button class="button button-link-delete" type="button" disabled>' . esc_html(self::text('데모 운영에서 사용 가능', 'Available during demo operation')) . '</button>';
        }
        echo '</form></details></section>';
    }

    private static function renderRecovery(?array $lastReconciliation): void
    {
        $setup = OddRoom_Package::setupState();
        echo '<section id="recovery" class="oddroom-panel"><div class="oddroom-section-heading"><div><p class="oddroom-eyebrow">NEXT ORDER &amp; RECOVERY</p><h2>'
            . esc_html(self::text('다음 주문의 처리 방식', 'How the next order will run')) . '</h2><p>'
            . esc_html(self::text('다음 데모 주문이 바로 완료될지, 재시도나 관리자 확인을 거칠지 선택할 수 있습니다.', 'Choose whether the next demo order completes immediately, retries, or waits for administrator review.')) . '</p></div></div>';
        echo '<form class="oddroom-form" method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_scenario">';
        wp_nonce_field('oddroom_orderops_scenario');
        $demoMode = $setup['mode'] === OddRoom_Package::DEMO_MODE;
        echo '<label>' . esc_html(self::text('다음 주문에 적용할 방식', 'Behavior for the next order')) . '<select name="scenario"' . ($demoMode ? '' : ' disabled') . '>';
        $scenarios = [
            'normal' => self::text('문제 없이 완료', 'Complete normally'),
            'fail_once' => self::text('한 번 실패한 뒤 자동으로 다시 처리', 'Fail once, then retry automatically'),
            'terminal' => self::text('관리자가 직접 다시 시작', 'Wait for an administrator to retry'),
            'operator_review' => self::text('관리자 확인 후 결과 확정', 'Wait for administrator confirmation'),
        ];
        foreach ($scenarios as $value => $label) {
            echo '<option value="' . esc_attr($value) . '"' . selected($setup['scenario'], $value, false) . '>' . esc_html($label) . '</option>';
        }
        echo '</select></label> ';
        if ($demoMode) {
            submit_button(self::text('다음 주문에 적용', 'Apply to next order'), 'secondary', 'submit', false);
        } else {
            echo '<button class="button button-secondary" type="button" disabled>' . esc_html(self::text('데모 운영에서 사용 가능', 'Available during demo operation')) . '</button>';
        }
        echo '</form><div class="oddroom-scenario-key"><span><i class="is-normal"></i>' . esc_html(self::text('정상', 'Normal')) . '</span><span><i class="is-retrying"></i>' . esc_html(self::text('재시도', 'Retrying')) . '</span><span><i class="is-failed"></i>' . esc_html(self::text('실패', 'Failed')) . '</span><span><i class="is-recovered"></i>' . esc_html(self::text('복구', 'Recovered')) . '</span></div>';
        echo '<hr><h3>' . esc_html(self::text('누락 주문 기록 점검', 'Check for missing order records')) . '</h3><p>'
            . esc_html(self::text('최근 7일 주문을 확인해 빠진 처리 기록만 다시 만듭니다.', 'Checks orders from the last seven days and recreates only missing processing records.')) . '</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_reconcile">';
        wp_nonce_field('oddroom_orderops_reconcile');
        submit_button(self::text('주문 기록 점검', 'Check order records'), 'secondary', 'submit', false);
        echo '</form><p class="oddroom-boundary">' . esc_html(is_array($lastReconciliation)
            ? sprintf(self::text('최근 점검: %s · %s', 'Latest check: %s · %s'), self::reconciliationLabel((string) ($lastReconciliation['status'] ?? '')), (string) ($lastReconciliation['observed_at_utc'] ?? 'unknown'))
            : self::text('아직 주문 기록을 점검하지 않았습니다.', 'Order records have not been checked yet.')) . '</p></section>';
    }

    private static function renderEvent(object $row): void
    {
        $status = self::displayStatus($row);
        echo '<article class="oddroom-event-card status-' . esc_attr($status['class']) . '"><header><div><span class="oddroom-event-type">'
            . esc_html(self::eventTypeLabel((string) $row->event_type)) . '</span><h3>'
            . esc_html(sprintf(self::text('주문 #%d · 처리 기록 #%d', 'Order #%d · Record #%d'), (int) $row->order_id, (int) $row->id))
            . '</h3><p><code>' . esc_html(self::maskIdentifier($row->event_key)) . '</code> · '
            . esc_html((string) $row->occurred_at_utc) . '</p></div><span class="oddroom-status">' . esc_html($status['label']) . '</span></header>';
        echo '<div class="oddroom-event-metrics">';
        self::metric(self::text('처리 단계', 'Processing stage'), self::phaseLabel((string) $row->processing_phase));
        self::metric(self::text('처리 횟수', 'Attempts'), $row->attempt_count . ' / ' . $row->max_attempts);
        self::metric(self::text('다음 자동 재시도', 'Next automatic retry'), $row->next_attempt_at ?? '—');
        self::metric(self::text('응답 코드', 'Response code'), $row->last_http_status ?? '—');
        echo '</div><details class="oddroom-event-details"><summary>' . esc_html(self::text('처리 과정과 관리자 작업', 'Processing details and actions')) . '</summary>';
        echo '<div class="oddroom-correlation"><span>Woo <b>#' . esc_html((string) $row->order_id) . '</b></span><i>→</i><span>PF07 <b>#' . esc_html((string) $row->id) . '</b></span><i>→</i><span>n8n <b>'
            . esc_html($row->adapter_dispatch_state . '/' . ($row->adapter_dispatch_attempt ?? '—')) . '</b></span><i>→</i><span>CRM <b>'
            . esc_html(self::maskIdentifier($row->remote_deal_id)) . '</b></span><i>→</i><span>Slack <b>'
            . esc_html($row->slack_status) . '</b></span></div>';
        $facts = [
            self::text('시스템 상태 / 단계', 'System status / phase') => $row->status . ' / ' . $row->processing_phase,
            self::text('처리 횟수 (전체 / 자동 / 수동)', 'Attempts (total / automatic / manual)') => $row->attempt_count . ' / ' . $row->automatic_attempt_count . ' / ' . $row->manual_retry_count,
            self::text('작업 번호', 'Action number') => $row->action_id ?? '—',
            self::text('실행 잠금 경과', 'Lock elapsed') => $row->lock_age_seconds === null ? self::text('잠금 없음', 'No lock') : ((int) $row->lock_age_seconds . 's'),
            self::text('오류 코드', 'Error code') => $row->error_code ?? '—',
            self::text('정제된 오류', 'Sanitized error') => $row->last_error ?? '—',
            'Contact' => self::maskIdentifier($row->remote_contact_id),
            'Deal' => self::maskIdentifier($row->remote_deal_id),
            'Slack' => $row->slack_status . ' / ' . self::maskIdentifier($row->slack_message_ts),
            self::text('최근 변경 (UTC)', 'Last updated (UTC)') => $row->updated_at,
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
        $statuses = [
            'pending' => self::text('대기', 'Queued'),
            'processing' => self::text('처리 중', 'Processing'),
            'retry_wait' => self::text('자동 재시도 대기', 'Waiting to retry'),
            'operator_wait' => self::text('관리자 확인 대기', 'Waiting for review'),
            'failed' => self::text('실패', 'Failed'),
            'completed' => self::text('완료', 'Completed'),
        ];
        foreach ($statuses as $status => $label) {
            echo '<option value="' . esc_attr($status) . '"' . selected($filters['status'], $status, false) . '>' . esc_html($label) . '</option>';
        }
        echo '</select></label><label>' . esc_html(self::text('주문 단계', 'Order stage')) . '<select name="event_type"><option value="">' . esc_html(self::text('전체', 'All')) . '</option>';
        foreach (['ORDER_CREATED', 'PAYMENT_CONFIRMED', 'ORDER_CANCELLED', 'ORDER_REFUNDED'] as $event) {
            echo '<option value="' . esc_attr($event) . '"' . selected($filters['event_type'], $event, false) . '>' . esc_html(self::eventTypeLabel($event)) . '</option>';
        }
        echo '</select></label><label>' . esc_html(self::text('주문 번호 또는 처리 기록', 'Order number or record')) . '<input type="search" maxlength="191" name="search" value="' . esc_attr($filters['search']) . '"></label>';
        echo '<label>' . esc_html(self::text('정렬 기준', 'Sort by')) . '<select name="sort">';
        $sorts = [
            'id' => self::text('처리 기록', 'Activity record'),
            'order_id' => self::text('주문 번호', 'Order number'),
            'event_type' => self::text('주문 단계', 'Order stage'),
            'status' => self::text('상태', 'Status'),
            'occurred_at_utc' => self::text('발생 시각', 'Occurred at'),
            'updated_at' => self::text('최근 변경', 'Last updated'),
        ];
        foreach ($sorts as $sort => $label) {
            echo '<option value="' . esc_attr($sort) . '"' . selected($filters['sort'], $sort, false) . '>' . esc_html($label) . '</option>';
        }
        echo '</select></label><label>' . esc_html(self::text('정렬 방향', 'Order')) . '<select name="direction">';
        foreach (['DESC' => self::text('최신순', 'Newest first'), 'ASC' => self::text('오래된 순', 'Oldest first')] as $direction => $label) {
            echo '<option value="' . esc_attr($direction) . '"' . selected($filters['direction'], $direction, false) . '>' . esc_html($label) . '</option>';
        }
        echo '</select></label>';
        submit_button(self::text('조회', 'Search'), 'secondary', 'submit', false);
        echo '</form>';
    }

    private static function renderRowActions(object $row): void
    {
        if ((string) $row->status === 'failed') {
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_retry"><input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '">';
            wp_nonce_field('oddroom_orderops_retry_' . (int) $row->id);
            submit_button(self::text('다시 처리', 'Retry processing'), 'primary small', 'submit', false);
            echo '</form>';
        }
        if ((string) $row->status === 'operator_wait'
            && (int) $row->resolved_operator_wait_epoch < (int) $row->operator_wait_epoch) {
            echo '<details class="oddroom-resolve"><summary>' . esc_html(self::text('처리 결과 확정', 'Confirm processing outcome')) . '</summary><form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
            echo '<input type="hidden" name="action" value="oddroom_orderops_resolve"><input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '"><input type="hidden" name="epoch" value="' . esc_attr((string) $row->operator_wait_epoch) . '">';
            wp_nonce_field('oddroom_orderops_resolve_' . (int) $row->id . '_' . (int) $row->operator_wait_epoch);
            echo '<label>' . esc_html(self::text('처리 결과', 'Outcome')) . '<select name="decision">';
            $decisions = [
                'UNRESOLVED' => self::text('아직 확인되지 않음', 'Not confirmed yet'),
                'CONFIRMED_POSTED' => self::text('외부 반영 확인', 'Confirmed as delivered'),
                'CONFIRMED_NOT_POSTED' => self::text('외부 미반영 확인', 'Confirmed as not delivered'),
                'RETRY_AFTER_DUE' => self::text('예정 시각 이후 다시 처리', 'Retry after the due time'),
            ];
            foreach ($decisions as $decision => $label) {
                echo '<option value="' . esc_attr($decision) . '">' . esc_html($label) . '</option>';
            }
            echo '</select></label><label>' . esc_html(self::text('확인 근거 참조', 'Evidence reference')) . '<input required maxlength="255" name="evidence_ref"></label><label>' . esc_html(self::text('확인한 재개 지점', 'Verified resume point')) . '<select name="verified_phase"><option value="">' . esc_html(self::text('해당 없음', 'Not applicable')) . '</option>';
            foreach (['created', 'deal_resolved', 'contact_upserted', 'deal_upserted', 'associated', 'slack_pending'] as $phase) {
                echo '<option value="' . esc_attr($phase) . '">' . esc_html(self::phaseLabel($phase)) . '</option>';
            }
            echo '</select></label><label>' . esc_html(self::text('HubSpot 연락처 ID', 'HubSpot contact ID')) . '<input maxlength="128" name="remote_contact_id"></label><label>' . esc_html(self::text('HubSpot 거래 ID', 'HubSpot deal ID')) . '<input maxlength="128" name="remote_deal_id"></label><label>' . esc_html(self::text('Slack 메시지 ID', 'Slack message ID')) . '<input maxlength="64" name="slack_message_ts"></label><label>' . esc_html(self::text('다시 처리할 시각 (UTC)', 'Retry due time (UTC)')) . '<input maxlength="20" placeholder="YYYY-MM-DDTHH:MM:SSZ" name="due_at_utc"></label>';
            submit_button(self::text('결과 확정', 'Confirm outcome'), 'primary', 'submit', false);
            echo '</form></details>';
        }
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="oddroom_orderops_reveal"><input type="hidden" name="row_id" value="' . esc_attr((string) $row->id) . '">';
        wp_nonce_field('oddroom_orderops_reveal_' . (int) $row->id);
        submit_button(self::text('연동 ID 2분간 보기', 'Show connection IDs for 2 minutes'), 'secondary small', 'submit', false);
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
        $success = !empty($notice['success']);
        $code = (string) ($notice['code'] ?? 'UNKNOWN');
        $class = $success ? 'is-success' : 'is-error';
        echo '<div class="oddroom-notice ' . esc_attr($class) . '" role="status"><strong>'
            . esc_html(self::noticeMessage($code, $success))
            . '</strong><code>' . esc_html($code) . '</code></div>';
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
        echo '<div class="oddroom-notice is-info"><strong>' . esc_html(sprintf(self::text('처리 기록 #%d 연동 ID', 'Connection IDs for record #%d'), $rowId)) . '</strong><ul>';
        $labels = [
            'remote_contact_id' => self::text('HubSpot 연락처 ID', 'HubSpot contact ID'),
            'remote_deal_id' => self::text('HubSpot 거래 ID', 'HubSpot deal ID'),
            'slack_message_ts' => self::text('Slack 메시지 ID', 'Slack message ID'),
            'operator_evidence_ref' => self::text('확인 근거 참조', 'Evidence reference'),
        ];
        foreach ($labels as $field => $label) {
            echo '<li>' . esc_html($label) . ': <code>' . esc_html((string) ($values[$field] ?? '—')) . '</code></li>';
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
            'operator_wait' => ['class' => 'operator', 'label' => self::text('관리자 확인 대기', 'Waiting for review')],
            default => ['class' => 'queued', 'label' => self::text('대기', 'Queued')],
        };
    }

    private static function eventTypeLabel(string $eventType): string
    {
        return match ($eventType) {
            'ORDER_CREATED' => self::text('주문 접수', 'Order received'),
            'PAYMENT_CONFIRMED' => self::text('주문 승인', 'Order approved'),
            'ORDER_CANCELLED' => self::text('주문 취소', 'Order cancelled'),
            'ORDER_REFUNDED' => self::text('환불 완료', 'Refund completed'),
            default => $eventType === '' ? self::text('확인 전', 'Not available') : $eventType,
        };
    }

    private static function phaseLabel(string $phase): string
    {
        return match ($phase) {
            'created' => self::text('주문 접수', 'Order received'),
            'deal_resolved' => self::text('거래 확인', 'Deal checked'),
            'contact_upserted' => self::text('연락처 반영', 'Contact updated'),
            'deal_upserted' => self::text('거래 반영', 'Deal updated'),
            'associated' => self::text('연동 완료', 'Connection completed'),
            'slack_pending' => self::text('알림 대기', 'Notification pending'),
            'completed' => self::text('처리 완료', 'Processing completed'),
            default => $phase === '' ? '—' : str_replace('_', ' ', $phase),
        };
    }

    private static function modeLabel(string $mode): string
    {
        return match ($mode) {
            OddRoom_Package::DEMO_MODE => self::text('데모 운영', 'Demo operation'),
            OddRoom_Package::CONNECTED_MODE => self::text('외부 서비스 연결', 'Connected operation'),
            default => $mode === '' ? self::text('확인 필요', 'Needs attention') : $mode,
        };
    }

    private static function reconciliationLabel(string $status): string
    {
        return match ($status) {
            'PASS' => self::text('이상 없음', 'No issues found'),
            'HOLD' => self::text('확인 필요', 'Needs attention'),
            default => $status === '' ? self::text('결과 없음', 'No result') : $status,
        };
    }

    private static function noticeMessage(string $code, bool $success): string
    {
        if (!$success) {
            return self::text('작업을 완료하지 못했습니다. 아래 코드를 확인해 주세요.', 'The action could not be completed. Review the code below.');
        }
        return match (true) {
            str_starts_with($code, 'MANUAL_RETRY_SCHEDULED_') => self::text('다시 처리를 예약했습니다.', 'Processing has been scheduled again.'),
            str_starts_with($code, 'OUTCOME_') => self::text('처리 결과를 반영했습니다.', 'The processing outcome has been saved.'),
            str_starts_with($code, 'RECONCILIATION_') => self::text('주문 기록 점검을 마쳤습니다.', 'The order record check is complete.'),
            $code === 'PACKAGE_SETUP_SAVED' => self::text('연동 표시 이름을 저장했습니다.', 'Connection display names have been saved.'),
            str_starts_with($code, 'DEMO_SCENARIO_') => self::text('다음 주문의 처리 결과를 설정했습니다.', 'The result for the next order has been set.'),
            str_starts_with($code, 'DEMO_RESET_') => self::text('데모 주문 데이터를 비웠습니다.', 'Demo order data has been cleared.'),
            str_starts_with($code, 'STAGING_FAULT_ENABLED') => self::text('테스트 오류를 설정했습니다.', 'The test fault has been enabled.'),
            str_starts_with($code, 'RUN_FAULTS_DISABLED_') => self::text('테스트 오류 설정을 종료했습니다.', 'The test fault has been disabled.'),
            default => self::text('변경 내용을 적용했습니다.', 'The change has been applied.'),
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
