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
const tunnelOffButton = document.querySelector('#tunnel-off-button');
const tunnelStoreButton = document.querySelector('#tunnel-store-button');
const tunnelAdminButton = document.querySelector('#tunnel-admin-button');
const uninstallForm = document.querySelector('#uninstall-form');

let currentStatus = null;
let busy = false;
let currentPassword = '';

const copy = locale === 'en_US' ? {
  busy: 'Working', ready: 'Ready', waiting: 'Waiting', connected: 'Connected', checkFailed: 'Check failed',
  startFailed: 'Start failed', stopFailed: 'Stop failed', copied: 'Copied', copyPassword: 'Copy password',
  checking: 'Checking package state.',
  readyMessage: 'The store and administrator targets are ready to open.',
  waitingMessage: 'Select Start runtime to prepare the selected mode inside this package.',
  demoDescription: 'Start an isolated demo without service credentials. It uses synthetic orders only and never contacts real payment, external CRM, or Slack services.',
  connectedDescription: 'Protected recipient connections are active for synthetic orders only. Real payments and customer data remain disabled.',
  startMessage: 'The first start can take several minutes while pinned container images and dependencies are prepared.',
  stopMessage: 'Stopping containers while preserving package-local data.',
  languageMessage: 'Applying the presentation language to the same business runtime.',
  scenarioMessage: 'Applying the next deterministic delivery state.',
  scenarioApplied: 'The next synthetic order will use the selected delivery state.',
  resetMessage: 'Resetting package-owned synthetic business data.',
  resetComplete: 'Synthetic demo data was reset. The administrator, catalog, identity, and volumes were preserved.',
  actionFailed: 'The operation could not be completed.',
  connectedMessage: 'Testing the protected HubSpot and Slack connections, then switching this runtime.',
  connectedComplete: 'Connection tests passed. CONNECTED_MODE is active on the same business runtime.',
  demoModeMessage: 'Switching the same business runtime to credential-free DEMO_MODE.',
  demoModeComplete: 'DEMO_MODE is active. Stored recipient credentials remain protected and unused.',
  operationMessage: 'Running the package-scoped operation.',
  backupComplete: 'Encrypted backup created beside the extracted package folder. Keep its passphrase separately.',
  uninstallComplete: 'The confirmed package-owned resources were removed. This hub will not recreate runtime state.',
  phase: {
    preflight: 'Checking the Docker runtime.',
    downloads: 'Downloading and verifying exact pinned dependencies.',
    containers: 'Starting the isolated database and WordPress containers.',
    wordpress: 'Preparing WordPress and language support.',
    dependencies: 'Preparing pinned WooCommerce and Action Scheduler versions.',
    storefront: 'Preparing the Quiet Utility store and operations surfaces.',
    automation: 'Preparing the package-owned n8n workflow and background worker.',
    'task-runner-image': 'Preparing the versioned task runner from its pinned dependency lock.',
    verify: 'Verifying the store and administrator targets.',
    language: 'Applying the presentation language to the same business runtime.',
    stop: 'Stopping package containers.',
    stopped: 'The demo is stopped. Package-local data is preserved.',
    ready: 'The store and administrator targets are ready to open.',
    error: 'The last operation needs attention. Review the reported action and retry.',
  },
} : {
  busy: '작업 중', ready: '준비 완료', waiting: '대기', connected: '연결됨', checkFailed: '확인 실패',
  startFailed: '시작 실패', stopFailed: '중지 실패', copied: '복사했습니다', copyPassword: '비밀번호 복사',
  checking: '패키지 상태를 확인하고 있습니다.',
  readyMessage: '상점과 관리자 화면을 열 수 있습니다.',
  waitingMessage: '런타임 시작을 누르면 선택한 모드를 패키지 내부에 준비합니다.',
  demoDescription: '자격 증명 없이 시작하는 격리 데모입니다. 합성 주문만 사용하며 실제 결제, 외부 CRM, Slack을 호출하지 않습니다.',
  connectedDescription: '보호된 실제 수신자 연결이 활성화됐습니다. 합성 주문만 사용하며 실제 결제와 고객 데이터는 계속 차단됩니다.',
  startMessage: '첫 시작은 컨테이너 이미지와 고정 버전 의존성을 준비하므로 수 분이 걸릴 수 있습니다.',
  stopMessage: '컨테이너를 중지하고 로컬 데이터를 보존하는 중입니다.',
  languageMessage: '표시 언어를 같은 비즈니스 런타임에 적용하는 중입니다.',
  scenarioMessage: '다음 합성 주문의 전달 상태를 적용하는 중입니다.',
  scenarioApplied: '다음 합성 주문에 선택한 전달 상태가 적용됩니다.',
  resetMessage: '패키지 소유 합성 비즈니스 데이터를 초기화하는 중입니다.',
  resetComplete: '합성 데모 데이터를 초기화했습니다. 관리자·카탈로그·런타임 식별자·볼륨은 보존되었습니다.',
  actionFailed: '작업을 완료하지 못했습니다.',
  connectedMessage: '보호된 HubSpot·Slack 연결을 검사하고 같은 런타임의 운영 모드를 전환하는 중입니다.',
  connectedComplete: '연결 테스트를 통과했습니다. 같은 비즈니스 런타임에 CONNECTED_MODE가 적용됐습니다.',
  demoModeMessage: '같은 비즈니스 런타임을 자격 증명 없는 DEMO_MODE로 전환하는 중입니다.',
  demoModeComplete: 'DEMO_MODE가 적용됐습니다. 저장된 수신자 자격 증명은 보호된 채 사용되지 않습니다.',
  operationMessage: '패키지 범위 운영 작업을 실행하는 중입니다.',
  backupComplete: '추출 폴더 옆에 암호화 백업을 만들었습니다. passphrase는 별도로 보관하세요.',
  uninstallComplete: '확인된 패키지 소유 자원을 제거했습니다. 이 허브에서는 런타임 상태를 다시 만들지 않습니다.',
  phase: {},
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

function setBusy(value, message = '') {
  busy = value;
  startButton.disabled = value;
  stopButton.disabled = value;
  scenarioSelect.disabled = value;
  scenarioButton.disabled = value;
  resetConfirmation.disabled = value;
  resetButton.disabled = value || resetConfirmation.value !== 'RESET PF07 DEMO';
  connectedForm.querySelectorAll('input, button').forEach((control) => { control.disabled = value; });
  operationsPanel.querySelectorAll('input, select, button').forEach((control) => { control.disabled = value; });
  if (value) {
    statusBadge.className = 'badge badge-busy';
    statusBadge.textContent = copy.busy;
    signalFill.style.width = '62%';
    operationMessage.textContent = message;
  }
}

function render(status) {
  currentStatus = status;
  const ready = Boolean(status.ready);
  storeButton.disabled = busy || !ready;
  adminButton.disabled = busy || !ready;
  startButton.disabled = busy;
  stopButton.disabled = busy || status.services.length === 0;
  const demoReady = ready && status.mode === 'DEMO_MODE';
  scenarioSelect.disabled = busy || !demoReady;
  scenarioButton.disabled = busy || !demoReady;
  resetConfirmation.disabled = busy || !demoReady;
  resetButton.disabled = busy || !demoReady || resetConfirmation.value !== 'RESET PF07 DEMO';
  connectedForm.querySelectorAll('input, button').forEach((control) => { control.disabled = busy; });
  operationsPanel.querySelectorAll('input, select, button').forEach((control) => { control.disabled = busy; });
  const tunnelReady = status.tunnel?.state === 'ON';
  tunnelOffButton.disabled = busy || !tunnelReady;
  tunnelStoreButton.disabled = busy || !tunnelReady;
  tunnelAdminButton.disabled = busy || !tunnelReady;
  document.querySelector('#mode-fact').textContent = status.mode;
  document.querySelector('#mode-pill').textContent = `${status.mode.replace('_', ' ')} · 0 KRW`;
  document.querySelector('#mode-description').textContent = status.mode === 'CONNECTED_MODE' ? copy.connectedDescription : copy.demoDescription;
  document.querySelector('#store-fact').textContent = status.store_reachable ? copy.connected : copy.waiting;
  document.querySelector('#admin-fact').textContent = status.admin_reachable ? copy.connected : copy.waiting;
  document.querySelector('#n8n-fact').textContent = status.n8n_reachable ? copy.connected : copy.waiting;
  document.querySelector('#runner-fact').textContent = status.task_runner_running ? copy.connected : copy.waiting;
  document.querySelector('#worker-fact').textContent = status.worker_running ? copy.connected : copy.waiting;
  document.querySelector('#service-fact').textContent = `${status.services.length} / 5`;
  if (!busy) {
    statusBadge.className = `badge ${ready ? 'badge-ready' : 'badge-idle'}`;
    statusBadge.textContent = ready ? copy.ready : copy.waiting;
    signalFill.style.width = ready ? '100%' : status.services.length ? '52%' : '8%';
    const operation = status.operation;
    operationMessage.textContent = (locale === 'en_US' && operation
      ? copy.phase[operation.phase]
      : operation?.message) || (ready ? copy.readyMessage : copy.waitingMessage);
  }
}

async function refresh() {
  if (busy) return;
  try {
    render(await api('/api/status'));
  } catch (error) {
    statusBadge.className = 'badge badge-error';
    statusBadge.textContent = copy.checkFailed;
    operationMessage.textContent = error.message;
  }
}

startButton.addEventListener('click', async () => {
  setBusy(true, copy.startMessage);
  try {
    render(await api('/api/start', { method: 'POST' }));
  } catch (error) {
    statusBadge.className = 'badge badge-error';
    statusBadge.textContent = copy.startFailed;
    operationMessage.textContent = error.message;
  } finally {
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
  const confirmation = document.querySelector('#tunnel-confirmation');
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
