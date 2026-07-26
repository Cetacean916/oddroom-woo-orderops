#!/usr/bin/env node

import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import crypto from "node:crypto";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const packageRoot = process.env.PF07_PACKAGE_ROOT
  ? path.resolve(process.env.PF07_PACKAGE_ROOT)
  : null;
const outputRoot = process.argv[2] ? path.resolve(process.argv[2]) : null;
if (!packageRoot || !outputRoot) {
  throw new Error("usage: PF07_PACKAGE_ROOT=PACKAGE scripts/record-guided-service-tour.mjs OUTPUT_DIRECTORY");
}

const launcher = path.join(packageRoot, "pf07");
const hubLauncher = path.join(packageRoot, "launcher", "bin", "pf07-hub");
const runtimeEnvPath = path.join(packageRoot, ".pf07", "runtime.env");
const artifactManifestPath = path.join(packageRoot, "ARTIFACT-MANIFEST.json");
const chrome = process.env.PF07_CHROME_PATH || "/usr/bin/google-chrome";
const ffmpeg = process.env.PF07_FFMPEG_PATH || "/usr/bin/ffmpeg";
for (const required of [launcher, hubLauncher, runtimeEnvPath, artifactManifestPath, chrome, ffmpeg]) {
  await fsp.access(required, fs.constants.R_OK);
}
await fsp.mkdir(outputRoot, { recursive: true });

const artifactManifestBytes = await fsp.readFile(artifactManifestPath);
const artifactManifest = JSON.parse(artifactManifestBytes.toString("utf8"));
if (
  artifactManifest.schema !== "pf07.artifact-manifest.v1"
  || artifactManifest.package_version !== "1.0.6"
  || typeof artifactManifest.artifact_id !== "string"
  || typeof artifactManifest.build_id !== "string"
) {
  throw new Error("the guided tour requires an exact PF07 1.0.6 distribution manifest");
}
const artifactManifestSha256 = crypto
  .createHash("sha256")
  .update(artifactManifestBytes)
  .digest("hex");

const runtime = Object.fromEntries(
  (await fsp.readFile(runtimeEnvPath, "utf8"))
    .split(/\r?\n/)
    .filter((line) => line && !line.startsWith("#") && line.includes("="))
    .map((line) => {
      const separator = line.indexOf("=");
      return [line.slice(0, separator), line.slice(separator + 1)];
    }),
);
const baseUrl = `http://127.0.0.1:${runtime.PF07_WORDPRESS_PORT}`;
const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd || packageRoot,
      env: options.env || process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`${path.basename(command)} timed out`));
    }, options.timeout || 900000);
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      const output = Buffer.concat(stdout).toString("utf8");
      const errorOutput = Buffer.concat(stderr).toString("utf8");
      if (code === 0) resolve({ stdout: output, stderr: errorOutput });
      else reject(new Error(`${path.basename(command)} exited ${code}: ${errorOutput.trim()}`));
    });
  });
}

async function packageCommand(...args) {
  return run(launcher, args, { timeout: 900000 });
}

async function startHub() {
  const port = Number(process.env.PF07_GUIDED_HUB_PORT || "19076");
  const child = spawn(hubLauncher, ["--port", String(port), "--no-browser"], {
    cwd: packageRoot,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
  child.stderr.on("data", (chunk) => { stderr += chunk.toString("utf8"); });
  const deadline = Date.now() + 15000;
  while (!stdout.includes("PF07_HUB_URL=") && child.exitCode === null && Date.now() < deadline) {
    await wait(100);
  }
  if (!stdout.includes("PF07_HUB_URL=")) {
    child.kill("SIGTERM");
    throw new Error(`hub did not start: ${stderr.trim()}`);
  }
  return { child, url: `http://127.0.0.1:${port}/` };
}

async function stopHub(hub) {
  if (hub.child.exitCode !== null) return;
  hub.child.kill("SIGTERM");
  await new Promise((resolve) => hub.child.once("close", resolve));
}

async function overlay(page, eyebrow, title, detail) {
  await page.evaluate(({ eyebrow, title, detail }) => {
    document.querySelector("#offset-tour-caption")?.remove();
    const root = document.createElement("aside");
    root.id = "offset-tour-caption";
    root.setAttribute("aria-hidden", "true");
    Object.assign(root.style, {
      position: "fixed",
      zIndex: "2147483647",
      top: "20px",
      right: "20px",
      width: "min(390px, calc(100vw - 40px))",
      padding: "17px 19px 18px",
      color: "#171714",
      background: "rgba(244, 241, 232, .96)",
      border: "1px solid rgba(23, 23, 20, .8)",
      boxShadow: "0 16px 38px rgba(23, 23, 20, .13)",
      fontFamily: '"Noto Sans KR", "Pretendard", Arial, sans-serif',
      pointerEvents: "none",
    });
    const label = document.createElement("span");
    label.textContent = eyebrow;
    Object.assign(label.style, {
      display: "block",
      color: "#a84427",
      fontSize: "11px",
      fontWeight: "800",
      letterSpacing: ".16em",
    });
    const heading = document.createElement("strong");
    heading.textContent = title;
    Object.assign(heading.style, {
      display: "block",
      marginTop: "8px",
      fontSize: "22px",
      lineHeight: "1.25",
      letterSpacing: "-.025em",
      wordBreak: "keep-all",
    });
    const description = document.createElement("span");
    description.textContent = detail;
    Object.assign(description.style, {
      display: "block",
      marginTop: "7px",
      color: "#55564f",
      fontSize: "13px",
      lineHeight: "1.55",
      wordBreak: "keep-all",
    });
    root.append(label, heading, description);
    document.documentElement.append(root);
  }, { eyebrow, title, detail });
  await wait(1800);
}

async function showPageFromTopToBottom(page, pause = 1200) {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "auto" }));
  await wait(900);
  const positions = await page.evaluate(() => {
    const maximum = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    const step = Math.max(540, Math.round(window.innerHeight * 0.72));
    const values = [];
    for (let position = step; position < maximum; position += step) values.push(position);
    if (maximum > 0) values.push(maximum);
    return values;
  });
  for (const position of positions) {
    await page.evaluate((top) => window.scrollTo({ top, behavior: "smooth" }), position);
    await wait(pause);
  }
  await wait(700);
}

async function clickAndSettle(locator, page) {
  await locator.scrollIntoViewIfNeeded();
  await locator.hover();
  await wait(350);
  await Promise.all([
    page.waitForLoadState("domcontentloaded"),
    locator.click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
  await wait(800);
}

function chapter(markers, startedAt, label) {
  markers.push({
    seconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
    label,
  });
}

function timestamp(seconds) {
  const milliseconds = Math.max(0, Math.round(seconds * 1000));
  const hours = Math.floor(milliseconds / 3600000);
  const minutes = Math.floor((milliseconds % 3600000) / 60000);
  const secs = Math.floor((milliseconds % 60000) / 1000);
  const ms = milliseconds % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}

async function writeCaptions(target, markers, totalSeconds) {
  const cues = markers.map((marker, index) => {
    const end = index + 1 < markers.length ? markers[index + 1].seconds : totalSeconds;
    return `${index + 1}\n${timestamp(marker.seconds)} --> ${timestamp(Math.max(marker.seconds + 1, end))}\n${marker.label}\n`;
  });
  await fsp.writeFile(target, `WEBVTT\n\n${cues.join("\n")}`, "utf8");
}

async function recordLocale(browser, hub, locale) {
  const isKorean = locale === "ko_KR";
  const slug = isKorean ? "ko" : "en";
  const target = path.join(outputRoot, `${slug}-guided-overview.mp4`);
  const poster = path.join(outputRoot, `${slug}-guided-overview.png`);
  const captions = path.join(outputRoot, `${slug}-guided-overview.vtt`);
  const timeline = path.join(outputRoot, `${slug}-guided-overview.timeline.json`);
  for (const file of [target, poster, captions, timeline]) {
    if (fs.existsSync(file)) throw new Error(`refusing to replace ${file}`);
  }

  await packageCommand("mode", "DEMO_MODE");
  await packageCommand("language", locale);
  await packageCommand("reset-demo", "--confirm=RESET PF07 DEMO");

  const rawVideoDirectory = path.join(outputRoot, `.raw-${slug}-${Date.now()}`);
  await fsp.mkdir(rawVideoDirectory, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: rawVideoDirectory,
      size: { width: 1440, height: 900 },
    },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(45000);
  const video = page.video();
  const startedAt = Date.now();
  const markers = [];
  const words = isKorean ? {
    hub: ["SERVICE READY", "상점과 주문 운영을 한곳에서 시작합니다.", "고객용 상점과 운영자용 주문 관리는 서로 분리된 채 함께 준비됩니다."],
    store: ["CUSTOMER EXPERIENCE", "고객이 처음 만나는 상점입니다.", "첫인상부터 제품 정보와 주문 안내까지 전체 구성을 천천히 살펴봅니다."],
    catalog: ["PRODUCT DISCOVERY", "제품을 비교하고 선택합니다.", "컬렉션과 각 제품의 정보는 구매 흐름에만 집중하도록 구성했습니다."],
    product: ["PRODUCT DETAIL", "선택한 제품을 자세히 확인합니다.", "이미지와 옵션, 설명을 확인한 뒤 장바구니로 이어집니다."],
    cart: ["ORDER REVIEW", "선택한 제품을 주문 전에 확인합니다.", "실제 결제 없이 0원 데모 주문으로 구매 과정을 체험합니다."],
    checkout: ["SAFE DEMO CHECKOUT", "개인정보 없이 주문을 마칩니다.", "미리 준비된 예시 정보만 사용하며 계정·결제·배송 정보는 받지 않습니다."],
    complete: ["CUSTOMER JOURNEY COMPLETE", "고객의 구매 과정은 여기서 끝납니다.", "완료된 주문에서 운영에 필요한 정보만 별도의 관리 흐름으로 이어집니다."],
    operator: ["OPERATOR EXPERIENCE", "이제 운영자가 주문을 확인합니다.", "고객용 상점과 완전히 분리된 환경에서 접수 상태와 처리 흐름을 살펴봅니다."],
  } : {
    hub: ["SERVICE READY", "Start the store and order operation in one place.", "The customer store and operator tools are prepared together while remaining separate experiences."],
    store: ["CUSTOMER EXPERIENCE", "This is the store customers meet first.", "Move deliberately through its first impression, product story, and ordering guidance."],
    catalog: ["PRODUCT DISCOVERY", "Compare the collection and choose a product.", "The catalog and product information keep the customer focused on buying."],
    product: ["PRODUCT DETAIL", "Review the selected product in full.", "Images, options, and details lead naturally into the cart."],
    cart: ["ORDER REVIEW", "Confirm the selection before ordering.", "The 0 KRW demo completes the journey without a real payment."],
    checkout: ["SAFE DEMO CHECKOUT", "Complete the order without personal data.", "Only prepared example details are used; no account, payment, or delivery data is collected."],
    complete: ["CUSTOMER JOURNEY COMPLETE", "The customer journey ends here.", "Only the information needed to operate the completed order continues into a separate workflow."],
    operator: ["OPERATOR EXPERIENCE", "The operator now receives the order.", "A fully separate workspace shows order status and the next operational action."],
  };

  chapter(markers, startedAt, words.hub[1]);
  await page.goto(hub.url, { waitUntil: "networkidle" });
  await overlay(page, ...words.hub);
  await showPageFromTopToBottom(page, 950);

  chapter(markers, startedAt, words.store[1]);
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await overlay(page, ...words.store);
  await page.screenshot({ path: poster });
  await showPageFromTopToBottom(page, 1250);

  chapter(markers, startedAt, words.catalog[1]);
  await page.goto(`${baseUrl}/shop/`, { waitUntil: "networkidle" });
  await overlay(page, ...words.catalog);
  await showPageFromTopToBottom(page, 1200);

  chapter(markers, startedAt, words.product[1]);
  const product = page.locator('a[href*="/product/offset-dock/"]').first();
  await clickAndSettle(product, page);
  await overlay(page, ...words.product);
  await showPageFromTopToBottom(page, 1200);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await wait(800);
  await page.locator("button.single_add_to_cart_button").click();
  await wait(1000);

  chapter(markers, startedAt, words.cart[1]);
  await page.goto(`${baseUrl}/cart/`, { waitUntil: "networkidle" });
  await overlay(page, ...words.cart);
  await showPageFromTopToBottom(page, 1000);

  chapter(markers, startedAt, words.checkout[1]);
  await page.goto(`${baseUrl}/checkout/`, { waitUntil: "networkidle" });
  await page.locator("#billing_email").waitFor();
  await overlay(page, ...words.checkout);
  await showPageFromTopToBottom(page, 1100);
  const placeOrder = page.locator("#place_order");
  await placeOrder.scrollIntoViewIfNeeded();
  await wait(700);
  await Promise.all([
    page.waitForURL(/order-received/, { timeout: 60000 }),
    placeOrder.click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});

  chapter(markers, startedAt, words.complete[1]);
  await overlay(page, ...words.complete);
  await showPageFromTopToBottom(page, 1100);
  await wait(1200);

  chapter(markers, startedAt, words.operator[1]);
  await page.goto(`${baseUrl}/wp-login.php`, { waitUntil: "networkidle" });
  await page.locator("#user_login").fill(runtime.PF07_ADMIN_USER);
  await page.locator("#user_pass").fill(runtime.PF07_ADMIN_PASSWORD);
  await Promise.all([
    page.waitForLoadState("domcontentloaded"),
    page.locator("#wp-submit").click(),
  ]);
  await page.goto(`${baseUrl}/wp-admin/admin.php?page=oddroom-orderops`, { waitUntil: "networkidle" });
  await overlay(page, ...words.operator);
  await showPageFromTopToBottom(page, 1350);
  await wait(1800);

  const totalSeconds = Number(((Date.now() - startedAt) / 1000).toFixed(3));
  await context.close();
  const rawVideo = await video.path();
  await run(ffmpeg, [
    "-hide_banner", "-loglevel", "error", "-y",
    "-i", rawVideo,
    "-an",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    "-map_metadata", "-1",
    target,
  ], { timeout: 900000 });
  await writeCaptions(captions, markers, totalSeconds);
  await fsp.writeFile(timeline, `${JSON.stringify({
    schema: "pf07.guided-service-tour.v1",
    package_version: artifactManifest.package_version,
    artifact_id: artifactManifest.artifact_id,
    build_id: artifactManifest.build_id,
    artifact_manifest_sha256: artifactManifestSha256,
    locale,
    viewport: { width: 1440, height: 900 },
    full_content_view: true,
    time_compression: false,
    total_seconds: totalSeconds,
    chapters: markers,
  }, null, 2)}\n`, "utf8");
  await fsp.rm(rawVideoDirectory, { recursive: true, force: true });
}

const hub = await startHub();
const browser = await chromium.launch({
  headless: true,
  executablePath: chrome,
  args: ["--disable-dev-shm-usage", "--hide-scrollbars"],
});
try {
  await recordLocale(browser, hub, "ko_KR");
  await recordLocale(browser, hub, "en_US");
} finally {
  await browser.close();
  await stopHub(hub);
  await packageCommand("language", "ko_KR").catch(() => {});
}
