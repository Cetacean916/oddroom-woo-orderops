#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const captureRoot = process.argv[2] ? path.resolve(process.argv[2]) : "";
const outputRoot = process.argv[3] ? path.resolve(process.argv[3]) : "";
const releaseManifestPath = process.argv[4] ? path.resolve(process.argv[4]) : "";
if (!captureRoot || !outputRoot || !releaseManifestPath) {
  throw new Error(
    "usage: scripts/build-public-media-manifest.mjs COMPLETE_CAPTURE_DIRECTORY NEW_SHOWCASE_MEDIA_DIRECTORY PF07_RELEASE_MANIFEST",
  );
}
if (fs.existsSync(outputRoot)) {
  throw new Error("refusing to replace an existing showcase media directory");
}

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const focusedProofName = "execution-proof.json";
const guidedProofName = "guided-execution-proof.json";
const focusedProofPath = path.join(captureRoot, focusedProofName);
const guidedProofPath = path.join(captureRoot, guidedProofName);
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const readCapture = (name) => fsp.readFile(path.join(captureRoot, name));
const readSource = (relative) => fsp.readFile(path.join(sourceRoot, relative));
const locales = [
  { slug: "ko", runtime: "ko_KR" },
  { slug: "en", runtime: "en_US" },
];
const roles = {
  "guided-overview": {
    role: "guided_overview",
    outcome: "full_storefront_checkout_and_separate_operator_tour",
    recorder: "scripts/record-guided-service-tour.mjs",
    proof: "guided",
    timelineSchema: "pf07.guided-service-tour.v1",
    expectedEvents: [
      "SERVICE_READY", "STOREFRONT_HOME", "PRODUCT_CATALOG", "PRODUCT_DETAIL",
      "CART_REVIEW", "CHECKOUT", "ORDER_COMPLETE", "OPERATOR_ORDER_REVIEW",
    ],
  },
  "purchase-delivery": {
    role: "purchase_delivery",
    outcome: "product_selection_to_completed_order_handoff",
    recorder: "scripts/record-public-media.mjs",
    proof: "focused",
    timelineSchema: "pf07.focused-public-media.v1",
    expectedEvents: [
      "LAUNCH_HUB", "LIVE_STOREFRONT", "SHOP_OPENED", "PRODUCT_SELECTED",
      "CART_READY", "CHECKOUT_INPUT", "ORDER_RECEIVED", "OUTBOX_PENDING",
      "WORKER_RUN", "ADMIN_COMPLETED", "INTEGRATION_RESULT",
    ],
  },
  "failure-recovery": {
    role: "failure_recovery",
    outcome: "failed_order_to_manual_retry_and_recovered",
    recorder: "scripts/record-public-media.mjs",
    proof: "focused",
    timelineSchema: "pf07.focused-public-media.v1",
    expectedEvents: [
      "OUTBOX_PENDING", "FAILURE_WORKER_RUN", "FAILED", "NORMAL_SCENARIO",
      "MANUAL_RETRY", "RECOVERY_WORKER_RUN", "RECOVERED",
    ],
  },
};

const requiredNames = [focusedProofName, guidedProofName];
for (const { slug } of locales) {
  for (const role of Object.keys(roles)) {
    requiredNames.push(
      `${slug}-${role}.mp4`,
      `${slug}-${role}.png`,
      `${slug}-${role}.vtt`,
      `${slug}-${role}.timeline.json`,
    );
  }
}
for (const name of requiredNames) {
  await fsp.access(path.join(captureRoot, name), fs.constants.R_OK);
}
await fsp.access(releaseManifestPath, fs.constants.R_OK);

const focusedProofBytes = await fsp.readFile(focusedProofPath);
const guidedProofBytes = await fsp.readFile(guidedProofPath);
const releaseManifestBytes = await fsp.readFile(releaseManifestPath);
const focusedProof = JSON.parse(focusedProofBytes.toString("utf8"));
const guidedProof = JSON.parse(guidedProofBytes.toString("utf8"));
const releaseManifest = JSON.parse(releaseManifestBytes.toString("utf8"));

if (
  focusedProof.schema_version !== 2
  || focusedProof.case_id !== "pf07"
  || focusedProof.classification !== "PUBLIC_SANITIZED_DIRECT_RUNTIME_RECORD"
  || focusedProof.metadata_stripped !== true
  || focusedProof.package_version !== "1.0.6"
  || focusedProof.package_artifact_id !== "pf07-linux-x86_64"
  || focusedProof.actual_checkout_observed !== true
  || focusedProof.visible_worker_terminal_observed !== true
) {
  throw new Error("focused execution proof identity is invalid");
}
if (
  guidedProof.schema_version !== 1
  || guidedProof.case_id !== "pf07"
  || guidedProof.classification !== "PUBLIC_SANITIZED_GUIDED_RUNTIME_RECORD"
  || guidedProof.metadata_stripped !== true
  || guidedProof.package_version !== focusedProof.package_version
  || guidedProof.package_artifact_id !== focusedProof.package_artifact_id
  || guidedProof.package_build_id !== focusedProof.package_build_id
  || guidedProof.package_artifact_manifest_sha256 !== focusedProof.package_artifact_manifest_sha256
  || guidedProof.exact_runtime_locale_count !== 2
) {
  throw new Error("guided execution proof identity is invalid");
}

const linuxAsset = releaseManifest.package_assets?.find(
  (asset) => asset.artifact_id === "pf07-linux-x86_64",
);
if (
  releaseManifest.schema !== "pf07.public-release-manifest.v1"
  || releaseManifest.package_version !== focusedProof.package_version
  || releaseManifest.release_tag !== "pf07-v1.0.6"
  || releaseManifest.build_id !== focusedProof.package_build_id
  || releaseManifest.repository?.source_commit !== releaseManifest.intended_published_release?.tag_target_commit
  || releaseManifest.repository?.source_tree !== releaseManifest.intended_published_release?.tag_target_tree
  || releaseManifest.final_ci?.head_sha !== releaseManifest.repository?.source_commit
  || releaseManifest.final_ci?.conclusion !== "success"
  || linuxAsset?.artifact_manifest_sha256 !== focusedProof.package_artifact_manifest_sha256
) {
  throw new Error("published 1.0.6 release identity does not match the recorded package");
}

const authorityFiles = {
  focused_recording: "scripts/record-public-media.mjs",
  guided_recording: "scripts/record-guided-service-tour.mjs",
  media_builder: "scripts/build-public-media-manifest.mjs",
};
const authorityBytes = {};
const captureAuthorities = {};
for (const [id, relative] of Object.entries(authorityFiles)) {
  const bytes = await readSource(relative);
  const publicFile = `assets/media/pf07/provenance/${path.basename(relative)}`;
  authorityBytes[id] = bytes;
  captureAuthorities[id] = {
    file: publicFile,
    sha256: sha256(bytes),
  };
}
if (
  focusedProof.recording_script_sha256 !== captureAuthorities.focused_recording.sha256
  || guidedProof.recording_script_sha256 !== captureAuthorities.guided_recording.sha256
) {
  throw new Error("recording source does not match its execution proof");
}

const release = {
  package_version: releaseManifest.package_version,
  release_tag: releaseManifest.release_tag,
  immutable_predecessor_tag: "pf07-v1.0.5",
  source_commit: releaseManifest.repository.source_commit,
  source_tree: releaseManifest.repository.source_tree,
  package_build_id: releaseManifest.build_id,
  artifact_set_sha256: releaseManifest.build_identity.artifact_set_manifest.sha256,
  release_manifest_sha256: sha256(releaseManifestBytes),
  linux_package_filename: linuxAsset.filename,
  linux_package_sha256: linuxAsset.sha256,
  linux_package_manifest_sha256: linuxAsset.artifact_manifest_sha256,
  release_url: releaseManifest.intended_published_release.release_url,
  publication_state: "PUBLIC_PACKAGE_RELEASE_ACTIVE",
};

function probeVideo(name) {
  const result = spawnSync(process.env.PF07_FFPROBE_PATH || "ffprobe", [
    "-v", "error",
    "-select_streams", "v:0",
    "-count_frames",
    "-show_entries",
    "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_read_frames:format=duration,size:format_tags",
    "-of", "json",
    path.join(captureRoot, name),
  ], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  if (result.status !== 0) {
    throw new Error(`${name}: ffprobe failed`);
  }
  const parsed = JSON.parse(result.stdout);
  const stream = parsed.streams?.[0];
  const format = parsed.format;
  if (!stream || !format) {
    throw new Error(`${name}: video stream is missing`);
  }
  const forbiddenMetadata = new Set([
    "artist", "author", "comment", "copyright", "creation_time", "description",
    "encoded_by", "location", "publisher", "synopsis", "title",
  ]);
  if (Object.keys(format.tags || {}).some((key) => forbiddenMetadata.has(key.toLowerCase()))) {
    throw new Error(`${name}: identifying metadata remains`);
  }
  return {
    codec: stream.codec_name,
    pixel_format: stream.pix_fmt,
    width: Number(stream.width),
    height: Number(stream.height),
    average_frame_rate: stream.avg_frame_rate,
    frame_count: Number(stream.nb_read_frames),
    duration_seconds: Number(Number(format.duration).toFixed(3)),
    bytes: Number(format.size),
  };
}

function pngInfo(bytes, name) {
  if (
    bytes.length < 24
    || !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  ) {
    throw new Error(`${name}: invalid PNG`);
  }
  let offset = 8;
  let sawHeader = false;
  let sawEnd = false;
  const identifyingChunks = new Set(["tEXt", "zTXt", "iTXt", "eXIf", "tIME"]);
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.subarray(offset + 4, offset + 8).toString("ascii");
    const end = offset + 12 + length;
    if (end > bytes.length || identifyingChunks.has(type)) {
      throw new Error(`${name}: truncated or identifying PNG chunk`);
    }
    if (!sawHeader) {
      sawHeader = type === "IHDR" && length === 13;
    }
    if (type === "IEND") {
      sawEnd = length === 0 && end === bytes.length;
      break;
    }
    offset = end;
  }
  if (!sawHeader || !sawEnd) {
    throw new Error(`${name}: incomplete PNG structure`);
  }
  return {
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
    bytes: bytes.length,
  };
}

function extractFrameHash(videoName, atSeconds, event) {
  const result = spawnSync(process.env.PF07_FFMPEG_PATH || "/usr/bin/ffmpeg", [
    "-hide_banner", "-loglevel", "error",
    "-i", path.join(captureRoot, videoName),
    "-ss", String(atSeconds),
    "-frames:v", "1",
    "-f", "image2pipe",
    "-vcodec", "png",
    "-",
  ], { maxBuffer: 32 * 1024 * 1024 });
  if (result.status !== 0) {
    throw new Error(`${videoName}: frame extraction failed for ${event}`);
  }
  return sha256(result.stdout);
}

function exactVideoFacts(actual, committed) {
  return (
    actual.codec === committed.codec
    && actual.pixel_format === committed.pixel_format
    && actual.width === Number(committed.width)
    && actual.height === Number(committed.height)
    && actual.frame_count === Number(committed.frame_count)
    && Math.abs(actual.duration_seconds - Number(committed.duration_seconds)) < 0.001
  );
}

function exactEvents(actual, expected) {
  return (
    Array.isArray(actual)
    && actual.length === expected.length
    && actual.every((event, index) => event.event === expected[index])
  );
}

const stagedAssets = [];
const assetBytesByTarget = new Map();
const uniqueHashes = {
  video: new Set(),
  poster: new Set(),
  captions: new Set(),
  timeline: new Set(),
};

for (const { slug, runtime } of locales) {
  for (const [mediaKind, contract] of Object.entries(roles)) {
    const prefix = `${slug}-${mediaKind}`;
    const videoName = `${prefix}.mp4`;
    const posterName = `${prefix}.png`;
    const captionsName = `${prefix}.vtt`;
    const timelineName = `${prefix}.timeline.json`;
    const [videoBytes, posterBytes, captionsBytes, timelineBytes] = await Promise.all([
      readCapture(videoName),
      readCapture(posterName),
      readCapture(captionsName),
      readCapture(timelineName),
    ]);
    const timelineText = timelineBytes.toString("utf8");
    const timeline = JSON.parse(timelineText);
    const chapters = timeline.chapters;
    const chapterSeconds = (chapterItem) => Number(
      contract.proof === "guided" ? chapterItem.seconds : chapterItem.at_seconds,
    );
    if (
      timeline.schema !== contract.timelineSchema
      || timeline.package_version !== focusedProof.package_version
      || timeline.build_id !== focusedProof.package_build_id
      || timeline.artifact_manifest_sha256 !== focusedProof.package_artifact_manifest_sha256
      || timeline.locale !== runtime
      || timeline.time_compression !== false
      || (contract.proof === "focused" && timeline.media_kind !== mediaKind)
      || !exactEvents(chapters, contract.expectedEvents)
      || !chapters.every((chapterItem, index) => (
        Number.isFinite(chapterSeconds(chapterItem))
        && chapterSeconds(chapterItem) >= 0
        && (index === 0 || chapterSeconds(chapterItem) > chapterSeconds(chapters[index - 1]))
        && typeof chapterItem.label === "string"
        && chapterItem.label.length > 0
      ))
    ) {
      throw new Error(`${timelineName}: timeline identity or chapter order differs`);
    }
    const captionsText = captionsBytes.toString("utf8");
    const cueBlocks = captionsText.trim().split(/\n{2,}/).slice(1);
    if (
      !captionsText.startsWith("WEBVTT\n")
      || cueBlocks.length !== chapters.length
      || !cueBlocks.every((cue, index) => (
        /^\d+\n\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}\n/.test(cue)
        && cue.split("\n").slice(2).join("\n").includes(chapters[index].label)
      ))
    ) {
      throw new Error(`${captionsName}: WebVTT chapter coverage differs`);
    }

    const videoFacts = probeVideo(videoName);
    const timelineSeconds = Number(timeline.total_seconds);
    if (
      !Number.isFinite(timelineSeconds)
      || Math.abs(videoFacts.duration_seconds - timelineSeconds) >= 1.5
      || chapters.some((chapterItem) => chapterSeconds(chapterItem) >= videoFacts.duration_seconds)
    ) {
      throw new Error(`${timelineName}: duration does not match the source video`);
    }

    const proofDocument = contract.proof === "guided" ? guidedProof : focusedProof;
    const videoProof = proofDocument.videos?.[videoName];
    const eventFrames = videoProof?.event_frames;
    if (
      !videoProof
      || videoProof.locale !== runtime
      || videoProof.media_kind !== mediaKind
      || videoProof.sha256 !== sha256(videoBytes)
      || videoProof.continuous_capture !== true
      || videoProof.time_compression !== false
      || (contract.proof === "guided" && videoProof.full_content_view !== true)
      || !exactVideoFacts(videoFacts, videoProof)
      || videoProof.poster?.file !== posterName
      || videoProof.poster?.sha256 !== sha256(posterBytes)
      || videoProof.captions?.file !== captionsName
      || videoProof.captions?.sha256 !== sha256(captionsBytes)
      || videoProof.timeline?.file !== timelineName
      || videoProof.timeline?.sha256 !== sha256(timelineBytes)
      || !exactEvents(eventFrames, contract.expectedEvents)
    ) {
      throw new Error(`${videoName}: execution proof commitment differs`);
    }
    for (let index = 0; index < eventFrames.length; index += 1) {
      const eventFrame = eventFrames[index];
      const timelineSeconds = chapterSeconds(chapters[index]);
      const proofSeconds = Number(
        contract.proof === "guided" ? eventFrame.seconds : eventFrame.at_seconds,
      );
      if (
        !Number.isFinite(proofSeconds)
        || Math.abs(proofSeconds - timelineSeconds) >= 0.001
        || !/^[0-9a-f]{64}$/.test(eventFrame.frame_sha256)
        || extractFrameHash(videoName, proofSeconds, eventFrame.event) !== eventFrame.frame_sha256
      ) {
        throw new Error(`${videoName}: ${eventFrame.event} frame commitment differs`);
      }
    }

    const common = {
      locale: slug,
      runtime_locale: runtime,
      role: contract.role,
      outcome: contract.outcome,
      capture_authority: captureAuthorities[`${contract.proof}_recording`].file,
      capture_authority_sha256: captureAuthorities[`${contract.proof}_recording`].sha256,
      continuous_runtime_capture: true,
      full_content_view: contract.proof === "guided",
      time_compression: false,
      metadata_stripped: true,
    };
    const targetBase = `assets/media/pf07`;
    const targetVideo = `${targetBase}/videos/${slug}/${mediaKind}.mp4`;
    const targetPoster = `${targetBase}/posters/${slug}/${mediaKind}.png`;
    const targetCaptions = `${targetBase}/captions/${slug}/${mediaKind}.vtt`;
    const targetTimeline = `${targetBase}/timelines/${slug}/${mediaKind}.json`;
    const proofFile = `${targetBase}/proof/${contract.proof}-execution-proof.json`;

    stagedAssets.push({
      asset_id: `PF07-VIDEO-${slug.toUpperCase()}-${mediaKind.toUpperCase().replaceAll("-", "_")}`,
      file: targetVideo,
      kind: "video",
      ...common,
      ...videoFacts,
      sha256: sha256(videoBytes),
      source_proof: proofFile,
      source_proof_sha256: sha256(contract.proof === "guided" ? guidedProofBytes : focusedProofBytes),
    });
    stagedAssets.push({
      asset_id: `PF07-POSTER-${slug.toUpperCase()}-${mediaKind.toUpperCase().replaceAll("-", "_")}`,
      file: targetPoster,
      kind: "poster",
      ...common,
      source_video: targetVideo,
      ...pngInfo(posterBytes, posterName),
      sha256: sha256(posterBytes),
    });
    stagedAssets.push({
      asset_id: `PF07-CAPTIONS-${slug.toUpperCase()}-${mediaKind.toUpperCase().replaceAll("-", "_")}`,
      file: targetCaptions,
      kind: "captions",
      format: "WEBVTT",
      ...common,
      source_video: targetVideo,
      bytes: captionsBytes.length,
      sha256: sha256(captionsBytes),
    });
    stagedAssets.push({
      asset_id: `PF07-TIMELINE-${slug.toUpperCase()}-${mediaKind.toUpperCase().replaceAll("-", "_")}`,
      file: targetTimeline,
      kind: "timeline",
      format: "JSON",
      ...common,
      source_video: targetVideo,
      bytes: timelineBytes.length,
      sha256: sha256(timelineBytes),
    });
    assetBytesByTarget.set(targetVideo, videoBytes);
    assetBytesByTarget.set(targetPoster, posterBytes);
    assetBytesByTarget.set(targetCaptions, captionsBytes);
    assetBytesByTarget.set(targetTimeline, timelineBytes);
    uniqueHashes.video.add(sha256(videoBytes));
    uniqueHashes.poster.add(sha256(posterBytes));
    uniqueHashes.captions.add(sha256(captionsBytes));
    uniqueHashes.timeline.add(sha256(timelineBytes));
  }
}

for (const [kind, digests] of Object.entries(uniqueHashes)) {
  if (digests.size !== 6) {
    throw new Error(`the six ${kind} assets are not distinct`);
  }
}

const aggregateProof = {
  schema: "pf07.localized-showcase-execution-proof.v4",
  case_id: "pf07",
  classification: "PUBLIC_SANITIZED_EXECUTION_PROOF",
  metadata_stripped: true,
  release,
  exact_runtime_locale_count: 2,
  actual_checkout_observed: true,
  visible_worker_terminal_observed: true,
  capture_authorities: captureAuthorities,
  source_proofs: {
    focused: {
      file: "assets/media/pf07/proof/focused-execution-proof.json",
      sha256: sha256(focusedProofBytes),
    },
    guided: {
      file: "assets/media/pf07/proof/guided-execution-proof.json",
      sha256: sha256(guidedProofBytes),
    },
  },
};
const aggregateProofBytes = Buffer.from(`${JSON.stringify(aggregateProof, null, 2)}\n`);
const manifest = {
  schema: "pf07.localized-showcase-media-manifest.v4",
  state: "CURRENT_RELEASE_BOUND",
  case_id: "pf07",
  classification: "PUBLIC_SANITIZED_LOCALIZED_RUNTIME_MEDIA",
  metadata_stripped: true,
  registration_manifest_case_count: 6,
  release,
  execution_proof: {
    file: "assets/media/pf07/execution-proof.json",
    sha256: sha256(aggregateProofBytes),
  },
  capture_authorities: captureAuthorities,
  source_commitments: {
    public_acceptance_matrix_sha256: sha256(
      await readSource("evidence/refinement/public/acceptance-matrix.json"),
    ),
    public_product_quality_record_sha256: sha256(
      await readSource("evidence/refinement/public/product-quality.json"),
    ),
    public_restore_drill_record_sha256: sha256(
      await readSource("evidence/refinement/public/restore-drill.json"),
    ),
    release_manifest_sha256: sha256(releaseManifestBytes),
  },
  exact_asset_count: stagedAssets.length,
  locale_asset_counts: { ko: 12, en: 12 },
  assets: stagedAssets,
};

for (const relative of [
  "videos/ko", "videos/en", "posters/ko", "posters/en",
  "captions/ko", "captions/en", "timelines/ko", "timelines/en",
  "proof", "provenance",
]) {
  await fsp.mkdir(path.join(outputRoot, relative), { recursive: true });
}
for (const [publicPath, bytes] of assetBytesByTarget) {
  const relative = publicPath.replace(/^assets\/media\/pf07\//, "");
  await fsp.writeFile(path.join(outputRoot, relative), bytes, { flag: "wx" });
}
await Promise.all([
  fsp.writeFile(path.join(outputRoot, "proof", "focused-execution-proof.json"), focusedProofBytes, { flag: "wx" }),
  fsp.writeFile(path.join(outputRoot, "proof", "guided-execution-proof.json"), guidedProofBytes, { flag: "wx" }),
  fsp.writeFile(path.join(outputRoot, "execution-proof.json"), aggregateProofBytes, { flag: "wx" }),
  fsp.writeFile(path.join(outputRoot, "media-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, { flag: "wx" }),
  ...Object.entries(authorityBytes).map(([id, bytes]) => fsp.writeFile(
    path.join(outputRoot, "provenance", path.basename(authorityFiles[id])),
    bytes,
    { flag: "wx" },
  )),
]);

process.stdout.write(`${JSON.stringify({
  output_directory: outputRoot,
  release_tag: release.release_tag,
  media_manifest_sha256: sha256(await fsp.readFile(path.join(outputRoot, "media-manifest.json"))),
  execution_proof_sha256: sha256(aggregateProofBytes),
  exact_asset_count: stagedAssets.length,
  locale_asset_counts: manifest.locale_asset_counts,
})}\n`);
