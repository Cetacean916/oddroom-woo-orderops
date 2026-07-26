import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { createWorker } from "tesseract.js";
import englishData from "@tesseract.js-data/eng";

const sha256 = (data) => crypto.createHash("sha256").update(data).digest("hex");
const requireCondition = (condition, message) => {
  if (!condition) throw new Error(message);
};
const run = (command, args, encoding = null) => {
  const result = spawnSync(command, args, {
    encoding,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.status !== 0) {
    const error = encoding ? result.stderr : result.stderr?.toString("utf8");
    throw new Error(`${path.basename(command)} failed: ${(error || "unknown error").trim()}`);
  }
  return result.stdout;
};
const frameAt = (videoPath, seconds) => run("ffmpeg", [
  "-hide_banner", "-loglevel", "error",
  "-i", videoPath,
  "-ss", String(seconds),
  "-frames:v", "1",
  "-f", "image2pipe",
  "-vcodec", "png",
  "-",
]);
const sampleDynamics = (videoPath) => {
  const output = run("ffmpeg", [
    "-hide_banner", "-loglevel", "error",
    "-i", videoPath,
    "-vf", "fps=1,scale=160:90,format=gray",
    "-f", "framemd5",
    "-",
  ]).toString("utf8");
  const hashes = output.split("\n")
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => line.split(",").at(-1).trim());
  return { sampled: hashes.length, unique: new Set(hashes).size };
};

const expectedPackageVersion = "1.0.6";
const expectedReleaseTag = "pf07-v1.0.6";
const immutablePredecessorTag = "pf07-v1.0.5";
const repositoryRoot = new URL("https://github.com/Cetacean916/oddroom-woo-orderops/");
const deploymentRoot = new URL("https://cetacean916.github.io/portfolio-showcase/");
const publicEvidenceRoot = new URL(
  `https://raw.githubusercontent.com/Cetacean916/oddroom-woo-orderops/${expectedReleaseTag}/`,
);
const releaseManifestUrl = new URL(
  `releases/download/${expectedReleaseTag}/PF07-RELEASE-MANIFEST.json`,
  repositoryRoot,
);
const caseRoutes = {
  ko: new URL("case-pf07-ko.html", deploymentRoot).href,
  en: new URL("case-pf07-en.html", deploymentRoot).href,
};
let expectedRelease;
const expectedTimelines = {
  "purchase-delivery": [
    ["LAUNCH_HUB", "final_package_hub_ready"],
    ["LIVE_STOREFRONT", "home_visible"],
    ["SHOP_OPENED", "shop_visible"],
    ["PRODUCT_SELECTED", "product_page_visible"],
    ["CART_READY", "cart_contains_product"],
    ["CHECKOUT_INPUT", "synthetic_checkout_input_visible"],
    ["ORDER_RECEIVED", "woocommerce_confirmation_visible"],
    ["OUTBOX_PENDING", "status_pending"],
    ["WORKER_RUN", "visible_terminal_foreground_worker_exit_zero"],
    ["ADMIN_COMPLETED", "status_completed"],
    ["INTEGRATION_RESULT", "masked_integration_correlation_visible"],
  ],
  "failure-recovery": [
    ["OUTBOX_PENDING", "status_pending"],
    ["FAILURE_WORKER_RUN", "visible_terminal_failure_worker_exit_zero"],
    ["FAILED", "status_failed_manual_retry_visible"],
    ["NORMAL_SCENARIO", "actual_hub_normal_scenario_applied"],
    ["MANUAL_RETRY", "manual_retry_scheduled_pending"],
    ["RECOVERY_WORKER_RUN", "visible_terminal_recovery_worker_exit_zero"],
    ["RECOVERED", "status_recovered"],
  ],
};
const roles = {
  "guided-overview": { role: "guided_overview", minimum: 30, maximum: 45 },
  "purchase-delivery": { role: "purchase_delivery", minimum: 60, maximum: 90 },
  "failure-recovery": { role: "failure_recovery", minimum: 8, maximum: 30 },
};
const expectedCurrentUiSurfaces = [
  "storefront-home-desktop.png",
  "storefront-home-mobile.png",
  "storefront-shop-desktop.png",
  "product-detail-desktop.png",
  "cart-desktop.png",
  "checkout-desktop.png",
  "order-complete-desktop.png",
  "operator-console-desktop.png",
  "runtime-hub-desktop.png",
  "operator-failed-desktop.png",
  "operator-retrying-desktop.png",
  "operator-recovered-desktop.png",
];
const forbiddenMetadataKeys = new Set([
  "artist", "author", "comment", "copyright", "creation_time", "description",
  "encoded_by", "location", "location-eng", "title",
]);
const forbiddenPngChunks = new Set(["eXIf", "iTXt", "tEXt", "tIME", "zTXt"]);
const hasProtectedValue = (text) => (
  /\/home\/|file:\/\/|xox[baprs]-|gh[pousr]_|AKIA[0-9A-Z]{16}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/i.test(text)
);
const parseVttTimestamp = (value) => {
  const parts = value.trim().split(":").map(Number);
  requireCondition(parts.length === 2 || parts.length === 3, `invalid WebVTT timestamp: ${value}`);
  return parts.length === 2
    ? (parts[0] * 60) + parts[1]
    : (parts[0] * 3600) + (parts[1] * 60) + parts[2];
};
const inspectPng = (bytes, asset, label) => {
  requireCondition(
    bytes.length >= 20
      && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])),
    `${label}: PNG signature failed`,
  );
  requireCondition(
    bytes.readUInt32BE(16) === Number(asset.width)
      && bytes.readUInt32BE(20) === Number(asset.height)
      && bytes.length === Number(asset.bytes)
      && sha256(bytes) === asset.sha256,
    `${label}: PNG dimensions or byte commitment failed`,
  );
  let offset = 8;
  let ended = false;
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString("ascii", offset + 4, offset + 8);
    requireCondition(offset + 12 + length <= bytes.length, `${label}: PNG chunk boundary failed`);
    requireCondition(!forbiddenPngChunks.has(type), `${label}: identifying PNG metadata remains`);
    offset += 12 + length;
    if (type === "IEND") {
      ended = true;
      break;
    }
  }
  requireCondition(ended && offset === bytes.length, `${label}: PNG termination failed`);
};
const fetchBytes = async (url, label) => {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "PF07-public-validator/2",
      "Cache-Control": "no-cache",
    },
    signal: AbortSignal.timeout(30000),
  });
  requireCondition(response.ok, `${label}: deployed resource returned ${response.status}`);
  return Buffer.from(await response.arrayBuffer());
};
const fetchDeployment = (relative) => fetchBytes(new URL(relative, deploymentRoot), relative);

async function resolveExpectedRelease() {
  const manifestBytes = await fetchBytes(releaseManifestUrl, "PF07 release manifest");
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const linuxPackage = manifest.package_assets?.find(
    (asset) => asset.artifact_id === "pf07-linux-x86_64",
  );
  requireCondition(
    manifest.schema === "pf07.public-release-manifest.v1"
      && manifest.package_version === expectedPackageVersion
      && manifest.release_tag === expectedReleaseTag
      && manifest.public_package_delivery_mode === "GITHUB_RELEASE_ASSETS"
      && /^pf07-build-[0-9a-f]{20}$/.test(manifest.build_id)
      && /^[0-9a-f]{40}$/.test(manifest.repository?.source_commit)
      && /^[0-9a-f]{40}$/.test(manifest.repository?.source_tree)
      && manifest.intended_published_release?.tag_target_commit === manifest.repository.source_commit
      && manifest.intended_published_release?.tag_target_tree === manifest.repository.source_tree
      && manifest.build_identity?.release_manifest_is_build_input === false
      && manifest.build_identity?.release_manifest_is_inside_source_commit_or_package === false
      && manifest.package_assets?.length === 5
      && linuxPackage,
    "published PF07 release manifest identity failed",
  );
  return {
    package_version: manifest.package_version,
    release_tag: manifest.release_tag,
    immutable_predecessor_tag: immutablePredecessorTag,
    source_commit: manifest.repository.source_commit,
    source_tree: manifest.repository.source_tree,
    package_build_id: manifest.build_id,
    artifact_set_sha256: manifest.build_identity.artifact_set_manifest.sha256,
    release_manifest_sha256: sha256(manifestBytes),
    linux_package_filename: linuxPackage.filename,
    linux_package_sha256: linuxPackage.sha256,
    linux_package_manifest_sha256: linuxPackage.artifact_manifest_sha256,
  };
}

async function validatePublicEvidence() {
  const matrixBytes = await fetchBytes(
    new URL("evidence/refinement/public/acceptance-matrix.json", publicEvidenceRoot),
    "public acceptance matrix",
  );
  const matrix = JSON.parse(matrixBytes.toString("utf8"));
  const expectedGates = Array.from({ length: 10 }, (_, index) => `GATE-${String(index + 1).padStart(2, "0")}`);
  requireCondition(
    matrix.matrix_scope === "PRE_PUBLIC_BUYER_PROOF"
      && matrix.observations?.result === "PASS"
      && matrix.observations?.final_pass_claimed === false
      && Array.isArray(matrix.entries)
      && JSON.stringify(matrix.entries.map((entry) => entry.acceptance_id)) === JSON.stringify(expectedGates),
    "public buyer-proof matrix scope or exact ten-gate inventory failed",
  );
  const records = new Map();
  await Promise.all(matrix.entries.map(async (entry) => {
    requireCondition(
      typeof entry.record_path === "string"
        && /^evidence\/refinement\/public\/[a-z0-9-]+\.json$/.test(entry.record_path)
        && /^[0-9a-f]{64}$/.test(entry.record_sha256)
        && entry.result === "PASS",
      `${entry.acceptance_id}: public evidence link shape failed`,
    );
    const bytes = await fetchBytes(new URL(entry.record_path, publicEvidenceRoot), entry.acceptance_id);
    requireCondition(sha256(bytes) === entry.record_sha256, `${entry.acceptance_id}: public evidence hash failed`);
    const record = JSON.parse(bytes.toString("utf8"));
    requireCondition(
      record.acceptance_id === entry.acceptance_id
        && record.exit_code === 0
        && record.observations?.result === "PASS"
        && record.redaction_state === "PUBLIC_REDACTED",
      `${entry.acceptance_id}: public evidence result or redaction boundary failed`,
    );
    records.set(entry.acceptance_id, record);
  }));
  const observed = (gate, field) => records.get(gate)?.observations?.[field];
  const common = [
    [`${observed("GATE-02", "event_type_count")}`, "GATE-02"],
    [`${observed("GATE-03", "distinct_order_count")}`, "GATE-03"],
    [`worker ${observed("GATE-04", "concurrent_workers")} + retry conflict ${observed("GATE-04", "manual_retry_conflicts")}`, "GATE-04"],
    [`${observed("GATE-06", "automatic_attempt_limit")}`, "GATE-06"],
    [`${observed("GATE-07", "total_slack_posts")}`, "GATE-07"],
    [`${observed("GATE-08", "missing_event_repairs")}|${observed("GATE-08", "schedule_only_repairs")}|${observed("GATE-08", "second_scan_mutations")}`, "GATE-08"],
    [`${observed("GATE-10", "new_deal_count")}|${observed("GATE-10", "payment_slack_posts")}|${observed("GATE-10", "duplicate_additional_slack_posts")}`, "GATE-10"],
  ];
  requireCondition(!JSON.stringify(common).includes("undefined"), "public scorecard source observations are incomplete");
  const delays = observed("GATE-06", "retry_delays_seconds");
  requireCondition(Array.isArray(delays) && delays.length === 5, "public retry-delay observations are incomplete");
  return {
    matrix_sha256: sha256(matrixBytes),
    record_count: records.size,
    scorecards: {
      ko: [
        ["지원 주문 이벤트", `${common[0][0]}종`, common[0][1]],
        ["서로 다른 변수 입력 주문", `${common[1][0]}건`, common[1][1]],
        ["동시 중복 억제", common[2][0], common[2][1]],
        ["자동 시도 상한", `${common[3][0]}회 · ${delays.join("/")}초`, common[3][1]],
        ["부분 실패 복구", `CRM checkpoint 유지 · Slack 총 ${common[4][0]}`, common[4][1]],
        ["Reconciliation", `누락 ${observed("GATE-08", "missing_event_repairs")} + schedule-only ${observed("GATE-08", "schedule_only_repairs")} · 두 번째 ${observed("GATE-08", "second_scan_mutations")}`, common[5][1]],
        ["Clean restore", `Deal ${observed("GATE-10", "new_deal_count")} · payment Slack ${observed("GATE-10", "payment_slack_posts")} · duplicate +${observed("GATE-10", "duplicate_additional_slack_posts")}`, common[6][1]],
      ],
      en: [
        ["Supported order events", `${common[0][0]} types`, common[0][1]],
        ["Distinct variable-input orders", common[1][0], common[1][1]],
        ["Concurrent duplicate suppression", common[2][0], common[2][1]],
        ["Automatic-attempt cap", `${common[3][0]} · ${delays.join("/")} seconds`, common[3][1]],
        ["Partial-failure recovery", `CRM checkpoint kept · Slack total ${common[4][0]}`, common[4][1]],
        ["Reconciliation", `missing ${observed("GATE-08", "missing_event_repairs")} + schedule-only ${observed("GATE-08", "schedule_only_repairs")} · second scan ${observed("GATE-08", "second_scan_mutations")}`, common[5][1]],
        ["Clean restore", `Deal ${observed("GATE-10", "new_deal_count")} · payment Slack ${observed("GATE-10", "payment_slack_posts")} · duplicate +${observed("GATE-10", "duplicate_additional_slack_posts")}`, common[6][1]],
      ],
    },
  };
}

async function validateExecutionMedia() {
  const [manifestBytes, proofBytes, currentUiBytes] = await Promise.all([
    fetchDeployment("assets/media/pf07/media-manifest.json"),
    fetchDeployment("assets/media/pf07/execution-proof.json"),
    fetchDeployment("assets/media/pf07/current-ui-manifest.json"),
  ]);
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const proof = JSON.parse(proofBytes.toString("utf8"));
  const currentUi = JSON.parse(currentUiBytes.toString("utf8"));
  requireCondition(
    manifest.schema === "pf07.localized-showcase-media-manifest.v2"
      && manifest.state === "CURRENT_RELEASE_BOUND"
      && manifest.case_id === "pf07"
      && manifest.classification === "PUBLIC_SANITIZED_LOCALIZED_RUNTIME_MEDIA"
      && manifest.metadata_stripped === true
      && manifest.registration_manifest_case_count === 6,
    "localized media manifest identity failed",
  );
  requireCondition(
    proof.schema === "pf07.localized-showcase-execution-proof.v2"
      && proof.case_id === "pf07"
      && proof.classification === "PUBLIC_SANITIZED_EXECUTION_PROOF"
      && proof.metadata_stripped === true
      && !Object.hasOwn(proof, "status")
      && !Object.hasOwn(proof, "result"),
    "aggregate execution proof identity or no-self-PASS rule failed",
  );
  requireCondition(
    currentUi.schema === "pf07.current-ui-manifest.v3"
      && currentUi.state === "CURRENT_RELEASE_BOUND"
      && currentUi.case_id === "pf07"
      && currentUi.classification === "PUBLIC_SANITIZED_RUNTIME_CAPTURE"
      && currentUi.metadata_stripped === true,
    "current UI manifest identity failed",
  );
  requireCondition(
    JSON.stringify(manifest.release) === JSON.stringify(expectedRelease)
      && JSON.stringify(proof.release) === JSON.stringify(expectedRelease)
      && JSON.stringify(currentUi.release) === JSON.stringify(expectedRelease),
    "deployed current release identity commitment failed",
  );
  requireCondition(
    !hasProtectedValue(manifestBytes.toString("utf8"))
      && !hasProtectedValue(proofBytes.toString("utf8"))
      && !hasProtectedValue(currentUiBytes.toString("utf8")),
    "deployed PF07 manifest contains a protected locator or token",
  );
  requireCondition(
    manifest.execution_proof?.file === "assets/media/pf07/execution-proof.json"
      && manifest.execution_proof?.sha256 === sha256(proofBytes)
      && proof.final_linux_package_preflight === "PASS"
      && proof.synthetic_checkout_window_prepared_via_wp_cli === true
      && proof.exact_runtime_locale_count === 2,
    "aggregate execution proof hash or preflight boundary failed",
  );

  const expectedAuthorityFiles = {
    still_capture: "assets/media/pf07/provenance/capture-final-stills.mjs",
    retry_state_capture: "assets/media/pf07/provenance/capture-v1.0.6-retry-state.mjs",
    ko_recording_capture: "assets/media/pf07/provenance/record-public-media-ko-capture.mjs",
    current_recording_capture: "assets/media/pf07/provenance/record-public-media.mjs",
    release_evidence_builder: "assets/media/pf07/provenance/build-v1.0.6-release-evidence.mjs",
  };
  const authorityHashes = new Map();
  await Promise.all(Object.entries(expectedAuthorityFiles).map(async ([id, relative]) => {
    const bytes = await fetchDeployment(relative);
    const digest = sha256(bytes);
    requireCondition(
      manifest.capture_authorities?.[id]?.file === relative
        && manifest.capture_authorities?.[id]?.sha256 === digest
        && proof.capture_authorities?.[id]?.file === relative
        && proof.capture_authorities?.[id]?.sha256 === digest
        && currentUi.capture_authorities?.[id]?.file === relative
        && currentUi.capture_authorities?.[id]?.sha256 === digest,
      `${id}: deployed capture-authority commitment failed`,
    );
    authorityHashes.set(relative, digest);
  }));

  const expectedMediaFiles = [];
  for (const locale of ["ko", "en"]) {
    for (const slug of Object.keys(roles)) {
      expectedMediaFiles.push(
        `assets/media/pf07/videos/${locale}/${slug}.mp4`,
        `assets/media/pf07/posters/${locale}/${slug}.png`,
        `assets/media/pf07/captions/${locale}/${slug}.vtt`,
      );
    }
    expectedMediaFiles.push(`assets/media/pf07/proof/${locale}-recording-proof.json`);
  }
  expectedMediaFiles.sort();
  requireCondition(
    manifest.exact_asset_count === 20
      && manifest.locale_asset_counts?.ko === 10
      && manifest.locale_asset_counts?.en === 10
      && manifest.assets?.length === 20
      && new Set(manifest.assets.map((asset) => asset.asset_id)).size === 20
      && JSON.stringify(manifest.assets.map((asset) => asset.file).sort()) === JSON.stringify(expectedMediaFiles),
    "localized media exact asset set failed",
  );
  const expectedCurrentFiles = ["ko", "en"]
    .flatMap((locale) => expectedCurrentUiSurfaces.map((filename) => `${locale}/${filename}`))
    .sort();
  requireCondition(
    currentUi.assets?.length === 24
      && currentUi.locale_asset_counts?.ko === 12
      && currentUi.locale_asset_counts?.en === 12
      && new Set(currentUi.assets.map((asset) => asset.asset_id)).size === 24
      && JSON.stringify(currentUi.assets.map((asset) => asset.filename).sort()) === JSON.stringify(expectedCurrentFiles),
    "current UI exact 24-asset inventory failed",
  );

  const mediaBytes = new Map();
  const currentUiBytesByFile = new Map();
  await Promise.all([
    ...manifest.assets.map(async (asset) => {
      const bytes = await fetchDeployment(asset.file);
      requireCondition(bytes.length === Number(asset.bytes) && sha256(bytes) === asset.sha256, `${asset.file}: deployed byte commitment failed`);
      mediaBytes.set(asset.file, bytes);
    }),
    ...currentUi.assets.map(async (asset) => {
      const relative = `assets/media/pf07/current-ui/${asset.filename}`;
      const bytes = await fetchDeployment(relative);
      requireCondition(
        asset.metadata_stripped === true
          && asset.transformation === "capture-promoted-without-pixel-mutation"
          && asset.direct_review_result === "ACCEPTED_STEP050_DIRECT_REVIEW"
          && authorityHashes.get(asset.capture_authority) === asset.capture_authority_sha256,
        `${relative}: current UI authority or review boundary failed`,
      );
      inspectPng(bytes, asset, relative);
      currentUiBytesByFile.set(asset.filename, bytes);
    }),
  ]);

  const manifestByFile = new Map(manifest.assets.map((asset) => [asset.file, asset]));
  const temporaryRoot = await fs.mkdtemp(path.join(os.tmpdir(), "pf07-public-case-"));
  const summaries = {};
  const englishFrames = new Map();
  try {
    for (const locale of ["ko", "en"]) {
      const runtimeLocale = locale === "ko" ? "ko_KR" : "en_US";
      const recordingAuthorityId = locale === "ko" ? "ko_recording_capture" : "current_recording_capture";
      const proofRelative = `assets/media/pf07/proof/${locale}-recording-proof.json`;
      const localizedProofBytes = mediaBytes.get(proofRelative);
      const localizedProofText = localizedProofBytes.toString("utf8");
      const localizedProof = JSON.parse(localizedProofText);
      const aggregateProof = proof.recording_proofs?.[locale];
      const proofAsset = manifestByFile.get(proofRelative);
      requireCondition(
        localizedProof.schema_version === 1
          && localizedProof.case_id === "pf07"
          && localizedProof.classification === "PUBLIC_SANITIZED_EXECUTION_PROOF"
          && localizedProof.metadata_stripped === true
          && localizedProof.runtime_locale === runtimeLocale
          && localizedProof.package_build_id === expectedRelease.package_build_id
          && localizedProof.package_artifact_manifest_sha256 === expectedRelease.linux_package_manifest_sha256
          && localizedProof.final_linux_package_preflight === "PASS"
          && localizedProof.synthetic_checkout_window_prepared_via_wp_cli === true
          && !Object.hasOwn(localizedProof, "status")
          && !Object.hasOwn(localizedProof, "result")
          && !hasProtectedValue(localizedProofText),
        `${locale}: localized recording proof identity or boundary failed`,
      );
      const localizedProofHash = sha256(localizedProofBytes);
      const recordingAuthority = manifest.capture_authorities?.[recordingAuthorityId];
      requireCondition(
        aggregateProof?.file === proofRelative
          && aggregateProof?.sha256 === localizedProofHash
          && aggregateProof?.runtime_locale === runtimeLocale
          && proofAsset?.sha256 === localizedProofHash
          && proofAsset?.bytes === localizedProofBytes.length
          && localizedProof.recording_script_sha256 === recordingAuthority.sha256
          && aggregateProof?.recording_script_sha256 === recordingAuthority.sha256
          && proofAsset?.recording_script_sha256 === recordingAuthority.sha256,
        `${locale}: localized proof or recording authority commitment failed`,
      );

      for (const slug of ["purchase-delivery", "failure-recovery"]) {
        const relative = `assets/media/pf07/videos/${locale}/${slug}.mp4`;
        const bytes = mediaBytes.get(relative);
        const asset = manifestByFile.get(relative);
        const proofKey = slug === "purchase-delivery" ? "demo-video.mp4" : "recovery-clip.mp4";
        const videoProof = localizedProof.videos?.[proofKey];
        const timelineContract = expectedTimelines[slug];
        requireCondition(
          asset?.kind === "video"
            && asset.locale === locale
            && asset.role === roles[slug].role
            && asset.proof_video_key === proofKey
            && asset.source_proof === proofRelative
            && asset.source_proof_sha256 === localizedProofHash
            && asset.transformation === "byte-for-byte-promotion-from-localized-recording"
            && asset.sha256 === videoProof?.sha256,
          `${relative}: localized video proof binding failed`,
        );
        const videoPath = path.join(temporaryRoot, `${locale}-${slug}.mp4`);
        await fs.writeFile(videoPath, bytes);
        const probe = JSON.parse(run("ffprobe", [
          "-v", "error",
          "-select_streams", "v:0",
          "-count_frames",
          "-show_entries", "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_read_frames:format=duration,size:format_tags",
          "-of", "json",
          videoPath,
        ], "utf8"));
        const stream = probe.streams?.[0];
        const format = probe.format;
        const duration = Number(format?.duration);
        const frameCount = Number(stream?.nb_read_frames);
        requireCondition(
          stream?.codec_name === "h264"
            && stream?.pix_fmt === "yuv420p"
            && stream?.avg_frame_rate === "30/1"
            && Number(stream?.width) === 1280
            && Number(stream?.height) === 720
            && Math.abs(duration - Number(asset.duration_seconds)) < 0.001
            && Math.abs(duration - Number(videoProof.duration_seconds)) < 0.001
            && frameCount === Number(asset.frame_count)
            && frameCount === Number(videoProof.frame_count)
            && Number(format?.size) === asset.bytes
            && duration >= roles[slug].minimum
            && duration <= roles[slug].maximum
            && Math.abs(frameCount / duration - 30) < 0.1,
          `${relative}: codec, duration, dimensions, or frame commitment failed`,
        );
        requireCondition(
          !Object.keys(format?.tags || {}).some((key) => forbiddenMetadataKeys.has(key.toLowerCase())),
          `${relative}: identifying video metadata remains`,
        );
        run("ffmpeg", ["-v", "error", "-i", videoPath, "-map", "0:v:0", "-f", "null", "-"]);
        const dynamics = sampleDynamics(videoPath);
        requireCondition(
          dynamics.sampled === Number(videoProof.sampled_frame_count)
            && dynamics.unique === Number(videoProof.unique_sampled_frames)
            && dynamics.unique > timelineContract.length,
          `${relative}: dynamic continuous-capture evidence failed`,
        );
        const timeline = videoProof.timeline;
        requireCondition(Array.isArray(timeline) && timeline.length === timelineContract.length, `${relative}: exact timeline inventory failed`);
        let previousTime = -1;
        const frameHashes = new Set();
        for (let index = 0; index < timelineContract.length; index += 1) {
          const event = timeline[index];
          const [expectedEvent, expectedObservation] = timelineContract[index];
          requireCondition(
            event?.event === expectedEvent
              && event?.observation === expectedObservation
              && Number.isFinite(event.at_seconds)
              && event.at_seconds > previousTime
              && event.at_seconds < duration,
            `${relative}: timeline event ${index + 1} failed`,
          );
          previousTime = event.at_seconds;
          const frame = frameAt(videoPath, event.at_seconds);
          requireCondition(sha256(frame) === event.frame_sha256, `${relative}: frame commitment failed for ${expectedEvent}`);
          frameHashes.add(event.frame_sha256);
          if (locale === "en") englishFrames.set(`${proofKey}:${expectedEvent}`, frame);
        }
        requireCondition(frameHashes.size === timelineContract.length, `${relative}: event frames are not distinct`);
        if (slug === "purchase-delivery") {
          requireCondition(
            videoProof.continuous_capture === true
              && videoProof.actual_launcher_hub_observed === true
              && videoProof.actual_checkout_observed === true
              && videoProof.foreground_worker_observed === true
              && videoProof.visible_worker_terminal_observed === true
              && videoProof.final_status === "completed",
            `${relative}: purchase-delivery execution flags failed`,
          );
        } else {
          requireCondition(
            videoProof.continuous_capture === true
              && videoProof.actual_terminal_failure_observed === true
              && videoProof.actual_hub_scenario_transition_observed === true
              && videoProof.manual_retry_observed === true
              && videoProof.visible_worker_terminal_observed === true
              && videoProof.final_status === "recovered",
            `${relative}: failure-recovery execution flags failed`,
          );
        }
        summaries[`${locale}/${slug}`] = {
          duration_seconds: duration,
          frame_count: frameCount,
          unique_sampled_frames: dynamics.unique,
        };
      }

      for (const [proofName, filename] of [
        ["operator-failed.png", `${locale}/operator-failed-desktop.png`],
        ["operator-recovered.png", `${locale}/operator-recovered-desktop.png`],
      ]) {
        requireCondition(
          localizedProof.state_stills?.[proofName]?.sha256 === sha256(currentUiBytesByFile.get(filename)),
          `${locale}: ${proofName} state-still commitment failed`,
        );
      }

      const guidedRelative = `assets/media/pf07/videos/${locale}/guided-overview.mp4`;
      const purchaseRelative = `assets/media/pf07/videos/${locale}/purchase-delivery.mp4`;
      const guidedAsset = manifestByFile.get(guidedRelative);
      const guidedPath = path.join(temporaryRoot, `${locale}-guided-overview.mp4`);
      await fs.writeFile(guidedPath, mediaBytes.get(guidedRelative));
      const guidedProbe = JSON.parse(run("ffprobe", [
        "-v", "error",
        "-select_streams", "v:0",
        "-count_frames",
        "-show_entries", "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_read_frames:format=duration,size:format_tags",
        "-of", "json",
        guidedPath,
      ], "utf8"));
      const guidedStream = guidedProbe.streams?.[0];
      const guidedFormat = guidedProbe.format;
      const guidedDuration = Number(guidedFormat?.duration);
      const purchaseDuration = summaries[`${locale}/purchase-delivery`].duration_seconds;
      requireCondition(
        guidedAsset?.kind === "video"
          && guidedAsset.role === roles["guided-overview"].role
          && guidedAsset.derived_from === purchaseRelative
          && guidedAsset.transformation === "continuous-time-compression:setpts=0.64*PTS"
          && guidedStream?.codec_name === "h264"
          && guidedStream?.pix_fmt === "yuv420p"
          && guidedStream?.avg_frame_rate === "30/1"
          && Number(guidedStream?.width) === 1280
          && Number(guidedStream?.height) === 720
          && Number(guidedStream?.nb_read_frames) === guidedAsset.frame_count
          && Number(guidedFormat?.size) === guidedAsset.bytes
          && Math.abs(guidedDuration - guidedAsset.duration_seconds) < 0.001
          && guidedDuration >= roles["guided-overview"].minimum
          && guidedDuration <= roles["guided-overview"].maximum
          && Math.abs((guidedDuration / purchaseDuration) - 0.64) < 0.01
          && !Object.keys(guidedFormat?.tags || {}).some((key) => forbiddenMetadataKeys.has(key.toLowerCase())),
        `${guidedRelative}: guided continuous derivative contract failed`,
      );
      run("ffmpeg", ["-v", "error", "-i", guidedPath, "-map", "0:v:0", "-f", "null", "-"]);
      const guidedDynamics = sampleDynamics(guidedPath);
      requireCondition(guidedDynamics.unique > 12, `${guidedRelative}: guided tour is not a dynamic continuous recording`);
      summaries[`${locale}/guided-overview`] = {
        duration_seconds: guidedDuration,
        frame_count: Number(guidedStream.nb_read_frames),
        unique_sampled_frames: guidedDynamics.unique,
      };
    }

    const posterHashes = new Set();
    for (const locale of ["ko", "en"]) {
      for (const slug of Object.keys(roles)) {
        const posterRelative = `assets/media/pf07/posters/${locale}/${slug}.png`;
        const posterAsset = manifestByFile.get(posterRelative);
        requireCondition(
          posterAsset?.kind === "poster"
            && posterAsset.locale === locale
            && posterAsset.role === roles[slug].role
            && posterAsset.source_video === `assets/media/pf07/videos/${locale}/${slug}.mp4`
            && posterAsset.review_result === "ACCEPTED_STEP050_DIRECT_REVIEW",
          `${posterRelative}: poster authority failed`,
        );
        inspectPng(mediaBytes.get(posterRelative), posterAsset, posterRelative);
        posterHashes.add(posterAsset.sha256);

        const captionRelative = `assets/media/pf07/captions/${locale}/${slug}.vtt`;
        const captionAsset = manifestByFile.get(captionRelative);
        const captionBytes = mediaBytes.get(captionRelative);
        const captionText = captionBytes.toString("utf8");
        const videoDuration = summaries[`${locale}/${slug}`].duration_seconds;
        requireCondition(
          captionAsset?.kind === "captions"
            && captionAsset.format === "WEBVTT"
            && captionAsset.locale === locale
            && captionAsset.role === roles[slug].role
            && captionAsset.source_video === `assets/media/pf07/videos/${locale}/${slug}.mp4`
            && captionText.startsWith("WEBVTT\n")
            && !hasProtectedValue(captionText),
          `${captionRelative}: caption identity or boundary failed`,
        );
        const cues = [...captionText.matchAll(/(\d{2}:\d{2}(?::\d{2})?\.\d{3})\s+-->\s+(\d{2}:\d{2}(?::\d{2})?\.\d{3})/g)];
        requireCondition(cues.length >= 4, `${captionRelative}: too few caption cues`);
        let previousEnd = 0;
        for (const cue of cues) {
          const start = parseVttTimestamp(cue[1]);
          const end = parseVttTimestamp(cue[2]);
          requireCondition(
            start >= previousEnd - 0.001 && end > start && end <= videoDuration + 0.001,
            `${captionRelative}: caption timing contract failed`,
          );
          previousEnd = end;
        }
        requireCondition(
          locale === "ko" ? /[가-힣]/.test(captionText) : !/[ㄱ-ㆎ가-힣]/.test(captionText),
          `${captionRelative}: caption language boundary failed`,
        );
      }
    }
    requireCondition(posterHashes.size === 6, "localized outcome-specific posters are not all distinct");

    const retryState = proof.retry_wait_observation;
    requireCondition(
      retryState?.state === "retry_wait"
        && retryState?.http_status === 503
        && retryState?.attempt === 1
        && retryState?.capture_authority === expectedAuthorityFiles.retry_state_capture
        && retryState?.capture_authority_sha256 === authorityHashes.get(expectedAuthorityFiles.retry_state_capture),
      "retry-wait observation identity failed",
    );
    for (const locale of ["ko", "en"]) {
      const relative = `assets/media/pf07/current-ui/${locale}/operator-retrying-desktop.png`;
      requireCondition(
        retryState.assets?.[locale]?.file === relative
          && retryState.assets?.[locale]?.sha256 === sha256(currentUiBytesByFile.get(`${locale}/operator-retrying-desktop.png`)),
        `${locale}: actual retry-wait still commitment failed`,
      );
    }

    const ocrPolicy = {
      "demo-video.mp4": {
        LAUNCH_HUB: [/final linux package/i, /ready/i, /actual hub.*controls/i],
        CHECKOUT_INPUT: [/checkout/i, /test street/i, /seoul/i],
        ORDER_RECEIVED: [/woocommerce.*actual synthetic order/i],
        OUTBOX_PENDING: [/actual final admin/i, /order[\s._-]*cr\w*[\s._-]+pendin/i],
        WORKER_RUN: [/final package worker/i, /action-scheduler run/i],
        ADMIN_COMPLETED: [/order[\s._-]*created/i, /completed/i, /\b200\b/i],
        INTEGRATION_RESULT: [/woo.*pf[o0]7.*n(?:8)?n.*crm.*slack/i, /identifiers.*masked/i],
      },
      "recovery-clip.mp4": {
        OUTBOX_PENDING: [/same delivered\s+runtime/i, /order[\s._-]*cr\w*[\s._-]+pendin/i],
        FAILURE_WORKER_RUN: [/final package worker/i, /action-scheduler run/i],
        FAILED: [/manual retry now available/i, /422/i],
        NORMAL_SCENARIO: [/actual package hub control/i, /worker result/i],
        MANUAL_RETRY: [/actual administrator action/i, /scheduled one follow-up/i],
        RECOVERY_WORKER_RUN: [/final package worker/i, /action-scheduler run/i],
        RECOVERED: [/recovered/i, /http\s*200/i],
      },
    };
    const terminalEvents = new Set(["WORKER_RUN", "FAILURE_WORKER_RUN", "RECOVERY_WORKER_RUN"]);
    const worker = await createWorker("eng", 1, {
      langPath: englishData.langPath,
      gzip: englishData.gzip,
      cacheMethod: "none",
    });
    try {
      for (const [proofKey, events] of Object.entries(ocrPolicy)) {
        for (const [eventName, patterns] of Object.entries(events)) {
          const rectangle = terminalEvents.has(eventName)
            ? { left: 500, top: 475, width: 750, height: 220 }
            : { left: 840, top: 20, width: 420, height: 150 };
          const result = await worker.recognize(englishFrames.get(`${proofKey}:${eventName}`), { rectangle });
          const text = result.data.text.replace(/\s+/g, " ");
          requireCondition(
            patterns.every((pattern) => pattern.test(text)),
            `${proofKey}: deployed English frame text failed for ${eventName}`,
          );
        }
      }
    } finally {
      await worker.terminate();
    }
  } finally {
    await fs.rm(temporaryRoot, { recursive: true, force: true });
  }
  return {
    release_tag: expectedRelease.release_tag,
    media_manifest_sha256: sha256(manifestBytes),
    current_ui_manifest_sha256: sha256(currentUiBytes),
    execution_proof_sha256: sha256(proofBytes),
    localized_video_count: 6,
    localized_poster_count: 6,
    localized_caption_count: 6,
    localized_recording_proof_count: 2,
    current_ui_capture_count: 24,
    ocr_event_count: 14,
    videos: summaries,
  };
}

const expectedEvidenceLinks = [
  `https://github.com/Cetacean916/oddroom-woo-orderops/tree/${expectedReleaseTag}`,
  `https://github.com/Cetacean916/oddroom-woo-orderops/blob/${expectedReleaseTag}/evidence/refinement/public/acceptance-matrix.json`,
  `https://github.com/Cetacean916/oddroom-woo-orderops/blob/${expectedReleaseTag}/plugin/oddroom-orderops/tests/run.php`,
  `https://github.com/Cetacean916/oddroom-woo-orderops/blob/${expectedReleaseTag}/workflow/oddroom-orderops-vsl.json`,
  `https://github.com/Cetacean916/oddroom-woo-orderops/blob/${expectedReleaseTag}/docs/RECOVERY-RUNBOOK.md`,
  releaseManifestUrl.href,
  new URL("assets/media/pf07/execution-proof.json", deploymentRoot).href,
];
const expectedDownloadLinks = [
  `pf07-windows-x64-${expectedPackageVersion}.zip`,
  `pf07-windows-kvm-test-kit-${expectedPackageVersion}.zip`,
  `pf07-macos-universal-${expectedPackageVersion}.zip`,
  `pf07-linux-x86_64-${expectedPackageVersion}.tar.gz`,
  `pf07-linux-server-${expectedPackageVersion}.tar.gz`,
].map((filename) => `https://github.com/Cetacean916/oddroom-woo-orderops/releases/download/${expectedReleaseTag}/${filename}`);

async function validateBuyerPages(evidence) {
  await Promise.all(expectedEvidenceLinks.map(async (url) => {
    const response = await fetch(url, {
      headers: { "User-Agent": "PF07-public-validator/2", "Cache-Control": "no-cache" },
      signal: AbortSignal.timeout(30000),
    });
    requireCondition(response.ok, `buyer-verifiable link returned ${response.status}: ${url}`);
    await response.body?.cancel();
  }));
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const observations = [];
  try {
    for (const locale of ["ko", "en"]) {
      for (const width of [390, 768, 1440]) {
        const context = await browser.newContext({
          viewport: { width, height: 1000 },
          deviceScaleFactor: 1,
        });
        try {
          const page = await context.newPage();
          const consoleErrors = [];
          page.on("console", (message) => {
            if (message.type() === "error") consoleErrors.push(message.text());
          });
          page.on("pageerror", (error) => consoleErrors.push(error.message));
          await page.goto(caseRoutes[locale], { waitUntil: "networkidle", timeout: 30000 });
          await page.locator("[data-case-root] .pf07-case").waitFor({ state: "visible" });
          await page.locator("img").evaluateAll((images) => images.forEach((image) => { image.loading = "eager"; }));
          await page.evaluate(async () => {
            for (let y = 0; y < document.body.scrollHeight; y += 900) {
              window.scrollTo(0, y);
              await new Promise((resolve) => setTimeout(resolve, 15));
            }
            window.scrollTo(0, 0);
          });
          await page.waitForFunction(() => [...document.images].every((image) => image.complete), null, { timeout: 30000 });
          await page.waitForFunction(() => [...document.querySelectorAll("video")].every((video) => video.readyState >= 1), null, { timeout: 30000 });
          const audit = await page.evaluate(() => {
            const visibleActions = [...document.querySelectorAll("a,button")].filter((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
            });
            const shopper = document.querySelector(".pf07-role-lane.is-shopper");
            const handoff = document.querySelector(".pf07-role-handoff");
            const operator = document.querySelector(".pf07-role-lane.is-operator");
            return {
              lang: document.documentElement.lang,
              bodyLanguage: document.body.dataset.pf07Language,
              title: document.title,
              h1: document.querySelector("h1")?.textContent?.trim() || "",
              orientationTitle: document.querySelector("#pf07-orientation-title")?.textContent?.trim() || "",
              orientationBody: document.querySelector(".pf07-orientation > p")?.textContent?.trim() || "",
              scrollWidth: document.documentElement.scrollWidth,
              viewportWidth: innerWidth,
              brokenImages: [...document.images].filter((image) => image.naturalWidth === 0).length,
              clippedActions: visibleActions.filter((node) => node.scrollWidth > node.clientWidth + 2 || node.scrollHeight > node.clientHeight + 2).length,
              roleOrder: Boolean(shopper && handoff && operator
                && (shopper.compareDocumentPosition(handoff) & Node.DOCUMENT_POSITION_FOLLOWING)
                && (handoff.compareDocumentPosition(operator) & Node.DOCUMENT_POSITION_FOLLOWING)),
              shopperFigures: shopper?.querySelectorAll("figure").length || 0,
              operatorFigures: operator?.querySelectorAll("figure").length || 0,
              mediaCards: document.querySelectorAll(".pf07-media-card").length,
              videos: document.querySelectorAll(".pf07-media-card video").length,
              videoSources: [...document.querySelectorAll(".pf07-media-card video source")].map((source) => source.src),
              videoPosters: [...document.querySelectorAll(".pf07-media-card video")].map((video) => video.poster),
              captionTracks: [...document.querySelectorAll(".pf07-media-card video track")].map((track) => [track.srclang, track.src]),
              chapterCounts: [...document.querySelectorAll(".pf07-media-card")].map((card) => card.querySelectorAll(".pf07-chapters button").length),
              scorecard: [...document.querySelectorAll("[data-proof-scorecard] tbody tr")].map((row) => [
                row.querySelector("th")?.textContent?.trim() || "",
                row.querySelector("td")?.textContent?.trim() || "",
                row.querySelector("code")?.textContent?.trim() || "",
              ]),
              evidenceLinks: [...document.querySelectorAll("[data-evidence-links] a")].map((link) => link.href),
              downloadLinks: [...document.querySelectorAll(".pf07-download")].map((link) => link.href),
              claimsText: document.querySelector("[data-claims-boundary]")?.textContent || "",
              releaseBoundary: document.querySelector("[data-delivery-release-boundary]")?.textContent || "",
              activeLanguage: document.querySelector(".pf07-language [aria-current='page']")?.textContent?.trim() || "",
              canonical: document.querySelector("link[rel='canonical']")?.href || "",
            };
          });
          const expectedVideoSources = ["guided-overview", "purchase-delivery", "failure-recovery"]
            .map((slug) => new URL(`assets/media/pf07/videos/${locale}/${slug}.mp4`, deploymentRoot).href);
          const expectedPosters = ["guided-overview", "purchase-delivery", "failure-recovery"]
            .map((slug) => new URL(`assets/media/pf07/posters/${locale}/${slug}.png`, deploymentRoot).href);
          const expectedTracks = ["guided-overview", "purchase-delivery", "failure-recovery"]
            .map((slug) => [locale, new URL(`assets/media/pf07/captions/${locale}/${slug}.vtt`, deploymentRoot).href]);
          const expectedOrientation = locale === "ko"
            ? "각자의 자리에서, 필요한 경험에 집중하도록."
            : "Designed so each role can focus on the experience it needs.";
          requireCondition(
            audit.lang === locale
              && audit.bodyLanguage === locale
              && audit.title.includes("OFFSET")
              && audit.h1.includes("OFFSET / COMMERCE + OPERATIONS")
              && audit.orientationTitle === expectedOrientation
              && !audit.orientationTitle.includes("PF07")
              && !audit.orientationBody.includes("화면을 둘러보세요")
              && audit.canonical === caseRoutes[locale]
              && audit.activeLanguage.toLowerCase() === locale,
            `${locale}/${width}: localized buyer-page identity or copy failed`,
          );
          requireCondition(
            audit.scrollWidth <= audit.viewportWidth + 1
              && audit.brokenImages === 0
              && audit.clippedActions === 0
              && audit.roleOrder
              && audit.shopperFigures === 3
              && audit.operatorFigures === 3,
            `${locale}/${width}: layout, asset, or role-separation failure ${JSON.stringify(audit)}`,
          );
          requireCondition(
            audit.mediaCards === 3
              && audit.videos === 3
              && JSON.stringify(audit.videoSources) === JSON.stringify(expectedVideoSources)
              && JSON.stringify(audit.videoPosters) === JSON.stringify(expectedPosters)
              && JSON.stringify(audit.captionTracks) === JSON.stringify(expectedTracks)
              && JSON.stringify(audit.chapterCounts) === JSON.stringify([5, 6, 5]),
            `${locale}/${width}: localized three-part media inventory failed`,
          );
          requireCondition(
            JSON.stringify(audit.scorecard) === JSON.stringify(evidence.scorecards[locale])
              && JSON.stringify(audit.evidenceLinks) === JSON.stringify(expectedEvidenceLinks)
              && JSON.stringify(audit.downloadLinks) === JSON.stringify(expectedDownloadLinks)
              && audit.releaseBoundary.includes(expectedReleaseTag)
              && audit.releaseBoundary.includes("PUBLIC_PACKAGE_RELEASE_PASS"),
            `${locale}/${width}: evidence, download, or release-boundary presentation failed`,
          );
          const boundaryPhrases = locale === "ko"
            ? ["Formal exactly-once", "실결제", "Slack", "ON_DEMAND_ONLY"]
            : ["Formal exactly-once", "Live payments", "Slack", "ON_DEMAND_ONLY"];
          requireCondition(
            boundaryPhrases.every((phrase) => audit.claimsText.includes(phrase)),
            `${locale}/${width}: claims boundary is incomplete`,
          );
          const axe = await new AxeBuilder({ page }).analyze();
          const seriousViolations = axe.violations
            .filter((item) => ["serious", "critical"].includes(item.impact))
            .map((item) => ({
              id: item.id,
              impact: item.impact,
              targets: item.nodes.map((node) => node.target),
            }));
          requireCondition(
            seriousViolations.length === 0 && consoleErrors.length === 0,
            `${locale}/${width}: accessibility or console failure ${JSON.stringify({ seriousViolations, consoleErrors })}`,
          );
          const chapterButton = page.locator(".pf07-media-card").first().locator(".pf07-chapters button").nth(1);
          const targetSeconds = Number((await chapterButton.getAttribute("data-video-start")).split(":").reduce(
            (total, part) => (total * 60) + Number(part),
            0,
          ));
          await chapterButton.click();
          const observedTime = await page.locator(".pf07-media-card video").first().evaluate((video) => video.currentTime);
          requireCondition(Math.abs(observedTime - targetSeconds) < 0.25, `${locale}/${width}: chapter navigation did not seek the video`);
          observations.push({
            locale,
            width,
            serious_or_critical: 0,
            page_overflow: false,
            clipped_actions: 0,
            broken_images: 0,
            console_errors: 0,
            role_lanes: 2,
            video_count: 3,
            chapter_navigation: "PASS",
          });
        } finally {
          await context.close();
        }
      }
    }
  } finally {
    await browser.close();
  }
  return observations;
}

expectedRelease = await resolveExpectedRelease();
const evidence = await validatePublicEvidence();
const media = await validateExecutionMedia();
const observations = await validateBuyerPages(evidence);
console.log(JSON.stringify({
  schema_version: 2,
  result: "PASS",
  case_urls: caseRoutes,
  release: expectedRelease,
  evidence,
  media,
  observations,
}));
