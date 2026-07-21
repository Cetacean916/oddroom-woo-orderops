#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILDER_SOURCE = PROJECT_ROOT / "scripts/build-public-release"
VALIDATOR_SOURCE = PROJECT_ROOT / "scripts/validate-public"


def builder_allowed_names() -> set[str]:
    module = ast.parse(BUILDER_SOURCE.read_text(encoding="utf-8"))
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "allowed_names" for target in node.targets)
            and isinstance(node.value, ast.Set)
        ):
            return {
                item.value for item in node.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
    raise AssertionError("public builder exact-name allowlist is unavailable")


active_allowlist = json.loads(
    (PROJECT_ROOT / "release/public-allowlist.json").read_text(encoding="utf-8")
)["paths"]
extensionless_allowlisted_names = {
    PurePosixPath(relative).name
    for relative in active_allowlist
    if PurePosixPath(relative).suffix == ""
}
missing_extensionless_names = extensionless_allowlisted_names - builder_allowed_names()
if missing_extensionless_names:
    raise AssertionError(
        f"public builder rejects allowlisted extensionless names: {sorted(missing_extensionless_names)}"
    )


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
scenario(["payload.sqlite"], setup=lambda _root, source: (source / "payload.sqlite").write_bytes(b"not-public"))
scenario(["evidence/raw/payload.json"], setup=lambda _root, source: (source / "evidence/raw").mkdir(parents=True) or (source / "evidence/raw/payload.json").write_text("{}\n", encoding="utf-8"))
scenario(["evidence/refinement/raw-private/payload.json"], setup=lambda _root, source: (source / "evidence/refinement/raw-private").mkdir(parents=True) or (source / "evidence/refinement/raw-private/payload.json").write_text("{}\n", encoding="utf-8"))
scenario(["backup/snapshot.json"], setup=lambda _root, source: (source / "backup").mkdir() or (source / "backup/snapshot.json").write_text("{}\n", encoding="utf-8"))
scenario(["backups/snapshot.json"], setup=lambda _root, source: (source / "backups").mkdir() or (source / "backups/snapshot.json").write_text("{}\n", encoding="utf-8"))
scenario(["credentials/locator.json"], setup=lambda _root, source: (source / "credentials").mkdir() or (source / "credentials/locator.json").write_text("{}\n", encoding="utf-8"))


def validator_forbidden_roots() -> set[str]:
    module = ast.parse(VALIDATOR_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(module):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "forbidden" and isinstance(node.iter, (ast.Tuple, ast.List)):
            values = {item.value for item in node.iter.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)}
            if {"evidence/raw", "evidence/refinement/raw-private", "runtime", "backup", "backups", "credentials"} <= values:
                return values
    raise AssertionError("public validator protected-root denylist is incomplete")


validator_forbidden_roots()


def validator_dependency_install_boundary() -> None:
    module = ast.parse(VALIDATOR_SOURCE.read_text(encoding="utf-8"))
    candidate_function = next(
        (
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "candidate_files"
        ),
        None,
    )
    if candidate_function is None:
        raise AssertionError("public validator candidate inventory function is unavailable")
    constants = {
        node.value for node in ast.walk(candidate_function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    if ".git" not in constants or "node_modules" not in constants:
        raise AssertionError(
            "public validator must exclude Git metadata and installed node_modules from candidate bytes"
        )


validator_dependency_install_boundary()


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
