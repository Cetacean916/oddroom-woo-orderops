import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createWorker } from "tesseract.js";
import englishData from "@tesseract.js-data/eng";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sha256 = (data) => crypto.createHash("sha256").update(data).digest("hex");
const requireCondition = (condition, message) => { if (!condition) throw new Error(message); };
const run = (command, args, encoding = null) => {
  const result = spawnSync(command, args, { encoding, maxBuffer: 64 * 1024 * 1024 });
  if (result.status !== 0) {
    const error = encoding ? result.stderr : result.stderr?.toString("utf8");
    throw new Error(`${path.basename(command)} failed: ${(error || "unknown error").trim()}`);
  }
  return result.stdout;
};
const frameAt = (videoPath, seconds) => run("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-i", videoPath, "-ss", String(seconds),
  "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-",
]);
const sampleDynamics = (videoPath) => {
  const lines = run("ffmpeg", [
    "-hide_banner", "-loglevel", "error", "-i", videoPath,
    "-vf", "fps=1,scale=160:90,format=gray", "-f", "framemd5", "-",
  ]).toString("utf8").split("\n").filter((line) => line && !line.startsWith("#"));
  const hashes = lines.map((line) => line.split(",").at(-1).trim());
  return { sampled: hashes.length, unique: new Set(hashes).size };
};

const mediaPolicy = {
  "demo-video.mp4": {
    events: [
      ["LAUNCH_HUB", "final_package_hub_ready"],
      ["LIVE_STOREFRONT", "home_visible"], ["SHOP_OPENED", "shop_visible"],
      ["PRODUCT_SELECTED", "product_page_visible"], ["CART_READY", "cart_contains_product"],
      ["CHECKOUT_INPUT", "synthetic_checkout_input_visible"], ["ORDER_RECEIVED", "woocommerce_confirmation_visible"],
      ["OUTBOX_PENDING", "status_pending"], ["WORKER_RUN", "visible_terminal_foreground_worker_exit_zero"],
      ["ADMIN_COMPLETED", "status_completed"], ["INTEGRATION_RESULT", "masked_integration_correlation_visible"],
    ],
    ocr: {
      LAUNCH_HUB: [/final linux package/i, /ready/i, /actual hub.*controls/i],
      CHECKOUT_INPUT: [/checkout/i, /test street/i, /seoul/i],
      ORDER_RECEIVED: [/woocommerce.*actual synthetic order/i],
      OUTBOX_PENDING: [/actual final admin/i, /order[\s._-]*cr\w*[\s._-]+pendin/i],
      WORKER_RUN: [/final package worker/i, /action-scheduler run/i],
      ADMIN_COMPLETED: [/order[\s._-]*created/i, /completed/i, /\b200\b/i],
      INTEGRATION_RESULT: [/woo.*pf[o0]7.*n(?:8)?n.*crm.*slack/i, /identifiers.*masked/i],
    },
    duration: [60, 90],
  },
  "recovery-clip.mp4": {
    events: [
      ["OUTBOX_PENDING", "status_pending"], ["FAILURE_WORKER_RUN", "visible_terminal_failure_worker_exit_zero"],
      ["FAILED", "status_failed_manual_retry_visible"], ["NORMAL_SCENARIO", "actual_hub_normal_scenario_applied"],
      ["MANUAL_RETRY", "manual_retry_scheduled_pending"],
      ["RECOVERY_WORKER_RUN", "visible_terminal_recovery_worker_exit_zero"], ["RECOVERED", "status_recovered"],
    ],
    ocr: {
      OUTBOX_PENDING: [/same delivered\s+runtime/i, /order[\s._-]*cr\w*[\s._-]+pendin/i],
      FAILURE_WORKER_RUN: [/final package worker/i, /action-scheduler run/i],
      FAILED: [/manual retry now available/i, /422/i],
      NORMAL_SCENARIO: [/actual package hub control/i, /worker result/i],
      MANUAL_RETRY: [/actual administrator action/i, /scheduled one follow-up/i],
      RECOVERY_WORKER_RUN: [/final package worker/i, /action-scheduler run/i],
      RECOVERED: [/recovered/i, /http\s*200/i],
    },
    duration: [8, 30],
  },
};

const ocrRegions = {
  "demo-video.mp4": {
    WORKER_RUN: { left: 500, top: 475, width: 750, height: 220 },
  },
  "recovery-clip.mp4": {
    FAILURE_WORKER_RUN: { left: 500, top: 475, width: 750, height: 220 },
    RECOVERY_WORKER_RUN: { left: 500, top: 475, width: 750, height: 220 },
  },
};
// The isolated recorder places each public evidence caption at the upper-right
// edge. Keep non-terminal OCR scoped to that caption so unrelated page copy
// cannot satisfy the event-frame assertion.
const captionOcrRegion = { left: 840, top: 20, width: 420, height: 150 };

const staticImagePolicy = {
  "main-image.png": [1200, 1200],
  "detail-01-overview.png": [1200, 1350],
  "detail-02-flow.png": [1200, 1350],
  "detail-03-result.png": [1200, 1350],
  "video-poster.png": [1440, 1000],
};
const expectedManifestAssets = [
  ...Object.keys(staticImagePolicy),
  ...Object.keys(mediaPolicy),
  "execution-proof.json",
].sort();
const expectedCommitmentKeys = [
  "execution_proof_sha256", "public_acceptance_matrix_sha256",
  "public_product_quality_record_sha256", "public_restore_drill_record_sha256",
  "recording_script_sha256", "still_composition_script_sha256",
].sort();
const forbiddenMetadataTags = new Set([
  "artist", "author", "comment", "copyright", "creation_time", "description",
  "encoded_by", "location", "location-eng", "title",
]);
const forbiddenPngChunks = new Set(["eXIf", "iTXt", "tEXt", "tIME", "zTXt"]);

function inspectPngChunks(bytes, fileName) {
  requireCondition(bytes.length >= 20 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])),
    `${fileName}: deployed PNG signature failed`);
  let offset = 8;
  let ended = false;
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString("ascii", offset + 4, offset + 8);
    requireCondition(offset + 12 + length <= bytes.length, `${fileName}: deployed PNG chunk boundary failed`);
    requireCondition(!forbiddenPngChunks.has(type), `${fileName}: deployed identifying metadata chunk remains`);
    offset += 12 + length;
    if (type === "IEND") { ended = true; break; }
  }
  requireCondition(ended && offset === bytes.length, `${fileName}: deployed PNG termination failed`);
}

async function validatePublicExecutionMedia(caseUrl) {
  const deploymentRoot = new URL(".", caseUrl);
  const fetchBytes = async (url, label) => {
    const response = await fetch(url, {
      headers: { "Cache-Control": "no-cache" },
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error(`${label}: deployed asset returned ${response.status}`);
    return Buffer.from(await response.arrayBuffer());
  };
  const fetchAsset = (relative) => fetchBytes(new URL(`assets/media/pf07/${relative}`, deploymentRoot), relative);
  const publicEvidenceRoot = new URL("https://raw.githubusercontent.com/Cetacean916/oddroom-woo-orderops/main/");

  const [manifestBytes, proofBytes, demoBytes, recoveryBytes, recordingScriptBytes, stillBuilderBytes, acceptanceMatrixBytes] = await Promise.all([
    fetchAsset("media-manifest.json"), fetchAsset("execution-proof.json"),
    fetchAsset("demo-video.mp4"), fetchAsset("recovery-clip.mp4"),
    fs.readFile(path.join(root, "scripts/record-public-media.mjs")),
    fs.readFile(path.join(root, "scripts/build-public-stills.mjs")),
    fetchBytes(new URL("evidence/refinement/public/acceptance-matrix.json", publicEvidenceRoot), "public acceptance matrix"),
  ]);
  const staticImageBytes = Object.fromEntries(await Promise.all(
    Object.keys(staticImagePolicy).map(async (name) => [name, await fetchAsset(name)]),
  ));
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const proof = JSON.parse(proofBytes.toString("utf8"));
  const acceptanceMatrix = JSON.parse(acceptanceMatrixBytes.toString("utf8"));
  requireCondition(manifest.schema_version === 1 && manifest.case_id === "pf07"
    && manifest.classification === "PUBLIC_SANITIZED_MEDIA" && manifest.metadata_stripped === true
    && manifest.registration_manifest_case_count === 6,
  "deployed media manifest identity failed");
  requireCondition(JSON.stringify(Object.keys(manifest.assets || {}).sort()) === JSON.stringify(expectedManifestAssets)
    && JSON.stringify(Object.keys(manifest.source_commitments || {}).sort()) === JSON.stringify(expectedCommitmentKeys),
  "deployed media manifest exact asset or source-commitment inventory failed");
  requireCondition(proof.schema_version === 1 && proof.case_id === "pf07"
    && proof.classification === "PUBLIC_SANITIZED_EXECUTION_PROOF"
    && !Object.hasOwn(proof, "status") && !Object.hasOwn(proof, "result"),
  "deployed execution proof identity or no-self-PASS rule failed");
  requireCondition(!/\/home\/|https?:\/\/|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/.test(proofBytes.toString("utf8")),
    "deployed execution proof contains a protected locator or contact-like value");
  requireCondition(sha256(proofBytes) === manifest.source_commitments?.execution_proof_sha256
    && sha256(proofBytes) === manifest.assets?.["execution-proof.json"]?.sha256,
  "deployed execution proof commitment failed");
  requireCondition(sha256(recordingScriptBytes) === proof.recording_script_sha256
    && proof.recording_script_sha256 === manifest.source_commitments?.recording_script_sha256,
  "deployed recording-script commitment failed");
  const mainStill = manifest.assets?.["main-image.png"];
  const detailStill = manifest.assets?.["detail-01-overview.png"];
  const expectedStillFrames = Object.fromEntries(
    (proof.videos?.["demo-video.mp4"]?.timeline || [])
      .filter((event) => ["LIVE_STOREFRONT", "PRODUCT_SELECTED", "CHECKOUT_INPUT"].includes(event.event))
      .map((event) => [event.event, event.frame_sha256]),
  );
  const expectedMainStillFrames = { LIVE_STOREFRONT: expectedStillFrames.LIVE_STOREFRONT };
  requireCondition(sha256(stillBuilderBytes) === manifest.source_commitments?.still_composition_script_sha256
    && mainStill?.source_video === "demo-video.mp4"
    && mainStill?.source_video_sha256 === proof.videos?.["demo-video.mp4"]?.sha256
    && JSON.stringify(mainStill?.source_event_frame_sha256) === JSON.stringify(expectedMainStillFrames)
    && detailStill?.source_video === "demo-video.mp4"
    && detailStill?.source_video_sha256 === proof.videos?.["demo-video.mp4"]?.sha256
    && JSON.stringify(detailStill?.source_event_frame_sha256) === JSON.stringify(expectedStillFrames),
  "deployed real-execution still source commitment failed");
  requireCondition(sha256(acceptanceMatrixBytes) === manifest.source_commitments?.public_acceptance_matrix_sha256
    && acceptanceMatrix.matrix_scope === "PRE_PUBLIC_BUYER_PROOF"
    && acceptanceMatrix.observations?.final_pass_claimed === false
    && Array.isArray(acceptanceMatrix.entries) && acceptanceMatrix.entries.length === 10,
  "deployed public acceptance-matrix commitment or scope failed");

  const evidenceByGate = new Map();
  const expectedGates = Array.from({ length: 10 }, (_, index) => `GATE-${String(index + 1).padStart(2, "0")}`);
  requireCondition(JSON.stringify(acceptanceMatrix.entries.map((entry) => entry.acceptance_id)) === JSON.stringify(expectedGates),
    "deployed public acceptance-matrix gate inventory failed");
  await Promise.all(acceptanceMatrix.entries.map(async (entry) => {
    requireCondition(typeof entry.record_path === "string" && /^evidence\/refinement\/public\/[a-z0-9-]+\.json$/.test(entry.record_path)
      && /^[0-9a-f]{64}$/.test(entry.record_sha256) && entry.result === "PASS",
    `deployed public evidence link shape failed for ${entry.acceptance_id}`);
    const bytes = await fetchBytes(new URL(entry.record_path, publicEvidenceRoot), entry.acceptance_id);
    requireCondition(sha256(bytes) === entry.record_sha256, `deployed public evidence hash failed for ${entry.acceptance_id}`);
    evidenceByGate.set(entry.acceptance_id, { bytes, record: JSON.parse(bytes.toString("utf8")) });
  }));
  requireCondition(sha256(evidenceByGate.get("GATE-09").bytes) === manifest.source_commitments?.public_product_quality_record_sha256
    && sha256(evidenceByGate.get("GATE-10").bytes) === manifest.source_commitments?.public_restore_drill_record_sha256,
  "deployed product-quality or restore source commitment failed");

  const observed = (gate, field) => evidenceByGate.get(gate)?.record?.observations?.[field];
  const scorecard = [
    ["지원 주문 이벤트", `${observed("GATE-02", "event_type_count")}종`, "GATE-02"],
    ["서로 다른 변수 입력 주문", `${observed("GATE-03", "distinct_order_count")}건`, "GATE-03"],
    ["동시 중복 억제", `worker ${observed("GATE-04", "concurrent_workers")} + retry conflict ${observed("GATE-04", "manual_retry_conflicts")}`, "GATE-04"],
    ["자동 시도 상한", `${observed("GATE-06", "automatic_attempt_limit")}회 · ${observed("GATE-06", "retry_delays_seconds")?.join("/")}초`, "GATE-06"],
    ["부분 실패 복구", `CRM checkpoint 유지 · Slack 총 ${observed("GATE-07", "total_slack_posts")}`, "GATE-07"],
    ["Reconciliation", `누락 ${observed("GATE-08", "missing_event_repairs")} + schedule-only ${observed("GATE-08", "schedule_only_repairs")} · 두 번째 ${observed("GATE-08", "second_scan_mutations")}`, "GATE-08"],
    ["Clean restore", `Deal ${observed("GATE-10", "new_deal_count")} · payment Slack ${observed("GATE-10", "payment_slack_posts")} · duplicate +${observed("GATE-10", "duplicate_additional_slack_posts")}`, "GATE-10"],
  ];
  requireCondition(!JSON.stringify(scorecard).includes("undefined"), "deployed scorecard source observations are incomplete");

  const temporaryRoot = await fs.mkdtemp(path.join(os.tmpdir(), "pf07-public-media-"));
  const frames = new Map();
  const summaries = {};
  try {
    for (const [fileName, dimensions] of Object.entries(staticImagePolicy)) {
      const bytes = staticImageBytes[fileName];
      const asset = manifest.assets?.[fileName];
      const imagePath = path.join(temporaryRoot, fileName);
      requireCondition(asset && sha256(bytes) === asset.sha256
        && Number(asset.width) === dimensions[0] && Number(asset.height) === dimensions[1],
      `${fileName}: deployed image commitment failed`);
      inspectPngChunks(bytes, fileName);
      await fs.writeFile(imagePath, bytes);
      const imageProbe = JSON.parse(run("ffprobe", [
        "-v", "error", "-show_entries", "stream=codec_name,width,height:format_tags", "-of", "json", imagePath,
      ], "utf8"));
      requireCondition(imageProbe.streams?.length === 1 && imageProbe.streams[0]?.codec_name === "png"
        && Number(imageProbe.streams[0]?.width) === dimensions[0] && Number(imageProbe.streams[0]?.height) === dimensions[1]
        && !Object.keys(imageProbe.format?.tags || {}).some((key) => forbiddenMetadataTags.has(key.toLowerCase())),
      `${fileName}: deployed PNG decode, dimensions, or metadata failed`);
      run("ffmpeg", ["-v", "error", "-i", imagePath, "-frames:v", "1", "-f", "null", "-"]);
    }
    const videoBytesByName = {
      "demo-video.mp4": demoBytes,
      "recovery-clip.mp4": recoveryBytes,
    };
    for (const [fileName, policy] of Object.entries(mediaPolicy)) {
      const videoPath = path.join(temporaryRoot, fileName);
      await fs.writeFile(videoPath, videoBytesByName[fileName]);
      const videoProof = proof.videos?.[fileName];
      const asset = manifest.assets?.[fileName];
      requireCondition(videoProof && asset && sha256(videoBytesByName[fileName]) === videoProof.sha256
        && videoProof.sha256 === asset.sha256, `${fileName}: deployed byte commitment failed`);

      const probe = JSON.parse(run("ffprobe", [
        "-v", "error", "-count_frames",
        "-show_entries", "stream=codec_type,codec_name,pix_fmt,width,height,nb_read_frames:format=duration:format_tags",
        "-of", "json", videoPath,
      ], "utf8"));
      const videoStreams = (probe.streams || []).filter((stream) => stream.codec_type === "video");
      const stream = videoStreams[0];
      const duration = Number(probe.format?.duration);
      const frameCount = Number(stream?.nb_read_frames);
      requireCondition(probe.streams?.length === 1 && videoStreams.length === 1
        && stream?.codec_name === "h264" && stream?.pix_fmt === "yuv420p"
        && Number(stream?.width) === 1280 && Number(stream?.height) === 720,
      `${fileName}: deployed stream inventory, codec, or dimensions failed`);
      requireCondition(duration >= policy.duration[0] && duration <= policy.duration[1]
        && Math.abs(duration - Number(videoProof.duration_seconds)) < 0.01
        && frameCount === Number(videoProof.frame_count)
        && Math.abs(frameCount / duration - 30) < 0.1,
      `${fileName}: deployed duration, frame count, or continuity failed`);
      requireCondition(!Object.keys(probe.format?.tags || {}).some((key) => forbiddenMetadataTags.has(key.toLowerCase())),
        `${fileName}: deployed identifying metadata remains`);
      run("ffmpeg", ["-v", "error", "-i", videoPath, "-map", "0:v:0", "-f", "null", "-"]);
      const dynamics = sampleDynamics(videoPath);
      requireCondition(dynamics.sampled === Number(videoProof.sampled_frame_count)
        && dynamics.unique === Number(videoProof.unique_sampled_frames)
        && dynamics.unique > policy.events.length,
      `${fileName}: deployed dynamic content commitment failed`);

      const timeline = videoProof.timeline;
      requireCondition(Array.isArray(timeline) && timeline.length === policy.events.length,
        `${fileName}: deployed timeline inventory failed`);
      let previous = -1;
      const hashes = new Set();
      for (let index = 0; index < policy.events.length; index += 1) {
        const event = timeline[index];
        const [expectedEvent, expectedObservation] = policy.events[index];
        requireCondition(event?.event === expectedEvent && event?.observation === expectedObservation
          && event.at_seconds > previous && event.at_seconds < duration,
        `${fileName}: deployed timeline event ${index + 1} failed`);
        previous = event.at_seconds;
        const frame = frameAt(videoPath, event.at_seconds);
        requireCondition(sha256(frame) === event.frame_sha256, `${fileName}: deployed frame commitment failed for ${expectedEvent}`);
        frames.set(`${fileName}:${expectedEvent}`, frame);
        hashes.add(event.frame_sha256);
      }
      requireCondition(hashes.size === policy.events.length, `${fileName}: deployed event frames are not distinct`);
      if (fileName === "demo-video.mp4") {
        requireCondition(videoProof.continuous_capture === true
          && videoProof.actual_launcher_hub_observed === true
          && videoProof.actual_checkout_observed === true
          && videoProof.foreground_worker_observed === true
          && videoProof.visible_worker_terminal_observed === true
          && videoProof.final_status === "completed",
        `${fileName}: deployed real-execution flags failed`);
      } else {
        requireCondition(videoProof.continuous_capture === true
          && videoProof.actual_terminal_failure_observed === true
          && videoProof.actual_hub_scenario_transition_observed === true
          && videoProof.manual_retry_observed === true
          && videoProof.visible_worker_terminal_observed === true
          && videoProof.final_status === "recovered",
        `${fileName}: deployed real-recovery flags failed`);
      }
      summaries[fileName] = { duration_seconds: duration, frame_count: frameCount, unique_sampled_frames: dynamics.unique };
    }

    const poster = proof.poster;
    requireCondition(sha256(staticImageBytes["video-poster.png"]) === poster?.sha256
      && poster.sha256 === manifest.assets?.["video-poster.png"]?.sha256,
    "deployed poster commitment failed");
    const regeneratedPoster = run("ffmpeg", [
      "-hide_banner", "-loglevel", "error", "-i", path.join(temporaryRoot, poster.source_video),
      "-ss", String(poster.source_at_seconds), "-frames:v", "1",
      "-vf", "scale=1440:810:force_original_aspect_ratio=decrease,pad=1440:1000:(ow-iw)/2:(oh-ih)/2:color=0x171714",
      "-map_metadata", "-1", "-f", "image2pipe", "-vcodec", "png", "-",
    ]);
    requireCondition(sha256(regeneratedPoster) === poster.sha256, "deployed poster is not the committed execution frame");

    const worker = await createWorker("eng", 1, {
      langPath: englishData.langPath,
      gzip: englishData.gzip,
      cacheMethod: "none",
    });
    try {
      for (const [fileName, policy] of Object.entries(mediaPolicy)) {
        for (const [eventName, patterns] of Object.entries(policy.ocr)) {
          const rectangle = ocrRegions[fileName]?.[eventName] || captionOcrRegion;
          const result = await worker.recognize(
            frames.get(`${fileName}:${eventName}`),
            { rectangle },
          );
          const text = result.data.text.replace(/\s+/g, " ");
          requireCondition(patterns.every((pattern) => pattern.test(text)), `${fileName}: deployed frame text failed for ${eventName}`);
        }
      }
    } finally {
      await worker.terminate();
    }
  } finally {
    await fs.rm(temporaryRoot, { recursive: true, force: true });
  }
  return {
    proof_sha256: sha256(proofBytes),
    videos: summaries,
    image_count: Object.keys(staticImagePolicy).length,
    evidence_record_count: evidenceByGate.size,
    ocr_event_count: Object.values(mediaPolicy).reduce((sum, policy) => sum + Object.keys(policy.ocr).length, 0),
    scorecard,
  };
}

const caseUrl = process.env.PF07_PUBLIC_CASE_URL || "https://cetacean916.github.io/portfolio-showcase/case.html?id=pf07";
const mediaObservation = await validatePublicExecutionMedia(caseUrl);
const deploymentRoot = new URL(".", caseUrl);
const expectedEvidenceLinks = [
  "https://github.com/Cetacean916/oddroom-woo-orderops",
  "https://github.com/Cetacean916/oddroom-woo-orderops/blob/main/evidence/refinement/public/acceptance-matrix.json",
  "https://github.com/Cetacean916/oddroom-woo-orderops/blob/main/plugin/oddroom-orderops/tests/run.php",
  "https://github.com/Cetacean916/oddroom-woo-orderops/blob/main/workflow/oddroom-orderops-vsl.json",
  "https://github.com/Cetacean916/oddroom-woo-orderops/blob/main/docs/RECOVERY-RUNBOOK.md",
  "https://github.com/Cetacean916/oddroom-woo-orderops/releases/download/pf07-v1.0.3/PF07-RELEASE-MANIFEST.json",
  new URL("assets/media/pf07/execution-proof.json", deploymentRoot).href,
];
const expectedVideoSources = [
  new URL("assets/media/pf07/recovery-clip.mp4", deploymentRoot).href,
  new URL("assets/media/pf07/demo-video.mp4", deploymentRoot).href,
];
await Promise.all(expectedEvidenceLinks.map(async (url) => {
  const response = await fetch(url, {
    headers: { "User-Agent": "PF07-public-validator/1", "Cache-Control": "no-cache" },
    signal: AbortSignal.timeout(30000),
  });
  requireCondition(response.ok, `deployed buyer-verifiable link returned ${response.status}`);
  await response.body?.cancel();
}));
const browser = await chromium.launch({ channel: "chrome", headless: true });
const observations = [];

try {
  for (const width of [390, 768, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    await page.goto(caseUrl, { waitUntil: "networkidle", timeout: 30000 });
    await page.locator("[data-case-root] .case-page").waitFor({ state: "visible" });
    const audit = await page.evaluate(() => {
      const visibleActions = [...document.querySelectorAll("a,button")].filter((node) => {
        const style = getComputedStyle(node); const rect = node.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
      });
      return {
        title: document.title,
        h1: document.querySelector("h1")?.textContent?.trim() || "",
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
        brokenImages: [...document.images].filter((image) => image.complete && image.naturalWidth === 0).length,
        clippedActions: visibleActions.filter((node) => node.scrollWidth > node.clientWidth + 2 || node.scrollHeight > node.clientHeight + 2).length,
        scorecard: [...document.querySelectorAll("[data-proof-scorecard] tbody tr")].map((row) => [
          row.querySelector("th")?.textContent?.trim() || "",
          row.querySelector("td")?.textContent?.trim() || "",
          row.querySelector("code")?.textContent?.trim() || "",
        ]),
        evidenceLinks: [...document.querySelectorAll("[data-evidence-links] a")].map((link) => link.href),
        videoSources: [...document.querySelectorAll(".case-video video source")].map((source) => source.src),
        boundaryText: document.querySelector("[data-claims-boundary]")?.textContent || "",
        availability: document.querySelector("[data-hosting-availability]")?.textContent || "",
        videos: document.querySelectorAll("video").length,
      };
    });
    const axe = await new AxeBuilder({ page }).analyze();
    const seriousOrCritical = axe.violations.filter((item) => ["serious", "critical"].includes(item.impact)).length;
    if (!audit.title.includes("OFFSET") || !audit.h1.includes("OFFSET / ORDER SYSTEM")) throw new Error(`${width}: selected brand title or heading missing`);
    if (audit.scrollWidth > audit.viewportWidth + 1 || audit.brokenImages || audit.clippedActions) throw new Error(`${width}: layout or asset failure ${JSON.stringify(audit)}`);
    if (JSON.stringify(audit.scorecard) !== JSON.stringify(mediaObservation.scorecard)
      || JSON.stringify(audit.evidenceLinks) !== JSON.stringify(expectedEvidenceLinks)
      || JSON.stringify(audit.videoSources) !== JSON.stringify(expectedVideoSources)
      || audit.videos !== 2) {
      throw new Error(`${width}: exact scorecard, evidence-link, or recovery-before-normal video inventory failed ${JSON.stringify(audit)}`);
    }
    for (const phrase of ["exactly-once", "실결제", "Slack", "ON_DEMAND_ONLY"]) {
      if (!(audit.boundaryText + audit.availability).includes(phrase)) throw new Error(`${width}: missing boundary ${phrase}`);
    }
    if (seriousOrCritical || consoleErrors.length) {
      const seriousViolations = axe.violations
        .filter((item) => ["serious", "critical"].includes(item.impact))
        .map((item) => ({ id: item.id, impact: item.impact, targets: item.nodes.map((node) => node.target) }));
      throw new Error(`${width}: accessibility/console failure ${JSON.stringify({ seriousOrCritical, seriousViolations, consoleErrors })}`);
    }
    observations.push({ width, serious_or_critical: seriousOrCritical, page_overflow: false, clipped_actions: 0, broken_images: 0, console_errors: 0 });
    await context.close();
  }
  console.log(JSON.stringify({ schema_version: 1, result: "PASS", case_url: caseUrl, media: mediaObservation, observations }));
} finally {
  await browser.close();
}
