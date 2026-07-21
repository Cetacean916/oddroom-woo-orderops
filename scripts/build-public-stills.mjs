#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { chromium } from 'playwright';

const mediaRoot = process.argv[2] ? path.resolve(process.argv[2]) : '';
const outputRoot = process.argv[3] ? path.resolve(process.argv[3]) : '';
if (!mediaRoot || !outputRoot) {
  throw new Error('usage: scripts/build-public-stills.mjs EXECUTION_MEDIA_DIR OUTPUT_DIR');
}

const videoPath = path.join(mediaRoot, 'demo-video.mp4');
const recoveryVideoPath = path.join(mediaRoot, 'recovery-clip.mp4');
const proofPath = path.join(mediaRoot, 'execution-proof.json');
const mainOutputPath = path.join(outputRoot, 'main-image.png');
const outputPath = path.join(outputRoot, 'detail-01-overview.png');
const flowOutputPath = path.join(outputRoot, 'detail-02-flow.png');
const recoveryOutputPath = path.join(outputRoot, 'detail-03-result.png');
for (const required of [videoPath, recoveryVideoPath, proofPath]) await fsp.access(required, fs.constants.R_OK);
await fsp.mkdir(outputRoot, { recursive: true });
if ([mainOutputPath, outputPath, flowOutputPath, recoveryOutputPath].some((target) => fs.existsSync(target))) {
  throw new Error('refusing to replace an existing public still');
}

const proof = JSON.parse(await fsp.readFile(proofPath, 'utf8'));
const video = proof.videos?.['demo-video.mp4'];
if (!video || proof.classification !== 'PUBLIC_SANITIZED_EXECUTION_PROOF') {
  throw new Error('execution proof identity is invalid');
}

const sha256 = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const eventByName = new Map((video.timeline || []).map((event) => [event.event, event]));
const requiredEvents = ['LIVE_STOREFRONT', 'PRODUCT_SELECTED', 'CHECKOUT_INPUT'];
const frames = {};
for (const eventName of requiredEvents) {
  const event = eventByName.get(eventName);
  if (!event || !Number.isFinite(event.at_seconds) || !/^[0-9a-f]{64}$/.test(event.frame_sha256)) {
    throw new Error(`execution frame is missing: ${eventName}`);
  }
  const result = spawnSync(process.env.PF07_FFMPEG_PATH || '/usr/bin/ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-i', videoPath, '-ss', String(event.at_seconds),
    '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-',
  ], { maxBuffer: 32 * 1024 * 1024 });
  if (result.status !== 0 || sha256(result.stdout) !== event.frame_sha256) {
    throw new Error(`execution frame commitment failed: ${eventName}`);
  }
  frames[eventName] = `data:image/png;base64,${result.stdout.toString('base64')}`;
}
for (const eventName of ['ADMIN_COMPLETED']) {
  const event = eventByName.get(eventName);
  if (!event || !Number.isFinite(event.at_seconds) || !/^[0-9a-f]{64}$/.test(event.frame_sha256)) {
    throw new Error(`execution frame is missing: ${eventName}`);
  }
  const result = spawnSync(process.env.PF07_FFMPEG_PATH || '/usr/bin/ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-i', videoPath, '-ss', String(event.at_seconds),
    '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-',
  ], { maxBuffer: 32 * 1024 * 1024 });
  if (result.status !== 0 || sha256(result.stdout) !== event.frame_sha256) {
    throw new Error(`execution frame commitment failed: ${eventName}`);
  }
  frames[eventName] = `data:image/png;base64,${result.stdout.toString('base64')}`;
}
const recoveryVideo = proof.videos?.['recovery-clip.mp4'];
const recoveryEventByName = new Map((recoveryVideo?.timeline || []).map((event) => [event.event, event]));
for (const eventName of ['FAILED', 'RECOVERED']) {
  const event = recoveryEventByName.get(eventName);
  if (!event || !Number.isFinite(event.at_seconds) || !/^[0-9a-f]{64}$/.test(event.frame_sha256)) {
    throw new Error(`recovery frame is missing: ${eventName}`);
  }
  const result = spawnSync(process.env.PF07_FFMPEG_PATH || '/usr/bin/ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-i', recoveryVideoPath, '-ss', String(event.at_seconds),
    '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-',
  ], { maxBuffer: 32 * 1024 * 1024 });
  if (result.status !== 0 || sha256(result.stdout) !== event.frame_sha256) {
    throw new Error(`recovery frame commitment failed: ${eventName}`);
  }
  frames[eventName] = `data:image/png;base64,${result.stdout.toString('base64')}`;
}

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PF07_CHROME_PATH || '/usr/bin/google-chrome',
});
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 1350 }, deviceScaleFactor: 1 });
  await page.setContent(`<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; width: 1200px; height: 1350px; overflow: hidden; }
  body { background: #f3f0e7; color: #171714; font-family: "Noto Sans KR", "DejaVu Sans", sans-serif; }
  main { height: 100%; padding: 46px; display: grid; grid-template-rows: auto 520px 420px 94px; gap: 22px; }
  .eyebrow { margin: 0 0 15px; font: 700 17px/1.2 "DejaVu Sans Mono", monospace; letter-spacing: .12em; }
  h1 { margin: 0; max-width: 1040px; font-size: 56px; line-height: 1.08; letter-spacing: -.045em; }
  h1 em { color: #d65b31; font-style: normal; border-bottom: 2px solid #171714; }
  .lead { margin: 17px 0 0; font-size: 22px; line-height: 1.5; }
  .frame { position: relative; overflow: hidden; border: 1px solid #171714; background: #fff; }
  .frame img { width: 100%; height: 100%; display: block; object-fit: cover; object-position: top left; }
  .frame.wide img { object-position: top center; }
  .tag { position: absolute; top: 16px; left: 16px; z-index: 2; padding: 9px 12px; border: 1px solid #171714; background: #d65b31; color: #fff; font: 800 14px/1 "DejaVu Sans Mono", monospace; letter-spacing: .07em; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; min-height: 0; }
  .grid .frame img { object-position: top center; }
  footer { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid #171714; background: #171714; gap: 1px; }
  footer div { display: flex; align-items: center; padding: 15px 18px; background: #fff; font-size: 17px; font-weight: 750; }
  footer div:nth-child(1) { background: #9a9a6a; }
  footer div:nth-child(3) { background: #d65b31; color: #fff; }
</style></head><body><main>
  <header>
    <p class="eyebrow">01 / REAL STOREFRONT EXECUTION</p>
    <h1>설명용 화면이 아니라,<br><em>실제 주문 흐름</em>입니다.</h1>
    <p class="lead">검증된 ${Math.round(video.duration_seconds)}초 연속 영상의 같은 바이트에서 home · product · 합성 checkout 프레임을 추출했습니다.</p>
  </header>
  <section class="frame wide"><span class="tag">LIVE HOME</span><img src="${frames.LIVE_STOREFRONT}" alt=""></section>
  <section class="grid">
    <div class="frame"><span class="tag">ACTUAL PRODUCT</span><img src="${frames.PRODUCT_SELECTED}" alt=""></div>
    <div class="frame"><span class="tag">SYNTHETIC CHECKOUT</span><img src="${frames.CHECKOUT_INPUT}" alt=""></div>
  </section>
  <footer><div>실제 WooCommerce UI</div><div>합성 입력 · 비금전 주문</div><div>같은 주문이 outbox worker로 연결</div></footer>
</main></body></html>`, { waitUntil: 'load' });
  await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
  await page.screenshot({ path: outputPath, type: 'png' });

  await page.setViewportSize({ width: 1200, height: 1200 });
  await page.setContent(`<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; width: 1200px; height: 1200px; overflow: hidden; }
  body { background: #f3f0e7; color: #171714; font-family: "Noto Sans KR", "DejaVu Sans", sans-serif; }
  main { height: 100%; padding: 44px; display: grid; grid-template-rows: auto 710px 116px; gap: 22px; }
  .eyebrow { margin: 0 0 12px; font: 800 17px/1.2 "DejaVu Sans Mono", monospace; letter-spacing: .12em; }
  h1 { margin: 0; font-size: 52px; line-height: 1.09; letter-spacing: -.045em; }
  h1 em { color: #d65b31; font-style: normal; border-bottom: 2px solid #171714; }
  .frame { position: relative; overflow: hidden; border: 1px solid #171714; background: #fff; }
  .frame img { width: 100%; height: 100%; display: block; object-fit: cover; object-position: top left; }
  .tag { position: absolute; top: 16px; left: 16px; z-index: 2; padding: 9px 12px; border: 1px solid #171714; background: #d65b31; color: #fff; font: 800 14px/1 "DejaVu Sans Mono", monospace; letter-spacing: .07em; }
  footer { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid #171714; background: #171714; gap: 1px; }
  footer div { display: grid; align-content: center; padding: 13px 16px; background: #fff; }
  footer div:nth-child(1) { background: #9a9a6a; }
  footer div:nth-child(3) { background: #e6dfcf; }
  footer div:nth-child(4) { background: #d65b31; color: #fff; }
  strong { font: 850 30px/1 "DejaVu Sans", sans-serif; }
  span { margin-top: 8px; font-size: 14px; font-weight: 750; }
</style></head><body><main>
  <header>
    <p class="eyebrow">PF07 / WOO ORDEROPS</p>
    <h1>실제 주문은 흘리고,<br><em>복구 근거</em>는 남깁니다.</h1>
  </header>
  <section class="frame"><span class="tag">LIVE STOREFRONT</span><img src="${frames.LIVE_STOREFRONT}" alt=""></section>
  <footer>
    <div><strong>4</strong><span>주문 이벤트</span></div>
    <div><strong>6</strong><span>자동 시도 상한</span></div>
    <div><strong>1</strong><span>주문별 실행 lease</span></div>
    <div><strong>HMAC</strong><span>원문 바이트 서명</span></div>
  </footer>
</main></body></html>`, { waitUntil: 'load' });
  await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
  await page.screenshot({ path: mainOutputPath, type: 'png' });

  await page.setViewportSize({ width: 1200, height: 1350 });
  await page.setContent(`<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; width: 1200px; height: 1350px; overflow: hidden; }
  body { background: #f3f0e7; color: #171714; font-family: "Noto Sans KR", "DejaVu Sans", sans-serif; }
  main { height: 100%; padding: 46px; display: grid; grid-template-rows: auto 580px 1fr; gap: 28px; }
  .eyebrow { margin: 0 0 14px; font: 800 17px/1.2 "DejaVu Sans Mono", monospace; letter-spacing: .13em; }
  h1 { margin: 0; max-width: 1040px; font-size: 58px; line-height: 1.06; letter-spacing: -.05em; }
  h1 em { color: #d65b31; font-style: normal; }
  .frame { position: relative; overflow: hidden; border: 1px solid #171714; background: #fff; }
  .frame img { width: 100%; height: 100%; display: block; object-fit: cover; object-position: top center; }
  .frame b { position: absolute; top: 16px; left: 16px; padding: 9px 12px; background: #d65b31; color: #fff; border: 1px solid #171714; font: 800 14px/1 "DejaVu Sans Mono", monospace; letter-spacing: .08em; }
  .flow { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid #171714; background: #171714; gap: 1px; }
  .step { min-width: 0; padding: 24px 20px; background: #fff; display: grid; align-content: space-between; }
  .step:nth-child(2) { background: #e6dfcf; }
  .step:nth-child(3) { background: #9a9a6a; }
  .step:nth-child(4) { background: #171714; color: #f3f0e7; }
  .step small { font: 800 14px/1 "DejaVu Sans Mono", monospace; letter-spacing: .09em; }
  .step strong { margin-top: 46px; font-size: 27px; line-height: 1.1; letter-spacing: -.035em; }
  .step span { margin-top: 14px; font-size: 15px; line-height: 1.45; }
</style></head><body><main>
  <header>
    <p class="eyebrow">02 / DELIVERY PATH</p>
    <h1>화면에서 끝나지 않고,<br><em>운영 기록</em>까지 이어집니다.</h1>
  </header>
  <section class="frame"><b>ACTUAL ADMIN · COMPLETED</b><img src="${frames.ADMIN_COMPLETED}" alt=""></section>
  <section class="flow">
    <article class="step"><small>01 / ORDER</small><strong>WooCommerce</strong><span>합성 주문과 원문 이벤트를 생성</span></article>
    <article class="step"><small>02 / RECORD</small><strong>Outbox</strong><span>전달 전에 상태와 payload를 보존</span></article>
    <article class="step"><small>03 / RUN</small><strong>Worker</strong><span>lease · retry · HMAC 검증으로 처리</span></article>
    <article class="step"><small>04 / RESULT</small><strong>CRM + Slack</strong><span>같은 correlation으로 결과를 추적</span></article>
  </section>
</main></body></html>`, { waitUntil: 'load' });
  await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
  await page.screenshot({ path: flowOutputPath, type: 'png' });

  await page.setContent(`<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; width: 1200px; height: 1350px; overflow: hidden; }
  body { background: #171714; color: #f3f0e7; font-family: "Noto Sans KR", "DejaVu Sans", sans-serif; }
  main { height: 100%; padding: 46px; display: grid; grid-template-rows: auto 420px 420px 92px; gap: 22px; }
  .eyebrow { margin: 0 0 14px; color: #d65b31; font: 800 17px/1.2 "DejaVu Sans Mono", monospace; letter-spacing: .13em; }
  h1 { margin: 0; max-width: 1040px; font-size: 58px; line-height: 1.06; letter-spacing: -.05em; }
  h1 em { color: #d65b31; font-style: normal; }
  figure { position: relative; margin: 0; overflow: hidden; border: 1px solid #f3f0e7; background: #fff; }
  figure img { width: 100%; height: 100%; display: block; object-fit: cover; object-position: top center; }
  figcaption { position: absolute; inset: auto 0 0 0; min-height: 68px; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 14px 18px; background: rgba(243,240,231,.97); color: #171714; border-top: 1px solid #171714; }
  figcaption strong { font-size: 20px; letter-spacing: -.02em; }
  figcaption span { font: 800 13px/1 "DejaVu Sans Mono", monospace; letter-spacing: .08em; }
  .failed figcaption span { color: #d65b31; }
  .recovered { border-color: #9a9a6a; }
  .recovered figcaption { background: rgba(154,154,106,.97); }
  footer { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid #f3f0e7; background: #f3f0e7; gap: 1px; }
  footer div { display: grid; place-items: center; padding: 12px; color: #171714; background: #f3f0e7; font-weight: 800; }
  footer div:nth-child(2) { background: #d65b31; color: #fff; }
  footer div:nth-child(3) { background: #9a9a6a; }
</style></head><body><main>
  <header>
    <p class="eyebrow">03 / RECOVERY, OBSERVED</p>
    <h1>실패를 숨기지 않고,<br>같은 row를 <em>복구</em>합니다.</h1>
  </header>
  <figure class="failed"><img src="${frames.FAILED}" alt=""><figcaption><strong>terminal failure · 수동 재시도 가능</strong><span>FAILED</span></figcaption></figure>
  <figure class="recovered"><img src="${frames.RECOVERED}" alt=""><figcaption><strong>같은 outbox row · HTTP 200</strong><span>RECOVERED</span></figcaption></figure>
  <footer><div>자동 시도 상한</div><div>관리자 수동 재시도</div><div>상태 비회귀</div></footer>
</main></body></html>`, { waitUntil: 'load' });
  await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
  await page.screenshot({ path: recoveryOutputPath, type: 'png' });
} finally {
  await browser.close();
}

const outputBytes = await fsp.readFile(outputPath);
const mainOutputBytes = await fsp.readFile(mainOutputPath);
const flowOutputBytes = await fsp.readFile(flowOutputPath);
const recoveryOutputBytes = await fsp.readFile(recoveryOutputPath);
process.stdout.write(`${JSON.stringify({
  files: {
    [path.basename(mainOutputPath)]: {
      sha256: sha256(mainOutputBytes),
      width: mainOutputBytes.readUInt32BE(16),
      height: mainOutputBytes.readUInt32BE(20),
    },
    [path.basename(outputPath)]: {
      sha256: sha256(outputBytes),
      width: outputBytes.readUInt32BE(16),
      height: outputBytes.readUInt32BE(20),
    },
    [path.basename(flowOutputPath)]: {
      sha256: sha256(flowOutputBytes),
      width: flowOutputBytes.readUInt32BE(16),
      height: flowOutputBytes.readUInt32BE(20),
    },
    [path.basename(recoveryOutputPath)]: {
      sha256: sha256(recoveryOutputBytes),
      width: recoveryOutputBytes.readUInt32BE(16),
      height: recoveryOutputBytes.readUInt32BE(20),
    },
  },
  source_video_sha256: video.sha256,
  source_event_frame_sha256: Object.fromEntries(requiredEvents.map((name) => [name, eventByName.get(name).frame_sha256])),
})}\n`);
