#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILDER_SOURCE = PROJECT_ROOT / "scripts/build-public-release"


def make_source(base: Path) -> Path:
    source = base / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "release").mkdir()
    shutil.copy2(BUILDER_SOURCE, source / "scripts/build-public-release")
    (source / "README.md").write_text("synthetic builder fixture\n", encoding="utf-8")
    return source


def write_allowlist(source: Path, extra: list[str]) -> None:
    document = {
        "schema_version": 1,
        "paths": [
            "README.md",
            "release/public-allowlist.json",
            "scripts/build-public-release",
            *extra,
        ],
    }
    (source / "release/public-allowlist.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )


def run_builder(source: Path, output: Path, expected_success: bool) -> None:
    result = subprocess.run(
        [sys.executable, str(source / "scripts/build-public-release"), str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if (result.returncode == 0) != expected_success:
        raise AssertionError(f"unexpected builder result {result.returncode}: {result.stdout}")


def scenario(extra: list[str], setup=None, expected_success: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="pf07-builder-test-") as temporary:
        root = Path(temporary)
        source = make_source(root)
        if setup is not None:
            setup(root, source)
        write_allowlist(source, extra)
        output = root / "output"
        output.mkdir()
        run_builder(source, output, expected_success)


scenario([], expected_success=True)
scenario(["nested/./payload.txt"])
scenario(["nested//payload.txt"])
scenario(["../payload.txt"])
scenario(["/absolute.txt"])


def symlink_ancestor(root: Path, source: Path) -> None:
    external = root / "external"
    external.mkdir()
    (external / "payload.txt").write_text("outside\n", encoding="utf-8")
    (source / "linked").symlink_to(external, target_is_directory=True)


scenario(["linked/payload.txt"], setup=symlink_ancestor)


def hardlink_file(root: Path, source: Path) -> None:
    (source / "payload.txt").write_text("linked\n", encoding="utf-8")
    os.link(source / "payload.txt", root / "second-link.txt")


scenario(["payload.txt"], setup=hardlink_file)


def fifo_file(root: Path, source: Path) -> None:
    os.mkfifo(source / "payload.pipe")


scenario(["payload.pipe"], setup=fifo_file)

print("PASS: public builder canonical-path, containment, link, and file-type regressions")
