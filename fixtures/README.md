# Acceptance fixture bundle

STATUS: ACTIVE
CLASSIFICATION: PUBLIC_ORIGINAL_SAFE_SYNTHETIC
CANONICAL_MANIFEST: `fixtures/acceptance-fixtures.json`

This bundle defines executable assertions for every protected pre-public acceptance scenario. It does not treat a stored `result: PASS` field as proof. `fixtures/run` reads the observed fields, applies every fixture assertion, and verifies the required artifact commitments.

## Verification modes

Public-safe verification reads only `evidence/refinement/public`:

```bash
./fixtures/run --public
```

Protected verification additionally checks each required artifact against `evidence/refinement/raw-private/step-090/backend/protected-artifact-inventory.json` and its exact local bytes. The historical `evidence/raw` and `evidence/public` manifests remain immutable:

```bash
./fixtures/run --protected
```

One fixture can be selected with `--fixture <id>`. Any missing record, missing assertion, failed assertion, missing artifact commitment, or protected artifact hash mismatch is `FAIL` and exits nonzero.

## New live observations

Use `scripts/collect-evidence` to execute the real probe command. The probe must write its artifacts inside `PF07_EVIDENCE_OUTPUT_DIR` and print one JSON object containing `observations` and the exact artifact alias-to-file mapping. The collector derives PASS from this manifest, binds the current deterministic source tree, and refuses to replace canonical evidence unless `--replace` is explicit.

Secret values must enter the probe through the authorized protected environment or files. They must not appear in command arguments, stdout observations, or public evidence.

## Completion boundary

Passing this bundle establishes only its fixture assertions and artifact bindings. It does not establish repository publication, deployed showcase behavior, media semantics, the final acceptance matrix, or `FINAL_PASS`.
