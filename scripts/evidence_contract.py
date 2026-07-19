from __future__ import annotations

from datetime import datetime
import hashlib
import re


PUBLIC_RUN_ALIAS = "PF07-ACCEPTANCE-RUN"
TRANSFORM_ID = "pf07-public-evidence-redaction"
TRANSFORM_VERSION = "1"
PUBLIC_REDACTED_FIELDS = {
    "schema_version", "acceptance_id", "run_id", "started_at", "finished_at",
    "source_tree_sha256", "command_or_probe", "exit_code", "observations",
    "artifact_hashes", "redaction_state", "redaction_transform",
    "source_acceptance_id", "source_record_sha256", "source_artifact_hashes",
}


class EvidenceContractError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceContractError(message)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def validate_public_record_shape(record: object, transform_sha256: str) -> None:
    _require(isinstance(record, dict), "public record root is not an object")
    _require(set(record) == PUBLIC_REDACTED_FIELDS, "public record fields differ from the canonical transform output")
    _require(record.get("schema_version") == "1", "public schema version is invalid")
    acceptance_id = record.get("acceptance_id")
    _require(
        isinstance(acceptance_id, str)
        and re.fullmatch(r"GATE-[0-9]{2}(?:-[A-Z0-9-]+)?", acceptance_id) is not None,
        "public acceptance identity is invalid",
    )
    _require(record.get("run_id") == PUBLIC_RUN_ALIAS, "public run alias is invalid")
    _require(_is_timestamp(record.get("started_at")) and _is_timestamp(record.get("finished_at")), "public timestamps are invalid")
    _require(_is_sha256(record.get("source_tree_sha256")), "public source-tree commitment is invalid")
    _require(record.get("command_or_probe") == "recorded redaction of protected acceptance observation", "public transform description is invalid")
    _require(record.get("exit_code") == 0, "public executable result is nonzero")
    observations = record.get("observations")
    _require(isinstance(observations, dict) and observations.get("result") == "PASS", "public observations do not establish PASS")
    _require(record.get("artifact_hashes") == {}, "public record contains a backward artifact edge")
    _require(record.get("redaction_state") == "PUBLIC_REDACTED", "public redaction state is invalid")
    _require(
        record.get("redaction_transform") == {
            "id": TRANSFORM_ID,
            "version": TRANSFORM_VERSION,
            "script_sha256": transform_sha256,
        },
        "public transform identity does not match the current recorded transform",
    )
    _require(record.get("source_acceptance_id") == acceptance_id, "public source acceptance identity differs")
    _require(_is_sha256(record.get("source_record_sha256")), "public source-record commitment is invalid")
    source_artifacts = record.get("source_artifact_hashes")
    _require(isinstance(source_artifacts, dict) and bool(source_artifacts), "public source-artifact commitments are missing")
    for alias, digest in source_artifacts.items():
        _require(isinstance(alias, str) and re.fullmatch(r"[a-z0-9_]+", alias) is not None, "public source-artifact alias is invalid")
        _require(_is_sha256(digest), "public source-artifact digest is invalid")


def validate_public_lineage(record: object, raw_record: object, raw_bytes: bytes, transform_sha256: str) -> None:
    validate_public_record_shape(record, transform_sha256)
    _require(isinstance(raw_record, dict), "raw lineage root is not an object")
    comparisons = {
        "schema_version": raw_record.get("schema_version"),
        "acceptance_id": raw_record.get("acceptance_id"),
        "started_at": raw_record.get("started_at"),
        "finished_at": raw_record.get("finished_at"),
        "source_tree_sha256": raw_record.get("source_tree_sha256"),
        "exit_code": raw_record.get("exit_code"),
        "observations": raw_record.get("observations"),
    }
    for field, expected in comparisons.items():
        _require(record.get(field) == expected, f"public lineage differs from raw field: {field}")
    _require(record.get("source_acceptance_id") == raw_record.get("acceptance_id"), "public lineage source identity differs")
    _require(record.get("source_record_sha256") == hashlib.sha256(raw_bytes).hexdigest(), "public lineage source-record bytes differ")
    _require(record.get("source_artifact_hashes") == raw_record.get("artifact_hashes"), "public lineage source-artifact set differs")
