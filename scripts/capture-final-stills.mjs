#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { spawn, spawnSync } from "node:child_process";
import { chromium } from "playwright";

const packageRoot = process.argv[2] ? path.resolve(process.argv[2]) : null;
const assetRoot = process.argv[3] ? path.resolve(process.argv[3]) : null;
const buildRoot = process.argv[4] ? path.resolve(process.argv[4]) : null;
if (!packageRoot || !assetRoot || !buildRoot) {
  throw new Error("usage: scripts/capture-final-stills.mjs FINAL_LINUX_PACKAGE ASSET_ROOT FINAL_BUILD_ROOT");
}

const outputRoot = path.join(assetRoot, "public-assets", "own-ui-captures", "after-completion");
const runtimeEnvPath = path.join(packageRoot, ".pf07", "runtime.env");
const artifactSetPath = path.join(buildRoot, "ARTIFACT-MANIFEST.json");
const launcherPath = path.join(packageRoot, "pf07");
const hubPath = path.join(packageRoot, "launcher", "bin", "pf07-hub");
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

for (const required of [runtimeEnvPath, artifactSetPath, launcherPath, hubPath]) {
  await fsp.access(required, fs.constants.R_OK);
}
await fsp.mkdir(outputRoot, { recursive: true });

const runtime = Object.fromEntries(
  (await fsp.readFile(runtimeEnvPath, "utf8"))
    .split(/\r?\n/)
    .filter((line) => line && !line.startsWith("#") && line.includes("="))
    .map((line) => {
      const separator = line.indexOf("=");
      return [line.slice(0, separator), line.slice(separator + 1)];
    }),
);
for (const required of ["PF07_WORDPRESS_PORT", "PF07_ADMIN_USER", "PF07_ADMIN_PASSWORD"]) {
  if (!runtime[required]) throw new Error(`missing final package runtime value: ${required}`);
}

const artifactSetBytes = await fsp.readFile(artifactSetPath);
const artifactSet = JSON.parse(artifactSetBytes.toString("utf8"));
if (artifactSet.schema !== "pf07.artifact-set-manifest.v1"
  || artifactSet.package_version !== "1.0.1"
  || artifactSet.build_id !== "pf07-build-13003091bee3a5201dba"
  || artifactSet.artifact_count !== 5) {
  throw new Error("final artifact-set identity failed");
}
const artifactById = new Map(artifactSet.artifacts.map((artifact) => [artifact.artifact_id, artifact]));
for (const id of ["pf07-windows-x64", "pf07-windows-kvm-test-kit", "pf07-macos-universal", "pf07-linux-x86_64", "pf07-linux-server"]) {
  const artifact = artifactById.get(id);
  if (!artifact || sha256(await fsp.readFile(path.join(buildRoot, artifact.filename))) !== artifact.sha256) {
    throw new Error(`final artifact byte identity failed: ${id}`);
  }
}

const expectedOutputs = [
  "CASE-005_storefront-desktop_ko.png",
  "CASE-005_storefront-shop-desktop_ko.png",
  "CASE-006_storefront-mobile_ko.png",
  "CASE-007_storefront-desktop_en.png",
  "CASE-007_storefront-mobile_en.png",
  "CASE-007_storefront-shop-desktop_en.png",
  "CASE-008_variable-product_ko.png",
  "CASE-008_variable-product_en.png",
  "CASE-010_operator-console_ko.png",
  "CASE-010_operator-console_en.png",
  "CASE-009_cart_ko.png",
  "CASE-009_checkout_ko.png",
  "GUIDE-001_windows-download-start_ko.svg",
  "GUIDE-001_windows-download-start_en.svg",
  "GUIDE-002_windows-preflight-evidence_ko.svg",
  "GUIDE-002_windows-preflight-evidence_en.svg",
  "GUIDE-003_macos-download-first-launch_ko.svg",
  "GUIDE-003_macos-download-first-launch_en.svg",
  "GUIDE-004_macos-permission-runtime_ko.svg",
  "GUIDE-004_macos-permission-runtime_en.svg",
  "GUIDE-005_linux-install-run_ko.png",
  "GUIDE-005_linux-install-run_en.png",
];
if (process.env.PF07_CAPTURE_TUNNEL === "1") {
  expectedOutputs.push("GUIDE-008_https-tunnel_ko.png", "GUIDE-008_https-tunnel_en.png");
}
const resume = process.env.PF07_RESUME === "1";
for (const name of expectedOutputs) {
  if (!resume && fs.existsSync(path.join(outputRoot, name))) throw new Error(`refusing to replace accepted-looking output: ${name}`);
}

function checked(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? packageRoot,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    env: options.env ?? process.env,
  });
  if (result.status !== 0) throw new Error(`${path.basename(command)} failed: ${(result.stderr || result.stdout).trim()}`);
  return result.stdout;
}

const xmlEscape = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

async function writeGuide({ id, slug, language, eyebrow, title, subtitle, steps, artifact }) {
  const outputPath = path.join(outputRoot, `${id}_${slug}_${language}.svg`);
  if (resume && fs.existsSync(outputPath)) return;
  const symbolBytes = await fsp.readFile(path.join(packageRoot, "payload", "oddroom-orderops", "assets", "images", "brand", "symbol.svg"));
  const symbol = `data:image/svg+xml;base64,${symbolBytes.toString("base64")}`;
  const stepRows = steps.map((step, index) => {
    const y = 276 + index * 126;
    return `<g transform="translate(74 ${y})">
      <rect width="1292" height="100" rx="18" fill="#fff" stroke="#171a18" stroke-width="2"/>
      <rect width="92" height="100" rx="18" fill="${index === 0 ? "#d9e9d6" : "#eef1eb"}"/>
      <text x="46" y="62" text-anchor="middle" class="number">${String(index + 1).padStart(2, "0")}</text>
      <text x="122" y="46" class="step-title">${xmlEscape(step.title)}</text>
      <text x="122" y="74" class="step-copy">${xmlEscape(step.copy)}</text>
    </g>`;
  }).join("\n");
  const boundary = language === "ko"
    ? "산출물 기반 안내 · 실제 Windows/macOS 실행 화면이 아님"
    : "ARTIFACT-DRIVEN GUIDE · NOT A NATIVE WINDOWS/macOS EXECUTION SCREEN";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" viewBox="0 0 1440 900" role="img" aria-labelledby="title desc">
  <title id="title">${xmlEscape(title)}</title><desc id="desc">${xmlEscape(subtitle)} ${xmlEscape(boundary)}</desc>
  <style>
    text{font-family:"Noto Sans KR","DejaVu Sans",Arial,sans-serif;fill:#171a18}.eyebrow{font:700 17px "DejaVu Sans Mono",monospace;letter-spacing:2px;fill:#4b6452}.title{font-size:48px;font-weight:800;letter-spacing:-1.8px}.subtitle{font-size:19px;fill:#4f574f}.number{font:800 26px "DejaVu Sans Mono",monospace}.step-title{font-size:21px;font-weight:800}.step-copy{font-size:16px;fill:#4f574f}.meta{font:600 13px "DejaVu Sans Mono",monospace;fill:#4f574f}.boundary{font:700 14px "DejaVu Sans Mono",monospace;letter-spacing:.5px;fill:#7b4d3f}
  </style>
  <rect width="1440" height="900" fill="#f5f2e9"/><path d="M0 0h1440v16H0z" fill="#36513d"/>
  <image href="${symbol}" x="74" y="64" width="62" height="62"/>
  <text x="158" y="84" class="eyebrow">${xmlEscape(eyebrow)}</text>
  <text x="158" y="126" class="meta">${xmlEscape(artifact.filename)} · SHA-256 ${xmlEscape(artifact.sha256)}</text>
  <text x="74" y="196" class="title">${xmlEscape(title)}</text>
  <text x="74" y="232" class="subtitle">${xmlEscape(subtitle)}</text>
  ${stepRows}
  <rect x="74" y="804" width="1292" height="52" rx="14" fill="#f1e2dc" stroke="#9a6454"/>
  <text x="98" y="837" class="boundary">${xmlEscape(boundary)} · ${xmlEscape(artifact.tested_boundary)}</text>
  </svg>\n`;
  await fsp.writeFile(outputPath, svg, "utf8");
}

const windows = artifactById.get("pf07-windows-x64");
const kvm = artifactById.get("pf07-windows-kvm-test-kit");
const macos = artifactById.get("pf07-macos-universal");
await writeGuide({
  id: "GUIDE-001", slug: "windows-download-start", language: "ko", eyebrow: "WINDOWS BUYER PACKAGE / 1.0.1",
  title: "다운로드에서 실행 허브까지", subtitle: "최종 Windows x64 아카이브의 실제 파일명과 진입점을 따릅니다.", artifact: windows,
  steps: [
    { title: "아카이브 받기", copy: `${windows.filename}의 SHA-256을 확인합니다.` },
    { title: "새 폴더에 압축 해제", copy: "실행 중인 기존 폴더 위에 덮어쓰지 않습니다." },
    { title: "그래픽 진입점 실행", copy: "PF07-Launcher.exe를 열고 필요한 구성요소 안내를 완료합니다." },
    { title: "준비 상태 확인", copy: "허브에서 Ready 이후 Open Store와 Open Admin을 사용합니다." },
  ],
});
await writeGuide({
  id: "GUIDE-001", slug: "windows-download-start", language: "en", eyebrow: "WINDOWS BUYER PACKAGE / 1.0.1",
  title: "From download to launch hub", subtitle: "Follow the exact file names and entrypoints in the final Windows x64 artifact.", artifact: windows,
  steps: [
    { title: "Download the archive", copy: `Verify the SHA-256 of ${windows.filename}.` },
    { title: "Extract to a new folder", copy: "Never overwrite a package folder that is already running." },
    { title: "Open the graphical entrypoint", copy: "Run PF07-Launcher.exe and complete the prerequisite guidance." },
    { title: "Wait for Ready", copy: "Use Open Store and Open Admin only after the hub reports Ready." },
  ],
});
await writeGuide({
  id: "GUIDE-002", slug: "windows-preflight-evidence", language: "ko", eyebrow: "WINDOWS KVM TEST KIT / 1.0.1",
  title: "사전 점검에서 증거 내보내기까지", subtitle: "독립 KVM 테스트 키트와 구매자 패키지의 실제 제어를 순서대로 사용합니다.", artifact: kvm,
  steps: [
    { title: "테스트 키트 분리", copy: `${kvm.filename}을 구매자 패키지와 별도 폴더에 풉니다.` },
    { title: "GUI 우선 점검", copy: "RUN-KVM-TEST.cmd와 PF07-KVM-TEST.html의 번호 순서를 따릅니다." },
    { title: "실제 상태 확인", copy: "허브의 사전점검·상점·관리자·복구 동작을 직접 확인합니다." },
    { title: "기계 판독 증거", copy: "PF07-KVM-Evidence.ps1로 결과를 내보내고 비밀값 부재를 검사합니다." },
  ],
});
await writeGuide({
  id: "GUIDE-002", slug: "windows-preflight-evidence", language: "en", eyebrow: "WINDOWS KVM TEST KIT / 1.0.1",
  title: "Preflight, result, evidence", subtitle: "Use the real controls in the independent KVM kit and buyer package in order.", artifact: kvm,
  steps: [
    { title: "Keep the test kit separate", copy: `Extract ${kvm.filename} beside, not inside, the buyer package.` },
    { title: "Follow the GUI-first checklist", copy: "Use RUN-KVM-TEST.cmd and the numbered PF07-KVM-TEST.html steps." },
    { title: "Observe the real state", copy: "Check preflight, store, admin, and recovery through the package hub." },
    { title: "Export machine-readable evidence", copy: "Run PF07-KVM-Evidence.ps1 and verify that no secret is included." },
  ],
});
await writeGuide({
  id: "GUIDE-003", slug: "macos-download-first-launch", language: "ko", eyebrow: "macOS UNIVERSAL PACKAGE / 1.0.1",
  title: "Applications 배치와 최초 실행", subtitle: "최종 앱 번들의 실제 구조와 unsigned 첫 실행 경계를 정확히 안내합니다.", artifact: macos,
  steps: [
    { title: "아카이브 검증", copy: `${macos.filename}과 SHA-256을 확인합니다.` },
    { title: "앱 배치", copy: "PF07 Launcher.app을 Applications로 이동합니다." },
    { title: "최초 실행 허용", copy: "서명·공증되지 않은 앱의 Finder 열기 또는 개인정보 보호 안내를 따릅니다." },
    { title: "명령 폴백", copy: "필요하면 pf07.command 또는 ./pf07을 같은 추출본에서 사용합니다." },
  ],
});
await writeGuide({
  id: "GUIDE-003", slug: "macos-download-first-launch", language: "en", eyebrow: "macOS UNIVERSAL PACKAGE / 1.0.1",
  title: "Applications and first launch", subtitle: "Follow the exact app-bundle layout and unsigned first-launch boundary.", artifact: macos,
  steps: [
    { title: "Verify the archive", copy: `Check ${macos.filename} and its SHA-256.` },
    { title: "Place the app", copy: "Move PF07 Launcher.app to Applications." },
    { title: "Allow the first launch", copy: "Use Finder Open or the Privacy & Security guidance for the unsigned app." },
    { title: "Use the command fallback", copy: "Run pf07.command or ./pf07 from the same extraction if needed." },
  ],
});
await writeGuide({
  id: "GUIDE-004", slug: "macos-permission-runtime", language: "ko", eyebrow: "macOS RUNTIME PATH / 0 KRW",
  title: "권한과 컨테이너 런타임 연결", subtitle: "앱 진입점은 동일한 패키지 허브와 한 개의 비즈니스 런타임을 사용합니다.", artifact: macos,
  steps: [
    { title: "Rancher Desktop 준비", copy: "Apple Silicon 또는 Intel용 유지보수 설치본과 Moby 엔진을 사용합니다." },
    { title: "필수 권한만 허용", copy: "앱 실행과 컨테이너 런타임 연결에 표시되는 OS 안내만 따릅니다." },
    { title: "허브에서 재검사", copy: "구성요소 설치·재로그인 뒤 앱을 다시 열어 사전점검을 재개합니다." },
    { title: "같은 런타임 유지", copy: "언어 전환·중지·재시작은 새 비즈니스 상태를 만들지 않습니다." },
  ],
});
await writeGuide({
  id: "GUIDE-004", slug: "macos-permission-runtime", language: "en", eyebrow: "macOS RUNTIME PATH / 0 KRW",
  title: "Permissions and container runtime", subtitle: "The app entrypoint uses the same package hub and one business runtime.", artifact: macos,
  steps: [
    { title: "Prepare Rancher Desktop", copy: "Use the maintained Apple Silicon or Intel build with the Moby engine." },
    { title: "Grant only prompted access", copy: "Follow OS prompts required for app launch and runtime connection." },
    { title: "Recheck in the hub", copy: "Reopen the app after install, login, or reboot and resume preflight." },
    { title: "Keep one runtime", copy: "Language, stop, and restart actions do not create new business state." },
  ],
});

checked(launcherPath, ["language", "ko_KR"]);
const hubPort = Number(process.env.PF07_HUB_PORT || "19075");
const hub = spawn(hubPath, ["--port", String(hubPort), "--no-browser"], {
  cwd: packageRoot,
  env: process.env,
  stdio: ["ignore", "pipe", "pipe"],
});
let hubOutput = "";
hub.stdout.on("data", (chunk) => { hubOutput += chunk.toString("utf8"); });
let hubError = "";
hub.stderr.on("data", (chunk) => { hubError += chunk.toString("utf8"); });
const deadline = Date.now() + 10000;
while (!hubOutput.includes("PF07_HUB_URL=") && Date.now() < deadline) {
  await new Promise((resolve) => setTimeout(resolve, 100));
}
if (!hubOutput.includes("PF07_HUB_URL=")) {
  hub.kill("SIGTERM");
  throw new Error(`final package hub did not start: ${hubError.trim()}`);
}
const hubUrl = `http://127.0.0.1:${hubPort}/`;
const baseUrl = `http://127.0.0.1:${runtime.PF07_WORDPRESS_PORT}`;
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PF07_CHROME_PATH || "/usr/bin/google-chrome",
});

const capturePage = async ({ locale, viewport, route, output, readySelector = "body", beforeCapture = null }) => {
  if (resume && fs.existsSync(path.join(outputRoot, output))) return;
  checked(launcherPath, ["language", locale]);
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  try {
    await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle" });
    await page.locator(readySelector).first().waitFor({ state: "visible" });
    await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
    if (beforeCapture) await beforeCapture(page);
    await page.screenshot({ path: path.join(outputRoot, output), type: "png" });
  } finally {
    await page.close();
  }
};

const captureAdmin = async ({ locale, output }) => {
  if (resume && fs.existsSync(path.join(outputRoot, output))) return;
  checked(launcherPath, ["language", locale]);
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  try {
    await page.goto(`${baseUrl}/wp-login.php`, { waitUntil: "networkidle" });
    await page.locator("#user_login").fill(runtime.PF07_ADMIN_USER);
    await page.locator("#user_pass").fill(runtime.PF07_ADMIN_PASSWORD);
    await Promise.all([
      page.waitForNavigation({ waitUntil: "networkidle" }),
      page.locator("#wp-submit").click(),
    ]);
    await page.goto(`${baseUrl}/wp-admin/admin.php?page=oddroom-orderops`, { waitUntil: "networkidle" });
    await page.locator(".oddroom-orderops").waitFor({ state: "visible" });
    await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
    await page.screenshot({ path: path.join(outputRoot, output), type: "png" });
  } finally {
    await context.close();
  }
};

try {
  await capturePage({ locale: "ko_KR", viewport: { width: 1440, height: 1000 }, route: "/", output: "CASE-005_storefront-desktop_ko.png", readySelector: "#oddroom-main" });
  await capturePage({ locale: "ko_KR", viewport: { width: 1440, height: 1000 }, route: "/shop/", output: "CASE-005_storefront-shop-desktop_ko.png", readySelector: ".wc-block-product-template" });
  await capturePage({ locale: "ko_KR", viewport: { width: 390, height: 844 }, route: "/", output: "CASE-006_storefront-mobile_ko.png", readySelector: "#oddroom-main" });
  await capturePage({ locale: "en_US", viewport: { width: 1440, height: 1000 }, route: "/", output: "CASE-007_storefront-desktop_en.png", readySelector: "#oddroom-main" });
  await capturePage({ locale: "en_US", viewport: { width: 390, height: 844 }, route: "/", output: "CASE-007_storefront-mobile_en.png", readySelector: "#oddroom-main" });
  await capturePage({ locale: "en_US", viewport: { width: 1440, height: 1000 }, route: "/shop/", output: "CASE-007_storefront-shop-desktop_en.png", readySelector: ".wc-block-product-template" });
  await capturePage({ locale: "ko_KR", viewport: { width: 1440, height: 1000 }, route: "/product/foldline-tech-case/", output: "CASE-008_variable-product_ko.png", readySelector: "form.variations_form" });
  await capturePage({ locale: "en_US", viewport: { width: 1440, height: 1000 }, route: "/product/foldline-tech-case/", output: "CASE-008_variable-product_en.png", readySelector: "form.variations_form" });
  await captureAdmin({ locale: "ko_KR", output: "CASE-010_operator-console_ko.png" });
  await captureAdmin({ locale: "en_US", output: "CASE-010_operator-console_en.png" });

  checked(launcherPath, ["language", "ko_KR"]);
  if (!["CASE-009_cart_ko.png", "CASE-009_checkout_ko.png"].every((name) => resume && fs.existsSync(path.join(outputRoot, name)))) {
    const commerce = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    try {
      await commerce.goto(`${baseUrl}/product/offset-dock/`, { waitUntil: "networkidle" });
      await commerce.locator("button.single_add_to_cart_button").click();
      await commerce.waitForTimeout(900);
      await commerce.goto(`${baseUrl}/cart/`, { waitUntil: "networkidle" });
      await commerce.locator("table.shop_table").first().waitFor({ state: "visible" });
      if (!(resume && fs.existsSync(path.join(outputRoot, "CASE-009_cart_ko.png")))) {
        await commerce.screenshot({ path: path.join(outputRoot, "CASE-009_cart_ko.png"), type: "png" });
      }
      await commerce.goto(`${baseUrl}/checkout/`, { waitUntil: "networkidle" });
      await commerce.locator("#billing_email").waitFor({ state: "visible" });
      if (!(resume && fs.existsSync(path.join(outputRoot, "CASE-009_checkout_ko.png")))) {
        await commerce.screenshot({ path: path.join(outputRoot, "CASE-009_checkout_ko.png"), type: "png" });
      }
    } finally {
      await commerce.close();
    }
  }

  for (const [locale, suffix] of [["ko_KR", "ko"], ["en_US", "en"]]) {
    checked(launcherPath, ["language", locale]);
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    try {
      await page.goto(hubUrl, { waitUntil: "networkidle" });
      await page.locator("#status-badge").filter({ hasText: locale === "ko_KR" ? "준비 완료" : "Ready" }).waitFor();
      const guide005 = path.join(outputRoot, `GUIDE-005_linux-install-run_${suffix}.png`);
      if (!(resume && fs.existsSync(guide005))) await page.screenshot({ path: guide005, type: "png" });
      if (process.env.PF07_CAPTURE_TUNNEL === "1") {
        const tunnelStatus = JSON.parse(checked(launcherPath, ["tunnel-status"]));
        if (tunnelStatus.state !== "ON") throw new Error("GUIDE-008 requires the actual final package tunnel to be ON");
        await page.locator("#tunnel-form").scrollIntoViewIfNeeded();
        const guide008 = path.join(outputRoot, `GUIDE-008_https-tunnel_${suffix}.png`);
        if (!(resume && fs.existsSync(guide008))) await page.locator("#tunnel-form").screenshot({ path: guide008, type: "png" });
      }
    } finally {
      await page.close();
    }
  }
} finally {
  checked(launcherPath, ["language", "ko_KR"]);
  await browser.close();
  hub.kill("SIGTERM");
  await new Promise((resolve) => hub.once("close", resolve));
}

const results = {};
for (const name of expectedOutputs) {
  const bytes = await fsp.readFile(path.join(outputRoot, name));
  results[name] = { bytes: bytes.length, sha256: sha256(bytes) };
}
process.stdout.write(`${JSON.stringify({
  schema: "pf07.step080-final-stills.v1",
  build_id: artifactSet.build_id,
  artifact_set_sha256: sha256(artifactSetBytes),
  final_package_manifest_sha256: sha256(await fsp.readFile(path.join(packageRoot, "ARTIFACT-MANIFEST.json"))),
  files: results,
}, null, 2)}\n`);
