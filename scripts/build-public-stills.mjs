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
const proofPath = path.join(mediaRoot, 'execution-proof.json');
const mainOutputPath = path.join(outputRoot, 'main-image.png');
const outputPath = path.join(outputRoot, 'detail-01-overview.png');
for (const required of [videoPath, proofPath]) await fsp.access(required, fs.constants.R_OK);
await fsp.mkdir(outputRoot, { recursive: true });
if ([mainOutputPath, outputPath].some((target) => fs.existsSync(target))) {
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
  body { background: #f8f1e5; color: #090909; font-family: "Noto Sans KR", "DejaVu Sans", sans-serif; }
  main { height: 100%; padding: 46px; display: grid; grid-template-rows: auto 520px 420px 94px; gap: 22px; }
  .eyebrow { margin: 0 0 15px; font: 700 17px/1.2 "DejaVu Sans Mono", monospace; letter-spacing: .12em; }
  h1 { margin: 0; max-width: 1040px; font-size: 56px; line-height: 1.08; letter-spacing: -.045em; }
  h1 em { color: #315dff; font-style: normal; border-bottom: 7px solid #ff4e7f; }
  .lead { margin: 17px 0 0; font-size: 22px; line-height: 1.5; }
  .frame { position: relative; overflow: hidden; border: 4px solid #090909; background: #fff; box-shadow: 12px 12px 0 #090909; }
  .frame img { width: 100%; height: 100%; display: block; object-fit: cover; object-position: top left; }
  .frame.wide img { object-position: top center; }
  .tag { position: absolute; top: 16px; left: 16px; z-index: 2; padding: 9px 12px; border: 2px solid #090909; background: #d8ff3f; font: 800 14px/1 "DejaVu Sans Mono", monospace; letter-spacing: .07em; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; min-height: 0; }
  .grid .frame img { object-position: top center; }
  footer { display: grid; grid-template-columns: repeat(3, 1fr); border: 3px solid #090909; background: #090909; gap: 3px; }
  footer div { display: flex; align-items: center; padding: 15px 18px; background: #fff; font-size: 17px; font-weight: 750; }
  footer div:nth-child(1) { background: #d8ff3f; }
  footer div:nth-child(3) { background: #315dff; color: #fff; }
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
  body { background: #f8f1e5; color: #090909; font-family: "Noto Sans KR", "DejaVu Sans", sans-serif; }
  main { height: 100%; padding: 44px; display: grid; grid-template-rows: auto 710px 116px; gap: 22px; }
  .eyebrow { margin: 0 0 12px; font: 800 17px/1.2 "DejaVu Sans Mono", monospace; letter-spacing: .12em; }
  h1 { margin: 0; font-size: 52px; line-height: 1.09; letter-spacing: -.045em; }
  h1 em { color: #315dff; font-style: normal; border-bottom: 7px solid #ff4e7f; }
  .frame { position: relative; overflow: hidden; border: 4px solid #090909; background: #fff; box-shadow: 12px 12px 0 #090909; }
  .frame img { width: 100%; height: 100%; display: block; object-fit: cover; object-position: top left; }
  .tag { position: absolute; top: 16px; left: 16px; z-index: 2; padding: 9px 12px; border: 2px solid #090909; background: #d8ff3f; font: 800 14px/1 "DejaVu Sans Mono", monospace; letter-spacing: .07em; }
  footer { display: grid; grid-template-columns: repeat(4, 1fr); border: 3px solid #090909; background: #090909; gap: 3px; }
  footer div { display: grid; align-content: center; padding: 13px 16px; background: #fff; }
  footer div:nth-child(1) { background: #d8ff3f; }
  footer div:nth-child(3) { background: #ff4e7f; }
  footer div:nth-child(4) { background: #315dff; color: #fff; }
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
} finally {
  await browser.close();
}

const outputBytes = await fsp.readFile(outputPath);
const mainOutputBytes = await fsp.readFile(mainOutputPath);
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
  },
  source_video_sha256: video.sha256,
  source_event_frame_sha256: Object.fromEntries(requiredEvents.map((name) => [name, eventByName.get(name).frame_sha256])),
})}\n`);
