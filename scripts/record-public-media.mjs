#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const projectRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const scriptPath = fileURLToPath(import.meta.url);
const outputDir = process.argv[2] ? path.resolve(process.argv[2]) : null;
const packageRoot = process.env.PF07_PACKAGE_ROOT ? path.resolve(process.env.PF07_PACKAGE_ROOT) : null;
if (!outputDir || !packageRoot || !process.env.DISPLAY) {
  throw new Error("usage: DISPLAY=:N PF07_PACKAGE_ROOT=FINAL_PACKAGE scripts/record-public-media.mjs OUTPUT_DIR");
}
const captureDisplay = /^:(\d+)(?:\.\d+)?$/.exec(process.env.DISPLAY);
if (!captureDisplay || Number(captureDisplay[1]) < 10) {
  throw new Error("public media recording requires a dedicated Xvfb display (:10 or higher); refusing to capture an owner desktop");
}

const targets = {
  demo: path.join(outputDir, "demo-video.mp4"),
  recovery: path.join(outputDir, "recovery-clip.mp4"),
  poster: path.join(outputDir, "video-poster.png"),
  proof: path.join(outputDir, "execution-proof.json"),
};
await fsp.mkdir(outputDir, { recursive: true });
for (const target of Object.values(targets)) {
  if (fs.existsSync(target)) throw new Error(`refusing to replace existing output: ${path.basename(target)}`);
}

const ffmpeg = process.env.PF07_FFMPEG_PATH || "/usr/bin/ffmpeg";
const ffprobe = process.env.PF07_FFPROBE_PATH || "/usr/bin/ffprobe";
const chrome = process.env.PF07_CHROME_PATH || "/usr/bin/google-chrome";
const terminal = process.env.PF07_TERMINAL_PATH || "/usr/bin/xfce4-terminal";
const launcher = path.join(packageRoot, "pf07");
const hubLauncher = path.join(packageRoot, "launcher", "bin", "pf07-hub");
const runtimeEnv = path.join(packageRoot, ".pf07", "runtime.env");
const composeFile = path.join(packageRoot, "packaging", "common", "compose.yaml");
const artifactManifestPath = path.join(packageRoot, "ARTIFACT-MANIFEST.json");
for (const required of [ffmpeg, ffprobe, chrome, terminal, launcher, hubLauncher, runtimeEnv, composeFile, artifactManifestPath]) {
  await fsp.access(required, fs.constants.R_OK);
}
await fsp.access(terminal, fs.constants.X_OK);

const runtime = Object.fromEntries(
  (await fsp.readFile(runtimeEnv, "utf8"))
    .split(/\r?\n/)
    .filter((line) => line && !line.startsWith("#") && line.includes("="))
    .map((line) => {
      const separator = line.indexOf("=");
      return [line.slice(0, separator), line.slice(separator + 1)];
    }),
);
for (const key of ["PF07_WORDPRESS_PORT", "PF07_ADMIN_USER", "PF07_ADMIN_PASSWORD", "PF07_COMPOSE_PROJECT"]) {
  if (!runtime[key]) throw new Error(`missing final package runtime value: ${key}`);
}
const artifactManifestBytes = await fsp.readFile(artifactManifestPath);
const artifactManifest = JSON.parse(artifactManifestBytes.toString("utf8"));
if (artifactManifest.schema !== "pf07.artifact-manifest.v1"
  || artifactManifest.artifact_id !== "pf07-linux-x86_64"
  || artifactManifest.package_version !== "1.0.2"
  || artifactManifest.build_id !== "pf07-build-b99af2ac12d22b464865"
  || artifactManifest.actual_os_runtime_execution !== false
  || artifactManifest.tested_boundary !== "ACTUAL_LINUX_LOCAL_EXECUTION_REQUIRED_ON_CANONICAL_CI_BYTES_IN_STEP_090") {
  throw new Error("final Linux package identity or execution boundary failed");
}

const baseUrl = `http://127.0.0.1:${runtime.PF07_WORDPRESS_PORT}`;
const scratchRoot = path.resolve(process.env.PF07_SCRATCH_ROOT || os.tmpdir());
await fsp.mkdir(scratchRoot, { recursive: true });
const visibleOperationRoot = await fsp.mkdtemp(path.join(scratchRoot, "pf07-final-media-terminal-"));
const localPreflight = await fetch(`${baseUrl}/`);
if (!localPreflight.ok || !(await localPreflight.text()).includes("OFFSET")) {
  throw new Error("final package storefront preflight failed");
}

const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const sha256File = async (file) => sha256(await fsp.readFile(file));
const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function runProcess(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd || packageRoot,
      env: options.env || process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`${path.basename(command)} timed out`));
    }, options.timeout || 180000);
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) reject(new Error(`${path.basename(command)} exited ${code}: ${Buffer.concat(stderr).toString("utf8").trim()}`));
      else resolve({ stdout: Buffer.concat(stdout), stderr: Buffer.concat(stderr) });
    });
  });
}

async function packageCommand(...args) {
  const result = await runProcess(launcher, args);
  return result.stdout.toString("utf8").trim();
}

async function compose(...args) {
  return runProcess("docker", [
    "compose", "--progress", "quiet", "--env-file", runtimeEnv, "-f", composeFile,
    "-p", runtime.PF07_COMPOSE_PROJECT, ...args,
  ], { timeout: 180000 });
}

async function startHub() {
  const port = Number(process.env.PF07_HUB_PORT || "19075");
  const child = spawn(hubLauncher, ["--port", String(port), "--no-browser"], {
    cwd: packageRoot,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
  child.stderr.on("data", (chunk) => { stderr += chunk.toString("utf8"); });
  const deadline = Date.now() + 10000;
  while (!stdout.includes("PF07_HUB_URL=") && child.exitCode === null && Date.now() < deadline) await wait(100);
  if (!stdout.includes("PF07_HUB_URL=")) {
    child.kill("SIGTERM");
    throw new Error(`final package hub did not start: ${stderr.trim()}`);
  }
  return { child, url: `http://127.0.0.1:${port}/` };
}

async function stopHub(hub) {
  if (hub.child.exitCode !== null) return;
  hub.child.kill("SIGTERM");
  await new Promise((resolve) => hub.child.once("close", resolve));
}

async function startCapture(target) {
  const display = process.env.DISPLAY.includes(".") ? process.env.DISPLAY : `${process.env.DISPLAY}.0`;
  const startedAt = Date.now();
  const child = spawn(ffmpeg, [
    "-hide_banner", "-loglevel", "error", "-y",
    "-f", "x11grab", "-draw_mouse", "1", "-framerate", "30", "-video_size", "1280x720",
    "-i", `${display}+0,0`, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-map_metadata", "-1",
    "-metadata", "title=", "-metadata", "comment=", "-metadata", "creation_time=", target,
  ], { stdio: ["pipe", "ignore", "pipe"] });
  const errors = [];
  child.stderr.on("data", (chunk) => errors.push(chunk));
  await wait(700);
  if (child.exitCode !== null) throw new Error(`ffmpeg capture failed: ${Buffer.concat(errors).toString("utf8").trim()}`);
  return { child, errors, startedAt };
}

async function stopCapture(capture) {
  const completed = new Promise((resolve, reject) => {
    capture.child.once("error", reject);
    capture.child.once("close", (code) => code === 0 ? resolve() : reject(new Error(`ffmpeg capture exited ${code}`)));
  });
  capture.child.stdin.write("q\n");
  await completed;
}

function mark(capture, timeline, event, observation) {
  timeline.push({
    event,
    at_seconds: Number(((Date.now() - capture.startedAt) / 1000).toFixed(3)),
    observation,
  });
}

async function caption(page, marker, detail) {
  await page.evaluate(({ marker, detail }) => {
    document.querySelector("#pf07-recording-caption")?.remove();
    const root = document.createElement("div");
    root.id = "pf07-recording-caption";
    Object.assign(root.style, {
      position: "fixed", zIndex: "2147483647", top: "18px", right: "18px", width: "372px",
      padding: "15px 17px", color: "#171714", background: "rgba(243,240,231,.97)",
      border: "1px solid #171714", borderRadius: "0", boxShadow: "none",
      fontFamily: '"Noto Sans KR","DejaVu Sans",Arial,sans-serif', pointerEvents: "none", lineHeight: "1.35",
    });
    const strong = document.createElement("strong");
    strong.textContent = marker;
    Object.assign(strong.style, { display: "block", color: "#a43f22", fontSize: "20px", letterSpacing: ".055em" });
    const text = document.createElement("span");
    text.textContent = detail;
    Object.assign(text.style, { display: "block", marginTop: "5px", fontSize: "14px" });
    root.append(strong, text);
    document.documentElement.append(root);
  }, { marker, detail });
  await wait(600);
}

async function setCaptureBounds(page) {
  const session = await page.context().newCDPSession(page);
  const { windowId } = await session.send("Browser.getWindowForTarget");
  await session.send("Browser.setWindowBounds", {
    windowId,
    bounds: { windowState: "fullscreen" },
  });
  await wait(450);
}

async function openContext(browser) {
  const context = await browser.newContext({ viewport: null });
  await context.addInitScript(() => {
    const sanitizeText = (node) => {
      if (node.nodeType !== Node.TEXT_NODE || !node.nodeValue) return;
      const sanitized = node.nodeValue
        .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "masked-email")
        .replace(/@example\.com/gi, "masked domain")
        .replace(/Synthetic\s*\/\s*Buyer/gi, "masked buyer")
        .replace(/pf07-operator/gi, "masked-operator");
      if (sanitized !== node.nodeValue) node.nodeValue = sanitized;
    };
    const sanitizeTree = (root) => {
      if (root.nodeType === Node.TEXT_NODE) return sanitizeText(root);
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(node.parentElement?.tagName || "")
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT,
      });
      while (walker.nextNode()) sanitizeText(walker.currentNode);
    };
    let styleInstalled = false;
    const installStyle = () => {
      if (styleInstalled || !document.documentElement) return;
      const style = document.createElement("style");
      style.id = "pf07-capture-privacy";
      style.textContent = `
        #billing_first_name, #billing_last_name, #billing_email {
          color: transparent !important; -webkit-text-fill-color: transparent !important;
          text-shadow: 0 0 10px #334 !important;
        }
        .woocommerce-order-overview__order.order,
        .woocommerce-order-overview__email.email,
        .woocommerce-order-overview__customer.customer,
        .woocommerce-order-overview li strong,
        .woocommerce-customer-details, .woocommerce-customer-details address,
        .oddroom-event-card h3, .oddroom-event-card header code,
        .oddroom-correlation b, .oddroom-fact-grid dd,
        #wp-admin-bar-my-account, #wp-admin-bar-user-info, .display-name {
          filter: blur(8px) !important; user-select: none !important;
        }
        #wp-admin-bar-my-account, #wp-admin-bar-my-account > .ab-item,
        #wp-admin-bar-user-info, .display-name {
          visibility: hidden !important; opacity: 0 !important;
        }
        body.woocommerce-order-received .oddroom-commerce-intro > p:last-of-type,
        .woocommerce-order-overview__email.email,
        .woocommerce-order-overview__email.email strong,
        .woocommerce-customer-details,
        .woocommerce-customer-details address {
          color: transparent !important; -webkit-text-fill-color: transparent !important;
          text-shadow: 0 0 10px #334 !important;
        }
      `;
      document.documentElement.append(style);
      styleInstalled = true;
    };
    installStyle();
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => sanitizeTree(document), { once: true });
    } else {
      sanitizeTree(document);
    }
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  await setCaptureBounds(page);
  return { context, page };
}

async function focusAction(locator) {
  await locator.scrollIntoViewIfNeeded();
  await locator.hover();
  await locator.focus();
  await locator.evaluate((node) => {
    node.style.outline = "3px solid #d65b31";
    node.style.outlineOffset = "4px";
  });
  await wait(350);
}

async function openHubTarget(hubPage, context, selector, expectedPathPrefix) {
  await hubPage.evaluate(() => {
    window.__pf07CapturedTarget = null;
    window.open = (target) => {
      window.__pf07CapturedTarget = String(target);
      return null;
    };
  });
  const button = hubPage.locator(selector);
  await focusAction(button);
  await button.click();
  await hubPage.waitForFunction(() => typeof window.__pf07CapturedTarget === "string");
  const target = await hubPage.evaluate(() => window.__pf07CapturedTarget);
  const parsed = new URL(target);
  if (parsed.origin !== baseUrl || !parsed.pathname.startsWith(expectedPathPrefix)) {
    throw new Error(`hub target failed package-local boundary: ${expectedPathPrefix}`);
  }
  const page = await context.newPage();
  await page.goto(target, { waitUntil: "networkidle" });
  await setCaptureBounds(page);
  return page;
}

async function clickAndWait(locator, page) {
  await focusAction(locator);
  await Promise.all([
    page.waitForLoadState("domcontentloaded"),
    locator.click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
}

async function slowFill(page, selector, value, { protect = false, instant = false } = {}) {
  const field = page.locator(selector);
  if (protect) {
    await field.evaluate((node) => {
      node.style.setProperty("color", "transparent", "important");
      node.style.setProperty("-webkit-text-fill-color", "transparent", "important");
      node.style.setProperty("text-shadow", "0 0 10px #334", "important");
      node.style.setProperty("caret-color", "#d65b31", "important");
    });
  }
  await field.focus();
  await field.fill("");
  if (instant) await field.fill(value);
  else await field.pressSequentially(value, { delay: 35 });
}

async function sanitizeVisibleIdentityText(page) {
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(node.parentElement?.tagName || "")
        ? NodeFilter.FILTER_REJECT
        : NodeFilter.FILTER_ACCEPT,
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const sanitized = node.nodeValue
        .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "masked-email")
        .replace(/@example\.com/gi, "masked domain")
        .replace(/Synthetic\s*\/\s*Buyer/gi, "masked buyer");
      if (sanitized !== node.nodeValue) node.nodeValue = sanitized;
    }
  });
}

async function createOrderThroughCheckout(page, timelineState = null) {
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  if (timelineState) {
    await caption(page, "LIVE STOREFRONT", "Final Linux package · actual WooCommerce home");
    mark(timelineState.capture, timelineState.timeline, "LIVE_STOREFRONT", "home_visible");
    await wait(2500);
    await page.evaluate(() => window.scrollTo({ top: 420, behavior: "smooth" }));
    await wait(600);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await wait(300);
  }

  const shopLink = page.getByRole("link", { name: /컬렉션 보기|컬렉션에서 시작|Shop the collection|Start with the collection/i }).first();
  await clickAndWait(shopLink, page);
  if (timelineState) {
    await caption(page, "SHOP OPENED", "Actual final catalog · synthetic products only");
    mark(timelineState.capture, timelineState.timeline, "SHOP_OPENED", "shop_visible");
    await wait(2200);
  }

  const productLink = page.locator('a[href*="/product/offset-dock/"]').first();
  await clickAndWait(productLink, page);
  if (timelineState) {
    await caption(page, "PRODUCT SELECTED", "Offset Dock · real final product detail");
    mark(timelineState.capture, timelineState.timeline, "PRODUCT_SELECTED", "product_page_visible");
    await wait(2200);
  }
  const addButton = page.locator("button.single_add_to_cart_button");
  await focusAction(addButton);
  await addButton.click();
  await wait(900);
  const cartLink = page.locator('.oddroom-frontbar a[href*="/cart/"]').first();
  await clickAndWait(cartLink, page);
  await page.locator("table.shop_table").first().waitFor();
  if (timelineState) {
    await caption(page, "CART READY", "Actual cart state · no real payment");
    mark(timelineState.capture, timelineState.timeline, "CART_READY", "cart_contains_product");
    await wait(2200);
  }

  const checkoutLink = page.locator("a.checkout-button").first();
  await clickAndWait(checkoutLink, page);
  await page.locator("#billing_email").waitFor();
  await sanitizeVisibleIdentityText(page);
  await slowFill(page, "#billing_first_name", "Synthetic", { protect: true });
  await slowFill(page, "#billing_last_name", "Buyer", { protect: true });
  await page.locator("#billing_country").selectOption("KR");
  await slowFill(page, "#billing_address_1", "123 Test Street");
  await slowFill(page, "#billing_city", "Seoul");
  await slowFill(page, "#billing_postcode", "04524");
  await slowFill(page, "#billing_email", `pf07-video-${Date.now()}@example.com`, { protect: true });
  if (timelineState) {
    await caption(page, "SYNTHETIC CHECKOUT", "Test Street · Seoul · protected dummy contact fields");
    mark(timelineState.capture, timelineState.timeline, "CHECKOUT_INPUT", "synthetic_checkout_input_visible");
    await wait(2000);
  }

  const placeOrder = page.locator("#place_order");
  await focusAction(placeOrder);
  await Promise.all([
    page.waitForURL(/order-received/, { timeout: 45000 }),
    placeOrder.click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.addStyleTag({ content: `
    .woocommerce-order-overview__order.order,
    .woocommerce-order-overview__email.email,
    .woocommerce-order-overview__customer.customer,
    .woocommerce-order-overview li strong,
    .woocommerce-customer-details,
    .woocommerce-customer-details address { filter: blur(10px) !important; user-select: none !important; }
  ` });
  await sanitizeVisibleIdentityText(page);
  const confirmation = await page.locator("body").innerText();
  if (!/order received|주문.*접수|주문이 완료/i.test(confirmation)) throw new Error("actual checkout did not reach order confirmation");
  if (/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(confirmation)) throw new Error("confirmation still exposes an email-like value");
  if (timelineState) {
    await caption(page, "ORDER RECEIVED", "WooCommerce created the actual synthetic order");
    mark(timelineState.capture, timelineState.timeline, "ORDER_RECEIVED", "woocommerce_confirmation_visible");
    await wait(2500);
  }
}

async function loginAdmin(page, { requireCard = true } = {}) {
  const adminUrl = `${baseUrl}/wp-admin/admin.php?page=oddroom-orderops`;
  await page.goto(adminUrl, { waitUntil: "domcontentloaded" });
  if (/\/wp-login\.php/.test(page.url())) {
    await page.locator("#user_login").evaluate((node) => { node.type = "password"; });
    await slowFill(page, "#user_login", runtime.PF07_ADMIN_USER, { protect: true, instant: true });
    await slowFill(page, "#user_pass", runtime.PF07_ADMIN_PASSWORD, { protect: true, instant: true });
    await Promise.all([
      page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 45000 }),
      page.click("#wp-submit"),
    ]);
    await page.locator("#adminmenu").waitFor({ timeout: 45000 });
  }
  if (!/[?&]page=oddroom-orderops(?:&|$)/.test(page.url())) {
    await page.goto(adminUrl, { waitUntil: "commit", timeout: 45000 });
  }
  await maskAdmin(page);
  if (requireCard) {
    await page.locator(".oddroom-event-card").first().waitFor({ timeout: 45000 });
    await focusNewestCard(page);
  }
}

async function maskAdmin(page) {
  await page.addStyleTag({ content: `
    .oddroom-event-card h3,
    .oddroom-event-card header code,
    .oddroom-correlation b,
    .oddroom-fact-grid dd,
    #wp-admin-bar-my-account,
    #wp-admin-bar-user-info,
    .display-name { filter: blur(7px) !important; user-select: none !important; }
    #wp-admin-bar-my-account,
    #wp-admin-bar-my-account > .ab-item,
    #wp-admin-bar-user-info,
    .display-name { visibility: hidden !important; opacity: 0 !important; }
  ` });
}

async function focusNewestCard(page) {
  const card = page.locator(".oddroom-event-card").first();
  await card.waitFor({ state: "visible", timeout: 45000 });
  await card.scrollIntoViewIfNeeded({ timeout: 45000 });
  await wait(350);
  return card;
}

async function newestClass(page) {
  return (await page.locator(".oddroom-event-card").first().getAttribute("class")) || "";
}

function extractEventPanel(source) {
  const start = source.indexOf('<section id="events"');
  const end = start < 0 ? -1 : source.indexOf("</section>", start);
  if (start < 0 || end < start) throw new Error("actual admin response omitted the event panel");
  const panel = source.slice(start, end + "</section>".length);
  if (!panel.includes("oddroom-event-card")) throw new Error("actual admin response omitted the event ledger");
  return panel;
}

async function replaceEventPanel(page, source) {
  const replaced = await page.evaluate((panelSource) => {
    const currentPanel = document.querySelector(".oddroom-events-panel");
    const template = document.createElement("template");
    template.innerHTML = panelSource;
    const nextPanel = template.content.querySelector(".oddroom-events-panel");
    if (!currentPanel || !nextPanel || !nextPanel.querySelector(".oddroom-event-card")) return false;
    currentPanel.replaceWith(nextPanel);
    return true;
  }, source);
  if (!replaced) throw new Error("actual admin response could not replace the event ledger");
}

async function reloadAdmin(page) {
  const response = await page.request.get(`${baseUrl}/wp-admin/admin.php?page=oddroom-orderops`);
  try {
    if (!response.ok()) throw new Error(`admin refresh returned HTTP ${response.status()}`);
    await replaceEventPanel(page, extractEventPanel(await response.text()));
  } finally {
    await response.dispose();
  }
  await sanitizeVisibleIdentityText(page);
  await focusNewestCard(page);
}

async function submitAdminButtonInPlace(page, button) {
  const formFacts = await button.evaluate((node) => {
    const form = node.form;
    if (!form) throw new Error("administrator action form is missing");
    const actionAttribute = form.getAttribute("action");
    if (!actionAttribute) throw new Error("administrator action URL is missing");
    form.addEventListener("submit", (event) => event.preventDefault(), { once: true });
    node.click();
    return {
      action: new URL(actionAttribute, document.baseURI).href,
      method: (form.method || "post").toUpperCase(),
      fields: Array.from(new FormData(form).entries()),
    };
  });
  const observedAction = new URL(formFacts.action);
  if (observedAction.pathname !== "/wp-admin/admin-post.php") {
    throw new Error("administrator action endpoint changed");
  }
  const response = await page.request.fetch(`${baseUrl}/wp-admin/admin-post.php`, {
    method: formFacts.method,
    form: Object.fromEntries(formFacts.fields),
    maxRedirects: 5,
  });
  try {
    if (!response.ok()) throw new Error(`administrator action returned HTTP ${response.status()}`);
    await replaceEventPanel(page, extractEventPanel(await response.text()));
  } finally {
    await response.dispose();
  }
}

async function applyHubScenario(hubPage, scenario, capture, timeline, event, observation) {
  await hubPage.bringToFront();
  await hubPage.locator("#recovery-button").click();
  await hubPage.locator("#scenario-select").selectOption(scenario);
  await focusAction(hubPage.locator("#scenario-button"));
  await hubPage.locator("#scenario-button").click();
  await hubPage.locator("#recovery-result").filter({ hasText: /적용|applied/i }).waitFor();
  if (capture) {
    await caption(hubPage, scenario === "terminal" ? "TERMINAL SCENARIO" : "NORMAL SCENARIO", "Actual package hub control changed the next worker result");
    mark(capture, timeline, event, observation);
    await wait(300);
  }
}

const visibleOperationShell = String.raw`
set +e
printf '\033[2J\033[H'
printf '%s\n' "$PF07_VISIBLE_HEADING"
printf '$ %s\n' "$PF07_VISIBLE_COMMAND"
printf 'RUNNING actual final-package worker...\n'
sleep 0.9
docker compose --progress quiet --env-file "$PF07_VISIBLE_RUNTIME_ENV" -f "$PF07_VISIBLE_COMPOSE_FILE" -p "$PF07_VISIBLE_COMPOSE_PROJECT" --profile tools run --rm -T wpcli action-scheduler run --hooks=oddroom_orderops_process --batch-size=25 --batches=1 --force >"$PF07_VISIBLE_LOG" 2>&1
operation_status=$?
if [ "$operation_status" -eq 0 ]; then
  printf '[PASS] actual process exit = 0\n'
else
  printf '[FAIL] actual process exit = %s\n' "$operation_status"
fi
sleep 0.8
exit "$operation_status"
`;

async function runVisibleWorker({ heading, command, capture, timeline, event, observation }) {
  const logPath = path.join(visibleOperationRoot, `${String(timeline.length).padStart(2, "0")}-worker.log`);
  const child = spawn(terminal, [
    "--disable-server", "--geometry=76x10+500+470", "--title=PF07 Final Package Worker",
    "--hide-menubar", "--hide-toolbar", "--hide-scrollbar", "--font=DejaVu Sans Mono 15",
    "--color-text=#f3f0e7", "--color-bg=#171714", "--execute", "bash", "-lc", visibleOperationShell,
  ], {
    env: {
      ...process.env,
      PF07_VISIBLE_HEADING: heading,
      PF07_VISIBLE_COMMAND: command,
      PF07_VISIBLE_RUNTIME_ENV: runtimeEnv,
      PF07_VISIBLE_COMPOSE_FILE: composeFile,
      PF07_VISIBLE_COMPOSE_PROJECT: runtime.PF07_COMPOSE_PROJECT,
      PF07_VISIBLE_LOG: logPath,
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  const stderr = [];
  child.stderr.on("data", (chunk) => stderr.push(chunk));
  const completed = new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("close", (code) => code === 0
      ? resolve()
      : reject(new Error(`visible worker terminal exited ${code}: ${Buffer.concat(stderr).toString("utf8").trim()}`)));
  });
  await wait(700);
  if (child.exitCode !== null) throw new Error("visible worker terminal ended before observation");
  mark(capture, timeline, event, observation);
  await completed;
  await fsp.rm(logPath, { force: true });
}

async function resetCheckoutAllowance() {
  const result = await compose("--profile", "tools", "run", "--rm", "-T", "wpcli", "oddroom-orderops", "reset-checkout-limit");
  const record = JSON.parse(result.stdout.toString("utf8"));
  if (record.status !== "PASS" || record.scope !== "SYNTHETIC_CHECKOUT_RATE_LIMIT_ONLY") {
    throw new Error("synthetic checkout allowance reset failed");
  }
}

async function createRecoveryOrderViaWpCli() {
  const alias = `media${Date.now()}`;
  const result = await compose(
    "--profile", "tools", "run", "--rm", "-T", "wpcli",
    "oddroom-orderops", "create-order", "--shape=variable", `--alias=${alias}`,
  );
  const record = JSON.parse(result.stdout.toString("utf8"));
  if (!Number.isInteger(record.order_id) || record.order_id < 1
    || !Number.isInteger(record.outbox_id) || record.outbox_id < 1
    || !Number.isInteger(record.action_id) || record.action_id < 1
    || record.shape !== "variable") {
    throw new Error("protected recovery order preparation failed");
  }
}

async function videoProbe(file) {
  const { stdout } = await runProcess(ffprobe, [
    "-v", "error", "-select_streams", "v:0", "-count_frames",
    "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_frames:format=duration",
    "-of", "json", file,
  ]);
  const parsed = JSON.parse(stdout.toString("utf8"));
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
    "-hide_banner", "-loglevel", "error", "-i", file,
    "-vf", "fps=1,scale=160:90,format=gray", "-f", "framemd5", "-",
  ]);
  const hashes = stdout.toString("utf8").split("\n")
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => line.split(",").at(-1).trim());
  return { sampled_frame_count: hashes.length, unique_sampled_frames: new Set(hashes).size };
}

async function frameSha(file, seconds) {
  const { stdout } = await runProcess(ffmpeg, [
    "-hide_banner", "-loglevel", "error", "-i", file, "-ss", String(seconds),
    "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-",
  ]);
  return sha256(stdout);
}

async function bindTimelineFrames(file, timeline) {
  for (const event of timeline) event.frame_sha256 = await frameSha(file, event.at_seconds);
}

await packageCommand("mode", "DEMO_MODE");
await packageCommand("language", "ko_KR");
await packageCommand("scenario", "normal");
const hub = await startHub();
const browser = await chromium.launch({
  headless: false,
  executablePath: chrome,
  args: [
    "--kiosk", "--window-position=0,0", "--window-size=1280,720", "--no-first-run",
    "--disable-session-crashed-bubble", "--disable-infobars", "--disable-notifications",
    "--disable-background-networking", "--disable-component-update", "--disable-translate",
    "--disable-features=Translate,TranslateUI", "--force-device-scale-factor=1",
  ],
});

let activeCapture = null;
const demoTimeline = [];
const recoveryTimeline = [];
try {
  await packageCommand("reset-demo", "--confirm=RESET PF07 DEMO");
  await resetCheckoutAllowance();
  const demoSession = await openContext(browser);
  await demoSession.page.goto(hub.url, { waitUntil: "networkidle" });
  await demoSession.page.locator("#status-badge").filter({ hasText: "준비 완료" }).waitFor();
  const demoAdminSession = await openContext(browser);
  await loginAdmin(demoAdminSession.page, { requireCard: false });
  await demoSession.page.bringToFront();
  const demoCapture = await startCapture(targets.demo);
  activeCapture = demoCapture;
  await caption(demoSession.page, "PACKAGE LAUNCH HUB", "Final Linux package · READY · actual hub controls");
  mark(demoCapture, demoTimeline, "LAUNCH_HUB", "final_package_hub_ready");
  await wait(2500);

  const storePage = await openHubTarget(demoSession.page, demoSession.context, "#store-button", "/");
  const adminPage = demoAdminSession.page;
  await storePage.bringToFront();
  await compose("stop", "-t", "1", "worker");
  await createOrderThroughCheckout(storePage, { capture: demoCapture, timeline: demoTimeline });

  await adminPage.bringToFront();
  await loginAdmin(adminPage);
  if (!(await newestClass(adminPage)).includes("status-queued")) throw new Error("demo row was not pending before foreground worker");
  await caption(adminPage, "OUTBOX PENDING", "ORDER_CREATED · pending · actual final admin");
  mark(demoCapture, demoTimeline, "OUTBOX_PENDING", "status_pending");
  await wait(2000);

  await caption(adminPage, "FOREGROUND WORKER", "Actual final-package Action Scheduler run");
  await runVisibleWorker({
    heading: "PF07 FINAL PACKAGE WORKER",
    command: "action-scheduler run --hooks=oddroom_orderops_process",
    capture: demoCapture,
    timeline: demoTimeline,
    event: "WORKER_RUN",
    observation: "visible_terminal_foreground_worker_exit_zero",
  });
  await reloadAdmin(adminPage);
  if (!(await newestClass(adminPage)).includes("status-normal")) throw new Error("demo row did not complete");
  await caption(adminPage, "ADMIN COMPLETED", "ORDER_CREATED · completed · HTTP 200");
  mark(demoCapture, demoTimeline, "ADMIN_COMPLETED", "status_completed");
  await wait(2500);
  const details = adminPage.locator(".oddroom-event-card").first().locator("details");
  await details.locator("summary").click();
  await details.scrollIntoViewIfNeeded();
  await caption(adminPage, "INTEGRATION RESULT", "Woo → PF07 → n8n → CRM → Slack · identifiers masked");
  mark(demoCapture, demoTimeline, "INTEGRATION_RESULT", "masked_integration_correlation_visible");
  const demoElapsed = (Date.now() - demoCapture.startedAt) / 1000;
  if (demoElapsed < 62) await wait((62 - demoElapsed) * 1000);
  await stopCapture(demoCapture);
  activeCapture = null;
  await demoSession.context.close();
  await demoAdminSession.context.close();

  await compose("start", "worker");
  await packageCommand("reset-demo", "--confirm=RESET PF07 DEMO");
  await resetCheckoutAllowance();
  const recoverySession = await openContext(browser);
  await recoverySession.page.goto(hub.url, { waitUntil: "networkidle" });
  await recoverySession.page.locator("#status-badge").filter({ hasText: "준비 완료" }).waitFor();
  await applyHubScenario(recoverySession.page, "terminal", null, null, null, null);
  await compose("stop", "-t", "1", "worker");
  await createRecoveryOrderViaWpCli();
  const recoveryAdmin = await recoverySession.context.newPage();
  await setCaptureBounds(recoveryAdmin);
  await loginAdmin(recoveryAdmin);
  if (!(await newestClass(recoveryAdmin)).includes("status-queued")) throw new Error("recovery row was not pending");

  const recoveryCapture = await startCapture(targets.recovery);
  activeCapture = recoveryCapture;
  await caption(recoveryAdmin, "OUTBOX PENDING", "ORDER_CREATED · pending · same delivered runtime");
  mark(recoveryCapture, recoveryTimeline, "OUTBOX_PENDING", "status_pending");
  await wait(300);
  await recoveryAdmin.bringToFront();
  await caption(recoveryAdmin, "FAILURE WORKER", "Actual final-package worker enters terminal failure");
  await runVisibleWorker({
    heading: "PF07 FINAL PACKAGE WORKER",
    command: "action-scheduler run --hooks=oddroom_orderops_process",
    capture: recoveryCapture,
    timeline: recoveryTimeline,
    event: "FAILURE_WORKER_RUN",
    observation: "visible_terminal_failure_worker_exit_zero",
  });
  await reloadAdmin(recoveryAdmin);
  if (!(await newestClass(recoveryAdmin)).includes("status-failed")) throw new Error("recovery row did not enter failed");
  await caption(recoveryAdmin, "FAILED", "Same outbox row · HTTP 422 · manual retry now available");
  mark(recoveryCapture, recoveryTimeline, "FAILED", "status_failed_manual_retry_visible");
  await wait(250);
  await compose("start", "worker");
  await recoverySession.page.bringToFront();
  await recoverySession.page.waitForFunction(async () => {
    try {
      const response = await fetch("/api/status", { cache: "no-store" });
      return response.ok && (await response.json()).ready === true;
    } catch {
      return false;
    }
  }, null, { timeout: 15000, polling: 500 });
  await recoverySession.page.waitForFunction(() => !document.querySelector("#scenario-button")?.disabled, null, { timeout: 10000 });
  await applyHubScenario(
    recoverySession.page, "normal", recoveryCapture, recoveryTimeline,
    "NORMAL_SCENARIO", "actual_hub_normal_scenario_applied",
  );
  await compose("stop", "-t", "1", "worker");
  await recoveryAdmin.bringToFront();
  await recoveryAdmin.locator(".oddroom-event-card").first().locator("details summary").click();
  const retryButton = recoveryAdmin.getByRole("button", { name: /수동 재시도|Manual retry/i }).first();
  await focusAction(retryButton);
  await submitAdminButtonInPlace(recoveryAdmin, retryButton);
  await sanitizeVisibleIdentityText(recoveryAdmin);
  await focusNewestCard(recoveryAdmin);
  if (!(await newestClass(recoveryAdmin)).includes("status-queued")) throw new Error("manual retry did not return row to pending");
  await caption(recoveryAdmin, "MANUAL RETRY", "Actual administrator action scheduled one follow-up");
  mark(recoveryCapture, recoveryTimeline, "MANUAL_RETRY", "manual_retry_scheduled_pending");
  await wait(250);
  await caption(recoveryAdmin, "RECOVERY WORKER", "Actual final-package worker resumes the same row");
  await runVisibleWorker({
    heading: "PF07 FINAL PACKAGE WORKER",
    command: "action-scheduler run --hooks=oddroom_orderops_process",
    capture: recoveryCapture,
    timeline: recoveryTimeline,
    event: "RECOVERY_WORKER_RUN",
    observation: "visible_terminal_recovery_worker_exit_zero",
  });
  await reloadAdmin(recoveryAdmin);
  if (!(await newestClass(recoveryAdmin)).includes("status-recovered")) throw new Error("recovery row did not reach recovered");
  await caption(recoveryAdmin, "RECOVERED", "Same outbox row · recovered · HTTP 200");
  mark(recoveryCapture, recoveryTimeline, "RECOVERED", "status_recovered");
  await wait(300);
  await stopCapture(recoveryCapture);
  activeCapture = null;
  await recoverySession.context.close();
} finally {
  if (activeCapture) await stopCapture(activeCapture).catch(() => {});
  await packageCommand("scenario", "normal").catch(() => {});
  await packageCommand("language", "ko_KR").catch(() => {});
  await compose("start", "worker").catch(() => {});
  await browser.close().catch(() => {});
  await stopHub(hub).catch(() => {});
  await fsp.rm(visibleOperationRoot, { recursive: true, force: true });
}

const posterTime = Math.max(0, (demoTimeline.find((event) => event.event === "ADMIN_COMPLETED")?.at_seconds || 55) + 0.5);
await runProcess(ffmpeg, [
  "-hide_banner", "-loglevel", "error", "-i", targets.demo, "-ss", String(posterTime),
  "-frames:v", "1", "-vf", "scale=1440:810:force_original_aspect_ratio=decrease,pad=1440:1000:(ow-iw)/2:(oh-ih)/2:color=0x171714",
  "-map_metadata", "-1", targets.poster,
]);

await bindTimelineFrames(targets.demo, demoTimeline);
await bindTimelineFrames(targets.recovery, recoveryTimeline);
const demoProbe = await videoProbe(targets.demo);
const recoveryProbe = await videoProbe(targets.recovery);
if (demoProbe.duration_seconds < 60 || demoProbe.duration_seconds > 90) throw new Error("demo duration is outside 60-90 seconds");
if (recoveryProbe.duration_seconds < 8 || recoveryProbe.duration_seconds > 30) throw new Error("recovery duration is outside 8-30 seconds");

const proof = {
  schema_version: 1,
  case_id: "pf07",
  classification: "PUBLIC_SANITIZED_EXECUTION_PROOF",
  recording_script: "scripts/record-public-media.mjs",
  recording_script_sha256: await sha256File(scriptPath),
  metadata_stripped: true,
  package_build_id: artifactManifest.build_id,
  package_artifact_manifest_sha256: sha256(artifactManifestBytes),
  final_linux_package_preflight: "PASS",
  synthetic_checkout_window_prepared_via_wp_cli: true,
  videos: {
    "demo-video.mp4": {
      sha256: await sha256File(targets.demo),
      ...demoProbe,
      ...(await sampleDynamics(targets.demo)),
      continuous_capture: true,
      actual_launcher_hub_observed: true,
      actual_checkout_observed: true,
      foreground_worker_observed: true,
      visible_worker_terminal_observed: true,
      final_status: "completed",
      timeline: demoTimeline,
    },
    "recovery-clip.mp4": {
      sha256: await sha256File(targets.recovery),
      ...recoveryProbe,
      ...(await sampleDynamics(targets.recovery)),
      continuous_capture: true,
      actual_terminal_failure_observed: true,
      actual_hub_scenario_transition_observed: true,
      manual_retry_observed: true,
      visible_worker_terminal_observed: true,
      final_status: "recovered",
      timeline: recoveryTimeline,
    },
  },
  poster: {
    file: "video-poster.png",
    sha256: await sha256File(targets.poster),
    source_video: "demo-video.mp4",
    source_at_seconds: posterTime,
  },
};
await fsp.writeFile(targets.proof, `${JSON.stringify(proof, null, 2)}\n`, { mode: 0o644 });
process.stdout.write(`${JSON.stringify({
  demo_duration_seconds: demoProbe.duration_seconds,
  recovery_duration_seconds: recoveryProbe.duration_seconds,
  demo_events: demoTimeline.length,
  recovery_events: recoveryTimeline.length,
}, null, 2)}\n`);
