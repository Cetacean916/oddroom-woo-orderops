from __future__ import annotations

from pathlib import Path


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
