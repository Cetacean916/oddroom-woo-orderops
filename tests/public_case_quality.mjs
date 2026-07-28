import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

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
const expectedPackageVersion = "1.0.8";
const expectedReleaseTag = "pf07-v1.0.8";
const immutablePredecessorTag = "pf07-v1.0.7";
const mediaEvidencePackageVersion = "1.0.6";
const mediaEvidenceReleaseTag = "pf07-v1.0.6";
const mediaEvidencePredecessorTag = "pf07-v1.0.5";
const repositoryRoot = new URL("https://github.com/Cetacean916/oddroom-woo-orderops/");
const deploymentRoot = new URL("https://cetacean916.github.io/portfolio-showcase/");
const publicEvidenceRoot = new URL(
  `https://raw.githubusercontent.com/Cetacean916/oddroom-woo-orderops/${expectedReleaseTag}/`,
);
const releaseManifestUrl = new URL(
  `releases/download/${expectedReleaseTag}/PF07-RELEASE-MANIFEST.json`,
  repositoryRoot,
);
const mediaEvidenceReleaseManifestUrl = new URL(
  `releases/download/${mediaEvidenceReleaseTag}/PF07-RELEASE-MANIFEST.json`,
  repositoryRoot,
);
const caseRoutes = {
  ko: new URL("case-pf07-ko.html", deploymentRoot).href,
  en: new URL("case-pf07-en.html", deploymentRoot).href,
};
let expectedRelease;
let expectedMediaRelease;
const expectedTimelines = {
  "guided-overview": [
    "SERVICE_READY", "STOREFRONT_HOME", "PRODUCT_CATALOG", "PRODUCT_DETAIL",
    "CART_REVIEW", "CHECKOUT", "ORDER_COMPLETE", "OPERATOR_ORDER_REVIEW",
  ],
  "purchase-delivery": [
    "LAUNCH_HUB", "LIVE_STOREFRONT", "SHOP_OPENED", "PRODUCT_SELECTED",
    "CART_READY", "CHECKOUT_INPUT", "ORDER_RECEIVED", "OUTBOX_PENDING",
    "WORKER_RUN", "ADMIN_COMPLETED", "INTEGRATION_RESULT",
  ],
  "failure-recovery": [
    "OUTBOX_PENDING", "FAILURE_WORKER_RUN", "FAILED", "NORMAL_SCENARIO",
    "MANUAL_RETRY", "RECOVERY_WORKER_RUN", "RECOVERED",
  ],
};
const roles = {
  "guided-overview": { role: "guided_overview", minimum: 75, maximum: 120 },
  "purchase-delivery": { role: "purchase_delivery", minimum: 60, maximum: 90 },
  "failure-recovery": { role: "failure_recovery", minimum: 8, maximum: 35 },
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

async function resolveExpectedRelease({
  manifestUrl,
  packageVersion,
  releaseTag,
  predecessorTag,
  label,
}) {
  const manifestBytes = await fetchBytes(manifestUrl, label);
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const linuxPackage = manifest.package_assets?.find(
    (asset) => asset.artifact_id === "pf07-linux-x86_64",
  );
  requireCondition(
    manifest.schema === "pf07.public-release-manifest.v1"
      && manifest.package_version === packageVersion
      && manifest.release_tag === releaseTag
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
    `${label} identity failed`,
  );
  return {
    package_version: manifest.package_version,
    release_tag: manifest.release_tag,
    immutable_predecessor_tag: predecessorTag,
    source_commit: manifest.repository.source_commit,
    source_tree: manifest.repository.source_tree,
    package_build_id: manifest.build_id,
    artifact_set_sha256: manifest.build_identity.artifact_set_manifest.sha256,
    release_manifest_sha256: sha256(manifestBytes),
    linux_package_filename: linuxPackage.filename,
    linux_package_sha256: linuxPackage.sha256,
    linux_package_manifest_sha256: linuxPackage.artifact_manifest_sha256,
    release_url: manifest.intended_published_release.release_url,
    publication_state: "PUBLIC_PACKAGE_RELEASE_ACTIVE",
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
  const exactRelease = (release) => (
    release
    && Object.keys(release).length === Object.keys(expectedMediaRelease).length
    && Object.entries(expectedMediaRelease).every(([key, value]) => release[key] === value)
  );

  requireCondition(
    manifest.schema === "pf07.localized-showcase-media-manifest.v4"
      && manifest.state === "CURRENT_RELEASE_BOUND"
      && manifest.case_id === "pf07"
      && manifest.classification === "PUBLIC_SANITIZED_LOCALIZED_RUNTIME_MEDIA"
      && manifest.metadata_stripped === true
      && manifest.registration_manifest_case_count === 6
      && exactRelease(manifest.release),
    "localized media manifest identity failed",
  );
  requireCondition(
    proof.schema === "pf07.localized-showcase-execution-proof.v4"
      && proof.case_id === "pf07"
      && proof.classification === "PUBLIC_SANITIZED_EXECUTION_PROOF"
      && proof.metadata_stripped === true
      && proof.exact_runtime_locale_count === 2
      && proof.actual_checkout_observed === true
      && proof.visible_worker_terminal_observed === true
      && !Object.hasOwn(proof, "status")
      && !Object.hasOwn(proof, "result")
      && exactRelease(proof.release),
    "aggregate execution proof identity failed",
  );
  requireCondition(
    currentUi.schema === "pf07.current-ui-manifest.v4"
      && currentUi.state === "CURRENT_RELEASE_BOUND"
      && currentUi.case_id === "pf07"
      && currentUi.classification === "PUBLIC_SANITIZED_RUNTIME_CAPTURE"
      && currentUi.metadata_stripped === true
      && exactRelease(currentUi.release),
    "current UI manifest identity failed",
  );
  requireCondition(
    !hasProtectedValue(manifestBytes.toString("utf8"))
      && !hasProtectedValue(proofBytes.toString("utf8"))
      && !hasProtectedValue(currentUiBytes.toString("utf8"))
      && manifest.execution_proof?.file === "assets/media/pf07/execution-proof.json"
      && manifest.execution_proof?.sha256 === sha256(proofBytes),
    "deployed media commitment or public-data boundary failed",
  );

  const expectedMediaAuthorities = {
    focused_recording: "assets/media/pf07/provenance/record-public-media.mjs",
    guided_recording: "assets/media/pf07/provenance/record-guided-service-tour.mjs",
    media_builder: "assets/media/pf07/provenance/build-public-media-manifest.mjs",
  };
  const authorityHashes = new Map();
  await Promise.all(Object.entries(expectedMediaAuthorities).map(async ([id, relative]) => {
    const bytes = await fetchDeployment(relative);
    const digest = sha256(bytes);
    requireCondition(
      manifest.capture_authorities?.[id]?.file === relative
        && manifest.capture_authorities?.[id]?.sha256 === digest
        && proof.capture_authorities?.[id]?.file === relative
        && proof.capture_authorities?.[id]?.sha256 === digest,
      `${id}: media capture-authority commitment failed`,
    );
    authorityHashes.set(relative, digest);
  }));
  requireCondition(
    Object.keys(currentUi.capture_authorities || {}).length >= 1
      && currentUi.capture_authorities?.still_capture,
    "current UI capture authority is missing",
  );
  await Promise.all(Object.entries(currentUi.capture_authorities).map(async ([id, authority]) => {
    requireCondition(
      /^assets\/media\/pf07\/provenance\/[a-z0-9.-]+\.mjs$/.test(authority?.file || "")
        && /^[0-9a-f]{64}$/.test(authority?.sha256 || ""),
      `${id}: current UI capture-authority shape failed`,
    );
    const bytes = await fetchDeployment(authority.file);
    const digest = sha256(bytes);
    requireCondition(digest === authority.sha256, `${id}: current UI capture-authority hash failed`);
    authorityHashes.set(authority.file, digest);
  }));

  const sourceProofContracts = {
    focused: {
      file: "assets/media/pf07/proof/focused-execution-proof.json",
      schemaVersion: 2,
      classification: "PUBLIC_SANITIZED_DIRECT_RUNTIME_RECORD",
      recorder: expectedMediaAuthorities.focused_recording,
    },
    guided: {
      file: "assets/media/pf07/proof/guided-execution-proof.json",
      schemaVersion: 1,
      classification: "PUBLIC_SANITIZED_GUIDED_RUNTIME_RECORD",
      recorder: expectedMediaAuthorities.guided_recording,
    },
  };
  const sourceProofs = {};
  const sourceProofHashes = {};
  await Promise.all(Object.entries(sourceProofContracts).map(async ([id, contract]) => {
    const bytes = await fetchDeployment(contract.file);
    const digest = sha256(bytes);
    const document = JSON.parse(bytes.toString("utf8"));
    requireCondition(
      proof.source_proofs?.[id]?.file === contract.file
        && proof.source_proofs?.[id]?.sha256 === digest
        && document.schema_version === contract.schemaVersion
        && document.case_id === "pf07"
        && document.classification === contract.classification
        && document.metadata_stripped === true
        && document.package_version === expectedMediaRelease.package_version
        && document.package_artifact_id === "pf07-linux-x86_64"
        && document.package_build_id === expectedMediaRelease.package_build_id
        && document.package_artifact_manifest_sha256 === expectedMediaRelease.linux_package_manifest_sha256
        && document.recording_script_sha256 === authorityHashes.get(contract.recorder)
        && !Object.hasOwn(document, "status")
        && !Object.hasOwn(document, "result")
        && !hasProtectedValue(bytes.toString("utf8")),
      `${id}: source execution proof identity failed`,
    );
    sourceProofs[id] = document;
    sourceProofHashes[id] = digest;
  }));
  requireCondition(
    sourceProofs.focused.actual_checkout_observed === true
      && sourceProofs.focused.visible_worker_terminal_observed === true
      && sourceProofs.guided.exact_runtime_locale_count === 2,
    "source execution proof observation boundary failed",
  );

  const expectedMediaFiles = [];
  for (const locale of ["ko", "en"]) {
    for (const slug of Object.keys(roles)) {
      expectedMediaFiles.push(
        `assets/media/pf07/videos/${locale}/${slug}.mp4`,
        `assets/media/pf07/posters/${locale}/${slug}.png`,
        `assets/media/pf07/captions/${locale}/${slug}.vtt`,
        `assets/media/pf07/timelines/${locale}/${slug}.json`,
      );
    }
  }
  expectedMediaFiles.sort();
  requireCondition(
    manifest.exact_asset_count === 24
      && manifest.locale_asset_counts?.ko === 12
      && manifest.locale_asset_counts?.en === 12
      && manifest.assets?.length === 24
      && new Set(manifest.assets.map((asset) => asset.asset_id)).size === 24
      && JSON.stringify(manifest.assets.map((asset) => asset.file).sort()) === JSON.stringify(expectedMediaFiles),
    "localized media exact 24-asset set failed",
  );

  const expectedCurrentFiles = ["ko", "en"]
    .flatMap((locale) => expectedCurrentUiSurfaces.map(
      (filename) => `assets/media/pf07/current-ui/${locale}/${filename}`,
    ))
    .sort();
  requireCondition(
    currentUi.exact_file_count === 24
      && currentUi.locale_asset_counts?.ko === 12
      && currentUi.locale_asset_counts?.en === 12
      && currentUi.assets?.length === 24
      && new Set(currentUi.assets.map((asset) => asset.asset_id)).size === 24
      && JSON.stringify(currentUi.assets.map((asset) => asset.file).sort()) === JSON.stringify(expectedCurrentFiles),
    "current UI exact 24-asset inventory failed",
  );

  const mediaBytes = new Map();
  await Promise.all(manifest.assets.map(async (asset) => {
    const bytes = await fetchDeployment(asset.file);
    requireCondition(
      bytes.length === Number(asset.bytes) && sha256(bytes) === asset.sha256,
      `${asset.file}: deployed byte commitment failed`,
    );
    mediaBytes.set(asset.file, bytes);
  }));
  await Promise.all(currentUi.assets.map(async (asset) => {
    const bytes = await fetchDeployment(asset.file);
    const expectedRuntimeLocale = asset.locale === "ko" ? "ko_KR" : "en_US";
    requireCondition(
      asset.runtime_locale === expectedRuntimeLocale
        && asset.source_kind === "direct-runtime-capture"
        && asset.transformation === "promoted-without-pixel-mutation"
        && asset.metadata_stripped === true
        && /^\d{4}-\d{2}-\d{2}$/.test(asset.observed_on || ""),
      `${asset.file}: current UI capture identity failed`,
    );
    inspectPng(bytes, asset, asset.file);
  }));

  const manifestByFile = new Map(manifest.assets.map((asset) => [asset.file, asset]));
  const temporaryRoot = await fs.mkdtemp(path.join(
    process.env.PF07_SCRATCH_ROOT || os.tmpdir(),
    "pf07-public-case-",
  ));
  const summaries = {};
  const uniqueHashes = {
    video: new Set(),
    poster: new Set(),
    captions: new Set(),
    timeline: new Set(),
  };
  try {
    for (const locale of ["ko", "en"]) {
      const runtimeLocale = locale === "ko" ? "ko_KR" : "en_US";
      for (const [slug, contract] of Object.entries(roles)) {
        const proofKind = slug === "guided-overview" ? "guided" : "focused";
        const sourceProof = sourceProofs[proofKind];
        const sourceProofFile = sourceProofContracts[proofKind].file;
        const sourceName = `${locale}-${slug}.mp4`;
        const videoProof = sourceProof.videos?.[sourceName];
        const videoRelative = `assets/media/pf07/videos/${locale}/${slug}.mp4`;
        const posterRelative = `assets/media/pf07/posters/${locale}/${slug}.png`;
        const captionRelative = `assets/media/pf07/captions/${locale}/${slug}.vtt`;
        const timelineRelative = `assets/media/pf07/timelines/${locale}/${slug}.json`;
        const videoAsset = manifestByFile.get(videoRelative);
        const posterAsset = manifestByFile.get(posterRelative);
        const captionAsset = manifestByFile.get(captionRelative);
        const timelineAsset = manifestByFile.get(timelineRelative);
        const videoBytes = mediaBytes.get(videoRelative);
        const posterBytes = mediaBytes.get(posterRelative);
        const captionBytes = mediaBytes.get(captionRelative);
        const timelineBytes = mediaBytes.get(timelineRelative);
        const recorder = expectedMediaAuthorities[`${proofKind}_recording`];

        requireCondition(
          videoAsset?.kind === "video"
            && videoAsset.locale === locale
            && videoAsset.runtime_locale === runtimeLocale
            && videoAsset.role === contract.role
            && videoAsset.capture_authority === recorder
            && videoAsset.capture_authority_sha256 === authorityHashes.get(recorder)
            && videoAsset.continuous_runtime_capture === true
            && videoAsset.full_content_view === (proofKind === "guided")
            && videoAsset.time_compression === false
            && videoAsset.metadata_stripped === true
            && videoAsset.source_proof === sourceProofFile
            && videoAsset.source_proof_sha256 === sourceProofHashes[proofKind]
            && videoAsset.sha256 === videoProof?.sha256,
          `${videoRelative}: runtime video proof binding failed`,
        );

        const videoPath = path.join(temporaryRoot, `${locale}-${slug}.mp4`);
        await fs.writeFile(videoPath, videoBytes);
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
        const expectedWidth = slug === "guided-overview" ? 1440 : 1280;
        const expectedHeight = slug === "guided-overview" ? 900 : 720;
        requireCondition(
          stream?.codec_name === "h264"
            && stream?.pix_fmt === "yuv420p"
            && stream?.avg_frame_rate === "30/1"
            && Number(stream?.width) === expectedWidth
            && Number(stream?.height) === expectedHeight
            && frameCount === Number(videoAsset.frame_count)
            && frameCount === Number(videoProof?.frame_count)
            && Number(format?.size) === Number(videoAsset.bytes)
            && Math.abs(duration - Number(videoAsset.duration_seconds)) < 0.001
            && Math.abs(duration - Number(videoProof?.duration_seconds)) < 0.001
            && duration >= contract.minimum
            && duration <= contract.maximum
            && Math.abs(frameCount / duration - 30) < 0.1
            && !Object.keys(format?.tags || {}).some((key) => forbiddenMetadataKeys.has(key.toLowerCase())),
          `${videoRelative}: codec, dimensions, duration, or frame commitment failed`,
        );
        run("ffmpeg", ["-v", "error", "-i", videoPath, "-map", "0:v:0", "-f", "null", "-"]);

        const timelineText = timelineBytes.toString("utf8");
        const timeline = JSON.parse(timelineText);
        const chapters = timeline.chapters;
        const expectedEvents = expectedTimelines[slug];
        const chapterSeconds = (chapter) => Number(
          proofKind === "guided" ? chapter.seconds : chapter.at_seconds,
        );
        requireCondition(
          timelineAsset?.kind === "timeline"
            && timelineAsset.format === "JSON"
            && timelineAsset.locale === locale
            && timelineAsset.role === contract.role
            && timelineAsset.source_video === videoRelative
            && timeline.schema === (proofKind === "guided"
              ? "pf07.guided-service-tour.v1"
              : "pf07.focused-public-media.v1")
            && timeline.package_version === expectedMediaRelease.package_version
            && timeline.build_id === expectedMediaRelease.package_build_id
            && timeline.artifact_manifest_sha256 === expectedMediaRelease.linux_package_manifest_sha256
            && timeline.locale === runtimeLocale
            && timeline.time_compression === false
            && (proofKind === "guided" || timeline.media_kind === slug)
            && Number.isFinite(Number(timeline.total_seconds))
            && Math.abs(Number(timeline.total_seconds) - duration) < 1.5
            && Array.isArray(chapters)
            && chapters.length === expectedEvents.length
            && chapters.every((chapter, index) => (
              chapter.event === expectedEvents[index]
              && typeof chapter.label === "string"
              && chapter.label.length > 0
              && Number.isFinite(chapterSeconds(chapter))
              && chapterSeconds(chapter) >= 0
              && chapterSeconds(chapter) < duration
              && (index === 0 || chapterSeconds(chapter) > chapterSeconds(chapters[index - 1]))
            )),
          `${timelineRelative}: timeline identity or chapter order failed`,
        );

        const captionText = captionBytes.toString("utf8");
        const cues = [...captionText.matchAll(
          /(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}\.\d{3})/g,
        )];
        requireCondition(
          captionAsset?.kind === "captions"
            && captionAsset.format === "WEBVTT"
            && captionAsset.locale === locale
            && captionAsset.role === contract.role
            && captionAsset.source_video === videoRelative
            && captionText.startsWith("WEBVTT\n")
            && cues.length === chapters.length
            && !hasProtectedValue(captionText)
            && (locale === "ko" ? /[가-힣]/.test(captionText) : !/[ㄱ-ㆎ가-힣]/.test(captionText)),
          `${captionRelative}: caption identity or language failed`,
        );
        let previousCueEnd = 0;
        for (const cue of cues) {
          const start = parseVttTimestamp(cue[1]);
          const end = parseVttTimestamp(cue[2]);
          requireCondition(
            start >= previousCueEnd - 0.001 && end > start && end <= duration + 0.001,
            `${captionRelative}: caption timing failed`,
          );
          previousCueEnd = end;
        }

        requireCondition(
          posterAsset?.kind === "poster"
            && posterAsset.locale === locale
            && posterAsset.role === contract.role
            && posterAsset.source_video === videoRelative,
          `${posterRelative}: poster identity failed`,
        );
        inspectPng(posterBytes, posterAsset, posterRelative);

        requireCondition(
          videoProof?.locale === runtimeLocale
            && videoProof.media_kind === slug
            && videoProof.continuous_capture === true
            && videoProof.time_compression === false
            && (proofKind !== "guided" || videoProof.full_content_view === true)
            && videoProof.poster?.file === `${locale}-${slug}.png`
            && videoProof.poster?.sha256 === posterAsset.sha256
            && videoProof.captions?.file === `${locale}-${slug}.vtt`
            && videoProof.captions?.sha256 === captionAsset.sha256
            && videoProof.timeline?.file === `${locale}-${slug}.timeline.json`
            && videoProof.timeline?.sha256 === timelineAsset.sha256
            && Array.isArray(videoProof.event_frames)
            && videoProof.event_frames.length === expectedEvents.length,
          `${videoRelative}: source recording proof failed`,
        );
        for (let index = 0; index < expectedEvents.length; index += 1) {
          const eventFrame = videoProof.event_frames[index];
          const seconds = Number(proofKind === "guided" ? eventFrame.seconds : eventFrame.at_seconds);
          requireCondition(
            eventFrame.event === expectedEvents[index]
              && Math.abs(seconds - chapterSeconds(chapters[index])) < 0.001
              && sha256(frameAt(videoPath, seconds)) === eventFrame.frame_sha256,
            `${videoRelative}: ${expectedEvents[index]} frame commitment failed`,
          );
        }

        uniqueHashes.video.add(videoAsset.sha256);
        uniqueHashes.poster.add(posterAsset.sha256);
        uniqueHashes.captions.add(captionAsset.sha256);
        uniqueHashes.timeline.add(timelineAsset.sha256);
        summaries[`${locale}/${slug}`] = {
          duration_seconds: duration,
          frame_count: frameCount,
        };
      }
    }
  } finally {
    await fs.rm(temporaryRoot, { recursive: true, force: true });
  }
  for (const [kind, hashes] of Object.entries(uniqueHashes)) {
    requireCondition(hashes.size === 6, `localized ${kind} assets are not all distinct`);
  }

  return {
    release_tag: expectedMediaRelease.release_tag,
    media_manifest_sha256: sha256(manifestBytes),
    current_ui_manifest_sha256: sha256(currentUiBytes),
    execution_proof_sha256: sha256(proofBytes),
    localized_video_count: 6,
    localized_poster_count: 6,
    localized_caption_count: 6,
    localized_timeline_count: 6,
    source_execution_proof_count: 2,
    current_ui_capture_count: 24,
    videos: summaries,
  };
}

const expectedDownloadLinks = [
  `pf07-windows-x64-${expectedPackageVersion}.zip`,
  `pf07-windows-kvm-test-kit-${expectedPackageVersion}.zip`,
  `pf07-macos-universal-${expectedPackageVersion}.zip`,
  `pf07-linux-x86_64-${expectedPackageVersion}.tar.gz`,
  `pf07-linux-server-${expectedPackageVersion}.tar.gz`,
].map((filename) => `https://github.com/Cetacean916/oddroom-woo-orderops/releases/download/${expectedReleaseTag}/${filename}`);

async function validateBuyerPages() {
  const expectedTechnicalLinks = [
    `https://github.com/Cetacean916/oddroom-woo-orderops/tree/${expectedReleaseTag}`,
    `https://github.com/Cetacean916/oddroom-woo-orderops/releases/tag/${expectedReleaseTag}`,
    new URL("assets/media/pf07/execution-proof.json", deploymentRoot).href,
  ];
  await Promise.all([...expectedTechnicalLinks, ...expectedDownloadLinks].map(async (url) => {
    const response = await fetch(url, {
      headers: { "User-Agent": "PF07-public-validator/3", "Cache-Control": "no-cache" },
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
          await page.waitForFunction(
            () => [...document.images].every((image) => image.complete),
            null,
            { timeout: 30000 },
          );
          await page.waitForFunction(
            () => [...document.querySelectorAll("video")].every((video) => video.readyState >= 1),
            null,
            { timeout: 30000 },
          );

          const audit = await page.evaluate(() => {
            const visibleActions = [...document.querySelectorAll("a,button")].filter((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.display !== "none"
                && style.visibility !== "hidden"
                && rect.width > 0
                && rect.height > 0;
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
              orientationBody: document.querySelector(".pf07-orientation-copy > p:last-child")?.textContent?.trim() || "",
              scrollWidth: document.documentElement.scrollWidth,
              viewportWidth: innerWidth,
              brokenImages: [...document.images].filter((image) => image.naturalWidth === 0).length,
              clippedActions: visibleActions.filter(
                (node) => node.scrollWidth > node.clientWidth + 2 || node.scrollHeight > node.clientHeight + 2,
              ).length,
              roleOrder: Boolean(
                shopper
                && handoff
                && operator
                && (shopper.compareDocumentPosition(handoff) & Node.DOCUMENT_POSITION_FOLLOWING)
                && (handoff.compareDocumentPosition(operator) & Node.DOCUMENT_POSITION_FOLLOWING)
              ),
              shopperFigures: shopper?.querySelectorAll("figure").length || 0,
              operatorFigures: operator?.querySelectorAll("figure").length || 0,
              mediaCards: document.querySelectorAll(".pf07-media-card").length,
              videoSources: [...document.querySelectorAll(".pf07-media-card video source")]
                .map((source) => source.src),
              videoPosters: [...document.querySelectorAll(".pf07-media-card video")]
                .map((video) => video.poster),
              captionTracks: [...document.querySelectorAll(".pf07-media-card video track")]
                .map((track) => [track.srclang, track.src]),
              chapterCounts: [...document.querySelectorAll(".pf07-media-card")]
                .map((card) => card.querySelectorAll(".pf07-chapters button").length),
              downloadLinks: [...document.querySelectorAll(".pf07-download")].map((link) => link.href),
              technicalLinks: [...document.querySelectorAll(".pf07-technical-details a")]
                .map((link) => link.href),
              releaseBoundary: document.querySelector("[data-delivery-release-boundary]")?.textContent || "",
              boundaryText: document.querySelector(".pf07-boundary")?.textContent || "",
              inquiryButton: document.querySelector("[data-copy-brief]")?.textContent?.trim() || "",
              inquiryLink: document.querySelector(".case-bottom-nav a[href='inquiry-automation.html']")?.href || "",
              activeLanguage: document.querySelector(".pf07-language [aria-current='page']")?.textContent?.trim() || "",
              canonical: document.querySelector("link[rel='canonical']")?.href || "",
              alternates: [...document.querySelectorAll("link[rel='alternate'][hreflang]")]
                .map((link) => [link.hreflang, link.href]),
            };
          });

          const expectedVideoSources = ["guided-overview", "purchase-delivery", "failure-recovery"]
            .map((slug) => new URL(`assets/media/pf07/videos/${locale}/${slug}.mp4`, deploymentRoot).href);
          const expectedPosters = ["guided-overview", "purchase-delivery", "failure-recovery"]
            .map((slug) => new URL(`assets/media/pf07/posters/${locale}/${slug}.png`, deploymentRoot).href);
          const expectedTracks = ["guided-overview", "purchase-delivery", "failure-recovery"]
            .map((slug) => [
              locale,
              new URL(`assets/media/pf07/captions/${locale}/${slug}.vtt`, deploymentRoot).href,
            ]);
          const expectedOrientation = locale === "ko"
            ? "각자의 자리에서, 필요한 경험에 집중하도록."
            : "Each role stays focused on the experience it needs.";
          const expectedBoundaryPhrases = locale === "ko"
            ? ["합성", "비금전", "실제 도입"]
            : ["synthetic", "non-monetary", "live rollout"];

          requireCondition(
            audit.lang === locale
              && audit.bodyLanguage === locale
              && audit.title.includes("OFFSET")
              && audit.h1.includes("OFFSET / COMMERCE + OPERATIONS")
              && audit.orientationTitle.replace(/\s+/g, " ") === expectedOrientation
              && !audit.orientationTitle.includes("PF07")
              && !audit.orientationBody.includes("화면을 둘러보세요")
              && audit.canonical === caseRoutes[locale]
              && audit.activeLanguage.toLowerCase() === locale
              && JSON.stringify(audit.alternates) === JSON.stringify([
                ["ko", caseRoutes.ko],
                ["en", caseRoutes.en],
              ]),
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
              && JSON.stringify(audit.videoSources) === JSON.stringify(expectedVideoSources)
              && JSON.stringify(audit.videoPosters) === JSON.stringify(expectedPosters)
              && JSON.stringify(audit.captionTracks) === JSON.stringify(expectedTracks)
              && JSON.stringify(audit.chapterCounts) === JSON.stringify([8, 11, 7]),
            `${locale}/${width}: localized three-part media inventory failed`,
          );
          requireCondition(
            JSON.stringify(audit.downloadLinks) === JSON.stringify(expectedDownloadLinks)
              && JSON.stringify(audit.technicalLinks) === JSON.stringify(expectedTechnicalLinks)
              && audit.releaseBoundary.includes(expectedReleaseTag)
              && expectedBoundaryPhrases.every((phrase) => (
                audit.boundaryText.toLowerCase().includes(phrase.toLowerCase())
              ))
              && audit.inquiryButton.length > 0
              && audit.inquiryLink === new URL("inquiry-automation.html", deploymentRoot).href,
            `${locale}/${width}: release, boundary, or inquiry presentation failed`,
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

          const chapterButton = page.locator(".pf07-media-card").first()
            .locator(".pf07-chapters button").nth(1);
          const targetSeconds = Number((await chapterButton.getAttribute("data-video-start"))
            .split(":")
            .reduce((total, part) => (total * 60) + Number(part), 0));
          await chapterButton.click();
          const observedTime = await page.locator(".pf07-media-card video").first()
            .evaluate((video) => video.currentTime);
          requireCondition(
            Math.abs(observedTime - targetSeconds) < 0.25,
            `${locale}/${width}: chapter navigation did not seek the video`,
          );
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

expectedRelease = await resolveExpectedRelease({
  manifestUrl: releaseManifestUrl,
  packageVersion: expectedPackageVersion,
  releaseTag: expectedReleaseTag,
  predecessorTag: immutablePredecessorTag,
  label: "current PF07 release manifest",
});
expectedMediaRelease = await resolveExpectedRelease({
  manifestUrl: mediaEvidenceReleaseManifestUrl,
  packageVersion: mediaEvidencePackageVersion,
  releaseTag: mediaEvidenceReleaseTag,
  predecessorTag: mediaEvidencePredecessorTag,
  label: "PF07 1.0.6 media-evidence release manifest",
});
const evidence = await validatePublicEvidence();
const media = await validateExecutionMedia();
const observations = await validateBuyerPages();
console.log(JSON.stringify({
  schema_version: 2,
  result: "PASS",
  case_urls: caseRoutes,
  release: expectedRelease,
  evidence,
  media,
  observations,
}));
