from __future__ import annotations

import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import stat


SUCCESSOR_RAW_RELATIVE = Path("evidence/refinement/raw-private/step-090/backend")
SUCCESSOR_PUBLIC_RELATIVE = Path("evidence/refinement/public")
SUCCESSOR_PUBLIC_PREFIX = SUCCESSOR_PUBLIC_RELATIVE.as_posix()
PUBLIC_RUN_ALIAS = "PF07-REFINEMENT-ACCEPTANCE-RUN"

# These two manifests are part of the historical v1.0.2 immutability chain.
# Successor evidence is written to the separate refinement namespace above.
LEGACY_RAW_MANIFEST_SHA256 = "04d31a7a7d9014bea5aea24eb02ba325d8c1908b0a96e94e565e1b6d325bfbb8"
LEGACY_PUBLIC_MANIFEST_SHA256 = "854ebc6a23a31864a0e49e1478774194c6271b07fc16650a913eac4cf6bc60f0"


def successor_raw_root(project_root: Path) -> Path:
    return project_root / SUCCESSOR_RAW_RELATIVE


def successor_public_root(project_root: Path) -> Path:
    return project_root / SUCCESSOR_PUBLIC_RELATIVE


def public_candidate_source_sha256(project_root: Path) -> str:
    """Hash the non-evidence bytes that the deny-by-default public builder ships."""
    root = project_root.resolve()
    allowlist_path = root / "release/public-allowlist.json"
    document = json.loads(allowlist_path.read_text(encoding="utf-8"))
    paths = document.get("paths")
    if document.get("schema_version") != 1 or not isinstance(paths, list) or not paths:
        raise ValueError("public allowlist schema is invalid for source identity")
    if len(paths) != len(set(paths)):
        raise ValueError("public allowlist is duplicated for source identity")

    excluded_roots = {"dist", "evidence", "reports", "runtime", ".git"}
    lines: list[str] = []
    for raw in sorted(paths):
        if not isinstance(raw, str) or raw == "" or "\\" in raw or "\x00" in raw:
            raise ValueError("public allowlist path is invalid for source identity")
        pure = PurePosixPath(raw)
        if raw != pure.as_posix() or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError("public allowlist path is unsafe for source identity")
        if pure.parts[0] in excluded_roots or raw == "release/public-build-manifest.json":
            continue
        path = root.joinpath(*pure.parts)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"public source identity input is missing or unsafe: {raw}")
        try:
            path.resolve(strict=True).relative_to(root)
        except ValueError as error:
            raise ValueError(f"public source identity input escaped the project: {raw}") from error
        mode = "0755" if path.stat().st_mode & stat.S_IXUSR else "0644"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{raw}\t{mode}\t{digest}")
    if not lines:
        raise ValueError("public source identity has no inputs")
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
