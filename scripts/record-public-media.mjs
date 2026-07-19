#!/usr/bin/env node
import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';


const projectRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const scriptPath = fileURLToPath(import.meta.url);
const outputDir = process.argv[2] ? path.resolve(process.argv[2]) : '';
const requiredEnvironment = [
  'DISPLAY', 'PF07_BASE_URL', 'PF07_ADMIN_BASE_URL', 'PF07_ADMIN_USER',
  'PF07_ADMIN_PASSWORD_FILE', 'PF07_RUNTIME_ROOT', 'PF07_COMPOSE_PROJECT',
];
for (const name of requiredEnvironment) {
  if (!process.env[name]) throw new Error(`${name} is required.`);
}
if (!outputDir) throw new Error('usage: scripts/record-public-media.mjs OUTPUT_DIR');
if (!/^https:\/\//.test(process.env.PF07_BASE_URL)) throw new Error('PF07_BASE_URL must be the authorized HTTPS storefront.');
if (!/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::[1-9][0-9]{0,4})?$/.test(process.env.PF07_ADMIN_BASE_URL)) {
  throw new Error('PF07_ADMIN_BASE_URL must be a loopback-only HTTP origin.');
}

const targets = {
  demo: path.join(outputDir, 'demo-video.mp4'),
  recovery: path.join(outputDir, 'recovery-clip.mp4'),
  poster: path.join(outputDir, 'video-poster.png'),
  proof: path.join(outputDir, 'execution-proof.json'),
};
await fsp.mkdir(outputDir, { recursive: true });
for (const target of Object.values(targets)) {
  if (fs.existsSync(target)) throw new Error(`refusing to replace existing output: ${path.basename(target)}`);
}

const ffmpeg = process.env.PF07_FFMPEG_PATH || '/usr/bin/ffmpeg';
const ffprobe = process.env.PF07_FFPROBE_PATH || '/usr/bin/ffprobe';
const chrome = process.env.PF07_CHROME_PATH || '/usr/bin/google-chrome';
const userXterm = path.join(process.env.HOME || '', '.local/opt/pf07-xterm/usr/bin/xterm');
const xterm = process.env.PF07_XTERM_PATH || (fs.existsSync(userXterm) ? userXterm : '/usr/bin/xterm');
const publicBase = process.env.PF07_BASE_URL.replace(/\/$/, '');
const recordingBase = (process.env.PF07_RECORDING_BASE_URL || publicBase).replace(/\/$/, '');
const adminBase = process.env.PF07_ADMIN_BASE_URL.replace(/\/$/, '');
if (recordingBase !== publicBase
  && !/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::[1-9][0-9]{0,4})?$/.test(recordingBase)) {
  throw new Error('PF07_RECORDING_BASE_URL must be the public URL or a loopback-only HTTP origin.');
}
const runtimeRoot = path.resolve(process.env.PF07_RUNTIME_ROOT);
const composeFile = process.env.PF07_COMPOSE_FILE || path.join(runtimeRoot, 'infra/compose.yaml');
const runtimeEnv = process.env.PF07_RUNTIME_ENV || path.join(runtimeRoot, 'runtime/runtime.env');
const queueRunner = process.env.PF07_QUEUE_RUNNER || path.join(projectRoot, 'scripts/queue-runner');
const n8nHealthUrl = process.env.PF07_N8N_HEALTH_URL || 'http://127.0.0.1:15678/healthz';
const password = (await fsp.readFile(process.env.PF07_ADMIN_PASSWORD_FILE, 'utf8')).trim();
if (!password) throw new Error('PF07 administrator password file is empty.');
for (const requiredPath of [ffmpeg, ffprobe, chrome, xterm, composeFile, runtimeEnv, queueRunner]) {
  await fsp.access(requiredPath, fs.constants.R_OK);
}
await fsp.access(xterm, fs.constants.X_OK);
const scratchRoot = path.resolve(process.env.PF07_SCRATCH_ROOT || os.tmpdir());
await fsp.mkdir(scratchRoot, { recursive: true });
const visibleOperationRoot = await fsp.mkdtemp(path.join(scratchRoot, 'pf07-media-terminal-'));
const publicPreflight = await fetch(`${publicBase}/`, {
  headers: { 'ngrok-skip-browser-warning': 'pf07-validation' },
});
if (!publicPreflight.ok || !(await publicPreflight.text()).includes('OddRoom')) {
  throw new Error('authorized public HTTPS storefront preflight failed.');
}

function sha256(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

async function sha256File(file) {
  return sha256(await fsp.readFile(file));
}

function runProcess(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd || projectRoot,
      env: options.env || process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on('data', (chunk) => stdout.push(chunk));
    child.stderr.on('data', (chunk) => stderr.push(chunk));
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error(`${path.basename(command)} timed out.`));
    }, options.timeout || 120000);
    child.on('error', (error) => { clearTimeout(timer); reject(error); });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) reject(new Error(`${path.basename(command)} exited ${code}.`));
      else resolve({ stdout: Buffer.concat(stdout), stderr: Buffer.concat(stderr) });
    });
  });
}

async function startCapture(target) {
  const display = process.env.DISPLAY.includes('.') ? process.env.DISPLAY : `${process.env.DISPLAY}.0`;
  const startedAt = Date.now();
  const child = spawn(ffmpeg, [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'x11grab', '-draw_mouse', '1', '-framerate', '30', '-video_size', '1280x720',
    '-i', `${display}+0,0`, '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-map_metadata', '-1',
    '-metadata', 'title=', '-metadata', 'comment=', '-metadata', 'creation_time=', target,
  ], { stdio: ['pipe', 'ignore', 'pipe'] });
  const errors = [];
  child.stderr.on('data', (chunk) => errors.push(chunk));
  await new Promise((resolve) => setTimeout(resolve, 700));
  if (child.exitCode !== null) throw new Error(`ffmpeg capture failed: ${Buffer.concat(errors).toString('utf8').trim()}`);
  return { child, errors, startedAt };
}

async function stopCapture(capture) {
  const completed = new Promise((resolve, reject) => {
    capture.child.once('error', reject);
    capture.child.once('close', (code) => code === 0 ? resolve() : reject(new Error(`ffmpeg capture exited ${code}.`)));
  });
  capture.child.stdin.write('q\n');
  await completed;
}

function mark(capture, timeline, event, observation) {
  timeline.push({
    event,
    at_seconds: Number(((Date.now() - capture.startedAt) / 1000).toFixed(3)),
    observation,
  });
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function caption(page, marker, detail) {
  await page.evaluate(async ({ marker, detail }) => {
    document.querySelector('#pf07-recording-caption')?.remove();
    const root = document.createElement('div');
    root.id = 'pf07-recording-caption';
    Object.assign(root.style, {
      position: 'fixed', zIndex: '2147483647', top: '20px', right: '20px', width: '360px',
      padding: '16px 18px', color: '#f7fbff', background: 'rgba(6, 17, 31, .94)',
      border: '2px solid #58a6ff', borderRadius: '12px', boxShadow: '0 14px 40px rgba(0,0,0,.34)',
      fontFamily: '"OddRoom Sans", "Noto Sans KR", Arial, sans-serif', pointerEvents: 'none', lineHeight: '1.35',
    });
    const strong = document.createElement('strong');
    strong.textContent = marker;
    Object.assign(strong.style, { display: 'block', color: '#7cc4ff', fontSize: '20px', letterSpacing: '.055em' });
    const text = document.createElement('span');
    text.textContent = detail;
    Object.assign(text.style, { display: 'block', marginTop: '5px', fontSize: '15px' });
    root.append(strong, text);
    document.body.append(root);
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }, { marker, detail });
  await wait(100);
}

async function setFullscreen(page) {
  const session = await page.context().newCDPSession(page);
  const { windowId } = await session.send('Browser.getWindowForTarget');
  await session.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'fullscreen' } });
  await wait(500);
}

async function openPublicContext(browser) {
  const extraHTTPHeaders = { 'ngrok-skip-browser-warning': 'pf07-validation' };
  if (recordingBase !== publicBase) extraHTTPHeaders['X-OddRoom-Private-Admin'] = 'loopback';
  const context = await browser.newContext({
    viewport: null,
    extraHTTPHeaders,
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  await setFullscreen(page);
  return { context, page };
}

async function slowFill(page, selector, value) {
  const field = page.locator(selector);
  await field.focus();
  await field.fill('');
  await field.pressSequentially(value, { delay: 42 });
  await wait(180);
}

async function highlightThenNavigate(page, locator, route) {
  await locator.scrollIntoViewIfNeeded();
  await locator.hover();
  await locator.focus();
  await wait(250);
  await locator.evaluate((node) => {
    node.style.transform = 'translateY(2px)';
    node.style.boxShadow = 'inset 0 0 0 3px #58a6ff';
  });
  await wait(350);
  await page.goto(`${recordingBase}${route}`, { waitUntil: 'networkidle' });
}

async function createOrderThroughCheckout(page, email, timelineState) {
  await page.goto(`${recordingBase}/`, { waitUntil: 'networkidle' });
  if (timelineState) {
    await caption(page, 'LIVE STOREFRONT', '실제 WooCommerce storefront에서 주문을 시작합니다.');
    mark(timelineState.capture, timelineState.timeline, 'LIVE_STOREFRONT', 'home_visible');
    await wait(4200);
    await page.evaluate(() => window.scrollTo({ top: 420, behavior: 'smooth' }));
    await wait(1600);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
    await wait(900);
  }

  await highlightThenNavigate(page, page.getByRole('link', { name: /데모 상품 보기/ }), '/shop/');
  if (timelineState) {
    await caption(page, 'PRODUCT INPUT', '고정 workflow fixture가 아니라 실제 상품을 선택합니다.');
    mark(timelineState.capture, timelineState.timeline, 'SHOP_OPENED', 'shop_visible');
    await wait(3700);
  }

  await highlightThenNavigate(
    page,
    page.locator('a[href*="/product/oddroom-drop-kit/"]').first(),
    '/product/oddroom-drop-kit/',
  );
  if (timelineState) {
    await caption(page, 'PRODUCT SELECTED', 'OddRoom Drop Kit을 cart에 실제로 추가합니다.');
    mark(timelineState.capture, timelineState.timeline, 'PRODUCT_SELECTED', 'product_page_visible');
    await wait(3600);
  }
  await page.locator('button.single_add_to_cart_button').click();
  await page.waitForLoadState('networkidle');
  await wait(900);

  await highlightThenNavigate(page, page.locator('.oddroom-frontbar a[href*="/cart/"]'), '/cart/');
  await page.locator('.wc-block-cart').waitFor();
  await page.waitForFunction(
    () => !document.querySelector('.wc-block-components-skeleton__element'),
    null,
    { timeout: 15000 },
  ).catch(() => {});
  if (timelineState) {
    await caption(page, 'CART READY', '실제 cart 상태와 합성 상품 금액을 확인합니다.');
    mark(timelineState.capture, timelineState.timeline, 'CART_READY', 'cart_contains_product');
    await wait(4200);
  }

  await highlightThenNavigate(page, page.locator('.wc-block-cart__submit-button'), '/checkout/');
  await page.locator('#email').waitFor();
  if (timelineState) {
    await caption(page, 'REAL CHECKOUT', '합성 구매자 정보를 입력하고 비금전 주문을 제출합니다.');
  }
  await slowFill(page, '#email', email);
  await page.locator('#billing-country').selectOption('KR');
  await wait(500);
  await slowFill(page, '#billing-first_name', 'Synthetic');
  await slowFill(page, '#billing-last_name', 'Buyer');
  await slowFill(page, '#billing-address_1', '123 Test Street');
  await slowFill(page, '#billing-city', 'Seoul');
  await slowFill(page, '#billing-postcode', '04524');
  if (timelineState) {
    mark(timelineState.capture, timelineState.timeline, 'CHECKOUT_INPUT', 'synthetic_checkout_input_visible');
    await wait(2600);
  }

  const [checkoutResponse] = await Promise.all([
    page.waitForResponse(
      (response) => response.request().method() === 'POST' && /\/wc\/store\/v1\/checkout(?:\?|$)/.test(response.url()),
      { timeout: 45000 },
    ),
    page.locator('.wc-block-components-checkout-place-order-button').click({ noWaitAfter: true }),
  ]);
  if (!checkoutResponse.ok()) {
    const body = await checkoutResponse.json().catch(() => ({}));
    const code = typeof body?.code === 'string' ? body.code : 'CHECKOUT_HTTP_ERROR';
    throw new Error(`checkout API returned ${checkoutResponse.status()}: ${code}`);
  }
  await page.waitForURL(/order-received/, { waitUntil: 'commit', timeout: 45000 });
  await page.getByText(/Order received|주문이 접수/i).first().waitFor({ state: 'visible', timeout: 30000 });
  await page.addStyleTag({ content: `
    .wc-block-order-confirmation-summary-list-item__value,
    .wc-block-components-address-card__address-section { filter: blur(7px) !important; }
  ` });
  const confirmation = await page.locator('body').innerText();
  if (!/order received|주문이 접수/i.test(confirmation)) throw new Error('real checkout did not reach order confirmation.');
  if (timelineState) {
    await caption(page, 'ORDER RECEIVED', '실제 주문이 생성됐습니다. 식별자는 공개 영상에서 마스킹합니다.');
    mark(timelineState.capture, timelineState.timeline, 'ORDER_RECEIVED', 'woocommerce_confirmation_visible');
    await wait(4700);
  }
}

async function loginAdmin(page) {
  await page.setExtraHTTPHeaders({ 'X-OddRoom-Private-Admin': 'loopback' });
  await page.goto(`${adminBase}/wp-login.php`, { waitUntil: 'domcontentloaded' });
  await page.fill('#user_login', process.env.PF07_ADMIN_USER);
  await page.fill('#user_pass', password);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('#wp-submit'),
  ]);
  await page.goto(`${adminBase}/wp-admin/admin.php?page=oddroom-orderops`, { waitUntil: 'networkidle' });
  await page.locator('.oddroom-orderops .oddroom-table-wrap tbody tr').first().waitFor();
  await maskAdmin(page);
  await focusNewestRow(page);
}

async function maskAdmin(page) {
  await page.addStyleTag({ content: `
    .oddroom-orderops th:nth-child(1), .oddroom-orderops td:nth-child(1),
    .oddroom-orderops th:nth-child(2), .oddroom-orderops td:nth-child(2),
    .oddroom-orderops th:nth-child(3), .oddroom-orderops td:nth-child(3),
    .oddroom-orderops th:nth-child(18), .oddroom-orderops td:nth-child(18) {
      filter: blur(7px) !important;
      user-select: none !important;
    }
  ` });
}

async function focusNewestRow(page) {
  const row = page.locator('.oddroom-orderops .oddroom-table-wrap tbody tr').first();
  await row.evaluate((node) => node.scrollIntoView({ block: 'center', inline: 'start', behavior: 'auto' }));
  await wait(500);
}

async function newestStatus(page) {
  return (await page.locator('.oddroom-orderops .oddroom-table-wrap tbody tr').first().locator('td').nth(4).innerText()).trim();
}

async function newestActionId(page) {
  const value = (await page.locator('.oddroom-orderops .oddroom-table-wrap tbody tr').first().locator('td').nth(17).innerText()).trim();
  return /^[1-9][0-9]*$/.test(value) ? Number(value) : 0;
}

async function reloadAdmin(page) {
  await page.reload({ waitUntil: 'networkidle' });
  await page.locator('.oddroom-orderops .oddroom-table-wrap tbody tr').first().waitFor();
  await maskAdmin(page);
  await focusNewestRow(page);
}

async function compose(...args) {
  return runProcess('docker', [
    'compose', '--env-file', runtimeEnv, '-f', composeFile,
    '-p', process.env.PF07_COMPOSE_PROJECT, ...args,
  ], { cwd: runtimeRoot, timeout: 120000 });
}

const visibleOperationShell = String.raw`
set +e
printf '\033[2J\033[H'
printf '%s\n' "$PF07_VISIBLE_HEADING"
printf '$ %s\n' "$PF07_VISIBLE_COMMAND"
printf 'RUNNING actual protected runtime action...\n'
sleep 0.9
case "$PF07_VISIBLE_KIND" in
  worker)
    "$PF07_VISIBLE_QUEUE_RUNNER" --once >"$PF07_VISIBLE_LOG" 2>&1
    operation_status=$?
    ;;
  stop-n8n)
    docker compose --env-file "$PF07_VISIBLE_RUNTIME_ENV" -f "$PF07_VISIBLE_COMPOSE_FILE" -p "$PF07_VISIBLE_COMPOSE_PROJECT" stop n8n >"$PF07_VISIBLE_LOG" 2>&1
    operation_status=$?
    ;;
  start-n8n)
    docker compose --env-file "$PF07_VISIBLE_RUNTIME_ENV" -f "$PF07_VISIBLE_COMPOSE_FILE" -p "$PF07_VISIBLE_COMPOSE_PROJECT" start n8n >"$PF07_VISIBLE_LOG" 2>&1
    operation_status=$?
    ;;
  *)
    operation_status=64
    ;;
esac
if [ "$operation_status" -eq 0 ]; then
  printf '[PASS] actual process exit = 0\n'
else
  printf '[FAIL] actual process exit = %s\n' "$operation_status"
fi
sleep 0.65
exit "$operation_status"
`;

async function runVisibleOperation({ kind, heading, command, capture, timeline, event, observation }) {
  const logPath = path.join(visibleOperationRoot, `${String(timeline.length).padStart(2, '0')}-${kind}.log`);
  const errors = [];
  const child = spawn(xterm, [
    '-T', 'PF07 Live Runtime', '-geometry', '73x9+510+490',
    '-fa', 'DejaVu Sans Mono', '-fs', '15',
    '-bg', '#07111f', '-fg', '#f7fbff', '-cr', '#7cc4ff',
    '-bd', '#58a6ff', '-bw', '3', '-e', 'bash', '-lc', visibleOperationShell,
  ], {
    env: {
      ...process.env,
      PF07_RUNTIME_ROOT: runtimeRoot,
      PF07_RUNTIME_ENV: runtimeEnv,
      PF07_COMPOSE_FILE: composeFile,
      PF07_VISIBLE_KIND: kind,
      PF07_VISIBLE_HEADING: heading,
      PF07_VISIBLE_COMMAND: command,
      PF07_VISIBLE_QUEUE_RUNNER: queueRunner,
      PF07_VISIBLE_RUNTIME_ENV: runtimeEnv,
      PF07_VISIBLE_COMPOSE_FILE: composeFile,
      PF07_VISIBLE_COMPOSE_PROJECT: process.env.PF07_COMPOSE_PROJECT,
      PF07_VISIBLE_LOG: logPath,
    },
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  child.stderr.on('data', (chunk) => errors.push(chunk));
  const completed = new Promise((resolve, reject) => {
    child.once('error', () => reject(new Error(`visible ${kind} terminal failed to start.`)));
    child.once('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`visible ${kind} operation exited non-zero.`));
    });
  });
  await wait(650);
  if (child.exitCode !== null) {
    throw new Error(`visible ${kind} terminal ended before observation.`);
  }
  mark(capture, timeline, event, observation);
  await completed;
  await fsp.rm(logPath, { force: true });
}

async function waitForCheckoutAllowance(requiredRemaining) {
  const { stdout: prefixOutput } = await compose('--profile', 'tools', 'run', '--rm', 'wpcli', 'db', 'prefix');
  const tablePrefix = prefixOutput.toString('utf8').trim();
  if (!/^[A-Za-z0-9_]+$/.test(tablePrefix)) throw new Error('WordPress database prefix is invalid.');
  const query = [
    "SELECT CONCAT(rate_limit_remaining, ':', GREATEST(rate_limit_expiry - UNIX_TIMESTAMP(), 0))",
    `FROM ${tablePrefix}wc_rate_limits`,
    "WHERE rate_limit_key LIKE 'store_api_request_%'",
    'AND rate_limit_expiry >= UNIX_TIMESTAMP()',
    'ORDER BY rate_limit_expiry DESC LIMIT 1',
  ].join(' ');
  const { stdout } = await compose(
    '--profile', 'tools', 'run', '--rm', 'wpcli',
    'db', 'query', query, '--skip-column-names',
  );
  const match = stdout.toString('utf8').trim().match(/^([0-9]+):([0-9]+)$/m);
  if (!match || Number(match[1]) >= requiredRemaining) return;
  await wait((Number(match[2]) + 2) * 1000);
}

async function resetSyntheticCheckoutAllowance() {
  const { stdout } = await compose(
    '--profile', 'tools', 'run', '--rm', 'wpcli',
    'oddroom-orderops', 'reset-checkout-limit',
  );
  const record = JSON.parse(stdout.toString('utf8'));
  if (record.status !== 'PASS' || record.scope !== 'SYNTHETIC_CHECKOUT_RATE_LIMIT_ONLY') {
    throw new Error('protected synthetic checkout reset did not pass.');
  }
}

async function waitForN8n() {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(n8nHealthUrl);
      if (response.ok) return;
    } catch {}
    await wait(750);
  }
  throw new Error('restored n8n did not become healthy after restart.');
}

async function videoProbe(file) {
  const { stdout } = await runProcess(ffprobe, [
    '-v', 'error', '-select_streams', 'v:0', '-count_frames',
    '-show_entries', 'stream=codec_name,pix_fmt,width,height,nb_read_frames:format=duration',
    '-of', 'json', file,
  ]);
  const parsed = JSON.parse(stdout.toString('utf8'));
  const stream = parsed.streams?.[0];
  return {
    codec: stream?.codec_name,
    pixel_format: stream?.pix_fmt,
    width: Number(stream?.width),
    height: Number(stream?.height),
    frame_count: Number(stream?.nb_read_frames),
    duration_seconds: Number(Number(parsed.format?.duration).toFixed(3)),
  };
}

async function sampleDynamics(file) {
  const { stdout } = await runProcess(ffmpeg, [
    '-hide_banner', '-loglevel', 'error', '-i', file,
    '-vf', 'fps=1,scale=160:90,format=gray', '-f', 'framemd5', '-',
  ]);
  const hashes = stdout.toString('utf8').split('\n')
    .filter((line) => line && !line.startsWith('#'))
    .map((line) => line.split(',').at(-1).trim());
  return { sampled_frame_count: hashes.length, unique_sampled_frames: new Set(hashes).size };
}

async function frameSha(file, seconds) {
  const { stdout } = await runProcess(ffmpeg, [
    '-hide_banner', '-loglevel', 'error', '-i', file, '-ss', String(seconds),
    '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-',
  ]);
  return sha256(stdout);
}

async function bindTimelineFrames(file, timeline) {
  for (const event of timeline) {
    event.frame_sha256 = await frameSha(file, Math.max(0, event.at_seconds));
  }
}

const browser = await chromium.launch({
  headless: false,
  executablePath: chrome,
  args: [
    '--kiosk', '--window-position=0,0', '--window-size=1280,720', '--no-first-run',
    '--disable-session-crashed-bubble', '--disable-infobars', '--disable-notifications',
    '--disable-background-networking', '--disable-component-update', '--disable-translate',
    '--disable-features=Translate,TranslateUI', '--force-device-scale-factor=1',
  ],
});

let n8nStopped = false;
let activeCapture = null;
const demoTimeline = [];
const recoveryTimeline = [];
try {
  await resetSyntheticCheckoutAllowance();
  await waitForCheckoutAllowance(2);
  const demoSession = await openPublicContext(browser);
  const demoCapture = await startCapture(targets.demo);
  activeCapture = demoCapture;
  const demoState = { capture: demoCapture, timeline: demoTimeline };
  await createOrderThroughCheckout(
    demoSession.page,
    `pf07-video-demo-${Date.now()}@example.com`,
    demoState,
  );
  await loginAdmin(demoSession.page);
  const initialStatus = await newestStatus(demoSession.page);
  if (initialStatus !== 'pending') throw new Error(`new demo row was not pending before worker execution: ${initialStatus}`);
  await caption(demoSession.page, 'OUTBOX PENDING', '새 immutable row가 foreground worker를 기다립니다.');
  mark(demoCapture, demoTimeline, 'OUTBOX_PENDING', 'status_pending');
  await wait(4300);

  await caption(demoSession.page, 'WORKER RUN', '실제 WP-CLI queue runner가 같은 row를 처리합니다.');
  await runVisibleOperation({
    kind: 'worker',
    heading: 'PF07 REAL WORKER',
    command: 'queue --once',
    capture: demoCapture,
    timeline: demoTimeline,
    event: 'WORKER_RUN',
    observation: 'visible_terminal_foreground_queue_exit_zero',
  });
  await wait(450);
  await reloadAdmin(demoSession.page);
  const completedStatus = await newestStatus(demoSession.page);
  if (completedStatus !== 'completed') throw new Error(`demo row did not complete: ${completedStatus}`);
  await caption(demoSession.page, 'ADMIN COMPLETED', 'WordPress outbox row가 completed로 수렴했습니다.');
  mark(demoCapture, demoTimeline, 'ADMIN_COMPLETED', 'status_completed');
  await wait(5000);
  await demoSession.page.locator('.oddroom-table-wrap').evaluate((node) => { node.scrollLeft = Math.round(node.scrollWidth * 0.58); });
  await caption(demoSession.page, 'MASKED CHECKPOINTS', '실제 CRM checkpoint는 공개 영상에서 마스킹된 상태로 확인합니다.');
  mark(demoCapture, demoTimeline, 'CHECKPOINTS_MASKED', 'crm_checkpoint_columns_visible_masked');
  await wait(5700);
  await stopCapture(demoCapture);
  activeCapture = null;
  await demoSession.context.close();

  await waitForCheckoutAllowance(1);
  const recoverySession = await openPublicContext(browser);
  await createOrderThroughCheckout(recoverySession.page, `pf07-video-recovery-${Date.now()}@example.com`, null);
  await loginAdmin(recoverySession.page);
  const recoveryInitial = await newestStatus(recoverySession.page);
  if (recoveryInitial !== 'pending') throw new Error(`new recovery row was not pending: ${recoveryInitial}`);
  const recoveryInitialActionId = await newestActionId(recoverySession.page);
  if (recoveryInitialActionId < 1) throw new Error('new recovery row had no scheduled action.');

  const recoveryCapture = await startCapture(targets.recovery);
  activeCapture = recoveryCapture;
  await caption(recoverySession.page, 'OUTBOX PENDING', '복구 검증용 실제 주문 row가 worker를 기다립니다.');
  mark(recoveryCapture, recoveryTimeline, 'OUTBOX_PENDING', 'status_pending');
  await wait(850);

  await runVisibleOperation({
    kind: 'stop-n8n',
    heading: 'PF07 RUNTIME CONTROL',
    command: 'stop n8n',
    capture: recoveryCapture,
    timeline: recoveryTimeline,
    event: 'ENDPOINT_STOP_COMMAND',
    observation: 'visible_terminal_stop_n8n_exit_zero',
  });
  n8nStopped = true;
  await caption(recoverySession.page, 'ENDPOINT DOWN', 'n8n endpoint를 실제로 중지하고 첫 전달을 실행합니다.');
  mark(recoveryCapture, recoveryTimeline, 'ENDPOINT_DOWN', 'restored_n8n_stopped');
  await wait(450);
  await runVisibleOperation({
    kind: 'worker',
    heading: 'PF07 REAL WORKER',
    command: 'queue --once (endpoint down)',
    capture: recoveryCapture,
    timeline: recoveryTimeline,
    event: 'FAILURE_WORKER_RUN',
    observation: 'visible_terminal_failure_worker_exit_zero',
  });
  await reloadAdmin(recoverySession.page);
  const failedStatus = await newestStatus(recoverySession.page);
  if (failedStatus !== 'retry_wait') throw new Error(`recovery row did not enter retry_wait: ${failedStatus}`);
  const recoveryFollowupActionId = await newestActionId(recoverySession.page);
  if (recoveryFollowupActionId < 1 || recoveryFollowupActionId === recoveryInitialActionId) {
    throw new Error('retry_wait did not retain a distinct pending follow-up action.');
  }
  await caption(recoverySession.page, 'RETRY WAIT', '같은 immutable payload와 bounded retry 상태가 남았습니다.');
  mark(recoveryCapture, recoveryTimeline, 'RETRY_WAIT', 'status_retry_wait_with_distinct_followup_action');
  await wait(850);

  await runVisibleOperation({
    kind: 'start-n8n',
    heading: 'PF07 RUNTIME CONTROL',
    command: 'start n8n',
    capture: recoveryCapture,
    timeline: recoveryTimeline,
    event: 'ENDPOINT_START_COMMAND',
    observation: 'visible_terminal_start_n8n_exit_zero',
  });
  n8nStopped = false;
  await waitForN8n();
  await caption(recoverySession.page, 'ENDPOINT RESTORED', '별도 follow-up action을 정상 경로에서 다시 실행합니다.');
  mark(recoveryCapture, recoveryTimeline, 'ENDPOINT_RESTORED', 'restored_n8n_healthy');
  await wait(450);
  await runVisibleOperation({
    kind: 'worker',
    heading: 'PF07 REAL WORKER',
    command: 'queue --once (retry)',
    capture: recoveryCapture,
    timeline: recoveryTimeline,
    event: 'RECOVERY_WORKER_RUN',
    observation: 'visible_terminal_recovery_worker_exit_zero',
  });
  await reloadAdmin(recoverySession.page);
  const recoveredStatus = await newestStatus(recoverySession.page);
  if (recoveredStatus !== 'completed') throw new Error(`recovery row did not complete: ${recoveredStatus}`);
  await caption(recoverySession.page, 'RECOVERED', 'retry_wait에서 completed로 실제 수렴했습니다.');
  mark(recoveryCapture, recoveryTimeline, 'RECOVERED', 'status_completed');
  await wait(500);
  await stopCapture(recoveryCapture);
  activeCapture = null;
  await recoverySession.context.close();
} finally {
  if (activeCapture) {
    await stopCapture(activeCapture).catch(() => {});
  }
  if (n8nStopped) {
    await compose('start', 'n8n').catch(() => {});
    await waitForN8n().catch(() => {});
  }
  await browser.close();
  await fsp.rm(visibleOperationRoot, { recursive: true, force: true });
}

const posterTime = Math.max(0, (demoTimeline.find((event) => event.event === 'ADMIN_COMPLETED')?.at_seconds || 55) + 1);
await runProcess(ffmpeg, [
  '-hide_banner', '-loglevel', 'error', '-i', targets.demo, '-ss', String(posterTime),
  '-frames:v', '1', '-vf', 'scale=1440:810:force_original_aspect_ratio=decrease,pad=1440:1000:(ow-iw)/2:(oh-ih)/2:color=0x07111f',
  '-map_metadata', '-1', targets.poster,
]);

await bindTimelineFrames(targets.demo, demoTimeline);
await bindTimelineFrames(targets.recovery, recoveryTimeline);
const demoProbe = await videoProbe(targets.demo);
const recoveryProbe = await videoProbe(targets.recovery);
const proof = {
  schema_version: 1,
  case_id: 'pf07',
  classification: 'PUBLIC_SANITIZED_EXECUTION_PROOF',
  recording_script: 'scripts/record-public-media.mjs',
  recording_script_sha256: await sha256File(scriptPath),
  metadata_stripped: true,
  public_https_storefront_preflight: 'PASS',
  synthetic_checkout_window_prepared_via_wp_cli: true,
  videos: {
    'demo-video.mp4': {
      sha256: await sha256File(targets.demo),
      ...demoProbe,
      ...(await sampleDynamics(targets.demo)),
      continuous_capture: true,
      actual_checkout_observed: true,
      foreground_worker_observed: true,
      visible_worker_terminal_observed: true,
      final_status: 'completed',
      timeline: demoTimeline,
    },
    'recovery-clip.mp4': {
      sha256: await sha256File(targets.recovery),
      ...recoveryProbe,
      ...(await sampleDynamics(targets.recovery)),
      continuous_capture: true,
      actual_endpoint_failure_observed: true,
      retry_wait_observed: true,
      distinct_followup_action_observed: true,
      endpoint_restore_observed: true,
      visible_endpoint_control_terminal_observed: true,
      visible_worker_terminal_observed: true,
      final_status: 'completed',
      timeline: recoveryTimeline,
    },
  },
  poster: {
    file: 'video-poster.png',
    sha256: await sha256File(targets.poster),
    source_video: 'demo-video.mp4',
    source_at_seconds: posterTime,
  },
};
await fsp.writeFile(targets.proof, `${JSON.stringify(proof, null, 2)}\n`, { mode: 0o644 });
process.stdout.write(JSON.stringify({
  status: 'PASS',
  demo_duration_seconds: demoProbe.duration_seconds,
  recovery_duration_seconds: recoveryProbe.duration_seconds,
  demo_events: demoTimeline.length,
  recovery_events: recoveryTimeline.length,
}) + '\n');
