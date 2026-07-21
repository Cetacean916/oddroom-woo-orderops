#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const mediaRoot = process.argv[2] ? path.resolve(process.argv[2]) : '';
if (!mediaRoot) throw new Error('usage: scripts/build-public-media-manifest.mjs MEDIA_DIR');

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outputPath = path.join(mediaRoot, 'media-manifest.json');
if (fs.existsSync(outputPath)) throw new Error('refusing to replace an existing public media manifest');

const sha256 = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const read = async (relative) => fsp.readFile(path.join(mediaRoot, relative));
const sourceBytes = async (relative) => fsp.readFile(path.join(sourceRoot, relative));
const imageNames = [
  'main-image.png', 'detail-01-overview.png', 'detail-02-flow.png',
  'detail-03-result.png', 'video-poster.png',
];
const videoNames = ['demo-video.mp4', 'recovery-clip.mp4'];
const requiredNames = [...imageNames, ...videoNames, 'execution-proof.json'];
for (const name of requiredNames) await fsp.access(path.join(mediaRoot, name), fs.constants.R_OK);

const proofBytes = await read('execution-proof.json');
const proof = JSON.parse(proofBytes.toString('utf8'));
if (proof.schema_version !== 1 || proof.case_id !== 'pf07'
  || proof.classification !== 'PUBLIC_SANITIZED_EXECUTION_PROOF') {
  throw new Error('execution proof identity is invalid');
}

const recordingScriptBytes = await sourceBytes('scripts/record-public-media.mjs');
const stillScriptBytes = await sourceBytes('scripts/build-public-stills.mjs');
if (sha256(recordingScriptBytes) !== proof.recording_script_sha256) {
  throw new Error('recording script does not match the execution proof');
}

const sourceCommitments = {
  public_acceptance_matrix_sha256: sha256(await sourceBytes('evidence/refinement/public/acceptance-matrix.json')),
  public_product_quality_record_sha256: sha256(await sourceBytes('evidence/refinement/public/product-quality.json')),
  public_restore_drill_record_sha256: sha256(await sourceBytes('evidence/refinement/public/restore-drill.json')),
  execution_proof_sha256: sha256(proofBytes),
  recording_script_sha256: sha256(recordingScriptBytes),
  still_composition_script_sha256: sha256(stillScriptBytes),
};

const assets = {};
for (const name of imageNames) {
  const bytes = await read(name);
  if (bytes.length < 24 || !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
    throw new Error(`${name}: invalid PNG`);
  }
  assets[name] = {
    sha256: sha256(bytes),
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
  };
}

const demo = proof.videos?.['demo-video.mp4'];
const byEvent = new Map((demo?.timeline || []).map((event) => [event.event, event]));
const eventHashes = (names) => Object.fromEntries(names.map((name) => {
  const event = byEvent.get(name);
  if (!event) throw new Error(`demo timeline event is missing: ${name}`);
  return [name, event.frame_sha256];
}));
for (const [name, events] of [
  ['main-image.png', ['LIVE_STOREFRONT']],
  ['detail-01-overview.png', ['LIVE_STOREFRONT', 'PRODUCT_SELECTED', 'CHECKOUT_INPUT']],
]) {
  assets[name].source_video = 'demo-video.mp4';
  assets[name].source_video_sha256 = demo.sha256;
  assets[name].source_event_frame_sha256 = eventHashes(events);
}

for (const name of videoNames) {
  const bytes = await read(name);
  const videoProof = proof.videos?.[name];
  if (!videoProof || sha256(bytes) !== videoProof.sha256) throw new Error(`${name}: proof byte commitment failed`);
  const probeResult = spawnSync('ffprobe', [
    '-v', 'error', '-select_streams', 'v:0', '-count_frames',
    '-show_entries', 'stream=codec_name,pix_fmt,width,height,nb_read_frames:format=duration',
    '-of', 'json', path.join(mediaRoot, name),
  ], { encoding: 'utf8' });
  if (probeResult.status !== 0) throw new Error(`${name}: ffprobe failed`);
  const probe = JSON.parse(probeResult.stdout);
  const stream = probe.streams?.[0];
  const duration = Number(probe.format?.duration);
  const frameCount = Number(stream?.nb_read_frames);
  if (stream?.codec_name !== videoProof.codec || stream?.pix_fmt !== videoProof.pixel_format
    || Number(stream?.width) !== Number(videoProof.width) || Number(stream?.height) !== Number(videoProof.height)
    || Math.abs(duration - Number(videoProof.duration_seconds)) >= 0.01
    || frameCount !== Number(videoProof.frame_count)) {
    throw new Error(`${name}: probed media facts do not match the execution proof`);
  }
  assets[name] = {
    sha256: videoProof.sha256,
    codec: videoProof.codec,
    pixel_format: videoProof.pixel_format,
    width: Number(videoProof.width),
    height: Number(videoProof.height),
    duration_seconds: duration,
    frame_count: frameCount,
    sampled_frame_count: Number(videoProof.sampled_frame_count),
    unique_sampled_frames: Number(videoProof.unique_sampled_frames),
    execution_proof: 'execution-proof.json',
  };
}

assets['execution-proof.json'] = {
  sha256: sha256(proofBytes),
  schema_version: proof.schema_version,
  classification: proof.classification,
};

const manifest = {
  schema_version: 1,
  case_id: 'pf07',
  classification: 'PUBLIC_SANITIZED_MEDIA',
  registration_manifest_case_count: 6,
  metadata_stripped: true,
  source_commitments: sourceCommitments,
  assets,
};
await fsp.writeFile(outputPath, `${JSON.stringify(manifest, null, 2)}\n`, { flag: 'wx' });
process.stdout.write(`${JSON.stringify({
  file: outputPath,
  sha256: sha256(await fsp.readFile(outputPath)),
  asset_count: Object.keys(assets).length,
  source_commitment_count: Object.keys(sourceCommitments).length,
})}\n`);
