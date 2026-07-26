const token = document.querySelector('meta[name="pf07-session-token"]').content;
const locale = document.querySelector('meta[name="pf07-locale"]').content;
const languageSelect = document.querySelector('#language-select');
const startButton = document.querySelector('#start-button');
const storeButton = document.querySelector('#store-button');
const adminButton = document.querySelector('#admin-button');
const stopButton = document.querySelector('#stop-button');
const credentialButton = document.querySelector('#credential-button');
const credentialPanel = document.querySelector('#credential-panel');
const copyButton = document.querySelector('#copy-button');
const setupButton = document.querySelector('#setup-button');
const connectionPanel = document.querySelector('#connection-panel');
const connectedForm = document.querySelector('#connected-form');
const connectedButton = document.querySelector('#connected-button');
const demoModeButton = document.querySelector('#demo-mode-button');
const connectionResult = document.querySelector('#connection-result');
const recoveryButton = document.querySelector('#recovery-button');
const recoveryPanel = document.querySelector('#recovery-panel');
const recoveryResult = document.querySelector('#recovery-result');
const scenarioForm = document.querySelector('#scenario-form');
const scenarioSelect = document.querySelector('#scenario-select');
const scenarioButton = document.querySelector('#scenario-button');
const resetForm = document.querySelector('#reset-form');
const resetConfirmation = document.querySelector('#reset-confirmation');
const resetButton = document.querySelector('#reset-button');
const statusBadge = document.querySelector('#status-badge');
const operationMessage = document.querySelector('#operation-message');
const signalFill = document.querySelector('#signal-fill');
const operationStep = document.querySelector('#operation-step');
const operationPercent = document.querySelector('#operation-percent');
const operationsPanel = document.querySelector('#operations-panel');
const operationsResult = document.querySelector('#operations-result');
const preflightButton = document.querySelector('#preflight-button');
const restartButton = document.querySelector('#restart-button');
const recoverButton = document.querySelector('#recover-button');
const diagnosticsButton = document.querySelector('#diagnostics-button');
const evidenceButton = document.querySelector('#evidence-button');
const backupForm = document.querySelector('#backup-form');
const restoreForm = document.querySelector('#restore-form');
const updateForm = document.querySelector('#update-form');
const tunnelForm = document.querySelector('#tunnel-form');
const tunnelProvider = document.querySelector('#tunnel-provider');
const tunnelExecutable = document.querySelector('#tunnel-executable');
const tunnelConfig = document.querySelector('#tunnel-config');
const tunnelConfirmation = document.querySelector('#tunnel-confirmation');
const tunnelDisableConfirmation = document.querySelector('#tunnel-disable-confirmation');
const tunnelOnButton = document.querySelector('#tunnel-on-button');
const tunnelOffButton = document.querySelector('#tunnel-off-button');
const tunnelStoreButton = document.querySelector('#tunnel-store-button');
const tunnelAdminButton = document.querySelector('#tunnel-admin-button');
const uninstallForm = document.querySelector('#uninstall-form');

let currentStatus = null;
let busy = false;
let currentPassword = '';
let refreshInFlight = false;

const copy = locale === 'en_US' ? {
  busy: 'Working', ready: 'Ready', waiting: 'Waiting', connected: 'Connected', checkFailed: 'Check failed',
  attention: 'Needs attention', operationNeedsAttention: 'Review the last action',
  startingService: 'Starting service', operationInProgress: 'Selected action in progress',
  demoMode: 'Demo operation', connectedMode: 'Connected operation',
  startFailed: 'Start failed', stopFailed: 'Stop failed', copied: 'Copied', copyPassword: 'Copy password',
  checking: 'Checking package state.',
  readyMessage: 'The service is ready. The store and order management can be opened.',
  waitingMessage: 'Select Start service to prepare the store and order management.',
  portOccupiedMessage: 'Another program is using the saved local address. Select Recover service to move this same store to a free local address.',
  demoDescription: 'Demo operation processes synthetic orders without account connections. It does not contact real payments, HubSpot, or Slack.',
  connectedDescription: 'Connected operation sends synthetic orders through protected HubSpot and Slack connections. Real payments and customer data remain disabled.',
  startMessage: 'Checking required images and pinned dependencies, then starting services. The first run can take several minutes.',
  stopMessage: 'Stopping containers and preserving package data.',
  languageMessage: 'Applying the selected language to the current service.',
  scenarioMessage: 'Applying the selected result to the next synthetic order.',
  scenarioApplied: 'The selected result will apply to the next synthetic order.',
  resetMessage: 'Resetting package-owned demo data.',
  resetComplete: 'Demo data was reset. The administrator, catalog, store identity, and saved service data were preserved.',
  actionFailed: 'The operation could not be completed.',
  connectedMessage: 'Checking HubSpot and sending the agreed synthetic setup message to the selected Slack channel.',
  connectedComplete: 'The selected pipeline and channel are ready. Connected operation is active.',
  demoModeMessage: 'Switching to demo operation.',
  demoModeComplete: 'Demo operation is active. Saved connections remain protected and unused.',
  operationMessage: 'Running the selected package operation.',
  backupComplete: 'Encrypted backup created beside the extracted package folder. Keep its passphrase separately.',
  uninstallComplete: 'The selected PF07 runtime resources were handled. The extracted package and this hub remain; a later start can reconnect preserved state or create new local state.',
  phase: {
    preflight: 'Checking the Docker start environment.',
    downloads: 'Downloading and verifying pinned dependencies.',
    containers: 'Starting the isolated database and WordPress containers.',
    wordpress: 'Preparing WordPress and language support.',
    dependencies: 'Preparing pinned WooCommerce and Action Scheduler versions.',
    storefront: 'Preparing the OFFSET store and administrator.',
    automation: 'Preparing order delivery and background processing.',
    'task-runner-image': 'Preparing the versioned task runner.',
    verify: 'Checking the store and order-management access.',
    language: 'Applying the presentation language to the same store and order data.',
    mode: 'Applying the selected operation mode to the same service.',
    stop: 'Stopping package containers.',
    stopped: 'The demo is stopped. Package-local data is preserved.',
    restart: 'Restarting the same package runtime.',
    'port-recovery': 'Moving the same store to an available local address.',
    'backup-quiesce': 'Pausing package writers while the encrypted backup is created.',
    'backup-complete': 'The encrypted package-local backup is ready.',
    'restore-quiesce': 'Stopping current package writers before restore.',
    'restore-materialized': 'The authenticated backup was restored to this package.',
    uninstall: 'Removing only the confirmed package-owned runtime resources.',
    uninstalled: 'The confirmed package-owned runtime resources were removed.',
    ready: 'The store and order management are ready to open.',
    error: 'The last operation needs attention. Review the reported action and retry.',
  },
} : {
  busy: '작업 중', ready: '준비 완료', waiting: '대기', connected: '연결됨', checkFailed: '확인 실패',
  attention: '확인 필요', operationNeedsAttention: '최근 작업 확인',
  startingService: '서비스 시작', operationInProgress: '선택한 작업 진행 중',
  demoMode: '데모 운영', connectedMode: '외부 서비스 연결 운영',
  startFailed: '시작 실패', stopFailed: '중지 실패', copied: '복사했습니다', copyPassword: '비밀번호 복사',
  checking: '패키지 상태를 확인하고 있습니다.',
  readyMessage: '서비스 준비가 끝났습니다. 상점과 주문 관리를 열 수 있습니다.',
  waitingMessage: '서비스 시작을 눌러 상점과 주문 관리를 준비하세요.',
  portOccupiedMessage: '저장된 로컬 주소를 다른 프로그램이 사용 중입니다. 문제 복구를 누르면 같은 상점을 사용 가능한 주소로 옮깁니다.',
  demoDescription: '데모 운영은 별도 계정 연결 없이 합성 주문만 처리합니다. 실제 결제, HubSpot, Slack에는 연결하지 않습니다.',
  connectedDescription: '외부 서비스 연결 운영은 보호된 HubSpot·Slack 연결로 합성 주문만 처리합니다. 실제 결제와 고객 데이터는 사용하지 않습니다.',
  startMessage: '필수 이미지와 고정 버전 의존성을 확인한 뒤 서비스를 시작합니다. 첫 실행에는 수 분이 걸릴 수 있습니다.',
  stopMessage: '컨테이너를 중지하고 패키지 데이터를 보존하는 중입니다.',
  languageMessage: '선택한 언어를 현재 서비스에 적용하는 중입니다.',
  scenarioMessage: '선택한 결과를 다음 합성 주문에 적용하는 중입니다.',
  scenarioApplied: '선택한 결과가 다음 합성 주문에 적용됩니다.',
  resetMessage: '패키지 소유 데모 데이터를 초기화하는 중입니다.',
  resetComplete: '데모 데이터를 초기화했습니다. 관리자·카탈로그·상점 식별자·저장된 서비스 데이터는 보존했습니다.',
  actionFailed: '작업을 완료하지 못했습니다.',
  connectedMessage: 'HubSpot을 확인하고, 동의한 합성 설정 메시지를 선택한 Slack 채널로 보내고 있습니다.',
  connectedComplete: '선택한 파이프라인과 채널 확인이 끝났습니다. 외부 서비스 연결 운영이 적용되었습니다.',
  demoModeMessage: '데모 운영으로 전환하고 있습니다.',
  demoModeComplete: '데모 운영이 적용되었습니다. 저장된 연결 정보는 보호된 채 사용하지 않습니다.',
  operationMessage: '선택한 패키지 작업을 실행하는 중입니다.',
  backupComplete: '추출 폴더 옆에 암호화 백업을 만들었습니다. passphrase는 별도로 보관하세요.',
  uninstallComplete: '선택한 범위의 PF07 런타임 자원을 정리했습니다. 추출한 패키지와 허브는 남으며, 이후 시작하면 보존한 상태를 다시 연결하거나 새 로컬 상태를 만들 수 있습니다.',
  phase: {
    preflight: 'Docker 실행 환경을 확인하고 있습니다.',
    downloads: '고정 버전 필수 파일을 준비하고 있습니다.',
    containers: '격리된 데이터베이스와 상점을 시작하고 있습니다.',
    wordpress: '상점 기반과 언어 설정을 준비하고 있습니다.',
    dependencies: 'WooCommerce와 주문 처리 구성요소를 준비하고 있습니다.',
    storefront: 'OFFSET 상점과 관리자 환경을 구성하고 있습니다.',
    automation: '주문 전달과 백그라운드 처리를 시작하고 있습니다.',
    'task-runner-image': '주문 처리에 필요한 코드 실행기를 준비하고 있습니다.',
    verify: '상점과 주문 관리 연결 상태를 마지막으로 확인하고 있습니다.',
    language: '같은 상점에 선택한 표시 언어를 적용하고 있습니다.',
    mode: '같은 서비스에 선택한 운영 방식을 적용하고 있습니다.',
    stop: '서비스를 중지하고 있습니다.',
    stopped: '데모가 중지됐습니다. 패키지 데이터는 보존됩니다.',
    restart: '같은 패키지 런타임을 다시 시작하고 있습니다.',
    'port-recovery': '같은 상점을 사용 가능한 로컬 주소로 옮기고 있습니다.',
    'backup-quiesce': '암호화 백업을 만드는 동안 패키지 쓰기를 잠시 멈추고 있습니다.',
    'backup-complete': '암호화된 패키지 로컬 백업을 만들었습니다.',
    'restore-quiesce': '복원 전에 현재 패키지 쓰기를 중지하고 있습니다.',
    'restore-materialized': '인증된 백업을 이 패키지에 복원했습니다.',
    uninstall: '확인된 패키지 소유 런타임 자원만 정리하고 있습니다.',
    uninstalled: '확인된 패키지 소유 런타임 자원을 정리했습니다.',
    ready: '상점과 주문 관리를 열 수 있습니다.',
    error: '마지막 작업을 완료하지 못했습니다. 안내된 조치 후 다시 시도하세요.',
  },
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'X-PF07-Hub-Token': token, ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function setBusy(value, message = '', progress = {}) {
  busy = value;
  startButton.disabled = value;
  stopButton.disabled = value;
  credentialButton.disabled = value;
  scenarioSelect.disabled = value;
  scenarioButton.disabled = value;
  resetConfirmation.disabled = value;
  resetButton.disabled = value || resetConfirmation.value !== 'RESET PF07 DEMO';
  connectedForm.querySelectorAll('input, button').forEach((control) => { control.disabled = value; });
  operationsPanel.querySelectorAll('input, select, button').forEach((control) => { control.disabled = value; });
  if (value) {
    const hasPercent = Number.isFinite(Number(progress.percent));
    const percent = hasPercent ? Math.max(0, Math.min(100, Number(progress.percent))) : 0;
    statusBadge.className = 'badge badge-busy';
    statusBadge.textContent = copy.busy;
    signalFill.style.width = `${percent}%`;
    operationStep.textContent = progress.label || copy.operationInProgress;
    operationPercent.textContent = hasPercent ? `${Math.round(percent)}%` : '—';
    operationMessage.textContent = message;
  }
}

function render(status) {
  currentStatus = status;
  const ready = Boolean(status.ready);
  const hasRuntimeState = Boolean(status.compose_project);
  storeButton.disabled = busy || !ready;
  adminButton.disabled = busy || !ready;
  credentialButton.disabled = busy || !status.admin_reachable;
  startButton.disabled = busy;
  stopButton.disabled = busy || status.services.length === 0;
  const demoReady = ready && status.mode === 'DEMO_MODE';
  scenarioSelect.disabled = busy || !demoReady;
  scenarioButton.disabled = busy || !demoReady;
  resetConfirmation.disabled = busy || !demoReady;
  resetButton.disabled = busy || !demoReady || resetConfirmation.value !== 'RESET PF07 DEMO';
  setupButton.disabled = busy || !ready;
  connectedForm.querySelectorAll('input, button').forEach((control) => { control.disabled = busy || !ready; });
  operationsPanel.querySelectorAll('input, select, button').forEach((control) => { control.disabled = busy; });
  restartButton.disabled = busy || !hasRuntimeState;
  backupForm.querySelectorAll('input, select, button').forEach((control) => { control.disabled = busy || !hasRuntimeState; });
  uninstallForm.querySelectorAll('input, select, button').forEach((control) => { control.disabled = busy || !hasRuntimeState; });
  const tunnelReady = status.tunnel?.state === 'ON';
  const tunnelPresent = status.tunnel?.state !== 'OFF';
  [tunnelProvider, tunnelExecutable, tunnelConfig, tunnelConfirmation, tunnelOnButton]
    .forEach((control) => { control.disabled = busy || !ready || tunnelReady; });
  tunnelDisableConfirmation.disabled = busy || !tunnelPresent;
  tunnelOffButton.disabled = busy || !tunnelPresent;
  tunnelStoreButton.disabled = busy || !tunnelReady;
  tunnelAdminButton.disabled = busy || !tunnelReady;
  const modeName = status.mode === 'CONNECTED_MODE' ? copy.connectedMode : copy.demoMode;
  document.querySelector('#mode-fact').textContent = modeName;
  document.querySelector('#mode-pill').textContent = `${modeName} · ${locale === 'en_US' ? '0 KRW' : '0원'}`;
  document.querySelector('#mode-description').textContent = status.mode === 'CONNECTED_MODE' ? copy.connectedDescription : copy.demoDescription;
  document.querySelector('#store-fact').textContent = status.store_reachable ? copy.connected : copy.waiting;
  document.querySelector('#admin-fact').textContent = status.admin_reachable ? copy.connected : copy.waiting;
  document.querySelector('#n8n-fact').textContent = status.n8n_reachable ? copy.connected : copy.waiting;
  document.querySelector('#runner-fact').textContent = status.task_runner_running ? copy.connected : copy.waiting;
  document.querySelector('#worker-fact').textContent = status.worker_running ? copy.connected : copy.waiting;
  document.querySelector('#service-fact').textContent = `${status.services.length} / 5`;
  const operation = status.operation;
  const operationRunning = operation?.result === 'IN_PROGRESS';
  const operationFailed = operation?.result === 'FAIL';
  const portOccupied = status.runtime_state === 'PORT_OCCUPIED';
  const progress = Number.isFinite(Number(operation?.progress_percent))
    ? Math.max(0, Math.min(100, Number(operation.progress_percent)))
    : ready ? 100 : status.services.length ? 52 : 0;
  const stepIndex = Number(operation?.step_index || 0);
  const stepTotal = Number(operation?.step_total || 0);
  statusBadge.className = `badge ${operationFailed ? 'badge-error' : operationRunning || busy ? 'badge-busy' : ready ? 'badge-ready' : 'badge-idle'}`;
  statusBadge.textContent = operationFailed ? copy.attention : operationRunning || busy ? copy.busy : ready ? copy.ready : copy.waiting;
  signalFill.style.width = `${progress}%`;
  operationStep.textContent = operationFailed
    ? copy.operationNeedsAttention
    : stepIndex && stepTotal
    ? (locale === 'en_US' ? `Preparation step ${stepIndex} of ${stepTotal}` : `준비 ${stepIndex} / ${stepTotal}단계`)
    : operationRunning
      ? copy.operationInProgress
    : portOccupied
      ? (locale === 'en_US' ? 'Local address recovery' : '로컬 주소 복구 필요')
    : ready
      ? (locale === 'en_US' ? 'Service ready' : '서비스 준비 완료')
      : (locale === 'en_US' ? 'Ready to start' : '시작 준비');
  operationPercent.textContent = `${Math.round(progress)}%`;
  const operationCopy = operation?.result === 'FAIL'
    ? [copy.phase.error, operation.message].filter(Boolean).join(' ')
    : operationRunning || ready || operation?.phase === 'stopped'
      ? copy.phase[operation?.phase] || operation?.message
      : null;
  operationMessage.textContent = operationCopy || (
    portOccupied ? copy.portOccupiedMessage : ready ? copy.readyMessage : copy.waitingMessage
  );
}

async function refresh(force = false) {
  if ((busy && !force) || refreshInFlight) return;
  refreshInFlight = true;
  try {
    render(await api('/api/status'));
  } catch (error) {
    statusBadge.className = 'badge badge-error';
    statusBadge.textContent = copy.checkFailed;
    operationMessage.textContent = error.message;
  } finally {
    refreshInFlight = false;
  }
}

startButton.addEventListener('click', async () => {
  setBusy(true, copy.startMessage, { label: copy.startingService, percent: 4 });
  const startPoll = window.setInterval(() => { refresh(true); }, 750);
  try {
    render(await api('/api/start', { method: 'POST' }));
  } catch (error) {
    statusBadge.className = 'badge badge-error';
    statusBadge.textContent = copy.startFailed;
    operationMessage.textContent = error.message;
  } finally {
    window.clearInterval(startPoll);
    busy = false;
    await refresh();
  }
});

stopButton.addEventListener('click', async () => {
  setBusy(true, copy.stopMessage);
  try {
    render(await api('/api/stop', { method: 'POST' }));
  } catch (error) {
    statusBadge.className = 'badge badge-error';
    statusBadge.textContent = copy.stopFailed;
    operationMessage.textContent = error.message;
  } finally {
    busy = false;
    await refresh();
  }
});

storeButton.addEventListener('click', () => {
  if (currentStatus?.ready) window.open(currentStatus.urls.store, '_blank', 'noopener');
});

adminButton.addEventListener('click', () => {
  if (currentStatus?.ready) window.open(currentStatus.urls.admin, '_blank', 'noopener');
});

credentialButton.addEventListener('click', async () => {
  try {
    const value = await api('/api/credentials');
    document.querySelector('#admin-user').textContent = value.admin_user;
    document.querySelector('#admin-password').textContent = value.admin_password;
    currentPassword = value.admin_password;
    credentialPanel.hidden = false;
    credentialPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (error) {
    operationMessage.textContent = error.message;
  }
});

copyButton.addEventListener('click', async () => {
  if (!currentPassword) return;
  await navigator.clipboard.writeText(currentPassword);
  copyButton.textContent = copy.copied;
  window.setTimeout(() => { copyButton.textContent = copy.copyPassword; }, 1600);
});

recoveryButton.addEventListener('click', () => {
  recoveryPanel.hidden = false;
  recoveryPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
});

setupButton.addEventListener('click', () => {
  connectionPanel.hidden = false;
  connectionPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
});

connectedForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setBusy(true, copy.connectedMessage);
  connectionResult.textContent = copy.connectedMessage;
  try {
    await api('/api/connected-setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hubspot_token: document.querySelector('#hubspot-token').value,
        hubspot_pipeline_id: document.querySelector('#hubspot-pipeline').value,
        hubspot_initial_stage_id: document.querySelector('#hubspot-stage').value,
        hubspot_alias: document.querySelector('#hubspot-alias').value,
        slack_token: document.querySelector('#slack-token').value,
        slack_channel_id: document.querySelector('#slack-channel').value,
        slack_alias: document.querySelector('#slack-alias').value,
        slack_test_confirmation: document.querySelector('#slack-test-confirmation').checked
          ? 'SEND PF07 SLACK TEST'
          : '',
      }),
    });
    connectionResult.textContent = copy.connectedComplete;
  } catch (error) {
    connectionResult.textContent = `${copy.actionFailed} ${error.message}`;
  } finally {
    document.querySelector('#hubspot-token').value = '';
    document.querySelector('#hubspot-pipeline').value = '';
    document.querySelector('#hubspot-stage').value = '';
    document.querySelector('#slack-token').value = '';
    document.querySelector('#slack-channel').value = '';
    document.querySelector('#slack-test-confirmation').checked = false;
    busy = false;
    await refresh();
  }
});

demoModeButton.addEventListener('click', async () => {
  setBusy(true, copy.demoModeMessage);
  connectionResult.textContent = copy.demoModeMessage;
  try {
    await api('/api/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'DEMO_MODE' }),
    });
    connectionResult.textContent = copy.demoModeComplete;
  } catch (error) {
    connectionResult.textContent = `${copy.actionFailed} ${error.message}`;
  } finally {
    busy = false;
    await refresh();
  }
});

scenarioForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setBusy(true, copy.scenarioMessage);
  recoveryResult.textContent = copy.scenarioMessage;
  try {
    await api('/api/scenario', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario: scenarioSelect.value }),
    });
    recoveryResult.textContent = copy.scenarioApplied;
  } catch (error) {
    recoveryResult.textContent = `${copy.actionFailed} ${error.message}`;
  } finally {
    busy = false;
    await refresh();
  }
});

resetConfirmation.addEventListener('input', () => {
  resetButton.disabled = busy || !currentStatus?.ready || currentStatus?.mode !== 'DEMO_MODE' || resetConfirmation.value !== 'RESET PF07 DEMO';
});

resetForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (resetConfirmation.value !== 'RESET PF07 DEMO') return;
  setBusy(true, copy.resetMessage);
  recoveryResult.textContent = copy.resetMessage;
  try {
    await api('/api/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation: resetConfirmation.value }),
    });
    resetConfirmation.value = '';
    recoveryResult.textContent = copy.resetComplete;
  } catch (error) {
    recoveryResult.textContent = `${copy.actionFailed} ${error.message}`;
  } finally {
    busy = false;
    await refresh();
  }
});

async function runOperation(path, options = {}, { refreshAfter = false } = {}) {
  setBusy(true, copy.operationMessage);
  operationsResult.textContent = copy.operationMessage;
  try {
    const result = await api(path, options);
    operationsResult.textContent = JSON.stringify(result, null, 2);
    return result;
  } catch (error) {
    operationsResult.textContent = `${copy.actionFailed} ${error.message}`;
    return null;
  } finally {
    busy = false;
    if (refreshAfter) await refresh();
    else if (currentStatus) render(currentStatus);
  }
}

preflightButton.addEventListener('click', () => runOperation('/api/open-prerequisite', { method: 'POST' }));
restartButton.addEventListener('click', () => runOperation('/api/restart', { method: 'POST' }, { refreshAfter: true }));
recoverButton.addEventListener('click', () => runOperation('/api/recover', { method: 'POST' }, { refreshAfter: true }));
diagnosticsButton.addEventListener('click', () => runOperation('/api/diagnostics'));
evidenceButton.addEventListener('click', () => runOperation('/api/evidence-export', { method: 'POST' }));

backupForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const passphrase = document.querySelector('#backup-passphrase');
  const result = await runOperation('/api/backup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ passphrase: passphrase.value }),
  }, { refreshAfter: true });
  passphrase.value = '';
  if (result) operationsResult.textContent = `${copy.backupComplete}\n\n${JSON.stringify(result, null, 2)}`;
});

restoreForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const archive = document.querySelector('#restore-archive');
  const passphrase = document.querySelector('#restore-passphrase');
  const confirmation = document.querySelector('#restore-confirmation');
  await runOperation('/api/restore', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ archive: archive.value, passphrase: passphrase.value, confirmation: confirmation.value }),
  }, { refreshAfter: true });
  passphrase.value = '';
  confirmation.value = '';
});

updateForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const predecessor = document.querySelector('#update-predecessor');
  const confirmation = document.querySelector('#update-confirmation');
  await runOperation('/api/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ predecessor: predecessor.value, confirmation: confirmation.value }),
  }, { refreshAfter: true });
  confirmation.value = '';
});

tunnelForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const config = document.querySelector('#tunnel-config');
  const provider = document.querySelector('#tunnel-provider');
  const executable = document.querySelector('#tunnel-executable');
  const confirmation = document.querySelector('#tunnel-confirmation');
  await runOperation('/api/tunnel-on', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      config: config.value,
      provider: provider.value,
      executable: executable.value,
      confirmation: confirmation.value,
    }),
  }, { refreshAfter: true });
  confirmation.value = '';
});

tunnelOffButton.addEventListener('click', async () => {
  const confirmation = document.querySelector('#tunnel-disable-confirmation');
  await runOperation('/api/tunnel-off', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmation: confirmation.value }),
  }, { refreshAfter: true });
  confirmation.value = '';
});

tunnelStoreButton.addEventListener('click', () => {
  if (currentStatus?.tunnel?.state === 'ON') window.open(currentStatus.tunnel.store_url, '_blank', 'noopener');
});

tunnelAdminButton.addEventListener('click', () => {
  if (currentStatus?.tunnel?.state === 'ON') window.open(currentStatus.tunnel.admin_url, '_blank', 'noopener');
});

uninstallForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const confirmation = document.querySelector('#uninstall-confirmation');
  const result = await runOperation('/api/uninstall', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      confirmation: confirmation.value,
      data_choice: document.querySelector('#uninstall-data-choice').value,
    }),
  });
  confirmation.value = '';
  if (result) {
    operationsResult.textContent = `${copy.uninstallComplete}\n\n${JSON.stringify(result, null, 2)}`;
    window.clearInterval(refreshTimer);
    document.querySelectorAll('button, input, select').forEach((control) => { control.disabled = true; });
  }
});

languageSelect.addEventListener('change', async () => {
  setBusy(true, copy.languageMessage);
  languageSelect.disabled = true;
  try {
    await api('/api/locale', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locale: languageSelect.value }),
    });
    window.location.reload();
  } catch (error) {
    languageSelect.disabled = false;
    busy = false;
    statusBadge.className = 'badge badge-error';
    statusBadge.textContent = copy.checkFailed;
    operationMessage.textContent = error.message;
  }
});

refresh();
const refreshTimer = window.setInterval(refresh, 5000);
