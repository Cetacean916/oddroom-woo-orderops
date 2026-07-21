#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_contract import EvidenceContractError, validate_public_lineage  # noqa: E402
from refinement_evidence_paths import PUBLIC_RUN_ALIAS  # noqa: E402


TRANSFORM_SHA = "a" * 64
RAW_BYTES = b'{"protected":"synthetic"}\n'
RAW = {
    "schema_version": "1",
    "acceptance_id": "GATE-06-LEASE",
    "run_id": "00000000-0000-4000-8000-000000000000",
    "started_at": "2026-07-19T00:00:00Z",
    "finished_at": "2026-07-19T00:01:00Z",
    "source_tree_sha256": "b" * 64,
    "command_or_probe": "protected probe",
    "exit_code": 0,
    "observations": {"result": "PASS", "second_sweep_mutations": 0},
    "artifact_hashes": {"lease_recovery_trace": "c" * 64},
    "redaction_state": "RAW_PROTECTED",
}
PUBLIC = {
    "schema_version": "1",
    "acceptance_id": RAW["acceptance_id"],
    "run_id": PUBLIC_RUN_ALIAS,
    "started_at": RAW["started_at"],
    "finished_at": RAW["finished_at"],
    "source_tree_sha256": RAW["source_tree_sha256"],
    "command_or_probe": "recorded redaction of protected acceptance observation",
    "exit_code": 0,
    "observations": RAW["observations"],
    "artifact_hashes": {},
    "redaction_state": "PUBLIC_REDACTED",
    "redaction_transform": {
        "id": "pf07-public-evidence-redaction",
        "version": "1",
        "script_sha256": TRANSFORM_SHA,
    },
    "source_acceptance_id": RAW["acceptance_id"],
    "source_record_sha256": hashlib.sha256(RAW_BYTES).hexdigest(),
    "source_artifact_hashes": RAW["artifact_hashes"],
}


validate_public_lineage(PUBLIC, RAW, RAW_BYTES, TRANSFORM_SHA)

mutations = []
wrong_transform = deepcopy(PUBLIC)
wrong_transform["redaction_transform"]["script_sha256"] = "d" * 64
mutations.append(wrong_transform)
missing_artifacts = deepcopy(PUBLIC)
missing_artifacts["source_artifact_hashes"] = {}
mutations.append(missing_artifacts)
changed_observation = deepcopy(PUBLIC)
changed_observation["observations"]["second_sweep_mutations"] = 1
mutations.append(changed_observation)
wrong_source_bytes = deepcopy(PUBLIC)
wrong_source_bytes["source_record_sha256"] = "e" * 64
mutations.append(wrong_source_bytes)
extra_field = deepcopy(PUBLIC)
extra_field["status"] = "PASS"
mutations.append(extra_field)

for index, value in enumerate(mutations, start=1):
    try:
        validate_public_lineage(value, RAW, RAW_BYTES, TRANSFORM_SHA)
    except EvidenceContractError:
        continue
    raise AssertionError(f"invalid public evidence mutation passed: {index}")

print("PASS: public evidence shape, current-transform, and complete-lineage regressions")
