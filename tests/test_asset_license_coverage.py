#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTICE = (ROOT / "ASSET-LICENSES.md").read_text(encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bundled_visual_assets() -> list[Path]:
    roots = (
        ROOT / "plugin/oddroom-orderops/assets/fonts",
        ROOT / "plugin/oddroom-orderops/assets/images",
    )
    suffixes = {".jpeg", ".jpg", ".png", ".svg", ".webp", ".woff2"}
    return [
        path
        for root in roots
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix.lower() in suffixes
    ]


def main() -> None:
    assets = bundled_visual_assets()
    assert assets, "no bundled visual assets found"
    failures: list[str] = []
    for path in assets:
        relative = path.relative_to(ROOT).as_posix()
        digest = sha256(path)
        if f"`{relative}`" not in NOTICE:
            failures.append(f"missing path: {relative}")
        if f"`{digest}`" not in NOTICE:
            failures.append(f"missing SHA-256: {relative} {digest}")
    assert not failures, "asset license coverage failed:\n" + "\n".join(failures)
    print(f"PASS: ASSET-LICENSES covers {len(assets)} bundled visual/font assets")


if __name__ == "__main__":
    main()
