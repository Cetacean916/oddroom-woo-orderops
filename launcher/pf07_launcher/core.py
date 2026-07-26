from __future__ import annotations

import json
import hashlib
import hmac
import ipaddress
import io
import os
import platform
import re
import secrets
import signal
import shutil
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from .action_contract import PrerequisiteFacts, RuntimeFacts, classify_prerequisites, classify_runtime, recovery_action


ADMIN_USER = "pf07-operator"
ADMIN_EMAIL = "pf07-admin@example.com"
PACKAGE_VERSION = "1.0.5"
CONTROLLED_UPDATE_PREDECESSOR_VERSION = "1.0.4"
CONTROLLED_UPDATE_PREDECESSOR_BUILD_ID = "pf07-build-7fefca73ae30774c9a09"
CONTROLLED_UPDATE_PREDECESSOR_MANIFEST_SHA256 = {
    "pf07-linux-server": "c2fbe286b1555dfb3eab55408f29e14b7d9c6a85c0fb04b8de8878cd8c251a7a",
    "pf07-linux-x86_64": "cd20448ac0fb53be2b745d815429bd5452f543614e2f0f74c9d3546325b82429",
    "pf07-macos-universal": "15767b1b3861d7de2c7296c27e2958e66ccd8106a08489758bf80d0822d4d9f4",
    "pf07-windows-x64": "7f84549318e023c0cad8495af85bfa8f46aad562ff81faac05ce61fee44b345b",
}
DEFAULT_WORDPRESS_PORT = 19081
STATE_DIR_NAME = ".pf07"
UPDATE_FENCE_NAME = "UPDATE-FENCE.json"
CONTROLLED_UPDATE_GATE_NAME = "controlled-update-gate.json"
SUPPORTED_LOCALES = {"ko_KR", "en_US"}
SUPPORTED_MODES = {"DEMO_MODE", "CONNECTED_MODE"}
DEMO_WORKFLOW_ID = "PF07PackageDemoV1"
CONNECTED_WORKFLOW_ID = "PF07OrderOpsVSL1"
CONNECTED_ENV_KEYS = {
    "HUBSPOT_RUNTIME_TOKEN",
    "HUBSPOT_PIPELINE_ID",
    "HUBSPOT_INITIAL_STAGE_ID",
    "HUBSPOT_CREDENTIAL_ALIAS",
    "SLACK_BOT_TOKEN",
    "SLACK_CHANNEL_ID",
    "SLACK_CREDENTIAL_ALIAS",
}
REQUIRED_ENV_KEYS = {
    "N8N_ENCRYPTION_KEY",
    "N8N_RUNNERS_AUTH_TOKEN",
    "ODDROOM_PUBLIC_BASE_URL",
    "ODDROOM_RUN_ID",
    "ODDROOM_SHOP_INSTANCE_ID",
    "ODDROOM_WEBHOOK_HMAC_KEY",
    "ODDROOM_WEBHOOK_PATH",
    "PF07_ADMIN_PASSWORD",
    "PF07_ADMIN_USER",
    "PF07_COMPOSE_PROJECT",
    "PF07_DB_PASSWORD",
    "PF07_DB_ROOT_PASSWORD",
    "PF07_HUBSPOT_CONFIGURED",
    "PF07_NETWORK_SUBNET",
    "PF07_SLACK_CONFIGURED",
    "PF07_WORDPRESS_PORT",
}
VERIFIED_DOWNLOADS = {
    "wordpress-7.0.2.zip": {
        "url": "https://wordpress.org/wordpress-7.0.2.zip",
        "sha256": "a616580ed2152ae71d81439884b4bcda329c5322f9bd2092ac7a3a68dbcea7a7",
    },
    "action-scheduler-4.0.0.zip": {
        "url": "https://github.com/woocommerce/action-scheduler/releases/download/4.0.0/action-scheduler.zip",
        "sha256": "7dc68d4bfe8f72c02fe2717ee0580a1a6ae5044fb455793e1bb076dc56d8a4fb",
    },
    "woocommerce.10.9.4.zip": {
        "url": "https://downloads.wordpress.org/plugin/woocommerce.10.9.4.zip",
        "sha256": "6e58fc3ba9b18d1c9aee6b0227d3c3c09e4fe2c1332823bd2e0ac54ffcff64a9",
    },
    "wordpress-7.0.2-ko_KR.zip": {
        "url": "https://downloads.wordpress.org/translation/core/7.0.2/ko_KR.zip",
        "sha256": "eb7ed99e224a346340cb992fa7427de32db58e9700c842ea379985d33e02200d",
    },
    "woocommerce-10.9.4-ko_KR.zip": {
        "url": "https://downloads.wordpress.org/translation/plugin/woocommerce/10.9.4/ko_KR.zip",
        "sha256": "b4de863b0b240f30f382b742027902464933c3e0f9e3b13b6d02586f8e892654",
    },
}
_OPERATION_LOCK_CONTEXT = threading.local()
WORDPRESS_IMAGE_REFERENCE = "wordpress@sha256:d40b86dbdfcfad808a2029acf6543c670c4a61c29f70b9d24605e7d0b31ab83d"
TASK_RUNNER_IMAGE_REFERENCE = "pf07-task-runners:2.25.7-json-bigint-1.0.0-pf07v1"
TASK_RUNNER_IMAGE_CONTRACT = "n8n-2.25.7-json-bigint-1.0.0-pf07v1"
BACKUP_MAGIC = b"PF07-AUTHENTICATED-BACKUP-V1\n"
BACKUP_KDF_ITERATIONS = 600_000
PROTECTED_IO_TIMEOUT_SECONDS = 900
MAX_VOLUME_ARCHIVE_MEMBERS = 250_000
MAX_VOLUME_ARCHIVE_FILE_BYTES = 8 * 1024 * 1024 * 1024
MAX_VOLUME_ARCHIVE_TOTAL_BYTES = 32 * 1024 * 1024 * 1024
START_PROGRESS = {
    "preflight": (1, 8, 8),
    "downloads": (2, 8, 18),
    "containers": (3, 8, 34),
    "wordpress": (4, 8, 48),
    "dependencies": (5, 8, 62),
    "storefront": (6, 8, 76),
    "automation": (7, 8, 88),
    "task-runner-image": (7, 8, 92),
    "verify": (8, 8, 97),
    "ready": (8, 8, 100),
}


class LauncherError(RuntimeError):
    """A buyer-actionable launcher failure."""


def package_root() -> Path:
    """Resolve the package from this module, never from the caller's cwd."""
    root = Path(__file__).resolve().parent.parent.parent
    required = (
        root / "packaging" / "common" / "bootstrap-manifest.json",
        root / "packaging" / "common" / "action-contract.json",
        root / "packaging" / "common" / "compose.yaml",
        root / "packaging" / "network" / "tunnel-route-allowlist.json",
        root / "payload" / "oddroom-orderops" / "oddroom-orderops.php",
        root / "launcher" / "ui" / "index.ko.html",
        root / "launcher" / "ui" / "index.en.html",
    )
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise LauncherError("Package is incomplete; missing: " + ", ".join(missing))
    return root


def state_dir() -> Path:
    return package_root() / STATE_DIR_NAME


def connected_env_path() -> Path:
    return state_dir() / "connected.env"


def _restore_transaction_path() -> Path:
    return state_dir() / "restore-transaction.json"


def _controlled_update_transaction_path() -> Path:
    return package_root() / ".pf07-controlled-update-transaction.json"


def _controlled_update_distribution_binding(identity: dict[str, Any]) -> dict[str, str]:
    return {
        "artifact_id": str(identity["artifact_id"]),
        "package_version": str(identity["package_version"]),
        "build_id": str(identity["build_id"]),
        "artifact_manifest_sha256": str(identity["artifact_manifest_sha256"]),
    }


def _controlled_update_state_file_binding(path: Path, *, required: bool) -> dict[str, Any]:
    if path.is_symlink():
        raise LauncherError(f"The controlled-update state file must not be a symbolic link: {path.name}")
    if not path.exists():
        if required:
            raise LauncherError(f"The controlled-update state file is unavailable: {path.name}")
        return {"present": False, "sha256": None, "bytes": None}
    if not path.is_file():
        raise LauncherError(f"The controlled-update state path is not a regular file: {path.name}")
    return {
        "present": True,
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _read_controlled_update_transaction() -> dict[str, Any] | None:
    path = _controlled_update_transaction_path()
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError(
            "The controlled-update transaction is unreadable. Keep both package extractions and use Recover service."
        ) from error
    if not isinstance(value, dict) or value.get("schema") != "pf07.controlled-update-transaction.v1":
        raise LauncherError(
            "The controlled-update transaction has an unknown format. Keep both package extractions and use Recover service."
        )
    transaction_id = str(value.get("transaction_id", ""))
    if not re.fullmatch(r"[a-f0-9]{32}", transaction_id):
        raise LauncherError("The controlled-update transaction identity is invalid.")
    successor_root = Path(str(value.get("successor_root", ""))).resolve()
    predecessor_root = Path(str(value.get("predecessor_root", ""))).resolve()
    if successor_root != package_root().resolve() or predecessor_root == successor_root:
        raise LauncherError("The controlled-update package roots do not match this successor package.")
    expected_names = {
        "stage_name": f".pf07-update-stage-{transaction_id}",
        "successor_preimage_name": f".pf07-update-preimage-{transaction_id}",
        "volume_preimage_name": f".pf07-update-volume-preimage-{transaction_id}",
    }
    if any(value.get(key) != expected for key, expected in expected_names.items()):
        raise LauncherError("The controlled-update recovery paths are outside the exact package transaction boundary.")
    distribution_bindings: dict[str, dict[str, str]] = {}
    for side in ("predecessor", "successor"):
        binding = value.get(f"{side}_distribution")
        if (
            not isinstance(binding, dict)
            or not re.fullmatch(r"pf07-[a-z0-9_-]+", str(binding.get("artifact_id", "")))
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(binding.get("package_version", "")))
            or not re.fullmatch(r"pf07-build-[a-f0-9]+", str(binding.get("build_id", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(binding.get("artifact_manifest_sha256", "")))
        ):
            raise LauncherError(f"The controlled-update {side} distribution identity is invalid.")
        distribution_bindings[side] = {
            "artifact_id": str(binding["artifact_id"]),
            "package_version": str(binding["package_version"]),
            "build_id": str(binding["build_id"]),
            "artifact_manifest_sha256": str(binding["artifact_manifest_sha256"]),
        }
    if (
        value.get("from_build_id") != distribution_bindings["predecessor"]["build_id"]
        or value.get("to_build_id") != distribution_bindings["successor"]["build_id"]
        or distribution_bindings["predecessor"]["artifact_id"]
        != distribution_bindings["successor"]["artifact_id"]
    ):
        raise LauncherError("The controlled-update distribution transition identity is inconsistent.")
    state_bindings = value.get("predecessor_state_files")
    if not isinstance(state_bindings, dict) or set(state_bindings) != {
        "runtime.env",
        "config.json",
        "connected.env",
    }:
        raise LauncherError("The controlled-update predecessor state identity is invalid.")
    for name, binding in state_bindings.items():
        if not isinstance(binding, dict) or not isinstance(binding.get("present"), bool):
            raise LauncherError("The controlled-update predecessor state identity is invalid.")
        if binding["present"]:
            if (
                not re.fullmatch(r"[a-f0-9]{64}", str(binding.get("sha256", "")))
                or not isinstance(binding.get("bytes"), int)
                or isinstance(binding.get("bytes"), bool)
                or binding["bytes"] < 0
            ):
                raise LauncherError("The controlled-update predecessor state identity is invalid.")
        elif binding.get("sha256") is not None or binding.get("bytes") is not None:
            raise LauncherError("The controlled-update predecessor state identity is invalid.")
        if name in {"runtime.env", "config.json"} and not binding["present"]:
            raise LauncherError("The controlled-update predecessor required-state identity is invalid.")
    compose_project = str(value.get("predecessor_compose_project", ""))
    if not re.fullmatch(r"pf07pkg-[a-f0-9]{12}", compose_project):
        raise LauncherError("The controlled-update predecessor project identity is invalid.")
    if not re.fullmatch(r"[a-f0-9]{64}", str(value.get("predecessor_shop_instance_id_sha256", ""))):
        raise LauncherError("The controlled-update predecessor shop identity is invalid.")
    recorded_volume_names = value.get("predecessor_volume_names")
    expected_volume_names = {
        logical_name: f"{compose_project}_{logical_name}"
        for logical_name in ("mariadb_data", "wordpress_data", "n8n_data")
    }
    if recorded_volume_names != expected_volume_names:
        raise LauncherError("The controlled-update predecessor volume identity is invalid.")
    active_container = value.get("active_container")
    if active_container is not None and not re.fullmatch(r"pf07-update-restore-[a-f0-9]{16}", str(active_container)):
        raise LauncherError("The controlled-update transaction contains an invalid transient-container identity.")
    volumes = value.get("volumes")
    if not isinstance(volumes, list):
        raise LauncherError("The controlled-update volume preimage inventory is invalid.")
    logical_names: set[str] = set()
    for row in volumes:
        if not isinstance(row, dict):
            raise LauncherError("The controlled-update volume preimage inventory is invalid.")
        logical_name = str(row.get("logical_name", ""))
        if logical_name not in {"mariadb_data", "wordpress_data", "n8n_data"} or logical_name in logical_names:
            raise LauncherError("The controlled-update volume preimage inventory is invalid.")
        logical_names.add(logical_name)
        archive = row.get("archive")
        if archive is not None and archive != f"{logical_name}.tar":
            raise LauncherError("The controlled-update volume preimage archive identity is invalid.")
        digest = row.get("sha256")
        if digest is not None and not re.fullmatch(r"[a-f0-9]{64}", str(digest)):
            raise LauncherError("The controlled-update volume preimage digest is invalid.")
    if logical_names != {"mariadb_data", "wordpress_data", "n8n_data"}:
        raise LauncherError("The controlled-update volume preimage inventory is invalid.")
    if not isinstance(value.get("worker_enabled"), bool):
        raise LauncherError("The controlled-update worker activation state is invalid.")
    return value


def _update_controlled_update_transaction(**changes: Any) -> dict[str, Any]:
    value = _read_controlled_update_transaction()
    if value is None:
        raise LauncherError("The controlled-update transaction record is missing.")
    value.update(changes)
    value["updated_at_utc"] = _utc_now()
    _atomic_json(_controlled_update_transaction_path(), value)
    return value


def _require_no_controlled_update_transaction() -> None:
    value = _read_controlled_update_transaction()
    if value is None:
        return
    phase = str(value.get("phase", "RECOVERY_REQUIRED"))
    raise LauncherError(
        "A controlled PF07 update is incomplete "
        f"({phase}). Keep both package extractions and use Recover service before starting or changing this runtime."
    )


def _read_restore_transaction() -> dict[str, Any] | None:
    path = _restore_transaction_path()
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError(
            "A protected restore transaction is unreadable. Do not start or change the runtime until it is recovered."
        ) from error
    if not isinstance(value, dict) or value.get("schema") != "pf07.restore-transaction.v1":
        raise LauncherError(
            "A protected restore transaction has an unknown format. Do not start or change the runtime until it is recovered."
        )
    container_name = value.get("active_container")
    if container_name is not None and not re.fullmatch(r"pf07-restore-[a-f0-9]{16}", str(container_name)):
        raise LauncherError("The protected restore transaction contains an invalid transient-container identity.")
    if (
        not re.fullmatch(r"[a-f0-9]{64}", str(value.get("incoming_archive_sha256", "")))
        or not re.fullmatch(r"pf07pkg-[a-f0-9]{12}", str(value.get("incoming_target_compose_project", "")))
        or not re.fullmatch(
            r"[a-f0-9]{64}",
            str(value.get("incoming_target_shop_instance_id_sha256", "")),
        )
    ):
        raise LauncherError("The protected restore transaction does not bind its incoming archive identity.")
    if value.get("pre_restore_backup_path") is not None and (
        not re.fullmatch(r"[a-f0-9]{64}", str(value.get("pre_restore_backup_sha256", "")))
        or not re.fullmatch(r"pf07pkg-[a-f0-9]{12}", str(value.get("pre_restore_target_compose_project", "")))
        or not re.fullmatch(
            r"[a-f0-9]{64}",
            str(value.get("pre_restore_target_shop_instance_id_sha256", "")),
        )
    ):
        raise LauncherError("The protected restore transaction does not bind its pre-restore archive identity.")
    return value


def _update_restore_transaction(**changes: Any) -> dict[str, Any]:
    value = _read_restore_transaction()
    if value is None:
        raise LauncherError("The protected restore transaction record is missing.")
    value.update(changes)
    value["updated_at_utc"] = _utc_now()
    _atomic_json(_restore_transaction_path(), value)
    return value


def _require_no_restore_transaction() -> None:
    value = _read_restore_transaction()
    if value is None:
        return
    state = str(value.get("state", "RECOVERY_REQUIRED"))
    raise LauncherError(
        "A protected restore is incomplete "
        f"({state}). Use Recover service first; do not start or change this runtime until the recorded "
        "restore container is stopped and the exact recovery archive is applied."
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, mode)
    os.replace(temp, path)


def _file_preimage(path: Path) -> dict[str, Any]:
    try:
        metadata = path.stat()
        return {
            "exists": True,
            "payload": path.read_bytes(),
            "mode": metadata.st_mode & 0o777,
        }
    except FileNotFoundError:
        return {"exists": False, "payload": b"", "mode": 0o600}


def _restore_file_preimage(path: Path, preimage: dict[str, Any]) -> None:
    if not preimage["exists"]:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.restore")
    try:
        temp.write_bytes(preimage["payload"])
        os.chmod(temp, int(preimage["mode"]))
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _set_operation(phase: str, message: str, result: str = "IN_PROGRESS") -> None:
    operation_path = state_dir() / "operation.json"
    previous: dict[str, Any] = {}
    if operation_path.is_file():
        try:
            value = json.loads(operation_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                previous = value
        except (OSError, json.JSONDecodeError):
            previous = {}
    now = _utc_now()
    starting_new_sequence = phase == "preflight" or previous.get("result") not in {"IN_PROGRESS"}
    started_at = now if starting_new_sequence else str(previous.get("started_at_utc") or now)
    payload: dict[str, Any] = {
        "phase": phase,
        "message": message,
        "result": result,
        "started_at_utc": started_at,
        "updated_at_utc": now,
    }
    progress = START_PROGRESS.get(phase)
    if progress is not None:
        payload.update(
            {
                "step_index": progress[0],
                "step_total": progress[1],
                "progress_percent": progress[2],
            }
        )
    _atomic_json(
        operation_path,
        payload,
    )


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _select_free_loopback_port() -> int:
    for port in range(DEFAULT_WORDPRESS_PORT, DEFAULT_WORDPRESS_PORT + 100):
        if _port_available(port):
            return port
    raise LauncherError("No free loopback port was found for the local store.")


def _select_port() -> int:
    requested = os.environ.get("PF07_WORDPRESS_PORT", "").strip()
    if requested:
        try:
            port = int(requested)
        except ValueError as error:
            raise LauncherError("PF07_WORDPRESS_PORT must be an integer.") from error
        if not 1024 <= port <= 65535:
            raise LauncherError("PF07_WORDPRESS_PORT must be between 1024 and 65535.")
        if not _port_available(port):
            raise LauncherError(f"Requested local port {port} is already in use.")
        return port
    return _select_free_loopback_port()


def _occupied_ipv4_networks() -> list[ipaddress.IPv4Network]:
    occupied: list[ipaddress.IPv4Network] = []
    docker = shutil.which("docker")
    if docker:
        listed = subprocess.run(
            [docker, "network", "ls", "-q"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        network_ids = [value for value in listed.stdout.splitlines() if value]
        if listed.returncode == 0 and network_ids:
            inspected = subprocess.run(
                [docker, "network", "inspect", *network_ids],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
            if inspected.returncode == 0:
                try:
                    documents = json.loads(inspected.stdout)
                except json.JSONDecodeError:
                    documents = []
                for document in documents if isinstance(documents, list) else []:
                    configs = document.get("IPAM", {}).get("Config", []) if isinstance(document, dict) else []
                    for config in configs if isinstance(configs, list) else []:
                        subnet = config.get("Subnet") if isinstance(config, dict) else None
                        if not isinstance(subnet, str):
                            continue
                        try:
                            network = ipaddress.ip_network(subnet, strict=False)
                        except ValueError:
                            continue
                        if isinstance(network, ipaddress.IPv4Network):
                            occupied.append(network)

    ip_command = shutil.which("ip")
    if ip_command:
        routes = subprocess.run(
            [ip_command, "-j", "route", "show"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        if routes.returncode == 0:
            try:
                documents = json.loads(routes.stdout)
            except json.JSONDecodeError:
                documents = []
            for document in documents if isinstance(documents, list) else []:
                destination = document.get("dst") if isinstance(document, dict) else None
                if not isinstance(destination, str) or destination == "default":
                    continue
                try:
                    network = ipaddress.ip_network(destination, strict=False)
                except ValueError:
                    continue
                if isinstance(network, ipaddress.IPv4Network):
                    occupied.append(network)
    return occupied


def _select_network_subnet() -> str:
    requested = os.environ.get("PF07_NETWORK_SUBNET", "").strip()
    private_ranges = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )
    if requested:
        try:
            network = ipaddress.ip_network(requested, strict=True)
        except ValueError as error:
            raise LauncherError("PF07_NETWORK_SUBNET must be a canonical private IPv4 /24 subnet.") from error
        if (
            not isinstance(network, ipaddress.IPv4Network)
            or network.prefixlen != 24
            or not any(network.subnet_of(private_range) for private_range in private_ranges)
        ):
            raise LauncherError("PF07_NETWORK_SUBNET must be a canonical private IPv4 /24 subnet.")
        return str(network)

    occupied = _occupied_ipv4_networks()
    candidates = tuple(ipaddress.ip_network("10.240.0.0/12").subnets(new_prefix=24))
    seed = int(hashlib.sha256(str(package_root().resolve()).encode("utf-8")).hexdigest()[:8], 16)
    for index in range(len(candidates)):
        candidate = candidates[(seed + index) % len(candidates)]
        if not any(candidate.overlaps(network) for network in occupied):
            return str(candidate)
    raise LauncherError(
        "No free package network subnet was found. Stop an unused local container network or set PF07_NETWORK_SUBNET to a free private IPv4 /24."
    )


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _write_runtime_env(path: Path, values: dict[str, str]) -> None:
    payload = "# Generated locally by PF07. Do not share or commit.\n" + "".join(
        f"{key}={values[key]}\n" for key in sorted(values)
    )
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(payload, encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _controlled_update_gate_path() -> Path:
    return state_dir() / "control" / CONTROLLED_UPDATE_GATE_NAME


def _write_controlled_update_gate(
    gate_state: str,
    *,
    transaction_id: str | None = None,
    successor_build_id: str | None = None,
) -> None:
    if gate_state not in {"NORMAL", "TENTATIVE", "COMMITTED"}:
        raise LauncherError("The controlled-update outbound gate state is invalid.")
    if gate_state == "NORMAL":
        transaction_id = None
        successor_build_id = None
    elif (
        not re.fullmatch(r"[a-f0-9]{32}", str(transaction_id or ""))
        or not re.fullmatch(r"pf07-build-[a-f0-9]+", str(successor_build_id or ""))
    ):
        raise LauncherError("The controlled-update outbound gate identity is invalid.")
    control_dir = _controlled_update_gate_path().parent
    control_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    os.chmod(control_dir, 0o755)
    _atomic_json(
        _controlled_update_gate_path(),
        {
            "schema": "pf07.controlled-update-outbound-gate.v1",
            "state": gate_state,
            "transaction_id": transaction_id,
            "successor_build_id": successor_build_id,
            "updated_at_utc": _utc_now(),
        },
        mode=0o644,
    )


def _ensure_controlled_update_gate() -> None:
    path = _controlled_update_gate_path()
    if not path.exists():
        _write_controlled_update_gate("NORMAL")
        return
    if path.is_symlink() or not path.is_file():
        raise LauncherError("The controlled-update outbound gate path is unsafe.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError("The controlled-update outbound gate is unreadable.") from error
    if (
        not isinstance(value, dict)
        or value.get("schema") != "pf07.controlled-update-outbound-gate.v1"
        or value.get("state") not in {"NORMAL", "TENTATIVE", "COMMITTED"}
    ):
        raise LauncherError("The controlled-update outbound gate is invalid.")


def ensure_runtime() -> dict[str, str]:
    directory = state_dir()
    if (directory / UPDATE_FENCE_NAME).is_file():
        raise LauncherError(
            "This predecessor extraction was fenced by a completed PF07 update. Use the successor package path."
        )
    env_path = directory / "runtime.env"
    if env_path.exists():
        values = _parse_env(env_path)
        migrated = False
        if "N8N_ENCRYPTION_KEY" not in values:
            values["N8N_ENCRYPTION_KEY"] = secrets.token_urlsafe(48)
            migrated = True
        if "N8N_RUNNERS_AUTH_TOKEN" not in values:
            values["N8N_RUNNERS_AUTH_TOKEN"] = secrets.token_urlsafe(48)
            migrated = True
        if "ODDROOM_WEBHOOK_PATH" not in values:
            values["ODDROOM_WEBHOOK_PATH"] = (
                "oddroom-orderops-v1" if selected_mode() == "CONNECTED_MODE" else "oddroom-orderops-demo-v1"
            )
            migrated = True
        for key in ("PF07_HUBSPOT_CONFIGURED", "PF07_SLACK_CONFIGURED"):
            if key not in values:
                values[key] = "false"
                migrated = True
        if "PF07_NETWORK_SUBNET" not in values:
            values["PF07_NETWORK_SUBNET"] = _select_network_subnet()
            migrated = True
        if migrated:
            _write_runtime_env(env_path, values)
        missing = sorted(REQUIRED_ENV_KEYS - values.keys())
        if missing:
            raise LauncherError("Package-local runtime material is incomplete: " + ", ".join(missing))
        _ensure_controlled_update_gate()
        return values

    port = _select_port()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    credential_import = directory / "credential-import"
    credential_import.mkdir(mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    values = {
        "N8N_ENCRYPTION_KEY": secrets.token_urlsafe(48),
        "N8N_RUNNERS_AUTH_TOKEN": secrets.token_urlsafe(48),
        "ODDROOM_PUBLIC_BASE_URL": f"http://127.0.0.1:{port}",
        "ODDROOM_RUN_ID": str(uuid.uuid4()),
        "ODDROOM_SHOP_INSTANCE_ID": f"pf07-{uuid.uuid4()}",
        "ODDROOM_WEBHOOK_HMAC_KEY": secrets.token_urlsafe(48),
        "ODDROOM_WEBHOOK_PATH": "oddroom-orderops-demo-v1",
        "PF07_ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "PF07_ADMIN_USER": ADMIN_USER,
        "PF07_COMPOSE_PROJECT": f"pf07pkg-{uuid.uuid4().hex[:12]}",
        "PF07_DB_PASSWORD": secrets.token_urlsafe(30),
        "PF07_DB_ROOT_PASSWORD": secrets.token_urlsafe(36),
        "PF07_HUBSPOT_CONFIGURED": "false",
        "PF07_NETWORK_SUBNET": _select_network_subnet(),
        "PF07_SLACK_CONFIGURED": "false",
        "PF07_WORDPRESS_PORT": str(port),
    }
    _write_runtime_env(env_path, values)
    _ensure_controlled_update_gate()
    return values


def ensure_config() -> dict[str, str]:
    path = state_dir() / "config.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LauncherError("Package-local configuration is unreadable.") from error
        locale = str(value.get("locale", ""))
        mode = str(value.get("mode", ""))
        if locale not in SUPPORTED_LOCALES or mode not in SUPPORTED_MODES:
            raise LauncherError("Package-local mode or locale is invalid.")
        return {"locale": locale, "mode": mode}
    value = {"schema": "pf07.package-config.v1", "mode": "DEMO_MODE", "locale": "ko_KR"}
    _atomic_json(path, value)
    return {"locale": "ko_KR", "mode": "DEMO_MODE"}


def selected_locale() -> str:
    return ensure_config()["locale"]


def selected_mode() -> str:
    return ensure_config()["mode"]


def _synchronize_runtime_mode(values: dict[str, str]) -> dict[str, str]:
    expected = "oddroom-orderops-v1" if selected_mode() == "CONNECTED_MODE" else "oddroom-orderops-demo-v1"
    if values.get("ODDROOM_WEBHOOK_PATH") != expected:
        values["ODDROOM_WEBHOOK_PATH"] = expected
        _write_runtime_env(state_dir() / "runtime.env", values)
    return values


def _connected_values(*, required: bool = False) -> dict[str, str]:
    path = connected_env_path()
    if not path.is_file():
        if required:
            raise LauncherError("Complete the protected HubSpot and Slack connection setup first.")
        return {}
    values = _parse_env(path)
    missing = sorted(CONNECTED_ENV_KEYS - values.keys())
    if missing:
        if required:
            raise LauncherError("Protected connection setup is incomplete: " + ", ".join(missing))
        return {}
    return values


def connected_setup_status() -> dict[str, Any]:
    values = _connected_values()
    return {
        "configured": bool(values),
        "hubspot_alias": values.get("HUBSPOT_CREDENTIAL_ALIAS", "OFFSET Customer Records"),
        "slack_alias": values.get("SLACK_CREDENTIAL_ALIAS", "OFFSET Order Alerts"),
        "storage": "PACKAGE_PROTECTED_LOCAL",
        "connection_test": "PASS" if values else "NOT_RUN",
    }


def _validate_token(value: str, label: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{16,512}", value):
        raise LauncherError(f"{label} is empty or has an invalid protected-token shape.")
    return value


def _validate_identifier(value: str, label: str, pattern: str = r"[A-Za-z0-9_-]{1,96}") -> str:
    value = value.strip()
    if not re.fullmatch(pattern, value):
        raise LauncherError(f"{label} has an invalid identifier shape.")
    return value


def _connection_json(
    url: str,
    token: str,
    label: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    request_body = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None
        else (b"" if method == "POST" else None)
    )
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "PF07-Package-Launcher/1.0",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(
        url,
        data=request_body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status_code = int(response.status)
            raw = response.read(1_000_000)
    except urllib.error.HTTPError as error:
        raise LauncherError(f"{label} connection test was rejected with HTTP {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        raise LauncherError(f"{label} connection test could not reach the service.") from error
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LauncherError(f"{label} connection test returned an unreadable response.") from error
    if not isinstance(value, dict):
        raise LauncherError(f"{label} connection test returned an invalid response shape.")
    return status_code, value


def _test_connected_services(values: dict[str, str]) -> dict[str, Any]:
    hubspot_status, hubspot = _connection_json(
        "https://api.hubapi.com/crm/v3/pipelines/deals",
        values["HUBSPOT_RUNTIME_TOKEN"],
        "HubSpot",
    )
    pipelines = hubspot.get("results")
    if not isinstance(pipelines, list):
        raise LauncherError("HubSpot connection test could not read the Deal pipeline list.")
    pipeline = next(
        (item for item in pipelines if isinstance(item, dict) and str(item.get("id", "")) == values["HUBSPOT_PIPELINE_ID"]),
        None,
    )
    stages = pipeline.get("stages") if isinstance(pipeline, dict) else None
    if not isinstance(stages, list) or not any(
        isinstance(item, dict) and str(item.get("id", "")) == values["HUBSPOT_INITIAL_STAGE_ID"]
        for item in stages
    ):
        raise LauncherError("HubSpot connection passed, but the selected Deal pipeline or initial stage was not found.")

    slack_status, slack = _connection_json(
        "https://slack.com/api/auth.test",
        values["SLACK_BOT_TOKEN"],
        "Slack",
        method="POST",
    )
    if slack.get("ok") is not True:
        raise LauncherError("Slack connection test rejected the bot token.")
    slack_post_status, slack_post = _connection_json(
        "https://slack.com/api/chat.postMessage",
        values["SLACK_BOT_TOKEN"],
        "Slack channel",
        method="POST",
        payload={
            "channel": values["SLACK_CHANNEL_ID"],
            "text": (
                "OFFSET 연결 확인 · 이 메시지는 선택한 채널로 주문 알림을 보낼 수 있는지 "
                "확인하는 합성 설정 메시지입니다. 고객·주문·결제 데이터는 포함하지 않습니다."
            ),
        },
    )
    slack_error = str(slack_post.get("error", ""))
    response_channel = str(slack_post.get("channel", ""))
    response_ts = str(slack_post.get("ts", ""))
    if slack_post.get("ok") is not True or response_channel != values["SLACK_CHANNEL_ID"] or not response_ts:
        if slack_error in {"channel_not_found", "not_in_channel", "no_permission", "missing_scope"}:
            raise LauncherError(
                "Slack bot cannot post to the selected channel. Check the channel ID, invite the bot, and confirm chat:write access."
            )
        raise LauncherError("Slack did not confirm delivery of the synthetic setup message to the selected channel.")
    return {
        "hubspot": {"status": "PASS", "http_status": hubspot_status, "pipeline_and_stage": "MATCH"},
        "slack": {
            "status": "PASS",
            "authentication_http_status": slack_status,
            "authentication": "PASS",
            "channel_post_http_status": slack_post_status,
            "channel": "MATCH",
            "synthetic_setup_message": "POSTED",
            "message_ts": response_ts,
        },
    }


def _redact(text: str, values: dict[str, str], *, limit: int | None = 4000) -> str:
    redacted = text
    for key in (
        "PF07_ADMIN_PASSWORD",
        "PF07_DB_PASSWORD",
        "PF07_DB_ROOT_PASSWORD",
        "ODDROOM_WEBHOOK_HMAC_KEY",
        "N8N_ENCRYPTION_KEY",
        "N8N_RUNNERS_AUTH_TOKEN",
    ):
        secret = values.get(key, "")
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    protected = _connected_values()
    for key in ("HUBSPOT_RUNTIME_TOKEN", "SLACK_BOT_TOKEN"):
        secret = protected.get(key, "")
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted[-limit:] if limit is not None else redacted


def _run(
    command: list[str],
    values: dict[str, str],
    *,
    check: bool = True,
    timeout: int = 600,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=package_root(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            env=environment,
        )
    except FileNotFoundError as error:
        raise LauncherError(f"Required executable is unavailable: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise LauncherError(f"Command timed out after {timeout} seconds: {command[0]}") from error
    if check and result.returncode != 0:
        detail = _redact(result.stdout or "", values).strip()
        raise LauncherError(f"Command failed ({result.returncode}).\n{detail}")
    return result


def _compose_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in REQUIRED_ENV_KEYS | CONNECTED_ENV_KEYS | {"PF07_BIND_ADDRESS"}:
        environment.pop(key, None)
    return environment


def _compose(values: dict[str, str], arguments: list[str], *, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    env_arguments = ["--env-file", str(state_dir() / "runtime.env")]
    if connected_env_path().is_file():
        env_arguments.extend(["--env-file", str(connected_env_path())])
    command = [
        "docker",
        "compose",
        "--progress",
        "quiet",
        *env_arguments,
        "-f",
        str(package_root() / "packaging" / "common" / "compose.yaml"),
        "-p",
        values["PF07_COMPOSE_PROJECT"],
        *arguments,
    ]
    return _run(
        command,
        values,
        check=check,
        timeout=timeout,
        environment=_compose_environment(),
    )


def _wp(values: dict[str, str], arguments: list[str], *, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return _compose(
        values,
        ["--profile", "tools", "run", "--rm", "-T", "wpcli", *arguments],
        check=check,
        timeout=timeout,
    )


def _url_ready(
    url: str,
    timeout: float = 3.0,
    *,
    expected_any: tuple[bytes, ...] = (),
) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "PF07-Package-Launcher/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                return False
            if not expected_any:
                return True
            payload = response.read(1024 * 1024).lower()
            return any(token.lower() in payload for token in expected_any)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


def _wait_for_url(
    url: str,
    seconds: int,
    *,
    expected_any: tuple[bytes, ...] = (),
) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _url_ready(url, expected_any=expected_any):
            return
        time.sleep(2)
    raise LauncherError(f"The local target did not become reachable within {seconds} seconds: {url}")


def _verified_download(name: str) -> Path:
    specification = VERIFIED_DOWNLOADS[name]
    directory = state_dir() / "downloads"
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    os.chmod(directory, 0o755)
    target = directory / name
    if target.is_file() and _sha256_file(target) == specification["sha256"]:
        os.chmod(target, 0o644)
        return target
    if target.exists():
        target.unlink()
    temporary = directory / f".{name}.{uuid.uuid4().hex}.tmp"
    request = urllib.request.Request(str(specification["url"]), headers={"User-Agent": "PF07-Package-Launcher/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as destination:
            digest = hashlib.sha256()
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                destination.write(block)
                digest.update(block)
        if digest.hexdigest() != specification["sha256"]:
            raise LauncherError(f"Downloaded prerequisite failed SHA-256 verification: {name}")
        # These are public upstream distributions mounted read-only into a
        # non-privileged container; they contain no package-local secret.
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
        return target
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _prepare_verified_downloads() -> None:
    for name in VERIFIED_DOWNLOADS:
        _verified_download(name)


def _install_verified_wordpress_core(values: dict[str, str]) -> None:
    """Install the exact verified WordPress archive without another network fetch."""
    command = (
        "set -eu; "
        "work=/tmp/pf07-wordpress-core; "
        "rm -rf \"$work\"; mkdir -p \"$work\"; "
        "unzip -oq /workspace/downloads/wordpress-7.0.2.zip -d \"$work\"; "
        "rm -rf /var/www/html/wp-admin /var/www/html/wp-includes; "
        "cp -a \"$work/wordpress/wp-admin\" /var/www/html/wp-admin; "
        "cp -a \"$work/wordpress/wp-includes\" /var/www/html/wp-includes; "
        "find \"$work/wordpress\" -maxdepth 1 -type f -exec cp -f {} /var/www/html/ \\;; "
        "rm -rf \"$work\""
    )
    _compose(
        values,
        ["--profile", "tools", "run", "--rm", "-T", "--entrypoint", "sh", "wpcli", "-c", command],
        timeout=300,
    )
    version_lines = [line.strip() for line in _wp(values, ["core", "version"]).stdout.splitlines() if line.strip()]
    version = version_lines[-1] if version_lines else ""
    if version != "7.0.2":
        raise LauncherError(f"Verified WordPress core installation produced unexpected version: {version}")


def _install_verified_translations(values: dict[str, str]) -> None:
    command = (
        "set -eu; "
        "mkdir -p /var/www/html/wp-content/languages/plugins; "
        "unzip -oq /workspace/downloads/wordpress-7.0.2-ko_KR.zip -d /var/www/html/wp-content/languages; "
        "unzip -oq /workspace/downloads/woocommerce-10.9.4-ko_KR.zip -d /var/www/html/wp-content/languages/plugins"
    )
    _compose(
        values,
        ["--profile", "tools", "run", "--rm", "-T", "--entrypoint", "sh", "wpcli", "-c", command],
        timeout=300,
    )


def _plugin_version(values: dict[str, str], slug: str) -> str | None:
    result = _wp(values, ["plugin", "get", slug, "--field=version"], check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _ensure_wordpress_plugin(
    values: dict[str, str],
    slug: str,
    version: str,
    install_arguments: list[str],
) -> None:
    if _plugin_version(values, slug) != version:
        _wp(values, ["plugin", "install", *install_arguments, "--force"], timeout=900)
    _wp(values, ["plugin", "activate", slug])


def _apply_locale(values: dict[str, str]) -> None:
    locale = selected_locale()
    _wp(values, ["site", "switch-language", locale])


def _apply_package_mode(values: dict[str, str]) -> None:
    _wp(values, ["option", "update", "oddroom_orderops_package_mode", selected_mode()])


def _apply_package_setup(values: dict[str, str]) -> None:
    connected = connected_setup_status()
    payload = {
        "hubspot_alias": connected["hubspot_alias"],
        "slack_alias": connected["slack_alias"],
        "updated_at_utc": _utc_now(),
    }
    _wp(
        values,
        [
            "option",
            "update",
            "oddroom_orderops_package_setup",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "--format=json",
        ],
    )


def _n8n_workflow_ids(values: dict[str, str], *, active_only: bool = False) -> set[str]:
    arguments = ["run", "--rm", "-T", "n8n", "list:workflow"]
    if active_only:
        arguments.append("--active=true")
    arguments.append("--onlyId")
    listed = _compose(
        values,
        arguments,
        timeout=300,
    )
    return {line.strip() for line in listed.stdout.splitlines() if line.strip()}


def _import_connected_credentials(values: dict[str, str]) -> None:
    connected = _connected_values(required=True)
    directory = state_dir() / "credential-import"
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    files = {
        "hubspot.json": [
            {
                "id": "PF07HubSpotRuntime1",
                "name": "PF07 HubSpot Runtime",
                "type": "httpBearerAuth",
                "data": {"token": connected["HUBSPOT_RUNTIME_TOKEN"]},
            }
        ],
        "slack.json": [
            {
                "id": "PF07SlackRuntime1",
                "name": "PF07 Slack Runtime",
                "type": "httpHeaderAuth",
                "data": {"name": "Authorization", "value": "Bearer " + connected["SLACK_BOT_TOKEN"]},
            }
        ],
    }
    paths: list[Path] = []
    try:
        for name, payload in files.items():
            path = directory / name
            temp = directory / f".{name}.{uuid.uuid4().hex}.tmp"
            temp.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
            os.chmod(temp, 0o600)
            os.replace(temp, path)
            paths.append(path)
            _compose(
                values,
                ["run", "--rm", "-T", "n8n", "import:credentials", f"--input=/workspace/credential-import/{name}"],
                timeout=300,
            )
    finally:
        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _provision_n8n(values: dict[str, str]) -> None:
    workflows = {
        DEMO_WORKFLOW_ID: "/workspace/workflows/demo-mode.json",
        CONNECTED_WORKFLOW_ID: "/workspace/workflows/connected-mode.json",
    }
    # n8n replaces an existing workflow when an import carries the same stable
    # ID. Re-import both reviewed definitions on every provision so a
    # controlled package update applies workflow changes without creating a
    # second workflow identity.
    for workflow in workflows.values():
        _compose(
            values,
            ["run", "--rm", "-T", "n8n", "import:workflow", f"--input={workflow}"],
            timeout=300,
        )
    selected = CONNECTED_WORKFLOW_ID if selected_mode() == "CONNECTED_MODE" else DEMO_WORKFLOW_ID
    if selected == CONNECTED_WORKFLOW_ID:
        _import_connected_credentials(values)
    active = _n8n_workflow_ids(values, active_only=True)
    for workflow_id in active - {selected}:
        if workflow_id in workflows:
            _compose(values, ["run", "--rm", "-T", "n8n", "unpublish:workflow", f"--id={workflow_id}"], timeout=300)
    if selected not in active:
        _compose(values, ["run", "--rm", "-T", "n8n", "publish:workflow", f"--id={selected}"], timeout=300)


def _n8n_ready(values: dict[str, str]) -> bool:
    result = _compose(
        values,
        ["exec", "-T", "n8n", "wget", "-qO-", "http://127.0.0.1:5678/healthz"],
        check=False,
        timeout=15,
    )
    return result.returncode == 0 and "ok" in result.stdout.lower()


def _wait_for_n8n(values: dict[str, str], seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _n8n_ready(values):
            return
        time.sleep(2)
    raise LauncherError(f"The package-owned n8n service did not become ready within {seconds} seconds.")


def _n8n_webhook_ready(values: dict[str, str]) -> bool:
    path = values.get("ODDROOM_WEBHOOK_PATH", "")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", path) is None:
        return False
    url = "http://127.0.0.1:5678/webhook/" + path
    script = (
        f"fetch({json.dumps(url)},{{method:'POST',body:''}})"
        ".then(response=>process.stdout.write(String(response.status)))"
        ".catch(()=>process.exit(1));"
    )
    result = _compose(
        values,
        ["exec", "-T", "n8n", "node", "-e", script],
        check=False,
        timeout=15,
    )
    # Both reviewed workflows reject an unsigned request with 401. This
    # distinguishes a registered webhook from n8n's earlier health-only 404.
    return result.returncode == 0 and result.stdout.strip() == "401"


def _wait_for_n8n_webhook(values: dict[str, str], seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _n8n_webhook_ready(values):
            return
        time.sleep(1)
    raise LauncherError(
        f"The package-owned n8n webhook did not become active within {seconds} seconds."
    )


def _start_automation(values: dict[str, str], *, start_worker: bool = True) -> None:
    _compose(values, ["stop", "worker", "task-runners", "n8n"], check=False, timeout=180)
    _provision_n8n(values)
    _ensure_task_runner_image(values)
    _compose(values, ["up", "-d", "n8n", "task-runners"], timeout=900)
    _wait_for_n8n(values, 180)
    _wait_for_n8n_webhook(values, 120)
    if start_worker:
        _compose(values, ["up", "-d", "worker"], timeout=900)


def _ensure_task_runner_image(values: dict[str, str]) -> str:
    existing = _run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            '{{ index .Config.Labels "io.pf07.task-runner.contract" }}',
            TASK_RUNNER_IMAGE_REFERENCE,
        ],
        values,
        check=False,
        timeout=30,
    )
    if existing.returncode == 0 and existing.stdout.strip() == TASK_RUNNER_IMAGE_CONTRACT:
        return "CACHED_VERIFIED_IMAGE"
    _set_operation("task-runner-image", "고정 의존성으로 task runner 이미지를 첫 1회 준비하는 중입니다.")
    _compose(values, ["build", "task-runners"], timeout=900)
    verified = _run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            '{{ index .Config.Labels "io.pf07.task-runner.contract" }}',
            TASK_RUNNER_IMAGE_REFERENCE,
        ],
        values,
        check=False,
        timeout=30,
    )
    if verified.returncode != 0 or verified.stdout.strip() != TASK_RUNNER_IMAGE_CONTRACT:
        raise LauncherError("The versioned PF07 task-runner image was not created.")
    return "BUILT_FROM_PINNED_LOCK"


def _docker_preflight(values: dict[str, str]) -> None:
    result = preflight()
    if not result["ready"]:
        raise LauncherError(str(result["message"]))


def _installer_guidance() -> dict[str, Any]:
    system = platform.system().lower()
    if system == "windows":
        runtime = {
            "name": "Rancher Desktop",
            "cost": "0 KRW",
            "url": "https://rancherdesktop.io/",
            "instructions": [
                "Open the official Rancher Desktop download page.",
                "Install Rancher Desktop with the Moby container engine selected.",
                "Start Rancher Desktop and wait until its status is Ready.",
                "Open PF07-Launcher.exe again; the package resumes at prerequisite recheck.",
            ],
        }
    elif system == "darwin":
        runtime = {
            "name": "Rancher Desktop",
            "cost": "0 KRW",
            "url": "https://rancherdesktop.io/",
            "instructions": [
                "Open the official Rancher Desktop download page.",
                "Install the build matching this Mac and select the Moby container engine.",
                "Start Rancher Desktop and wait until its status is Ready.",
                "Open PF07 Launcher.app again; the package resumes at prerequisite recheck.",
            ],
        }
    else:
        runtime = {
            "name": "Docker Engine with Compose plugin",
            "cost": "0 KRW",
            "url": "https://docs.docker.com/engine/install/",
            "instructions": [
                "Open the official Docker Engine installation guide for this distribution.",
                "Install Docker Engine and the Compose plugin from the maintained repository.",
                "Start Docker and grant the current user documented local access.",
                "Open PF07-Launcher again; the package resumes at prerequisite recheck.",
            ],
        }
    return {
        "python": {
            "name": "Python 3.10 or newer",
            "url": "https://www.python.org/downloads/",
            "instructions": [
                "Open the official Python download page.",
                "Install Python 3.10 or newer and enable its launcher/PATH option.",
                "Open the PF07 launcher again to resume prerequisite recheck.",
            ],
        },
        "runtime": runtime,
        "docker_desktop_boundary": (
            "Docker Desktop is an optional alternative only when the recipient confirms applicable license eligibility."
        ),
    }


def preflight(*, open_installer: bool = False) -> dict[str, Any]:
    """Detect package prerequisites without creating runtime identity or secrets."""
    python_ready = sys.version_info >= (3, 10)
    docker_path = shutil.which("docker")
    runtime_cli_present = docker_path is not None
    runtime_daemon_ready = False
    compose_ready = False
    server_version: str | None = None
    compose_version: str | None = None
    if runtime_cli_present:
        try:
            info = subprocess.run(
                [docker_path, "info", "--format", "{{.ServerVersion}}"],
                cwd=package_root(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
            runtime_daemon_ready = info.returncode == 0
            if runtime_daemon_ready:
                server_version = info.stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            runtime_daemon_ready = False
        if runtime_daemon_ready:
            try:
                compose = subprocess.run(
                    [docker_path, "compose", "version", "--short"],
                    cwd=package_root(),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                    check=False,
                )
                compose_ready = compose.returncode == 0
                if compose_ready:
                    compose_version = compose.stdout.strip() or None
            except (OSError, subprocess.TimeoutExpired):
                compose_ready = False
    facts = PrerequisiteFacts(
        python_ready=python_ready,
        runtime_cli_present=runtime_cli_present,
        runtime_daemon_ready=runtime_daemon_ready,
        compose_ready=compose_ready,
    )
    state = classify_prerequisites(facts)
    guidance = _installer_guidance()
    target = guidance["python"] if state == "MISSING_PYTHON" else guidance["runtime"]
    opened = False
    if open_installer and state != "READY":
        opened = webbrowser.open(str(target["url"]), new=2)
    messages = {
        "READY": "Python, the container runtime, and Docker Compose are ready.",
        "MISSING_PYTHON": "Python 3.10 or newer is required. Use the graphical installer guide, then reopen PF07.",
        "MISSING_RUNTIME": "A supported Docker-compatible runtime is missing. Use the graphical installer guide, then reopen PF07.",
        "RUNTIME_STOPPED": "The container runtime is installed but not ready. Start it, wait for Ready, and recheck.",
        "MISSING_COMPOSE": "The Docker Compose plugin is missing. Complete the supported runtime installation, then recheck.",
    }
    return {
        "schema": "pf07.prerequisite-status.v1",
        "ready": state == "READY",
        "state": state,
        "recovery_action": recovery_action(state),
        "message": messages[state],
        "python": {"ready": python_ready, "version": platform.python_version()},
        "container_runtime": {
            "cli_present": runtime_cli_present,
            "daemon_ready": runtime_daemon_ready,
            "server_version": server_version,
            "compose_ready": compose_ready,
            "compose_version": compose_version,
        },
        "installer": target if state != "READY" else None,
        "installer_opened": opened,
        "all_guidance": guidance,
        "checked_at_utc": _utc_now(),
    }


@contextmanager
def _operation_lock(
    *,
    allow_restore_transaction: bool = False,
    allow_controlled_update_transaction: bool = False,
) -> Iterator[None]:
    lock_path = state_dir() / "operation.lock"
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_key = str(lock_path.resolve())
    if getattr(_OPERATION_LOCK_CONTEXT, "path", None) == lock_key:
        _OPERATION_LOCK_CONTEXT.depth += 1
        try:
            yield
        finally:
            _OPERATION_LOCK_CONTEXT.depth -= 1
        return
    if not allow_restore_transaction:
        _require_no_restore_transaction()
    if not allow_controlled_update_transaction:
        _require_no_controlled_update_transaction()
    if (state_dir() / "update.lock").exists():
        raise LauncherError("A controlled PF07 update is in progress or requires recovery before another operation.")
    descriptor: int | None = None
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(descriptor, f"{os.getpid()}\n{_utc_now()}\n".encode("ascii"))
            break
        except FileExistsError as error:
            if attempt == 0 and _recover_dead_package_lock(lock_path):
                continue
            raise LauncherError("Another PF07 operation is already running. Let it finish, then retry.") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
    _OPERATION_LOCK_CONTEXT.path = lock_key
    _OPERATION_LOCK_CONTEXT.depth = 1
    try:
        yield
    finally:
        _OPERATION_LOCK_CONTEXT.depth = 0
        _OPERATION_LOCK_CONTEXT.path = None
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        try:
            lock_path.parent.rmdir()
        except OSError:
            pass


def _recover_dead_package_lock(lock_path: Path) -> bool:
    """Remove only an unchanged package-owned lock whose host PID no longer exists."""
    try:
        snapshot = lock_path.stat()
        lines = lock_path.read_text(encoding="ascii").splitlines()
        pid = int(lines[0])
    except (FileNotFoundError, OSError, UnicodeError, ValueError, IndexError):
        return False
    if pid <= 0:
        return False
    if _host_process_alive(pid):
        return False
    try:
        current = lock_path.stat()
        if (
            current.st_dev != snapshot.st_dev
            or current.st_ino != snapshot.st_ino
            or current.st_size != snapshot.st_size
            or current.st_mtime_ns != snapshot.st_mtime_ns
        ):
            return False
        lock_path.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def _host_process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
        open_process.restype = ctypes.c_void_p
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        wait_for_single_object.restype = ctypes.c_uint32
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (ctypes.c_void_p,)
        close_handle.restype = ctypes.c_int
        synchronize = 0x00100000
        process_query_limited_information = 0x1000
        wait_timeout = 0x00000102
        handle = open_process(synchronize | process_query_limited_information, 0, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            return wait_for_single_object(handle, 0) == wait_timeout
        finally:
            close_handle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _release_owned_lock(lock_path: Path, descriptor: int | None) -> None:
    if descriptor is None:
        return
    snapshot = os.fstat(descriptor)
    os.close(descriptor)
    try:
        current = lock_path.stat()
        if current.st_dev == snapshot.st_dev and current.st_ino == snapshot.st_ino:
            lock_path.unlink()
    except FileNotFoundError:
        pass


def start(*, _controlled_update_tentative: bool = False) -> dict[str, Any]:
    # Establish the host runtime prerequisite before operation locking can
    # create package-local state.
    _docker_preflight({})
    with _operation_lock():
        try:
            package_state_existed = (state_dir() / "runtime.env").is_file()
            values = _synchronize_runtime_mode(ensure_runtime())
            if package_state_existed:
                current = status()
                if current["ready"]:
                    _set_operation("ready", "이미 실행 중인 상점과 관리자 화면에 다시 연결했습니다.", "PASS")
                    result = status()
                    if result["ready"]:
                        result["start_disposition"] = "RERUN_READY"
                        return result
                if current["runtime_state"] == "PORT_OCCUPIED":
                    stopped_tunnel = _stop_tunnel_processes()
                    if not all(stopped_tunnel.values()):
                        raise LauncherError(
                            "The HTTPS tunnel could not be fully stopped before local-address recovery. "
                            "Retry Disable tunnel, then recover PF07."
                        )
                    previous_port = values["PF07_WORDPRESS_PORT"]
                    recovered_port = _select_free_loopback_port()
                    values["PF07_WORDPRESS_PORT"] = str(recovered_port)
                    values["ODDROOM_PUBLIC_BASE_URL"] = f"http://127.0.0.1:{recovered_port}"
                    _write_runtime_env(state_dir() / "runtime.env", values)
                    _set_operation(
                        "port-recovery",
                        f"로컬 주소 {previous_port} 대신 사용 가능한 {recovered_port} 포트로 같은 상점을 옮겼습니다.",
                    )
            _set_operation("preflight", "Docker 실행 환경을 확인하는 중입니다.")
            _docker_preflight(values)
            # Populate the host-owned, read-only download cache before Compose
            # can materialize its bind-mount source as root.
            _set_operation("downloads", "고정 버전 필수 파일을 무결성 확인하는 중입니다.")
            _prepare_verified_downloads()
            _set_operation("containers", "격리된 데이터베이스와 WordPress를 시작하는 중입니다.")
            _compose(values, ["up", "-d", "db", "wordpress"], timeout=900)
            _wait_for_url(values["ODDROOM_PUBLIC_BASE_URL"], 300)

            _set_operation("wordpress", "WordPress와 한국어 표시를 준비하는 중입니다.")
            installed = _wp(values, ["core", "is-installed"], check=False)
            if installed.returncode != 0:
                _wp(
                    values,
                    [
                        "core",
                        "install",
                        f"--url={values['ODDROOM_PUBLIC_BASE_URL']}",
                        "--title=OFFSET Order System",
                        f"--admin_user={values['PF07_ADMIN_USER']}",
                        f"--admin_email={ADMIN_EMAIL}",
                        f"--admin_password={values['PF07_ADMIN_PASSWORD']}",
                        "--skip-email",
                    ],
                    timeout=600,
                )
            _set_operation("dependencies", "WooCommerce와 Action Scheduler를 고정 버전으로 준비하는 중입니다.")
            _install_verified_wordpress_core(values)
            _wp(values, ["core", "update-db"])
            _ensure_wordpress_plugin(
                values,
                "action-scheduler",
                "4.0.0",
                ["/workspace/downloads/action-scheduler-4.0.0.zip"],
            )
            _ensure_wordpress_plugin(values, "woocommerce", "10.9.4", ["/workspace/downloads/woocommerce.10.9.4.zip"])
            _install_verified_translations(values)

            _set_operation("storefront", "OFFSET 상점과 운영 화면을 준비하는 중입니다.")
            for key, value in (
                ("blog_public", "0"),
                ("timezone_string", "Asia/Seoul"),
                ("permalink_structure", "/%postname%/"),
                ("woocommerce_currency", "KRW"),
                ("woocommerce_price_num_decimals", "2"),
                ("woocommerce_enable_guest_checkout", "yes"),
            ):
                _wp(values, ["option", "update", key, value])
            _apply_locale(values)
            _wp(values, ["plugin", "activate", "oddroom-orderops"])
            _apply_package_mode(values)
            _apply_package_setup(values)
            _wp(values, ["oddroom-orderops", "preflight"])
            _wp(values, ["oddroom-orderops", "setup-storefront"])
            _wp(values, ["rewrite", "flush", "--hard"])

            _set_operation("automation", "패키지 소유 n8n 워크플로와 백그라운드 작업자를 준비하는 중입니다.")
            if selected_mode() == "CONNECTED_MODE":
                _connected_values(required=True)
            _start_automation(values, start_worker=not _controlled_update_tentative)

            _set_operation("verify", "상점, 관리자, n8n, 작업자 대상을 확인하는 중입니다.")
            _wait_for_url(
                values["ODDROOM_PUBLIC_BASE_URL"],
                120,
                expected_any=(b"oddroom-frontbar",),
            )
            _wait_for_url(
                values["ODDROOM_PUBLIC_BASE_URL"] + "/wp-admin/",
                120,
                expected_any=(b"user_login",),
            )
            result = status()
            if _controlled_update_tentative:
                expected_services = {"db", "wordpress", "n8n", "task-runners"}
                if (
                    set(result["services"]) != expected_services
                    or not result["store_reachable"]
                    or not result["admin_reachable"]
                    or not result["n8n_reachable"]
                    or not result["task_runner_running"]
                    or result["worker_running"]
                ):
                    raise LauncherError(
                        "The tentative successor did not become ready with outbound order processing paused."
                    )
                _set_operation(
                    "verify",
                    "상점과 운영 기반이 준비됐습니다. 업데이트 확정 전까지 주문 처리는 멈춰 있습니다.",
                )
                result = status()
                result["controlled_update_tentative_ready"] = True
                result["start_disposition"] = "CONTROLLED_UPDATE_TENTATIVE_READY"
                return result
            if not result["ready"]:
                raise LauncherError("The package started, but the storefront readiness check did not pass.")
            _set_operation("ready", "상점과 관리자 화면을 열 수 있습니다.", "PASS")
            result = status()
            result["start_disposition"] = "RERUN_READY" if package_state_existed else "FIRST_RUN_READY"
            return result
        except Exception as error:
            _set_operation("error", str(error), "FAIL")
            raise


def status() -> dict[str, Any]:
    package_state_existed = (state_dir() / "runtime.env").is_file()
    if not package_state_existed:
        config_path = state_dir() / "config.json"
        config = {"mode": "DEMO_MODE", "locale": "ko_KR"}
        operation: dict[str, Any] | None = None
        if config_path.is_file():
            try:
                candidate = json.loads(config_path.read_text(encoding="utf-8"))
                if candidate.get("mode") in SUPPORTED_MODES and candidate.get("locale") in SUPPORTED_LOCALES:
                    config = {"mode": candidate["mode"], "locale": candidate["locale"]}
            except (OSError, json.JSONDecodeError):
                pass
        operation_path = state_dir() / "operation.json"
        if operation_path.is_file():
            try:
                candidate = json.loads(operation_path.read_text(encoding="utf-8"))
                if isinstance(candidate, dict):
                    operation = candidate
            except (OSError, json.JSONDecodeError):
                operation = None
        return {
            "schema": "pf07.launcher-status.v1",
            "mode": config["mode"],
            "locale": config["locale"],
            "ready": False,
            "runtime_state": "FIRST_RUN",
            "recovery_action": recovery_action("FIRST_RUN"),
            "services": [],
            "requested_port_available": True,
            "store_reachable": False,
            "admin_reachable": False,
            "n8n_reachable": False,
            "worker_running": False,
            "task_runner_running": False,
            "connected_setup": {
                "configured": False,
                "hubspot_alias": "OFFSET Customer Records",
                "slack_alias": "OFFSET Order Alerts",
                "storage": "PACKAGE_PROTECTED_LOCAL",
                "connection_test": "NOT_RUN",
            },
            "urls": {"store": None, "admin": None},
            "admin_user": ADMIN_USER,
            "compose_project": None,
            "tunnel": tunnel_status(),
            "operation": operation,
            "checked_at_utc": _utc_now(),
        }
    values = _synchronize_runtime_mode(ensure_runtime())
    services: list[str] = []
    if shutil.which("docker") is not None:
        result = _compose(values, ["ps", "--status", "running", "--services"], check=False, timeout=30)
        if result.returncode == 0:
            services = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    base = values["ODDROOM_PUBLIC_BASE_URL"]
    store_reachable = _url_ready(base, expected_any=(b"oddroom-frontbar",))
    admin_reachable = _url_ready(base + "/wp-admin/", expected_any=(b"user_login",))
    n8n_reachable = "n8n" in services and _n8n_ready(values)
    worker_running = "worker" in services
    task_runner_running = "task-runners" in services
    operation: dict[str, Any] | None = None
    operation_path = state_dir() / "operation.json"
    if operation_path.is_file():
        try:
            operation = json.loads(operation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            operation = None
    requested_port_available = "wordpress" in services or _port_available(int(values["PF07_WORDPRESS_PORT"]))
    ready = store_reachable \
        and admin_reachable \
        and n8n_reachable \
        and worker_running \
        and task_runner_running \
        and {"db", "wordpress", "n8n", "task-runners", "worker"}.issubset(services)
    runtime_state = classify_runtime(
        RuntimeFacts(
            package_state_exists=package_state_existed,
            requested_port_available=requested_port_available,
            services_running=bool(services),
            health_ready=ready,
        )
    )
    return {
        "schema": "pf07.launcher-status.v1",
        "mode": selected_mode(),
        "locale": selected_locale(),
        "ready": ready,
        "runtime_state": runtime_state,
        "recovery_action": recovery_action(runtime_state),
        "services": services,
        "requested_port_available": requested_port_available,
        "store_reachable": store_reachable,
        "admin_reachable": admin_reachable,
        "n8n_reachable": n8n_reachable,
        "worker_running": worker_running,
        "task_runner_running": task_runner_running,
        "connected_setup": connected_setup_status(),
        "urls": {"store": base + "/", "admin": base + "/wp-admin/"},
        "admin_user": values["PF07_ADMIN_USER"],
        "compose_project": values["PF07_COMPOSE_PROJECT"],
        "tunnel": tunnel_status(),
        "operation": operation,
        "checked_at_utc": _utc_now(),
    }


def credentials() -> dict[str, str]:
    if not (state_dir() / "runtime.env").is_file():
        raise LauncherError("Start the service before opening the package-local management account.")
    values = ensure_runtime()
    return {
        "admin_user": values["PF07_ADMIN_USER"],
        "admin_password": values["PF07_ADMIN_PASSWORD"],
        "scope": "PACKAGE_LOCAL_DEMO_ADMIN",
    }


def _command_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    start_index = result.stdout.find("{")
    end_index = result.stdout.rfind("}")
    if start_index < 0 or end_index < start_index:
        raise LauncherError("The package command did not return a JSON result.")
    try:
        value = json.loads(result.stdout[start_index : end_index + 1])
    except json.JSONDecodeError as error:
        raise LauncherError("The package command returned an unreadable JSON result.") from error
    if not isinstance(value, dict):
        raise LauncherError("The package command returned an invalid result shape.")
    return value


def set_demo_scenario(scenario: str) -> dict[str, Any]:
    if scenario not in {"normal", "fail_once", "terminal", "operator_review"}:
        raise LauncherError("Demo scenario is invalid.")
    with _operation_lock():
        current = status()
        if not current["ready"] or selected_mode() != "DEMO_MODE":
            raise LauncherError("Start the ready DEMO_MODE runtime before selecting a delivery scenario.")
        values = ensure_runtime()
        return _command_json(_wp(values, ["oddroom-orderops", "demo-scenario", scenario]))


def reset_demo(confirmation: str) -> dict[str, Any]:
    if confirmation != "RESET PF07 DEMO":
        raise LauncherError("Type RESET PF07 DEMO exactly to confirm the package-scoped reset.")
    with _operation_lock():
        current = status()
        if not current["ready"] or selected_mode() != "DEMO_MODE":
            raise LauncherError("Start the ready DEMO_MODE runtime before resetting demo data.")
        values = ensure_runtime()
        return _command_json(
            _wp(values, ["oddroom-orderops", "reset-demo", "--confirm=RESET PF07 DEMO"], timeout=300)
        )


def _set_mode_locked(mode: str) -> dict[str, Any]:
    """Apply a validated mode while the caller owns the package operation lock."""
    if mode == "CONNECTED_MODE":
        _connected_values(required=True)
    current_config = ensure_config()
    _atomic_json(
        state_dir() / "config.json",
        {"schema": "pf07.package-config.v1", "mode": mode, "locale": current_config["locale"]},
    )
    values = ensure_runtime()
    values["ODDROOM_WEBHOOK_PATH"] = (
        "oddroom-orderops-v1" if mode == "CONNECTED_MODE" else "oddroom-orderops-demo-v1"
    )
    _write_runtime_env(state_dir() / "runtime.env", values)
    running = status()["services"]
    if not {"db", "wordpress"}.issubset(running):
        return status()
    _set_operation("mode", f"{mode} 자동화 경로를 같은 비즈니스 런타임에 적용하는 중입니다.")
    _compose(values, ["stop", "worker", "task-runners", "n8n"], check=False, timeout=180)
    _compose(values, ["up", "-d", "--force-recreate", "wordpress"], timeout=600)
    _wait_for_url(values["ODDROOM_PUBLIC_BASE_URL"], 180)
    _apply_package_mode(values)
    _apply_package_setup(values)
    _provision_n8n(values)
    _ensure_task_runner_image(values)
    _compose(values, ["up", "-d", "n8n", "task-runners", "worker"], timeout=900)
    _wait_for_n8n(values, 180)
    result = status()
    if not result["ready"]:
        raise LauncherError(f"{mode} was selected, but the package did not return to ready state.")
    _set_operation("ready", f"{mode}가 같은 비즈니스 런타임에 적용되었습니다.", "PASS")
    return status()


def _restore_ready_mode_transition(
    preimages: dict[Path, dict[str, Any]],
    previous_mode: str,
    running_before: list[str],
) -> tuple[bool, str | None]:
    """Restore protected state and the prior ready runtime after a failed mode transition."""
    try:
        for path, preimage in preimages.items():
            _restore_file_preimage(path, preimage)
        previous_values = ensure_runtime()
        resumed = _compose(
            previous_values,
            ["up", "-d", *running_before],
            check=False,
            timeout=900,
        )
        if resumed.returncode != 0:
            detail = _redact(resumed.stdout or "", previous_values).strip()
            raise LauncherError(f"The previous PF07 services could not be resumed. {detail}")
        restored = _set_mode_locked(previous_mode)
        if not restored["ready"] or restored["mode"] != previous_mode:
            raise LauncherError("The previous PF07 operation mode did not return to its ready state.")
        return True, None
    except Exception as rollback_error:
        return False, str(rollback_error)


def set_mode(mode: str) -> dict[str, Any]:
    mode = mode.strip().upper()
    if mode not in SUPPORTED_MODES:
        raise LauncherError("Mode must be DEMO_MODE or CONNECTED_MODE.")
    if not (state_dir() / "runtime.env").is_file():
        raise LauncherError("Start the service before changing its operation mode.")
    with _operation_lock():
        current = status()
        if not current["ready"]:
            raise LauncherError("Return PF07 to its ready state before changing its operation mode.")
        previous_mode = selected_mode()
        previous_values = ensure_runtime()
        running_before = _running_services(previous_values)
        protected_paths = (
            state_dir() / "config.json",
            state_dir() / "runtime.env",
            connected_env_path(),
        )
        preimages = {path: _file_preimage(path) for path in protected_paths}
        try:
            return _set_mode_locked(mode)
        except Exception as error:
            restored, rollback_error = _restore_ready_mode_transition(
                preimages,
                previous_mode,
                running_before,
            )
            message = (
                f"{error} Previous ready runtime restored={str(restored).lower()}."
                + (f" Recovery detail: {rollback_error}" if rollback_error else "")
            )
            _set_operation("error", message, "FAIL")
            raise LauncherError(message) from error


def configure_connected(configuration: dict[str, str]) -> dict[str, Any]:
    if not (state_dir() / "runtime.env").is_file():
        raise LauncherError("Start the service before configuring connected operation.")
    if configuration.get("slack_test_confirmation", "") != "SEND PF07 SLACK TEST":
        raise LauncherError(
            "Confirm the one-time synthetic Slack setup message before applying connected operation."
        )
    values = {
        "HUBSPOT_RUNTIME_TOKEN": _validate_token(configuration.get("hubspot_token", ""), "HubSpot token"),
        "HUBSPOT_PIPELINE_ID": _validate_identifier(configuration.get("hubspot_pipeline_id", ""), "HubSpot pipeline"),
        "HUBSPOT_INITIAL_STAGE_ID": _validate_identifier(configuration.get("hubspot_initial_stage_id", ""), "HubSpot initial stage"),
        "HUBSPOT_CREDENTIAL_ALIAS": _validate_identifier(
            configuration.get("hubspot_alias", "OFFSET Customer Records"),
            "HubSpot alias",
            r"[A-Za-z][A-Za-z0-9 ._-]{2,63}",
        ),
        "SLACK_BOT_TOKEN": _validate_token(configuration.get("slack_token", ""), "Slack token"),
        "SLACK_CHANNEL_ID": _validate_identifier(
            configuration.get("slack_channel_id", ""),
            "Slack channel",
            r"[CG][A-Z0-9]{8,20}",
        ),
        "SLACK_CREDENTIAL_ALIAS": _validate_identifier(
            configuration.get("slack_alias", "OFFSET Order Alerts"),
            "Slack alias",
            r"[A-Za-z][A-Za-z0-9 ._-]{2,63}",
        ),
    }
    tests = _test_connected_services(values)
    with _operation_lock():
        current = status()
        if not current["ready"]:
            raise LauncherError("Return PF07 to its ready state before configuring connected operation.")
        previous_mode = selected_mode()
        previous_values = ensure_runtime()
        running_before = _running_services(previous_values)
        protected_paths = (
            state_dir() / "config.json",
            state_dir() / "runtime.env",
            connected_env_path(),
        )
        preimages = {path: _file_preimage(path) for path in protected_paths}
        try:
            _write_runtime_env(connected_env_path(), values)
            runtime = dict(previous_values)
            runtime["PF07_HUBSPOT_CONFIGURED"] = "true"
            runtime["PF07_SLACK_CONFIGURED"] = "true"
            _write_runtime_env(state_dir() / "runtime.env", runtime)
            runtime_status = _set_mode_locked("CONNECTED_MODE")
        except Exception as error:
            restored, rollback_error = _restore_ready_mode_transition(
                preimages,
                previous_mode,
                running_before,
            )
            message = (
                f"{error} Previous ready runtime restored={str(restored).lower()}."
                + (f" Recovery detail: {rollback_error}" if rollback_error else "")
            )
            _set_operation("error", message, "FAIL")
            raise LauncherError(message) from error
    return {
        "status": "PASS",
        "mode": "CONNECTED_MODE",
        "connection_tests": tests,
        "connected_setup": connected_setup_status(),
        "runtime": runtime_status,
    }


def set_locale(locale: str) -> dict[str, Any]:
    if locale not in SUPPORTED_LOCALES:
        raise LauncherError("Locale must be ko_KR or en_US.")
    with _operation_lock():
        current_config = ensure_config()
        previous_locale = current_config["locale"]
        config_path = state_dir() / "config.json"
        config_preimage = _file_preimage(config_path)
        runtime_exists = (state_dir() / "runtime.env").is_file()
        values: dict[str, str] | None = ensure_runtime() if runtime_exists else None
        current = status() if values is not None else None
        apply_to_runtime = bool(
            current is not None and {"db", "wordpress"}.issubset(current["services"])
        )
        try:
            config = {"schema": "pf07.package-config.v1", "mode": current_config["mode"], "locale": locale}
            _atomic_json(config_path, config)
            if values is None:
                return status()
            if apply_to_runtime:
                _set_operation("language", "표시 언어를 같은 데모 런타임에 적용하는 중입니다.")
                _apply_locale(values)
                _wp(values, ["oddroom-orderops", "setup-storefront"])
                _set_operation("ready", "상점과 관리자 화면을 열 수 있습니다.", "PASS")
            return status()
        except Exception as error:
            restored = False
            rollback_error: str | None = None
            try:
                _restore_file_preimage(config_path, config_preimage)
                if values is not None and apply_to_runtime:
                    _apply_locale(values)
                    _wp(values, ["oddroom-orderops", "setup-storefront"])
                restored = selected_locale() == previous_locale
            except Exception as locale_rollback_error:
                rollback_error = str(locale_rollback_error)
            message = (
                f"{error} Previous locale restored={str(restored).lower()}."
                + (f" Recovery detail: {rollback_error}" if rollback_error else "")
            )
            _set_operation("error", message, "FAIL")
            raise LauncherError(message) from error


def _require_existing_runtime(action: str) -> None:
    if not (state_dir() / "runtime.env").is_file():
        raise LauncherError(f"Start PF07 successfully before {action}.")


def stop() -> dict[str, Any]:
    with _operation_lock(allow_restore_transaction=True):
        _require_existing_runtime("stopping its service")
        try:
            values = ensure_runtime()
            tunnel_result = _stop_tunnel_processes()
            if not all(tunnel_result.values()):
                raise LauncherError(
                    "The HTTPS tunnel could not be fully stopped. Retry Disable tunnel before stopping PF07."
                )
            _set_operation("stop", "패키지 컨테이너를 중지하는 중입니다.")
            _compose(values, ["stop"], timeout=180)
            _set_operation("stopped", "데모가 중지됐습니다. 로컬 데이터는 보존됩니다.", "PASS")
        except Exception as error:
            _set_operation("error", str(error), "FAIL")
            raise
    result = status()
    result["tunnel_stopped"] = all(tunnel_result.values())
    return result


def restart() -> dict[str, Any]:
    """Restart the one package-owned stack without changing its identity."""
    with _operation_lock():
        _require_existing_runtime("restarting its service")
        try:
            values = ensure_runtime()
            _set_operation("restart", "패키지 런타임을 같은 ID로 다시 시작하는 중입니다.")
            _compose(values, ["stop"], check=False, timeout=180)
            result = start()
            result["recovery_operation"] = "RESTART"
            return result
        except Exception as error:
            _set_operation("error", str(error), "FAIL")
            raise


def recover() -> dict[str, Any]:
    """Reconnect stopped services or reconcile an unhealthy package-owned stack."""
    with _operation_lock(
        allow_restore_transaction=True,
        allow_controlled_update_transaction=True,
    ):
        update_transaction = _read_controlled_update_transaction()
        if update_transaction is not None:
            return _recover_controlled_update(update_transaction)
        transaction = _read_restore_transaction()
        if transaction is not None:
            container_name = transaction.get("active_container")
            if container_name is not None:
                if not _remove_transient_container(str(container_name)):
                    raise LauncherError(
                        "The timed-out restore container is still active. Stop this exact package-owned "
                        f"container before any data recovery: {container_name}."
                    )
                transaction = _update_restore_transaction(
                    active_container=None,
                    container_stopped_at_utc=_utc_now(),
                )
            state = str(transaction.get("state", "RESTORE_IN_PROGRESS"))
            if state == "RESTORED_SERVICE_RECOVERY_REQUIRED":
                result = start()
                if result["ready"]:
                    _restore_transaction_path().unlink(missing_ok=True)
                    result["recovery_operation"] = "RECOVER_RESTORED_SERVICE"
                    return result
                raise LauncherError("The restored data remains unavailable. Resolve the reported start cause and retry Recover service.")
            required_key = (
                "pre_restore_backup_path"
                if transaction.get("pre_restore_backup_path")
                else "incoming_archive_path"
            )
            required_archive = str(transaction.get(required_key, ""))
            recovery_state = (
                "PREIMAGE_RESTORE_REQUIRED"
                if required_key == "pre_restore_backup_path"
                else "RETRY_RESTORE_REQUIRED"
            )
            _update_restore_transaction(
                state=recovery_state,
                required_archive_path=required_archive,
            )
            raise LauncherError(
                "The interrupted restore container is stopped. Keep the service stopped and use Restore backup "
                f"with this exact archive before starting anything: {required_archive}"
            )
        result = start()
        result["recovery_operation"] = "RECOVER"
        return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_verification() -> dict[str, Any]:
    root = package_root()
    checked: list[dict[str, Any]] = []
    checksum_path = root / "SHA256SUMS.txt"
    if checksum_path.is_file():
        for raw_line in checksum_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            expected, relative = raw_line.split(maxsplit=1)
            relative = relative.lstrip("* ")
            target = (root / relative).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                checked.append({"path": relative, "status": "MISSING"})
                continue
            actual = _sha256_file(target)
            checked.append({"path": relative, "status": "PASS" if actual == expected else "MISMATCH"})
    else:
        for relative in (
            "packaging/common/bootstrap-manifest.json",
            "packaging/common/action-contract.json",
            "packaging/common/workflows/demo-mode.json",
            "packaging/common/workflows/connected-mode.json",
            "payload/oddroom-orderops/oddroom-orderops.php",
        ):
            target = root / relative
            checked.append(
                {"path": relative, "status": "PASS" if target.is_file() else "MISSING", "sha256": _sha256_file(target) if target.is_file() else None}
            )
    return {
        "status": "PASS" if checked and all(item["status"] == "PASS" for item in checked) else "FAIL",
        "files_checked": len(checked),
        "results": checked,
    }


def _alias_package_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _alias_package_paths(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_alias_package_paths(child) for child in value]
    if isinstance(value, str):
        aliases: list[tuple[str, str]] = []
        for path, label in (
            (package_root().resolve(), "[PACKAGE_ROOT]"),
            (Path.home().resolve(), "[USER_HOME]"),
        ):
            for source in {str(path), path.as_posix()}:
                if source and source != "/":
                    aliases.append((source, label))
        result = value
        for source, label in sorted(set(aliases), key=lambda item: len(item[0]), reverse=True):
            result = result.replace(source, label)
        return result
    return value


def diagnostics() -> dict[str, Any]:
    """Return a redacted package-health record suitable for buyer evidence export."""
    prerequisite = preflight()
    runtime_status = status()
    compose_ps: list[dict[str, Any]] | str = []
    runtime_env = state_dir() / "runtime.env"
    if runtime_env.is_file() and prerequisite["container_runtime"]["compose_ready"]:
        values = ensure_runtime()
        result = _compose(values, ["ps", "--format", "json"], check=False, timeout=30)
        output = _redact(result.stdout or "", values, limit=None).strip()
        try:
            parsed = json.loads(output) if output else []
            compose_ps = _alias_package_paths(parsed if isinstance(parsed, list) else [parsed])
        except json.JSONDecodeError:
            try:
                compose_ps = _alias_package_paths(
                    [json.loads(line) for line in output.splitlines() if line.strip()]
                )
            except json.JSONDecodeError:
                compose_ps = _alias_package_paths(output[-2000:])
    return _alias_package_paths({
        "schema": "pf07.diagnostics.v1",
        "package_version": PACKAGE_VERSION,
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "prerequisite": prerequisite,
        "runtime": runtime_status,
        "compose_ps": compose_ps,
        "content_verification": _manifest_verification(),
        "privacy": {
            "secrets_included": False,
            "admin_password_included": False,
            "connected_tokens_included": False,
            "absolute_package_path_included": False,
        },
        "created_at_utc": _utc_now(),
    })


def _external_export_path(requested: str | None, prefix: str, suffix: str) -> Path:
    root = package_root().resolve()
    if requested:
        output = Path(requested).expanduser().resolve()
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = root.parent / f"{prefix}-{stamp}{suffix}"
    if output == root or output.is_relative_to(root):
        raise LauncherError("Choose an export destination outside the extracted PF07 package directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise LauncherError(f"Refusing to overwrite an existing export: {output.name}")
    return output


def export_evidence(requested: str | None = None) -> dict[str, Any]:
    output = _external_export_path(requested, "PF07-Evidence", ".zip")
    report = diagnostics()
    status_payload = report["runtime"]
    entries = {
        "diagnostics.json": json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
        "status.json": json.dumps(status_payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
        "README.txt": (
            "PF07 buyer evidence export\n"
            "This archive contains redacted package status and integrity observations only.\n"
            "It excludes administrator passwords, connected-service tokens, databases, orders, and logs.\n"
        ).encode("utf-8"),
    }
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return {
        "schema": "pf07.evidence-export.v1",
        "status": "PASS",
        "filename": output.name,
        "sha256": _sha256_file(output),
        "bytes": output.stat().st_size,
        "privacy": report["privacy"],
    }


def _tunnel_directory() -> Path:
    return state_dir() / "tunnel"


def _tunnel_state_path() -> Path:
    return _tunnel_directory() / "state.json"


def _linux_process_observation(pid: int) -> dict[str, str] | None:
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        closing_parenthesis = stat_text.rfind(")")
        if closing_parenthesis < 0:
            return None
        stat_fields = stat_text[closing_parenthesis + 1 :].split()
        start_ticks = stat_fields[19]
        command = (
            Path(f"/proc/{pid}/cmdline")
            .read_bytes()
            .replace(b"\0", b" ")
            .decode("utf-8", errors="replace")
        )
        executable = str(Path(f"/proc/{pid}/exe").resolve())
    except (OSError, ValueError, IndexError):
        return None
    return {
        "identity_kind": "linux-proc-start-ticks",
        "start_marker": start_ticks,
        "command": command,
        "executable": executable,
    }


def _windows_process_observation(pid: int) -> dict[str, str] | None:
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        get_process_times = kernel32.GetProcessTimes
        get_process_times.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        )
        get_process_times.restype = wintypes.BOOL
        query_image = kernel32.QueryFullProcessImageNameW
        query_image.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        query_image.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        handle = open_process(0x1000, False, pid)
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not get_process_times(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return None
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not query_image(handle, 0, buffer, ctypes.byref(size)):
                return None
            creation_time = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            executable = os.path.normcase(os.path.abspath(buffer.value))
        finally:
            close_handle(handle)
    except (AttributeError, OSError, ValueError):
        return None
    return {
        "identity_kind": "windows-creation-time",
        "start_marker": str(creation_time),
        "command": "",
        "executable": executable,
    }


def _posix_process_observation(pid: int) -> dict[str, str] | None:
    try:
        started = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    start_marker = started.stdout.strip()
    command_line = command.stdout.strip()
    if started.returncode != 0 or command.returncode != 0 or not start_marker or not command_line:
        return None
    return {
        "identity_kind": "posix-process-start-time",
        "start_marker": start_marker,
        "command": command_line,
        "executable": "",
    }


def _process_observation(pid: int) -> dict[str, str] | None:
    if os.name == "nt":
        return _windows_process_observation(pid)
    if platform.system() == "Linux":
        return _linux_process_observation(pid)
    return _posix_process_observation(pid)


def _process_record(process: subprocess.Popen[bytes], role: str, token: str) -> dict[str, Any]:
    return _process_record_for_pid(process.pid, role, token)


def _process_record_for_pid(pid: int, role: str, token: str) -> dict[str, Any]:
    observed = _process_observation(pid)
    if observed is None or (observed["command"] and token not in observed["command"]):
        raise LauncherError(f"The package-owned {role} process did not remain active.")
    return {
        "pid": pid,
        "identity_kind": observed["identity_kind"],
        "start_marker": observed["start_marker"],
        "executable": observed["executable"],
        "role": role,
        "command_token": token,
    }


def _process_matches(record: dict[str, Any]) -> bool:
    if "start_ticks" in record and "identity_kind" not in record:
        try:
            pid = int(record["pid"])
            start_ticks = str(record["start_ticks"])
            token = str(record["command_token"])
        except (KeyError, TypeError, ValueError):
            return False
        observed = _linux_process_observation(pid)
        return bool(
            observed
            and observed["start_marker"] == start_ticks
            and token
            and token in observed["command"]
        )
    try:
        pid = int(record["pid"])
        identity_kind = str(record["identity_kind"])
        start_marker = str(record["start_marker"])
        executable = str(record.get("executable", ""))
        token = str(record["command_token"])
    except (KeyError, TypeError, ValueError):
        return False
    observed = _process_observation(pid)
    if (
        observed is None
        or observed["identity_kind"] != identity_kind
        or observed["start_marker"] != start_marker
    ):
        return False
    if executable and os.path.normcase(observed["executable"]) != os.path.normcase(executable):
        return False
    if observed["command"]:
        return bool(token) and token in observed["command"]
    return os.name == "nt" and bool(executable)


def _wait_for_process_record_exit(record: dict[str, Any], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _process_matches(record):
            return True
        time.sleep(0.2)
    return not _process_matches(record)


def _taskkill_process_tree(pid: int, *, force: bool) -> None:
    command = ["taskkill", "/PID", str(pid), "/T"]
    if force:
        command.append("/F")
    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _terminate_process(record: dict[str, Any]) -> bool:
    if not _process_matches(record):
        return False
    pid = int(record["pid"])
    if os.name == "nt":
        _taskkill_process_tree(pid, force=False)
        if _wait_for_process_record_exit(record, 8):
            return True
        _taskkill_process_tree(pid, force=True)
        return _wait_for_process_record_exit(record, 5)
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    if _wait_for_process_record_exit(record, 8):
        return True
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    return _wait_for_process_record_exit(record, 5)


def _new_process_group_options() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate_spawned_process(process: subprocess.Popen[bytes] | None) -> bool:
    if process is None or process.poll() is not None:
        return True
    try:
        if os.name == "nt":
            _taskkill_process_tree(process.pid, force=True)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
        return True
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return False
    return True


def _select_free_port_range(start_port: int, end_port: int) -> int:
    for port in range(start_port, end_port + 1):
        if _port_available(port):
            return port
    raise LauncherError(f"No free loopback port is available in {start_port}-{end_port}.")


def _provider_executable_identity(executable: str, provider: str) -> dict[str, str]:
    path = Path(executable).resolve()
    if not path.is_file():
        raise LauncherError(f"The selected {provider} executable is unavailable.")
    try:
        result = subprocess.run(
            [str(path), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LauncherError(f"The selected {provider} executable version could not be inspected.") from error
    version_lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if result.returncode != 0 or not version_lines:
        raise LauncherError(f"The selected {provider} executable did not report a usable version.")
    version = re.sub(r"[\x00-\x1f\x7f]", "", version_lines[0])[:240]
    return {"filename": path.name, "version": version, "sha256": _sha256_file(path)}


def _redact_provider_failure(text: str, values: dict[str, str], config: Path | None) -> str:
    redacted = _redact(text, values)
    if config is not None:
        redacted = redacted.replace(str(config), "[EXTERNAL_CONFIG]")
    for pattern in (
        r"(?i)(authtoken[\"'=:\s]+)[^\"'\s,}]+",
        r"(?i)(authorization[\"'=:\s]+(?:bearer\s+)?)[^\"'\s,}]+",
        r"\b(?:xox[baprs]-)[A-Za-z0-9-]+\b",
        r"\bpat-[A-Za-z0-9._-]{16,}\b",
    ):
        redacted = re.sub(pattern, lambda match: match.group(1) + "[REDACTED]" if match.lastindex else "[REDACTED]", redacted)
    return redacted[-1600:]


def tunnel_status() -> dict[str, Any]:
    path = _tunnel_state_path()
    if not path.is_file():
        return {
            "schema": "pf07.tunnel-status.v1",
            "state": "OFF",
            "public_base": None,
            "store_url": None,
            "admin_url": None,
            "public_exposure_may_be_active": False,
            "recovery_action": "START_LOCAL_RUNTIME_OR_ENABLE_TUNNEL",
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema": "pf07.tunnel-status.v1",
            "state": "FAILED",
            "public_base": None,
            "store_url": None,
            "admin_url": None,
            "public_exposure_may_be_active": True,
            "recovery_action": "DISABLE_TUNNEL_AND_RETRY",
        }
    if value.get("state") == "OFF":
        return {
            "schema": "pf07.tunnel-status.v1",
            "state": "OFF",
            "provider": value.get("provider"),
            "public_base": None,
            "store_url": None,
            "admin_url": None,
            "public_exposure_may_be_active": False,
            "route_policy_sha256": value.get("route_policy_sha256"),
            "provider_executable": value.get("provider_executable"),
            "credential_storage": (
                "NOT_REQUIRED_FOR_QUICK_TUNNEL"
                if value.get("provider") == "cloudflared"
                else "EXTERNAL_PROVIDER_CONFIG_NOT_COPIED"
            ),
            "recovery_action": "ENABLE_TUNNEL",
        }
    process_names = ["proxy_process", "provider_process"]
    if isinstance(value.get("provider_child_process"), dict):
        process_names.append("provider_child_process")
    running = all(_process_matches(value.get(name, {})) for name in process_names)
    state = "ON" if value.get("state") == "ON" and running else "FAILED"
    public_base = value.get("public_base") if state == "ON" else None
    return {
        "schema": "pf07.tunnel-status.v1",
        "state": state,
        "provider": value.get("provider", "ngrok"),
        "public_base": public_base,
        "store_url": public_base + "/" if public_base else None,
        "admin_url": public_base + "/wp-admin/" if public_base else None,
        "public_exposure_may_be_active": (
            True if state == "ON" else bool(value.get("public_exposure_may_be_active", value.get("public_base")))
        ),
        "route_policy_sha256": value.get("route_policy_sha256"),
        "provider_executable": value.get("provider_executable"),
        "credential_storage": (
            "NOT_REQUIRED_FOR_QUICK_TUNNEL"
            if value.get("provider") == "cloudflared"
            else "EXTERNAL_PROVIDER_CONFIG_NOT_COPIED"
        ),
        "recovery_action": "DISABLE_TUNNEL" if state == "ON" else "DISABLE_TUNNEL_AND_RETRY",
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _remote_status(url: str) -> tuple[int, str | None]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PF07-Tunnel-Validator/1.0", "ngrok-skip-browser-warning": "1"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, response.headers.get("Location")
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Location")
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, None


def _stop_tunnel_processes(target_state: Path | None = None) -> dict[str, bool]:
    path = (target_state or state_dir()) / "tunnel" / "state.json"
    if not path.is_file():
        return {"provider_stopped": True, "proxy_stopped": True}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"provider_stopped": False, "proxy_stopped": False}

    def stop_record(name: str, fallback_key: str) -> bool:
        record = value.get(name)
        if isinstance(record, dict) and record:
            return _terminate_process(record) or not _process_matches(record)
        return bool(value.get(fallback_key, value.get("state") == "OFF"))

    provider_supervisor = stop_record("provider_process", "provider_stopped")
    provider_child_record = value.get("provider_child_process")
    provider_child = (
        _terminate_process(provider_child_record) or not _process_matches(provider_child_record)
        if isinstance(provider_child_record, dict) and provider_child_record
        else True
    )
    provider = provider_supervisor and provider_child
    proxy = stop_record("proxy_process", "proxy_stopped")
    stopped = provider and proxy
    value.update(
        {
            "state": "OFF" if stopped else "FAILED",
            "provider_stopped": provider,
            "proxy_stopped": proxy,
            "public_exposure_may_be_active": not provider,
            "stopped_at_utc" if stopped else "shutdown_attempted_at_utc": _utc_now(),
            "recovery_action": "ENABLE_TUNNEL" if stopped else "RETRY_DISABLE_TUNNEL",
        }
    )
    _atomic_json(path, value)
    return {"provider_stopped": provider, "proxy_stopped": proxy}


def tunnel_on(
    confirmation: str,
    config_name: str | None = None,
    provider: str = "cloudflared",
    executable_name: str | None = None,
) -> dict[str, Any]:
    with _operation_lock():
        return _tunnel_on_locked(confirmation, config_name, provider, executable_name)


def _tunnel_on_locked(
    confirmation: str,
    config_name: str | None = None,
    provider: str = "cloudflared",
    executable_name: str | None = None,
) -> dict[str, Any]:
    if confirmation != "ENABLE PF07 TUNNEL":
        raise LauncherError("Type ENABLE PF07 TUNNEL exactly to confirm public HTTPS exposure.")
    local = status()
    if not local["ready"]:
        raise LauncherError("Start the ready local PF07 runtime before enabling its optional tunnel.")
    if tunnel_status()["state"] == "ON":
        return tunnel_status()
    provider = provider.strip().lower()
    if provider not in {"cloudflared", "ngrok"}:
        raise LauncherError("Tunnel provider must be cloudflared or ngrok.")
    if executable_name:
        executable_path = Path(executable_name).expanduser().resolve()
        if not executable_path.is_file() or executable_path.is_relative_to(package_root().resolve()):
            raise LauncherError("Choose an existing tunnel-provider executable outside the PF07 package.")
        executable = str(executable_path)
    else:
        executable = shutil.which(provider)
    if executable is None:
        raise LauncherError(
            f"{provider} is not installed. Install the maintained provider CLI, then retry the optional tunnel."
        )
    provider_identity = _provider_executable_identity(executable, provider)
    config: Path | None = None
    if config_name:
        if provider != "ngrok":
            raise LauncherError("An external credential config is used only with the ngrok provider path.")
        config = Path(config_name).expanduser().resolve()
        if not config.is_file() or config.is_relative_to(package_root().resolve()):
            raise LauncherError("Choose an existing protected ngrok configuration outside the PF07 package.")
    directory = _tunnel_directory()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    prior_tunnel = _stop_tunnel_processes()
    if not all(prior_tunnel.values()):
        raise LauncherError("A prior HTTPS tunnel is still active. Disable it completely before enabling another.")
    proxy_port = _select_free_port_range(19181, 19230)
    public_base_file = directory / "public-base.json"
    _atomic_json(
        public_base_file,
        {"public_base": "https://pending.invalid", "local_base": str(local["urls"]["store"]).rstrip("/")},
    )
    route_policy = package_root() / "packaging/network/tunnel-route-allowlist.json"
    if not route_policy.is_file():
        raise LauncherError("The PF07 tunnel route allowlist is missing.")
    proxy_log = directory / "proxy.log"
    provider_log = directory / "provider.log"
    proxy_handle = proxy_log.open("wb", buffering=0)
    provider_log.write_bytes(b"")
    os.chmod(provider_log, 0o600)
    proxy_process: subprocess.Popen[bytes] | None = None
    provider_process: subprocess.Popen[bytes] | None = None
    public_base: str | None = None
    runtime_values = ensure_runtime()
    proxy_marker = hmac.new(
        runtime_values["ODDROOM_WEBHOOK_HMAC_KEY"].encode("utf-8"),
        b"pf07-tunnel-proxy-v1",
        hashlib.sha256,
    ).hexdigest()
    local_base = str(local["urls"]["store"]).rstrip("/")
    state_path = _tunnel_state_path()
    tunnel_runtime: dict[str, Any] = {
        "schema": "pf07.tunnel-runtime.v1",
        "state": "STARTING",
        "provider": provider,
        "public_base": None,
        "local_base": local_base,
        "route_policy_sha256": _sha256_file(route_policy),
        "provider_executable": provider_identity,
        "credential_source": (
            "EXTERNAL_PROVIDER_CONFIG_NOT_COPIED" if provider == "ngrok" else "NOT_REQUIRED_FOR_QUICK_TUNNEL"
        ),
        "proxy_stopped": True,
        "provider_stopped": True,
        "public_exposure_may_be_active": False,
        "recovery_action": "DISABLE_TUNNEL_AND_RETRY",
        "startup_began_at_utc": _utc_now(),
    }
    _atomic_json(state_path, tunnel_runtime)
    try:
        proxy_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pf07_launcher.tunnel_proxy",
                "--port",
                str(proxy_port),
                "--upstream-port",
                str(int(runtime_values["PF07_WORDPRESS_PORT"])),
                "--public-base-file",
                str(public_base_file),
                "--route-allowlist",
                str(route_policy),
            ],
            cwd=package_root(),
            env={
                **os.environ,
                "PYTHONPATH": str(package_root() / "launcher"),
                "PF07_TUNNEL_PROXY_MARKER": proxy_marker,
            },
            stdin=subprocess.DEVNULL,
            stdout=proxy_handle,
            stderr=subprocess.STDOUT,
            **_new_process_group_options(),
        )
        tunnel_runtime.update(
            {
                "proxy_process": _process_record(
                    proxy_process,
                    "route-proxy",
                    "pf07_launcher.tunnel_proxy",
                ),
                "proxy_stopped": False,
            }
        )
        _atomic_json(state_path, tunnel_runtime)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _port_available(proxy_port):
            if proxy_process.poll() is not None:
                raise LauncherError("The package-owned tunnel route proxy exited during startup.")
            time.sleep(0.2)
        if _port_available(proxy_port):
            raise LauncherError("The package-owned tunnel route proxy did not become ready.")
        if provider == "ngrok":
            command = [
                executable,
                "http",
                f"http://127.0.0.1:{proxy_port}",
                "--inspect=false",
                "--log",
                "stdout",
                "--log-format",
                "json",
            ]
            if config:
                command.extend(["--config", str(config)])
        else:
            command = [
                executable,
                "tunnel",
                "--url",
                f"http://127.0.0.1:{proxy_port}",
                "--no-autoupdate",
                "--metrics",
                "127.0.0.1:0",
                "--loglevel",
                "info",
            ]
        owner_observation = _process_observation(os.getpid())
        if owner_observation is None:
            raise LauncherError("The tunnel owner process identity could not be established.")
        supervisor_nonce = secrets.token_urlsafe(32)
        supervisor_launch = directory / "supervisor-launch.json"
        supervisor_control = directory / "supervisor-control.json"
        supervisor_status = directory / "supervisor-status.json"
        _atomic_json(
            supervisor_launch,
            {
                "schema": "pf07.tunnel-supervisor-launch.v1",
                "authorization_nonce": supervisor_nonce,
                "owner": {
                    "pid": os.getpid(),
                    "identity_kind": owner_observation["identity_kind"],
                    "start_marker": owner_observation["start_marker"],
                },
                "command": command,
                "working_directory": str(package_root()),
                "provider_log": str(provider_log),
            },
        )
        _atomic_json(
            supervisor_control,
            {
                "schema": "pf07.tunnel-supervisor-control.v1",
                "phase": "WAITING",
                "authorization_nonce": None,
            },
        )
        provider_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pf07_launcher.tunnel_supervisor",
                "--launch-spec",
                str(supervisor_launch),
                "--control-file",
                str(supervisor_control),
                "--status-file",
                str(supervisor_status),
            ],
            cwd=package_root(),
            env={**os.environ, "PYTHONPATH": str(package_root() / "launcher")},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_new_process_group_options(),
        )
        tunnel_runtime.update(
            {
                "provider_process": _process_record(
                    provider_process,
                    f"{provider}-supervisor",
                    "pf07_launcher.tunnel_supervisor",
                ),
                "provider_supervisor_status_file": supervisor_status.name,
                "provider_stopped": False,
                "public_exposure_may_be_active": False,
            }
        )
        _atomic_json(state_path, tunnel_runtime)
        _atomic_json(
            supervisor_control,
            {
                "schema": "pf07.tunnel-supervisor-control.v1",
                "phase": "AUTHORIZED",
                "authorization_nonce": supervisor_nonce,
            },
        )
        # Public ingress may begin only after the inert supervisor identity is
        # durable. Until final detachment, that supervisor also shuts the
        # provider down if this owner process disappears.
        tunnel_runtime["public_exposure_may_be_active"] = True
        _atomic_json(state_path, tunnel_runtime)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if provider_process.poll() is not None:
                break
            try:
                log_text = provider_log.read_text(encoding="utf-8", errors="replace")
                if provider == "ngrok":
                    pattern = r"https://[A-Za-z0-9.-]+(?:ngrok-free\.app|ngrok-free\.dev|ngrok\.app)"
                else:
                    pattern = r"https://[A-Za-z0-9-]+\.trycloudflare\.com"
                urls = sorted(set(re.findall(pattern, log_text)))
                if urls:
                    public_base = urls[0].rstrip("/")
                    break
            except OSError:
                pass
            time.sleep(0.5)
        if public_base is None:
            detail = provider_log.read_text(encoding="utf-8", errors="replace")[-1600:]
            detail = _redact_provider_failure(detail, runtime_values, config)
            raise LauncherError(f"The {provider} HTTPS endpoint did not become ready. " + detail)
        try:
            supervisor_value = json.loads(supervisor_status.read_text(encoding="utf-8"))
            provider_child_pid = int(supervisor_value["provider_pid"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise LauncherError("The tunnel provider child identity could not be established.") from error
        tunnel_runtime["provider_child_process"] = _process_record_for_pid(
            provider_child_pid,
            provider,
            f"127.0.0.1:{proxy_port}",
        )
        _atomic_json(state_path, tunnel_runtime)
        _atomic_json(
            public_base_file,
            {"public_base": public_base, "local_base": str(local["urls"]["store"]).rstrip("/")},
        )
        tunnel_runtime["public_base"] = public_base
        _atomic_json(state_path, tunnel_runtime)
        home_status = admin_status = internal_status = 0
        admin_location: str | None = None
        admin_denied = False
        # Quick-tunnel hostnames can be registered before their public DNS
        # record is visible. Keep the local runtime available while allowing a
        # bounded propagation window before reporting an isolated failure.
        validation_deadline = time.monotonic() + 120
        while time.monotonic() < validation_deadline:
            if provider_process.poll() is not None or proxy_process.poll() is not None:
                break
            home_status, _ = _remote_status(public_base + "/")
            admin_status, admin_location = _remote_status(public_base + "/wp-admin/")
            internal_status, _ = _remote_status(public_base + "/.pf07/")
            admin_denied = admin_status in {301, 302, 303, 307, 308, 401, 403} and bool(
                admin_location and "wp-login.php" in admin_location
            )
            if home_status == 200 and admin_denied and internal_status == 404:
                break
            time.sleep(1)
        if home_status != 200 or not admin_denied or internal_status != 404:
            raise LauncherError(
                "Tunnel validation failed: "
                f"home={home_status}, anonymous_admin={admin_status}, internal={internal_status}."
            )
        tunnel_runtime.update(
            {
                "state": "ON",
                "public_base": public_base,
                "proxy_stopped": False,
                "provider_stopped": False,
                "public_exposure_may_be_active": True,
                "recovery_action": "DISABLE_TUNNEL",
                "validation": {
                    "store_status": home_status,
                    "anonymous_admin_status": admin_status,
                    "anonymous_admin_denied": admin_denied,
                    "internal_endpoint_status": internal_status,
                    "internal_endpoint_denied": internal_status == 404,
                },
                "started_at_utc": _utc_now(),
            }
        )
        _atomic_json(state_path, tunnel_runtime)
        _atomic_json(
            supervisor_control,
            {
                "schema": "pf07.tunnel-supervisor-control.v1",
                "phase": "DETACHED",
                "authorization_nonce": supervisor_nonce,
            },
        )
        return tunnel_status() | {
            "validation": tunnel_runtime["validation"],
            "local_runtime_survived": status()["ready"],
        }
    except Exception as error:
        try:
            if "supervisor_control" in locals():
                _atomic_json(
                    supervisor_control,
                    {
                        "schema": "pf07.tunnel-supervisor-control.v1",
                        "phase": "STOP",
                        "authorization_nonce": None,
                    },
                )
        except OSError:
            pass
        provider_supervisor_stopped = _terminate_spawned_process(provider_process)
        provider_child_record = tunnel_runtime.get("provider_child_process")
        provider_child_stopped = (
            _terminate_process(provider_child_record) or not _process_matches(provider_child_record)
            if isinstance(provider_child_record, dict) and provider_child_record
            else True
        )
        provider_stopped = provider_supervisor_stopped and provider_child_stopped
        proxy_stopped = _terminate_spawned_process(proxy_process)
        local_survived = status()["ready"]
        safe_error = _redact_provider_failure(str(error), runtime_values, config)
        failure_state: dict[str, Any] = {
            "schema": "pf07.tunnel-runtime.v1",
            "state": "FAILED",
            "provider": provider,
            "public_base": public_base,
            "route_policy_sha256": tunnel_runtime["route_policy_sha256"],
            "provider_executable": provider_identity,
            "failure": safe_error,
            "provider_stopped": provider_stopped,
            "provider_supervisor_stopped": provider_supervisor_stopped,
            "provider_child_stopped": provider_child_stopped,
            "proxy_stopped": proxy_stopped,
            "public_exposure_may_be_active": not provider_stopped,
            "local_runtime_survived": local_survived,
            "recovery_action": (
                "CHECK_PROVIDER_INSTALL_NETWORK_OR_CREDENTIAL_THEN_RETRY"
                if provider_stopped and proxy_stopped
                else "RETRY_DISABLE_TUNNEL"
            ),
            "failed_at_utc": _utc_now(),
        }
        if not provider_stopped and provider_process is not None:
            try:
                failure_state["provider_process"] = _process_record(
                    provider_process,
                    f"{provider}-supervisor",
                    "pf07_launcher.tunnel_supervisor",
                )
            except LauncherError:
                failure_state["provider_process_pid_unverified"] = provider_process.pid
        if not provider_child_stopped and isinstance(provider_child_record, dict):
            failure_state["provider_child_process"] = provider_child_record
        if not proxy_stopped and proxy_process is not None:
            try:
                failure_state["proxy_process"] = _process_record(
                    proxy_process,
                    "route-proxy",
                    "pf07_launcher.tunnel_proxy",
                )
            except LauncherError:
                failure_state["proxy_process_pid_unverified"] = proxy_process.pid
        _atomic_json(
            state_path,
            failure_state,
        )
        raise LauncherError(
            f"HTTPS tunnel failed while local PF07 remained ready={str(local_survived).lower()}. "
            f"Check the provider installation, network, and credential when applicable, then retry. Cause: {safe_error}"
        ) from error
    finally:
        proxy_handle.close()


def tunnel_off(confirmation: str) -> dict[str, Any]:
    with _operation_lock(allow_restore_transaction=True):
        return _tunnel_off_locked(confirmation)


def _tunnel_off_locked(confirmation: str) -> dict[str, Any]:
    if confirmation != "DISABLE PF07 TUNNEL":
        raise LauncherError("Type DISABLE PF07 TUNNEL exactly to confirm tunnel shutdown.")
    stopped = _stop_tunnel_processes()
    local_ready = status()["ready"]
    fully_stopped = all(stopped.values())
    return {
        "schema": "pf07.tunnel-stop-result.v1",
        "status": "PASS" if fully_stopped else "PARTIAL",
        "state": "OFF" if fully_stopped else "FAILED",
        **stopped,
        "local_runtime_ready": local_ready,
        "public_exposure_active": not stopped["provider_stopped"],
    }


def open_tunnel_target(target: str) -> str:
    current = tunnel_status()
    if current["state"] != "ON" or target not in {"store", "admin"}:
        raise LauncherError("Enable the ready HTTPS tunnel before opening its store or admin target.")
    url = str(current[f"{target}_url"])
    if not webbrowser.open(url, new=2):
        raise LauncherError(f"A browser could not be opened automatically. Open this URL: {url}")
    return url


def _read_passphrase(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) < 12:
        raise LauncherError("The backup passphrase must contain at least 12 UTF-8 bytes.")
    if len(encoded) > 4096 or "\x00" in value or "\n" in value or "\r" in value:
        raise LauncherError("The backup passphrase contains an unsupported character or length.")
    return encoded


def _remove_transient_container(container_name: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "rm", "-f", container_name],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = (result.stdout or "").lower()
    return result.returncode == 0 or "no such container" in output


def _openssl_ctr(input_path: Path, output_path: Path, key: bytes, iv: bytes, *, decrypt: bool) -> None:
    if input_path.parent != output_path.parent:
        raise LauncherError("Internal encrypted-backup paths must share one protected temporary directory.")
    arguments = [
        "enc",
        "-d" if decrypt else "-e",
        "-aes-256-ctr",
        "-K",
        key.hex(),
        "-iv",
        iv.hex(),
        "-in",
        str(input_path),
        "-out",
        str(output_path),
    ]
    openssl = shutil.which("openssl")
    transient_container: str | None = None
    if openssl:
        command = [openssl, *arguments]
    else:
        preflight_result = preflight()
        if not preflight_result["ready"]:
            raise LauncherError("OpenSSL is unavailable and the supported container runtime is not ready for backup encryption.")
        directory = input_path.parent.resolve()
        container_arguments = [
            "enc",
            "-d" if decrypt else "-e",
            "-aes-256-ctr",
            "-K",
            key.hex(),
            "-iv",
            iv.hex(),
            "-in",
            f"/work/{input_path.name}",
            "-out",
            f"/work/{output_path.name}",
        ]
        transient_container = f"pf07-cipher-{uuid.uuid4().hex[:16]}"
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            transient_container,
            "--entrypoint",
            "openssl",
            "--mount",
            f"type=bind,source={directory},target=/work",
            WORDPRESS_IMAGE_REFERENCE,
            *container_arguments,
        ]
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=PROTECTED_IO_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        output_path.unlink(missing_ok=True)
        container_stopped = (
            _remove_transient_container(transient_container)
            if transient_container is not None
            else True
        )
        cleanup = "stopped" if container_stopped else f"still requires removal ({transient_container})"
        raise LauncherError(
            f"Authenticated-backup cipher operation timed out after "
            f"{PROTECTED_IO_TIMEOUT_SECONDS} seconds; partial output was removed and its container is {cleanup}."
        ) from error
    except OSError as error:
        output_path.unlink(missing_ok=True)
        raise LauncherError("Authenticated-backup cipher executable could not be started.") from error
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise LauncherError("Authenticated-backup cipher operation failed: " + (result.stdout or "")[-1000:])


def _encrypt_backup(plaintext: Path, output: Path, passphrase: str) -> dict[str, Any]:
    passphrase_bytes = _read_passphrase(passphrase)
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", passphrase_bytes, salt, BACKUP_KDF_ITERATIONS, dklen=64)
    encryption_key, authentication_key = derived[:32], derived[32:]
    ciphertext = plaintext.with_name("ciphertext.bin")
    _openssl_ctr(plaintext, ciphertext, encryption_key, iv, decrypt=False)
    header = {
        "schema": "pf07.authenticated-backup-envelope.v1",
        "package_version": PACKAGE_VERSION,
        "kdf": "PBKDF2-HMAC-SHA256",
        "kdf_iterations": BACKUP_KDF_ITERATIONS,
        "salt_hex": salt.hex(),
        "cipher": "AES-256-CTR",
        "iv_hex": iv.hex(),
        "authentication": "HMAC-SHA256-ENCRYPT_THEN_MAC",
        "passphrase_stored": False,
    }
    header_bytes = json.dumps(header, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    prefix = BACKUP_MAGIC + struct.pack(">I", len(header_bytes)) + header_bytes
    mac = hmac.new(authentication_key, digestmod=hashlib.sha256)
    mac.update(prefix)
    with ciphertext.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            mac.update(block)
    temporary_output = output.with_name(f".{output.name}.{uuid.uuid4().hex}.partial")
    try:
        with temporary_output.open("xb") as destination, ciphertext.open("rb") as source:
            destination.write(prefix)
            shutil.copyfileobj(source, destination, 1024 * 1024)
            destination.write(mac.digest())
        os.chmod(temporary_output, 0o600)
        os.replace(temporary_output, output)
    except Exception:
        try:
            temporary_output.unlink()
        except FileNotFoundError:
            pass
        raise
    return header


def _decrypt_backup(archive: Path, plaintext: Path, passphrase: str) -> dict[str, Any]:
    passphrase_bytes = _read_passphrase(passphrase)
    size = archive.stat().st_size
    with archive.open("rb") as source:
        magic = source.read(len(BACKUP_MAGIC))
        if magic != BACKUP_MAGIC:
            raise LauncherError("The selected file is not a PF07 authenticated backup.")
        length_bytes = source.read(4)
        if len(length_bytes) != 4:
            raise LauncherError("The PF07 backup envelope is truncated.")
        header_length = struct.unpack(">I", length_bytes)[0]
        if header_length < 32 or header_length > 16_384:
            raise LauncherError("The PF07 backup header length is invalid.")
        header_bytes = source.read(header_length)
        if len(header_bytes) != header_length:
            raise LauncherError("The PF07 backup header is truncated.")
        try:
            header = json.loads(header_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LauncherError("The PF07 backup header is unreadable.") from error
        required_header = {
            "schema": "pf07.authenticated-backup-envelope.v1",
            "kdf": "PBKDF2-HMAC-SHA256",
            "cipher": "AES-256-CTR",
            "authentication": "HMAC-SHA256-ENCRYPT_THEN_MAC",
        }
        if any(header.get(key) != expected for key, expected in required_header.items()):
            raise LauncherError("The PF07 backup cryptographic contract is unsupported.")
        iterations = int(header.get("kdf_iterations", 0))
        if iterations < BACKUP_KDF_ITERATIONS or iterations > 2_000_000:
            raise LauncherError("The PF07 backup KDF iteration count is outside the supported boundary.")
        try:
            salt = bytes.fromhex(str(header["salt_hex"]))
            iv = bytes.fromhex(str(header["iv_hex"]))
        except (KeyError, ValueError) as error:
            raise LauncherError("The PF07 backup salt or IV is invalid.") from error
        if len(salt) != 16 or len(iv) != 16:
            raise LauncherError("The PF07 backup salt or IV length is invalid.")
        ciphertext_length = size - len(BACKUP_MAGIC) - 4 - header_length - 32
        if ciphertext_length <= 0:
            raise LauncherError("The PF07 backup ciphertext is missing.")
        derived = hashlib.pbkdf2_hmac("sha256", passphrase_bytes, salt, iterations, dklen=64)
        encryption_key, authentication_key = derived[:32], derived[32:]
        prefix = BACKUP_MAGIC + length_bytes + header_bytes
        mac = hmac.new(authentication_key, digestmod=hashlib.sha256)
        mac.update(prefix)
        ciphertext = plaintext.with_name("ciphertext.bin")
        with ciphertext.open("wb") as destination:
            remaining = ciphertext_length
            while remaining:
                block = source.read(min(1024 * 1024, remaining))
                if not block:
                    raise LauncherError("The PF07 backup ciphertext is truncated.")
                destination.write(block)
                mac.update(block)
                remaining -= len(block)
            expected_mac = source.read(32)
            if len(expected_mac) != 32 or source.read(1):
                raise LauncherError("The PF07 backup authentication trailer is invalid.")
        if not hmac.compare_digest(mac.digest(), expected_mac):
            ciphertext.unlink(missing_ok=True)
            raise LauncherError("Backup authentication failed. The passphrase is wrong or the archive was modified.")
    _openssl_ctr(ciphertext, plaintext, encryption_key, iv, decrypt=True)
    return header


def _running_services(values: dict[str, str]) -> list[str]:
    result = _compose(values, ["ps", "--status", "running", "--services"], check=False, timeout=30)
    if result.returncode != 0:
        detail = _redact(result.stdout or "", values).strip()
        raise LauncherError(f"Could not observe running PF07 services before the protected operation.\n{detail}")
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _volume_names(values: dict[str, str]) -> dict[str, str]:
    project = values["PF07_COMPOSE_PROJECT"]
    if not re.fullmatch(r"pf07pkg-[a-f0-9]{12}", project):
        raise LauncherError("The package Compose project does not match the protected PF07 naming boundary.")
    return {name: f"{project}_{name}" for name in ("mariadb_data", "wordpress_data", "n8n_data")}


def _owned_volume_labels(volume: str, values: dict[str, str]) -> dict[str, str] | None:
    inspected = _run(
        ["docker", "volume", "inspect", volume],
        values,
        check=False,
        timeout=30,
    )
    if inspected.returncode != 0:
        return None
    try:
        payload = json.loads(inspected.stdout)
        labels = payload[0].get("Labels") or {}
    except (json.JSONDecodeError, IndexError, AttributeError, TypeError) as error:
        raise LauncherError(f"Could not establish ownership labels for volume {volume}.") from error
    if not isinstance(labels, dict):
        raise LauncherError(f"Could not establish ownership labels for volume {volume}.")
    return {str(key): str(value) for key, value in labels.items()}


def _require_owned_volume(volume: str, logical_name: str, values: dict[str, str]) -> None:
    labels = _owned_volume_labels(volume, values)
    if labels is None:
        raise LauncherError(f"The package-owned volume is missing: {volume}")
    if (
        labels.get("com.docker.compose.project") != values["PF07_COMPOSE_PROJECT"]
        or labels.get("com.docker.compose.volume") != logical_name
    ):
        raise LauncherError(f"Refusing to access a volume without exact PF07 ownership labels: {volume}")


def _archive_volume(volume: str, output: Path, values: dict[str, str]) -> None:
    logical_name = volume.removeprefix(values["PF07_COMPOSE_PROJECT"] + "_")
    if logical_name not in {"mariadb_data", "wordpress_data", "n8n_data"}:
        raise LauncherError("Refusing to archive a volume outside the exact PF07 volume set.")
    _require_owned_volume(volume, logical_name, values)
    container_name = f"pf07-archive-{uuid.uuid4().hex[:16]}"
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--entrypoint",
        "tar",
        "--mount",
        f"type=volume,source={volume},target=/volume,readonly",
        WORDPRESS_IMAGE_REFERENCE,
        "-C",
        "/volume",
        "-cf",
        "-",
        ".",
    ]
    try:
        with output.open("xb") as destination:
            result = subprocess.run(
                command,
                cwd=package_root(),
                stdout=destination,
                stderr=subprocess.PIPE,
                timeout=PROTECTED_IO_TIMEOUT_SECONDS,
                check=False,
            )
    except subprocess.TimeoutExpired as error:
        output.unlink(missing_ok=True)
        container_stopped = _remove_transient_container(container_name)
        cleanup = "stopped" if container_stopped else f"still requires removal ({container_name})"
        raise LauncherError(
            f"Archiving package volume {volume} timed out after {PROTECTED_IO_TIMEOUT_SECONDS} seconds; "
            f"the partial archive was removed and its container is {cleanup}."
        ) from error
    except OSError as error:
        output.unlink(missing_ok=True)
        raise LauncherError(f"Could not start the archive operation for package volume {volume}.") from error
    if result.returncode != 0:
        output.unlink(missing_ok=True)
        detail = _redact(result.stderr.decode("utf-8", errors="replace"), values)
        raise LauncherError(f"Could not archive package volume {volume}: {detail[-1000:]}")


def _restore_volume(volume: str, archive: Path, values: dict[str, str]) -> None:
    logical_name = volume.removeprefix(values["PF07_COMPOSE_PROJECT"] + "_")
    if logical_name not in {"mariadb_data", "wordpress_data", "n8n_data"}:
        raise LauncherError("Refusing to restore a volume outside the exact PF07 volume set.")
    labels = [
        "--label",
        f"com.docker.compose.project={values['PF07_COMPOSE_PROJECT']}",
        "--label",
        f"com.docker.compose.volume={logical_name}",
    ]
    if _owned_volume_labels(volume, values) is None:
        _run(["docker", "volume", "create", *labels, volume], values, timeout=30)
    _require_owned_volume(volume, logical_name, values)
    container_name = f"pf07-restore-{uuid.uuid4().hex[:16]}"
    _update_restore_transaction(
        active_container=container_name,
        active_volume=logical_name,
        active_volume_archive=archive.name,
        volume_phase="RESTORING",
    )
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--entrypoint",
        "sh",
        "--mount",
        f"type=volume,source={volume},target=/volume",
        "--mount",
        f"type=bind,source={archive.parent.resolve()},target=/backup,readonly",
        WORDPRESS_IMAGE_REFERENCE,
        "-c",
        f"set -eu; find /volume -mindepth 1 -maxdepth 1 -exec rm -rf -- {{}} +; tar -xf /backup/{archive.name} -C /volume",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=package_root(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=PROTECTED_IO_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        container_stopped = _remove_transient_container(container_name)
        _update_restore_transaction(
            active_container=None if container_stopped else container_name,
            volume_phase="TIMED_OUT_CONTAINER_STOPPED" if container_stopped else "TIMED_OUT_CONTAINER_ACTIVE",
        )
        cleanup = "stopped" if container_stopped else f"still requires removal ({container_name})"
        raise LauncherError(
            f"Restoring package volume {volume} timed out after {PROTECTED_IO_TIMEOUT_SECONDS} seconds; "
            f"its transient container is {cleanup}."
        ) from error
    except OSError as error:
        container_stopped = _remove_transient_container(container_name)
        _update_restore_transaction(
            active_container=None if container_stopped else container_name,
            volume_phase="START_FAILED_CONTAINER_STOPPED" if container_stopped else "START_FAILED_CONTAINER_ACTIVE",
        )
        raise LauncherError(f"Could not start the restore operation for package volume {volume}.") from error
    _update_restore_transaction(
        active_container=None,
        volume_phase="RESTORED" if result.returncode == 0 else "FAILED",
    )
    if result.returncode != 0:
        raise LauncherError(f"Could not restore package volume {volume}: {_redact(result.stdout, values)[-1000:]}")


def _restore_update_volume(volume: str, archive: Path, values: dict[str, str]) -> None:
    logical_name = volume.removeprefix(values["PF07_COMPOSE_PROJECT"] + "_")
    if logical_name not in {"mariadb_data", "wordpress_data", "n8n_data"}:
        raise LauncherError("Refusing to restore an update preimage outside the exact PF07 volume set.")
    _require_owned_volume(volume, logical_name, values)
    container_name = f"pf07-update-restore-{uuid.uuid4().hex[:16]}"
    _update_controlled_update_transaction(
        active_container=container_name,
        active_volume=logical_name,
        phase="ROLLBACK_VOLUME_RESTORING",
    )
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--entrypoint",
        "sh",
        "--mount",
        f"type=volume,source={volume},target=/volume",
        "--mount",
        f"type=bind,source={archive.parent.resolve()},target=/backup,readonly",
        WORDPRESS_IMAGE_REFERENCE,
        "-c",
        f"set -eu; find /volume -mindepth 1 -maxdepth 1 -exec rm -rf -- {{}} +; tar -xf /backup/{archive.name} -C /volume",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=package_root(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=PROTECTED_IO_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        container_stopped = _remove_transient_container(container_name)
        _update_controlled_update_transaction(
            active_container=None if container_stopped else container_name,
            phase="ROLLBACK_VOLUME_TIMEOUT",
        )
        raise LauncherError(
            f"Restoring update preimage volume {logical_name} timed out; "
            f"transient container stopped={str(container_stopped).lower()}."
        ) from error
    except OSError as error:
        container_stopped = _remove_transient_container(container_name)
        _update_controlled_update_transaction(
            active_container=None if container_stopped else container_name,
            phase="ROLLBACK_VOLUME_START_FAILED",
        )
        raise LauncherError(f"Could not start update preimage restoration for {logical_name}.") from error
    _update_controlled_update_transaction(
        active_container=None,
        phase="ROLLBACK_VOLUME_RESTORED" if result.returncode == 0 else "ROLLBACK_VOLUME_FAILED",
    )
    if result.returncode != 0:
        raise LauncherError(
            f"Could not restore update preimage volume {logical_name}: {_redact(result.stdout, values)[-1000:]}"
        )


def _compose_with_backup_env(
    values: dict[str, str],
    runtime_env: Path,
    connected_env: Path | None,
    arguments: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "--progress", "quiet", "--env-file", str(runtime_env)]
    if connected_env and connected_env.is_file():
        command.extend(["--env-file", str(connected_env)])
    command.extend(
        [
            "-f",
            str(package_root() / "packaging/common/compose.yaml"),
            "-p",
            values["PF07_COMPOSE_PROJECT"],
            *arguments,
        ]
    )
    return _run(
        command,
        values,
        check=check,
        timeout=600,
        environment=_compose_environment(),
    )


def _compose_at_root(
    root: Path,
    values: dict[str, str],
    runtime_env: Path,
    connected_env: Path | None,
    arguments: list[str],
    *,
    check: bool = True,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    compose = root / "packaging/common/compose.yaml"
    if not compose.is_file():
        raise LauncherError("The selected PF07 package does not contain its Compose definition.")
    command = ["docker", "compose", "--progress", "quiet", "--env-file", str(runtime_env)]
    if connected_env and connected_env.is_file():
        command.extend(["--env-file", str(connected_env)])
    command.extend(["-f", str(compose), "-p", values["PF07_COMPOSE_PROJECT"], *arguments])
    try:
        result = subprocess.run(
            command,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            env=_compose_environment(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise LauncherError("The selected PF07 package could not run Docker Compose.") from error
    if check and result.returncode != 0:
        raise LauncherError(
            f"Selected-package Compose command failed ({result.returncode}).\n{_redact(result.stdout or '', values).strip()}"
        )
    return result


def _distribution_identity_at(root: Path) -> dict[str, Any]:
    manifest_path = root / "ARTIFACT-MANIFEST.json"
    checksums_path = root / "SHA256SUMS.txt"
    if not manifest_path.is_file() or not checksums_path.is_file():
        raise LauncherError("Select the root of a complete PF07 distribution package.")
    checksums: dict[str, str] = {}
    for raw_line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            expected, relative = raw_line.split(maxsplit=1)
        except ValueError as error:
            raise LauncherError("The selected package checksum file is malformed.") from error
        relative = relative.lstrip("* ")
        if (
            not re.fullmatch(r"[a-f0-9]{64}", expected)
            or relative in checksums
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise LauncherError("The selected package checksum inventory is malformed.")
        raw_target = root / relative
        target = raw_target.resolve()
        if (
            raw_target.is_symlink()
            or not target.is_relative_to(root)
            or not target.is_file()
            or _sha256_file(target) != expected
        ):
            raise LauncherError(f"The selected package failed integrity verification: {relative}")
        checksums[relative] = expected
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError("The selected package artifact manifest is unreadable.") from error
    if manifest.get("schema") != "pf07.artifact-manifest.v1":
        raise LauncherError("The selected package artifact manifest is incompatible.")
    if not isinstance(manifest.get("build_id"), str) or not manifest["build_id"].startswith("pf07-build-"):
        raise LauncherError("The selected package build identity is invalid.")
    payload = manifest.get("payload")
    if not isinstance(payload, list) or manifest.get("payload_file_count") != len(payload):
        raise LauncherError("The selected package payload inventory is incomplete.")
    payload_inventory: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            raise LauncherError("The selected package payload inventory is malformed.")
        relative = row.get("path")
        if (
            not isinstance(relative, str)
            or relative in payload_inventory
            or not isinstance(row.get("sha256"), str)
            or not isinstance(row.get("bytes"), int)
        ):
            raise LauncherError("The selected package payload inventory is malformed.")
        payload_inventory[relative] = row
    if set(checksums) != {"ARTIFACT-MANIFEST.json", *payload_inventory}:
        raise LauncherError("The selected package checksum and payload inventories do not match.")
    for relative, row in payload_inventory.items():
        target = root / relative
        if checksums[relative] != row["sha256"] or target.stat().st_size != row["bytes"]:
            raise LauncherError(f"The selected package manifest does not bind its payload: {relative}")
    return {
        "artifact_id": manifest.get("artifact_id"),
        "package_version": manifest.get("package_version"),
        "build_id": manifest["build_id"],
        "artifact_manifest_sha256": _sha256_file(manifest_path),
        "files_verified": len(checksums),
    }


def _running_services_at_root(root: Path, values: dict[str, str], runtime_env: Path, connected_env: Path) -> list[str]:
    result = _compose_at_root(
        root,
        values,
        runtime_env,
        connected_env if connected_env.is_file() else None,
        ["ps", "--status", "running", "--services"],
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        detail = _redact(result.stdout or "", values).strip()
        raise LauncherError(f"Could not observe predecessor PF07 services during controlled update.\n{detail}")
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _project_service_container_count(values: dict[str, str], service: str) -> int:
    result = _run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={values['PF07_COMPOSE_PROJECT']}",
            "--filter",
            f"label=com.docker.compose.service={service}",
            "--format",
            "{{.ID}}",
        ],
        values,
        check=False,
        timeout=30,
    )
    return len([line for line in result.stdout.splitlines() if line.strip()]) if result.returncode == 0 else 0


def _running_project_containers(values: dict[str, str]) -> list[str]:
    result = _run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={values['PF07_COMPOSE_PROJECT']}",
            "--format",
            "{{.ID}}",
        ],
        values,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        detail = _redact(result.stdout or "", values).strip()
        raise LauncherError(f"Could not establish PF07 project quiescence. {detail}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _controlled_update_missing_runtime_keys(values: dict[str, str]) -> list[str]:
    """Require the reviewed 1.0.4 runtime identity before migration."""
    predecessor_keys = REQUIRED_ENV_KEYS - {"PF07_NETWORK_SUBNET"}
    return sorted(predecessor_keys - values.keys())


def _controlled_update_scratch_paths(transaction: dict[str, Any]) -> tuple[Path, Path, Path]:
    root = package_root().resolve()
    return (
        root / str(transaction["stage_name"]),
        root / str(transaction["successor_preimage_name"]),
        root / str(transaction["volume_preimage_name"]),
    )


def _remove_exact_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _rollback_successor_state(transaction: dict[str, Any]) -> None:
    current_state = state_dir()
    _, successor_preimage, _ = _controlled_update_scratch_paths(transaction)
    original_names = {
        str(name)
        for name in transaction.get("successor_original_names", [])
        if isinstance(name, str) and name not in {"", ".", "..", "operation.lock"} and "/" not in name and "\\" not in name
    }
    migration_names = {
        str(name)
        for name in transaction.get("migration_names", [])
        if isinstance(name, str) and name not in {"", ".", "..", "operation.lock"} and "/" not in name and "\\" not in name
    }
    if len(original_names) != len(transaction.get("successor_original_names", [])):
        raise LauncherError("The controlled-update successor preimage inventory is invalid.")
    if len(migration_names) != len(transaction.get("migration_names", [])):
        raise LauncherError("The controlled-update migrated-state inventory is invalid.")
    current_state.mkdir(mode=0o700, parents=True, exist_ok=True)
    preimage_entries = (
        {candidate.name: candidate for candidate in successor_preimage.iterdir()}
        if successor_preimage.exists()
        else {}
    )
    if set(preimage_entries) - original_names:
        raise LauncherError("The successor state preimage contains an unexpected entry.")
    for name in original_names:
        if name not in preimage_entries and not (current_state / name).exists():
            raise LauncherError("The controlled-update successor preimage is incomplete.")
    for candidate in sorted(current_state.iterdir(), key=lambda path: path.name):
        if candidate.name == "operation.lock":
            continue
        if candidate.name in original_names and candidate.name not in preimage_entries:
            continue
        _remove_exact_path(candidate)
    for name, candidate in sorted(preimage_entries.items()):
        target = current_state / name
        if target.exists():
            _remove_exact_path(target)
        os.replace(candidate, target)
    if successor_preimage.exists():
        successor_preimage.rmdir()
    restored_names = {
        candidate.name
        for candidate in current_state.iterdir()
        if candidate.name != "operation.lock"
    }
    if restored_names != original_names:
        raise LauncherError("The controlled-update successor state did not return to its exact pre-update inventory.")


def _require_controlled_update_recovery_identity(
    transaction: dict[str, Any],
) -> tuple[dict[str, str], Path, Path]:
    predecessor_root = Path(str(transaction["predecessor_root"])).resolve()
    predecessor_state = predecessor_root / STATE_DIR_NAME
    predecessor_runtime = predecessor_state / "runtime.env"
    predecessor_connected = predecessor_state / "connected.env"
    predecessor_config = predecessor_state / "config.json"

    observed_predecessor = _controlled_update_distribution_binding(
        _distribution_identity_at(predecessor_root)
    )
    observed_successor = _controlled_update_distribution_binding(
        _distribution_identity_at(package_root().resolve())
    )
    if observed_predecessor != transaction["predecessor_distribution"]:
        raise LauncherError(
            "The recorded predecessor package changed after the controlled update began; no project was stopped."
        )
    if observed_successor != transaction["successor_distribution"]:
        raise LauncherError(
            "The successor package changed after the controlled update began; no project was stopped."
        )

    observed_state = {
        "runtime.env": _controlled_update_state_file_binding(predecessor_runtime, required=True),
        "config.json": _controlled_update_state_file_binding(predecessor_config, required=True),
        "connected.env": _controlled_update_state_file_binding(predecessor_connected, required=False),
    }
    if observed_state != transaction["predecessor_state_files"]:
        raise LauncherError(
            "The recorded predecessor runtime or configuration changed after the controlled update began; "
            "no project was stopped."
        )

    values = _parse_env(predecessor_runtime)
    if _controlled_update_missing_runtime_keys(values):
        raise LauncherError("The recorded predecessor runtime state is incomplete; no project was stopped.")
    observed_shop_hash = hashlib.sha256(
        values["ODDROOM_SHOP_INSTANCE_ID"].encode("utf-8")
    ).hexdigest()
    observed_volumes = _volume_names(values)
    if (
        values["PF07_COMPOSE_PROJECT"] != transaction["predecessor_compose_project"]
        or observed_shop_hash != transaction["predecessor_shop_instance_id_sha256"]
        or observed_volumes != transaction["predecessor_volume_names"]
    ):
        raise LauncherError(
            "The recorded predecessor project, shop, or volume identity changed; no project was stopped."
        )
    for logical_name, volume_name in observed_volumes.items():
        _require_owned_volume(volume_name, logical_name, values)

    successor_runtime = state_dir() / "runtime.env"
    if successor_runtime.is_file():
        successor_values = _parse_env(successor_runtime)
        successor_shop_hash = hashlib.sha256(
            successor_values.get("ODDROOM_SHOP_INSTANCE_ID", "").encode("utf-8")
        ).hexdigest()
        if (
            successor_values.get("PF07_COMPOSE_PROJECT")
            != transaction["predecessor_compose_project"]
            or successor_shop_hash != transaction["predecessor_shop_instance_id_sha256"]
        ):
            raise LauncherError(
                "The migrated successor state no longer belongs to the recorded predecessor runtime; "
                "no project was stopped."
            )
    return values, predecessor_runtime, predecessor_connected


def _validated_update_volume_preimages(
    transaction: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Path]:
    _, _, volume_preimage = _controlled_update_scratch_paths(transaction)
    rows = transaction.get("volumes", [])
    if len(rows) != 3:
        raise LauncherError("The controlled-update volume preimage set is incomplete.")
    archives: dict[str, Path] = {}
    for row in rows:
        logical_name = str(row.get("logical_name", ""))
        archive_name = str(row.get("archive", ""))
        archive = volume_preimage / archive_name
        declared_bytes = row.get("bytes")
        declared_sha = str(row.get("sha256", ""))
        if (
            logical_name in archives
            or archive_name != f"{logical_name}.tar"
            or not isinstance(declared_bytes, int)
            or isinstance(declared_bytes, bool)
            or declared_bytes < 0
            or not re.fullmatch(r"[a-f0-9]{64}", declared_sha)
            or not archive.is_file()
            or archive.stat().st_size != declared_bytes
            or _sha256_file(archive) != declared_sha
        ):
            raise LauncherError("A controlled-update volume preimage failed its exact content binding.")
        _inspect_volume_archive(archive)
        _require_owned_volume(_volume_names(values)[logical_name], logical_name, values)
        archives[logical_name] = archive
    if set(archives) != {"mariadb_data", "wordpress_data", "n8n_data"}:
        raise LauncherError("The controlled-update volume preimage set is incomplete.")
    return archives


def _cleanup_controlled_update_scratch(transaction: dict[str, Any]) -> None:
    stage, successor_preimage, volume_preimage = _controlled_update_scratch_paths(transaction)
    for path in (stage, successor_preimage, volume_preimage):
        if path.exists():
            _remove_exact_path(path)


def _acquire_recovery_lock(path: Path) -> int:
    if path.exists() and not _recover_dead_package_lock(path):
        raise LauncherError(f"A package process still owns the controlled-update lock: {path.name}")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(descriptor, f"{os.getpid()}\n{_utc_now()}\n".encode("ascii"))
    return descriptor


def _rollback_controlled_update(
    transaction: dict[str, Any],
    *,
    acquire_predecessor_locks: bool,
) -> dict[str, Any]:
    predecessor_root = Path(str(transaction["predecessor_root"])).resolve()
    predecessor_state = predecessor_root / STATE_DIR_NAME
    values, predecessor_runtime, predecessor_connected = _require_controlled_update_recovery_identity(
        transaction
    )
    lock_path = predecessor_state / "update.lock"
    operation_lock_path = predecessor_state / "operation.lock"
    lock_descriptor: int | None = None
    operation_descriptor: int | None = None
    try:
        if acquire_predecessor_locks:
            lock_descriptor = _acquire_recovery_lock(lock_path)
            operation_descriptor = _acquire_recovery_lock(operation_lock_path)
            values, predecessor_runtime, predecessor_connected = (
                _require_controlled_update_recovery_identity(transaction)
            )
        active_container = transaction.get("active_container")
        if active_container is not None:
            if not _remove_transient_container(str(active_container)):
                raise LauncherError(
                    f"Stop the exact update restore container before retrying recovery: {active_container}"
                )
            transaction = _update_controlled_update_transaction(active_container=None)
        archives: dict[str, Path] = {}
        if bool(transaction.get("volume_mutation_started")):
            archives = _validated_update_volume_preimages(transaction, values)
        _update_controlled_update_transaction(phase="ROLLBACK_STOPPING_PROJECT")
        _compose_at_root(
            predecessor_root,
            values,
            predecessor_runtime,
            predecessor_connected if predecessor_connected.is_file() else None,
            ["down", "--remove-orphans"],
            check=False,
            timeout=300,
        )
        if _running_project_containers(values):
            raise LauncherError("The shared PF07 project still has running containers; volume rollback did not begin.")
        if bool(transaction.get("volume_mutation_started")):
            for logical_name in ("mariadb_data", "wordpress_data", "n8n_data"):
                _restore_update_volume(
                    _volume_names(values)[logical_name],
                    archives[logical_name],
                    values,
                )
        _update_controlled_update_transaction(phase="ROLLBACK_RESTORING_SUCCESSOR_STATE")
        _rollback_successor_state(transaction)
        fence_path = predecessor_state / UPDATE_FENCE_NAME
        if fence_path.is_file():
            try:
                fence = json.loads(fence_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise LauncherError("The predecessor update fence is unreadable; do not remove it manually.") from error
            if fence.get("transaction_id") != transaction["transaction_id"]:
                raise LauncherError("The predecessor update fence belongs to a different transaction.")
            fence_path.unlink()
        running_before = transaction.get("running_before", [])
        if (
            not isinstance(running_before, list)
            or not all(isinstance(service, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", service) for service in running_before)
        ):
            raise LauncherError("The controlled-update predecessor service inventory is invalid.")
        resumed_services: list[str] = []
        if running_before:
            _update_controlled_update_transaction(phase="ROLLBACK_STARTING_PREDECESSOR")
            resumed = _compose_at_root(
                predecessor_root,
                values,
                predecessor_runtime,
                predecessor_connected if predecessor_connected.is_file() else None,
                ["up", "-d", *running_before],
                check=False,
                timeout=900,
            )
            if resumed.returncode != 0:
                raise LauncherError(
                    "The exact predecessor data was restored, but its recorded services did not restart. "
                    + _redact(resumed.stdout or "", values)[-1000:]
                )
            resumed_services = _running_services_at_root(
                predecessor_root,
                values,
                predecessor_runtime,
                predecessor_connected,
            )
            if set(resumed_services) != set(running_before):
                raise LauncherError(
                    "The exact predecessor data was restored, but not all recorded predecessor services are running."
                )
        _update_controlled_update_transaction(phase="ROLLED_BACK_TO_PREDECESSOR")
        return {
            "schema": "pf07.controlled-update-recovery.v1",
            "status": "ROLLED_BACK",
            "recovery_operation": "CONTROLLED_UPDATE_ROLLBACK",
            "predecessor_root": str(predecessor_root),
            "predecessor_services": resumed_services,
            "predecessor_resumed": set(resumed_services) == set(running_before),
            "volume_preimage_restored": bool(transaction.get("volume_mutation_started")),
        }
    finally:
        if acquire_predecessor_locks:
            _release_owned_lock(operation_lock_path, operation_descriptor)
            _release_owned_lock(lock_path, lock_descriptor)


def _clear_stale_predecessor_update_locks(transaction: dict[str, Any]) -> None:
    predecessor_state = Path(str(transaction["predecessor_root"])).resolve() / STATE_DIR_NAME
    for name in ("operation.lock", "update.lock"):
        path = predecessor_state / name
        if path.exists() and not _recover_dead_package_lock(path):
            raise LauncherError(
                f"The recorded predecessor still has a live {name}; let that exact process finish before recovery."
            )


def _require_committed_predecessor_fence(transaction: dict[str, Any]) -> None:
    fence_path = (
        Path(str(transaction["predecessor_root"])).resolve()
        / STATE_DIR_NAME
        / UPDATE_FENCE_NAME
    )
    if fence_path.is_symlink() or not fence_path.is_file():
        raise LauncherError(
            "The committed predecessor update fence is unavailable; keep both extractions and do not start either package."
        )
    try:
        fence = json.loads(fence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError(
            "The committed predecessor update fence is unreadable; keep both extractions unchanged."
        ) from error
    successor = transaction["successor_distribution"]
    expected = {
        "schema": "pf07.predecessor-update-fence.v1",
        "status": "FENCED",
        "transaction_id": transaction["transaction_id"],
        "successor_build_id": successor["build_id"],
        "successor_artifact_manifest_sha256": successor["artifact_manifest_sha256"],
        "recovery_action": "USE_SUCCESSOR_PACKAGE",
    }
    if any(fence.get(key) != expected_value for key, expected_value in expected.items()):
        raise LauncherError(
            "The committed predecessor update fence no longer matches this exact successor transaction."
        )


def _finalize_rolled_back_update(transaction: dict[str, Any]) -> dict[str, Any]:
    predecessor_root = Path(str(transaction["predecessor_root"])).resolve()
    predecessor_state = predecessor_root / STATE_DIR_NAME
    values, predecessor_runtime, predecessor_connected = _require_controlled_update_recovery_identity(
        transaction
    )
    running_before = transaction.get("running_before", [])
    if not isinstance(running_before, list) or not all(isinstance(item, str) for item in running_before):
        raise LauncherError("The rolled-back predecessor service inventory is invalid.")
    _clear_stale_predecessor_update_locks(transaction)
    resumed_services = _running_services_at_root(
        predecessor_root,
        values,
        predecessor_runtime,
        predecessor_connected,
    )
    if set(resumed_services) != set(running_before) and running_before:
        resumed = _compose_at_root(
            predecessor_root,
            values,
            predecessor_runtime,
            predecessor_connected if predecessor_connected.is_file() else None,
            ["up", "-d", *running_before],
            check=False,
            timeout=900,
        )
        if resumed.returncode != 0:
            raise LauncherError("The rolled-back predecessor could not resume its recorded services.")
        resumed_services = _running_services_at_root(
            predecessor_root,
            values,
            predecessor_runtime,
            predecessor_connected,
        )
    if set(resumed_services) != set(running_before):
        raise LauncherError("The rolled-back predecessor has not returned to its recorded service set.")
    _cleanup_controlled_update_scratch(transaction)
    _controlled_update_transaction_path().unlink(missing_ok=True)
    return {
        "schema": "pf07.controlled-update-recovery.v1",
        "status": "ROLLED_BACK",
        "recovery_operation": "CONTROLLED_UPDATE_ROLLBACK_FINALIZED",
        "predecessor_root": str(predecessor_root),
        "predecessor_services": resumed_services,
        "predecessor_resumed": True,
        "volume_preimage_restored": bool(transaction.get("volume_mutation_started")),
    }


def _abort_unmutated_controlled_update(transaction: dict[str, Any]) -> dict[str, Any]:
    if transaction.get("volume_mutation_started") or transaction.get("running_before"):
        raise LauncherError("The controlled-update transaction is not an unmutated pre-observation transaction.")
    _clear_stale_predecessor_update_locks(transaction)
    _cleanup_controlled_update_scratch(transaction)
    _controlled_update_transaction_path().unlink(missing_ok=True)
    return {
        "schema": "pf07.controlled-update-recovery.v1",
        "status": "ABORTED_BEFORE_MUTATION",
        "recovery_operation": "CONTROLLED_UPDATE_ABORT",
        "predecessor_root": str(transaction["predecessor_root"]),
        "predecessor_untouched": True,
    }


def _recover_controlled_update(transaction: dict[str, Any]) -> dict[str, Any]:
    if transaction.get("phase") in {"LOCKING_PREDECESSOR", "PREDECESSOR_LOCKED"}:
        _require_controlled_update_recovery_identity(transaction)
        return _abort_unmutated_controlled_update(transaction)
    if transaction.get("phase") == "ROLLED_BACK_TO_PREDECESSOR":
        return _finalize_rolled_back_update(transaction)
    if transaction.get("phase") == "COMMITTED":
        _require_controlled_update_recovery_identity(transaction)
        _require_committed_predecessor_fence(transaction)
        _write_controlled_update_gate(
            "COMMITTED",
            transaction_id=str(transaction["transaction_id"]),
            successor_build_id=str(transaction["successor_distribution"]["build_id"]),
        )
        result = start()
        if not result["ready"]:
            raise LauncherError("The committed successor runtime is not ready; keep both extractions and retry Recover service.")
        current_values = ensure_runtime()
        active_counts = {
            service: _project_service_container_count(current_values, service)
            for service in ("db", "wordpress", "n8n", "task-runners", "worker")
        }
        if active_counts != {
            "db": 1,
            "wordpress": 1,
            "n8n": 1,
            "task-runners": 1,
            "worker": 1,
        }:
            raise LauncherError(
                "The committed successor does not own exactly one active business runtime; "
                "keep both extractions and retry Recover service."
            )
        _update_controlled_update_transaction(
            phase="COMMITTED",
            worker_enabled=True,
        )
        _require_committed_predecessor_fence(transaction)
        _clear_stale_predecessor_update_locks(transaction)
        _cleanup_controlled_update_scratch(transaction)
        _controlled_update_transaction_path().unlink(missing_ok=True)
        _write_controlled_update_gate("NORMAL")
        result["recovery_operation"] = "CONTROLLED_UPDATE_COMMIT_RECOVERY"
        return result
    _rollback_controlled_update(transaction, acquire_predecessor_locks=True)
    terminal = _read_controlled_update_transaction()
    if terminal is None or terminal.get("phase") != "ROLLED_BACK_TO_PREDECESSOR":
        raise LauncherError("The controlled-update rollback did not reach its durable terminal state.")
    return _finalize_rolled_back_update(terminal)


def controlled_update(predecessor_name: str, confirmation: str) -> dict[str, Any]:
    with _operation_lock():
        return _controlled_update_locked(predecessor_name, confirmation)


def _controlled_update_locked(predecessor_name: str, confirmation: str) -> dict[str, Any]:
    """Move one running predecessor state to this exact reviewed package without a second writer."""
    if confirmation != "UPDATE PF07":
        raise LauncherError("Type UPDATE PF07 exactly to confirm the controlled package update.")
    _docker_preflight({})
    current_root = package_root().resolve()
    predecessor_root = Path(predecessor_name).expanduser().resolve()
    if predecessor_root == current_root or predecessor_root.is_relative_to(current_root) or current_root.is_relative_to(predecessor_root):
        raise LauncherError("Choose a separate predecessor package extraction.")
    if not predecessor_root.is_dir():
        raise LauncherError("The selected predecessor package directory does not exist.")
    current_identity = _distribution_identity_at(current_root)
    predecessor_identity = _distribution_identity_at(predecessor_root)
    if current_identity["artifact_id"] != predecessor_identity["artifact_id"]:
        raise LauncherError("The predecessor and successor platform artifact IDs do not match.")
    approved_manifest = CONTROLLED_UPDATE_PREDECESSOR_MANIFEST_SHA256.get(
        str(predecessor_identity["artifact_id"])
    )
    if (
        approved_manifest is None
        or predecessor_identity["build_id"] != CONTROLLED_UPDATE_PREDECESSOR_BUILD_ID
        or predecessor_identity["artifact_manifest_sha256"] != approved_manifest
    ):
        raise LauncherError("The predecessor is not an exact approved public PF07 1.0.4 package.")
    expected_update = (CONTROLLED_UPDATE_PREDECESSOR_VERSION, PACKAGE_VERSION)
    observed_update = (predecessor_identity["package_version"], current_identity["package_version"])
    if observed_update != expected_update:
        raise LauncherError(
            "This controlled update requires the reviewed "
            f"{CONTROLLED_UPDATE_PREDECESSOR_VERSION} predecessor and {PACKAGE_VERSION} successor."
        )
    if current_identity["build_id"] == predecessor_identity["build_id"]:
        raise LauncherError("The selected predecessor already has this build identity.")

    predecessor_state = predecessor_root / STATE_DIR_NAME
    predecessor_runtime = predecessor_state / "runtime.env"
    predecessor_connected = predecessor_state / "connected.env"
    current_state = state_dir()
    if predecessor_state.is_symlink():
        raise LauncherError("The predecessor package state directory must not be a symbolic link.")
    if not predecessor_runtime.is_file() or not (predecessor_state / "config.json").is_file():
        raise LauncherError("Start the predecessor package successfully before updating it.")
    if predecessor_connected.is_symlink():
        raise LauncherError("The predecessor connected state must not be a symbolic link.")
    migration_sources = [
        predecessor_runtime,
        predecessor_state / "config.json",
        *([predecessor_connected] if predecessor_connected.exists() else []),
    ]
    if any(source.is_symlink() or not source.is_file() for source in migration_sources):
        raise LauncherError("The predecessor package contains an unsupported state-file link or type.")
    if (predecessor_state / UPDATE_FENCE_NAME).exists():
        raise LauncherError("The selected predecessor has already been fenced by an update.")
    predecessor_operation_lock = predecessor_state / "operation.lock"
    if predecessor_operation_lock.exists() and not _recover_dead_package_lock(predecessor_operation_lock):
        raise LauncherError("The predecessor is busy. Let its current operation finish, then retry the update.")
    predecessor_update_lock = predecessor_state / "update.lock"
    if predecessor_update_lock.exists():
        interrupted_markers = (
            (current_state / "runtime.env").exists()
            or any(current_root.glob(".pf07-update-stage-*"))
            or any(current_root.glob(".pf07-update-preimage-*"))
        )
        if interrupted_markers:
            raise LauncherError(
                "A prior controlled update stopped after migration work began. Preserve both extractions and use the successor recover path before retrying."
            )
        if not _recover_dead_package_lock(predecessor_update_lock):
            raise LauncherError("The predecessor update is still running. Let it finish before retrying.")
    predecessor_values = _parse_env(predecessor_runtime)
    missing = _controlled_update_missing_runtime_keys(predecessor_values)
    if missing:
        raise LauncherError("The predecessor runtime state is incomplete: " + ", ".join(missing))
    predecessor_volume_names = _volume_names(predecessor_values)
    predecessor_state_files = {
        "runtime.env": _controlled_update_state_file_binding(predecessor_runtime, required=True),
        "config.json": _controlled_update_state_file_binding(
            predecessor_state / "config.json",
            required=True,
        ),
        "connected.env": _controlled_update_state_file_binding(predecessor_connected, required=False),
    }

    if (current_state / "runtime.env").exists():
        raise LauncherError("The successor package already owns runtime state; use a clean extraction for update.")
    if current_state.exists():
        unexpected = sorted(
            path.name
            for path in current_state.iterdir()
            if path.name not in {"config.json", "operation.json", "operation.lock"}
        )
        if unexpected:
            raise LauncherError("The successor package contains unexpected local state: " + ", ".join(unexpected))

    transaction_id = uuid.uuid4().hex
    stage = current_root / f".pf07-update-stage-{transaction_id}"
    successor_preimage = current_root / f".pf07-update-preimage-{transaction_id}"
    volume_preimage = current_root / f".pf07-update-volume-preimage-{transaction_id}"
    lock_path = predecessor_state / "update.lock"
    lock_descriptor: int | None = None
    predecessor_operation_descriptor: int | None = None
    running_before: list[str] = []
    predecessor_locks_acquired = False
    running_observed = False
    successor_original_names = sorted(
        path.name for path in current_state.iterdir() if path.name != "operation.lock"
    )
    migration_names = sorted(source.name for source in migration_sources)
    transaction: dict[str, Any] = {
        "schema": "pf07.controlled-update-transaction.v1",
        "transaction_id": transaction_id,
        "phase": "LOCKING_PREDECESSOR",
        "successor_root": str(current_root),
        "predecessor_root": str(predecessor_root),
        "stage_name": stage.name,
        "successor_preimage_name": successor_preimage.name,
        "volume_preimage_name": volume_preimage.name,
        "successor_original_names": successor_original_names,
        "migration_names": migration_names,
        "from_build_id": predecessor_identity["build_id"],
        "to_build_id": current_identity["build_id"],
        "predecessor_distribution": _controlled_update_distribution_binding(predecessor_identity),
        "successor_distribution": _controlled_update_distribution_binding(current_identity),
        "predecessor_state_files": predecessor_state_files,
        "predecessor_compose_project": predecessor_values["PF07_COMPOSE_PROJECT"],
        "predecessor_shop_instance_id_sha256": hashlib.sha256(
            predecessor_values["ODDROOM_SHOP_INSTANCE_ID"].encode("utf-8")
        ).hexdigest(),
        "predecessor_volume_names": predecessor_volume_names,
        "running_before": [],
        "volume_mutation_started": False,
        "worker_enabled": False,
        "active_container": None,
        "active_volume": None,
        "volumes": [
            {
                "logical_name": logical_name,
                "phase": "PENDING",
                "archive": None,
                "sha256": None,
                "bytes": None,
            }
            for logical_name in ("mariadb_data", "wordpress_data", "n8n_data")
        ],
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
    }
    _atomic_json(_controlled_update_transaction_path(), transaction)
    try:
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(lock_descriptor, f"{os.getpid()}\n{_utc_now()}\n".encode("ascii"))
        predecessor_operation_descriptor = os.open(
            predecessor_operation_lock,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        os.write(predecessor_operation_descriptor, f"{os.getpid()}\n{_utc_now()}\n".encode("ascii"))
        predecessor_locks_acquired = True
        predecessor_values, predecessor_runtime, predecessor_connected = (
            _require_controlled_update_recovery_identity(transaction)
        )
        migration_sources = [
            predecessor_runtime,
            predecessor_state / "config.json",
            *([predecessor_connected] if predecessor_connected.exists() else []),
        ]
        _update_controlled_update_transaction(phase="PREDECESSOR_LOCKED")
        stage.mkdir(mode=0o700)
        for source in migration_sources:
            shutil.copy2(source, stage / source.name, follow_symlinks=False)
        running_before = _running_services_at_root(
            predecessor_root,
            predecessor_values,
            predecessor_runtime,
            predecessor_connected,
        )
        expected_services = {"db", "wordpress", "n8n", "task-runners", "worker"}
        if set(running_before) != expected_services:
            raise LauncherError(
                "The predecessor must be fully ready with its exact five runtime services before a controlled update."
            )
        transaction = _update_controlled_update_transaction(
            phase="PREDECESSOR_STATE_OBSERVED",
            running_before=running_before,
        )
        running_observed = True
        predecessor_tunnel = _stop_tunnel_processes(predecessor_state)
        if not all(predecessor_tunnel.values()):
            raise LauncherError(
                "The predecessor HTTPS tunnel could not be fully stopped. Disable it from the predecessor package before updating."
            )
        _compose_at_root(
            predecessor_root,
            predecessor_values,
            predecessor_runtime,
            predecessor_connected if predecessor_connected.is_file() else None,
            ["down", "--remove-orphans"],
            timeout=300,
        )
        quiesced = _running_services_at_root(
            predecessor_root,
            predecessor_values,
            predecessor_runtime,
            predecessor_connected,
        )
        if quiesced:
            raise LauncherError("The predecessor still has running services after the update fence was applied.")
        transaction = _update_controlled_update_transaction(phase="PREDECESSOR_QUIESCED")
        volume_preimage.mkdir(mode=0o700)
        volume_rows = [dict(row) for row in transaction["volumes"]]
        predecessor_volumes = _volume_names(predecessor_values)
        for row in volume_rows:
            logical_name = str(row["logical_name"])
            row["phase"] = "ARCHIVING"
            transaction = _update_controlled_update_transaction(
                phase=f"ARCHIVING_{logical_name.upper()}",
                volumes=volume_rows,
            )
            archive_path = volume_preimage / f"{logical_name}.tar"
            _archive_volume(predecessor_volumes[logical_name], archive_path, predecessor_values)
            row.update(
                {
                    "phase": "READY",
                    "archive": archive_path.name,
                    "sha256": _sha256_file(archive_path),
                    "bytes": archive_path.stat().st_size,
                }
            )
            transaction = _update_controlled_update_transaction(volumes=volume_rows)
        _validated_update_volume_preimages(transaction, predecessor_values)
        transaction = _update_controlled_update_transaction(phase="VOLUME_PREIMAGE_READY")
        successor_preimage.mkdir(mode=0o700)
        _update_controlled_update_transaction(phase="SUCCESSOR_STATE_SWAP_STARTED")
        for candidate in sorted(current_state.iterdir(), key=lambda path: path.name):
            if candidate.name != "operation.lock":
                os.replace(candidate, successor_preimage / candidate.name)
        for candidate in sorted(stage.iterdir(), key=lambda path: path.name):
            os.replace(candidate, current_state / candidate.name)
        stage.rmdir()
        _update_controlled_update_transaction(phase="SUCCESSOR_STATE_INSTALLED")
        _write_controlled_update_gate(
            "TENTATIVE",
            transaction_id=transaction_id,
            successor_build_id=str(current_identity["build_id"]),
        )
        migration_record = {
            "schema": "pf07.controlled-update-migration.v1",
            "status": "IN_PROGRESS",
            "from_build_id": predecessor_identity["build_id"],
            "to_build_id": current_identity["build_id"],
            "package_version": current_identity["package_version"],
            "migration_id": "controlled-1.0.4-to-1.0.5-v1",
            "manifest_migrations": [
                "oddroom-orderops-schema-1.1.0",
                "package-config-v1",
                "persistent-volume-schema-1",
            ],
            "shop_instance_id_sha256": hashlib.sha256(
                predecessor_values["ODDROOM_SHOP_INSTANCE_ID"].encode("utf-8")
            ).hexdigest(),
            "started_at_utc": _utc_now(),
        }
        _atomic_json(current_state / "controlled-update.json", migration_record)
        _update_controlled_update_transaction(
            phase="SUCCESSOR_STARTING",
            volume_mutation_started=True,
        )
        runtime = start(_controlled_update_tentative=True)
        current_values = ensure_runtime()
        _wp(current_values, ["option", "update", "oddroom_orderops_package_build_id", current_identity["build_id"]])
        migration_record.update({"status": "PASS", "completed_at_utc": _utc_now()})
        _atomic_json(current_state / "controlled-update.json", migration_record)
        tentative_counts = {
            service: _project_service_container_count(current_values, service)
            for service in ("db", "wordpress", "n8n", "task-runners", "worker")
        }
        if (
            not runtime.get("controlled_update_tentative_ready")
            or tentative_counts
            != {"db": 1, "wordpress": 1, "n8n": 1, "task-runners": 1, "worker": 0}
        ):
            raise LauncherError(
                "The tentative successor did not establish exactly one worker-paused business runtime."
            )
        _atomic_json(
            predecessor_state / UPDATE_FENCE_NAME,
            {
                "schema": "pf07.predecessor-update-fence.v1",
                "status": "FENCED",
                "transaction_id": transaction_id,
                "successor_build_id": current_identity["build_id"],
                "successor_artifact_manifest_sha256": current_identity["artifact_manifest_sha256"],
                "created_at_utc": _utc_now(),
                "recovery_action": "USE_SUCCESSOR_PACKAGE",
            },
        )
        transaction = _update_controlled_update_transaction(
            phase="COMMITTED",
            worker_enabled=False,
        )
        _write_controlled_update_gate(
            "COMMITTED",
            transaction_id=transaction_id,
            successor_build_id=str(current_identity["build_id"]),
        )
        _compose(current_values, ["up", "-d", "worker"], timeout=900)
        runtime = status()
        active_counts = {
            service: _project_service_container_count(current_values, service)
            for service in ("db", "wordpress", "n8n", "task-runners", "worker")
        }
        if (
            not runtime["ready"]
            or active_counts
            != {"db": 1, "wordpress": 1, "n8n": 1, "task-runners": 1, "worker": 1}
        ):
            raise LauncherError(
                "The committed successor did not establish exactly one active business runtime."
            )
        transaction = _update_controlled_update_transaction(
            phase="COMMITTED",
            worker_enabled=True,
        )
        result = {
            "schema": "pf07.controlled-update-result.v1",
            "status": "PASS",
            "package_version": current_identity["package_version"],
            "from_build_id": predecessor_identity["build_id"],
            "to_build_id": current_identity["build_id"],
            "predecessor_files_verified": predecessor_identity["files_verified"],
            "successor_files_verified": current_identity["files_verified"],
            "migration_id": migration_record["migration_id"],
            "migration_applied_once": True,
            "shop_instance_id_sha256": migration_record["shop_instance_id_sha256"],
            "quiesced_predecessor_services": 0,
            "predecessor_services_running_after_quiescence": len(quiesced),
            "active_service_container_counts": active_counts,
            "one_active_runtime": True,
            "predecessor_fenced": True,
            "runtime": runtime,
        }
        _release_owned_lock(predecessor_operation_lock, predecessor_operation_descriptor)
        predecessor_operation_descriptor = None
        _release_owned_lock(lock_path, lock_descriptor)
        lock_descriptor = None
        _cleanup_controlled_update_scratch(transaction)
        _controlled_update_transaction_path().unlink(missing_ok=True)
        _write_controlled_update_gate("NORMAL")
        return result
    except Exception as error:
        current_transaction: dict[str, Any] | None = None
        try:
            current_transaction = _read_controlled_update_transaction()
            if current_transaction is not None and current_transaction.get("phase") == "COMMITTED":
                raise LauncherError(
                    "The successor was committed, but cleanup was interrupted. Use Recover service in the successor package."
                )
            if predecessor_locks_acquired and running_observed and current_transaction is not None:
                rollback = _rollback_controlled_update(
                    current_transaction,
                    acquire_predecessor_locks=False,
                )
                _release_owned_lock(predecessor_operation_lock, predecessor_operation_descriptor)
                predecessor_operation_descriptor = None
                _release_owned_lock(lock_path, lock_descriptor)
                lock_descriptor = None
                terminal = _read_controlled_update_transaction()
                if terminal is None or terminal.get("phase") != "ROLLED_BACK_TO_PREDECESSOR":
                    raise LauncherError("The controlled-update rollback did not preserve its terminal transaction.")
                finalized = _finalize_rolled_back_update(terminal)
                raise LauncherError(
                    "Controlled update failed after migration began, and the exact predecessor data and services were restored. "
                    f"Predecessor resumed={str(finalized['predecessor_resumed']).lower()}. Cause: {error}"
                )
            if current_transaction is not None:
                _release_owned_lock(predecessor_operation_lock, predecessor_operation_descriptor)
                predecessor_operation_descriptor = None
                _release_owned_lock(lock_path, lock_descriptor)
                lock_descriptor = None
                _cleanup_controlled_update_scratch(current_transaction)
                _controlled_update_transaction_path().unlink(missing_ok=True)
        except Exception as recovery_error:
            if isinstance(recovery_error, LauncherError) and (
                "exact predecessor data and services were restored" in str(recovery_error)
                or "successor was committed" in str(recovery_error)
            ):
                raise recovery_error from error
            raise LauncherError(
                "Controlled update failed and its durable recovery transaction remains active. "
                f"Keep both package extractions and use Recover service in the successor package. "
                f"Cause: {error}. Recovery detail: {recovery_error}"
            ) from error
        raise LauncherError(
            f"Controlled update stopped before predecessor mutation began; no runtime data was changed. Cause: {error}"
        ) from error
    finally:
        _release_owned_lock(predecessor_operation_lock, predecessor_operation_descriptor)
        _release_owned_lock(lock_path, lock_descriptor)


def backup(requested: str | None, passphrase: str) -> dict[str, Any]:
    with _operation_lock():
        return _backup_locked(requested, passphrase)


def _backup_locked(requested: str | None, passphrase: str) -> dict[str, Any]:
    _require_existing_runtime("creating a package-local backup")
    output = _external_export_path(requested, "PF07-Backup", ".pf07backup")
    values = ensure_runtime()
    _docker_preflight(values)
    volumes = _volume_names(values)
    running_before = _running_services(values)
    if not all(_run(["docker", "volume", "inspect", volume], values, check=False, timeout=30).returncode == 0 for volume in volumes.values()):
        raise LauncherError("Start PF07 successfully at least once before creating a package-local backup.")
    with tempfile.TemporaryDirectory(prefix="backup-", dir=state_dir()) as temp_name:
        temp = Path(temp_name)
        resumed = False
        with _operation_lock():
            operation_error: Exception | None = None
            try:
                _set_operation("backup-quiesce", "백업 중 외부 쓰기를 막기 위해 패키지 작업자를 중지하는 중입니다.")
                if running_before:
                    _compose(values, ["stop"], timeout=240)
                    if _running_services(values):
                        raise LauncherError("PF07 still has running services; the encrypted backup did not begin.")
                volume_rows: list[dict[str, Any]] = []
                for logical, volume in volumes.items():
                    path = temp / f"{logical}.tar"
                    _archive_volume(volume, path, values)
                    volume_rows.append({"logical_name": logical, "archive": path.name, "sha256": _sha256_file(path), "bytes": path.stat().st_size})
                state_files: list[dict[str, Any]] = []
                state_copy = temp / "state"
                state_copy.mkdir(mode=0o700)
                for name in ("runtime.env", "config.json", "connected.env"):
                    source = state_dir() / name
                    if source.is_file():
                        target = state_copy / name
                        shutil.copyfile(source, target)
                        os.chmod(target, 0o600)
                        state_files.append({"path": f"state/{name}", "sha256": _sha256_file(target), "bytes": target.stat().st_size})
                manifest = {
                    "schema": "pf07.package-local-backup.v1",
                    "classification": "PACKAGE_LOCAL_BACKUP",
                    "package_version": PACKAGE_VERSION,
                    "compose_project_hash": hashlib.sha256(values["PF07_COMPOSE_PROJECT"].encode()).hexdigest(),
                    "shop_instance_id_hash": hashlib.sha256(values["ODDROOM_SHOP_INSTANCE_ID"].encode()).hexdigest(),
                    "volume_schema": "1",
                    "volumes": volume_rows,
                    "state_files": state_files,
                    "created_at_utc": _utc_now(),
                    "passphrase_stored": False,
                }
                manifest_path = temp / "BACKUP-MANIFEST.json"
                _atomic_json(manifest_path, manifest)
                plaintext = temp / "backup-content.tar"
                with tarfile.open(plaintext, "x") as archive:
                    archive.add(manifest_path, arcname="BACKUP-MANIFEST.json", recursive=False)
                    for row in state_files:
                        archive.add(temp / row["path"], arcname=row["path"], recursive=False)
                    for row in volume_rows:
                        archive.add(temp / row["archive"], arcname=f"volumes/{row['archive']}", recursive=False)
                encryption = _encrypt_backup(plaintext, output, passphrase)
                _set_operation("backup-complete", "암호화된 패키지 로컬 백업을 외부 경로에 만들었습니다.", "PASS")
            except Exception as error:
                operation_error = error
            finally:
                if running_before:
                    try:
                        restart_result = _compose(values, ["up", "-d", *running_before], check=False, timeout=900)
                        resumed = restart_result.returncode == 0
                    except Exception as resume_error:
                        resumed = False
                        if operation_error is None:
                            operation_error = resume_error
            if operation_error is not None:
                _set_operation("error", str(operation_error), "FAIL")
                raise operation_error
            if running_before and not resumed:
                _set_operation(
                    "error",
                    f"The encrypted backup was created as {output.name}, but the prior runtime did not resume. Use PF07 recover.",
                    "FAIL",
                )
    if running_before and not resumed:
        raise LauncherError(
            f"The encrypted backup was created as {output.name}, but the prior runtime did not resume. Use PF07 recover."
        )
    return {
        "schema": "pf07.backup-result.v1",
        "status": "PASS",
        "classification": "PACKAGE_LOCAL_BACKUP",
        "filename": output.name,
        "sha256": _sha256_file(output),
        "bytes": output.stat().st_size,
        "authenticated_encryption": encryption["authentication"],
        "passphrase_stored": False,
        "runtime_resumed": resumed if running_before else None,
        "recovery": "Keep the passphrase separately; loss of the passphrase is unrecoverable.",
    }


def _safe_extract_backup(plaintext: Path, destination: Path) -> set[str]:
    with tarfile.open(plaintext, "r") as archive:
        members = archive.getmembers()
        destinations: set[Path] = set()
        extracted_files: set[str] = set()
        for member in members:
            relative = PurePosixPath(member.name)
            if (
                relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or "\\" in member.name
                or not (member.isdir() or member.isreg())
            ):
                raise LauncherError("The authenticated backup contains an unsafe archive member.")
            target = (destination / Path(*relative.parts)).resolve()
            if not target.is_relative_to(destination.resolve()) or target in destinations:
                raise LauncherError("The authenticated backup contains a duplicate or unsafe archive member.")
            destinations.add(target)
            if member.isreg():
                extracted_files.add(relative.as_posix())
        for member in members:
            relative = PurePosixPath(member.name)
            target = destination / Path(*relative.parts)
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(target, 0o700)
                continue
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise LauncherError("The authenticated backup contains an unreadable archive member.")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            os.chmod(target, 0o600)
    return extracted_files


def _inspect_volume_archive(archive_path: Path) -> dict[str, int]:
    normalized_targets: set[str] = set()
    member_count = 0
    file_count = 0
    total_bytes = 0
    try:
        with tarfile.open(archive_path, "r:") as archive:
            for member in archive:
                member_count += 1
                if member_count > MAX_VOLUME_ARCHIVE_MEMBERS:
                    raise LauncherError("A volume archive contains too many filesystem entries.")
                raw_name = member.name
                if "\\" in raw_name or "\x00" in raw_name:
                    raise LauncherError("A volume archive contains an unsafe filesystem path.")
                while raw_name.startswith("./"):
                    raw_name = raw_name[2:]
                if raw_name in {"", "."}:
                    if member.type != tarfile.DIRTYPE:
                        raise LauncherError("A volume archive has an invalid root entry.")
                    normalized = "."
                else:
                    relative = PurePosixPath(raw_name)
                    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
                        raise LauncherError("A volume archive contains an unsafe filesystem path.")
                    normalized = relative.as_posix()
                if normalized in normalized_targets:
                    raise LauncherError("A volume archive contains duplicate normalized filesystem paths.")
                normalized_targets.add(normalized)
                if member.type == tarfile.DIRTYPE:
                    continue
                if member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}:
                    raise LauncherError(
                        "A volume archive contains a link, device, FIFO, or unsupported filesystem entry."
                    )
                if member.size < 0 or member.size > MAX_VOLUME_ARCHIVE_FILE_BYTES:
                    raise LauncherError("A volume archive contains an oversized file entry.")
                file_count += 1
                total_bytes += member.size
                if total_bytes > MAX_VOLUME_ARCHIVE_TOTAL_BYTES:
                    raise LauncherError("A volume archive exceeds the supported restored-data size.")
    except LauncherError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise LauncherError("A volume archive is unreadable or malformed.") from error
    return {
        "members": member_count,
        "files": file_count,
        "declared_file_bytes": total_bytes,
    }


def _validated_restore_payload(
    manifest: Any,
    extracted: Path,
    extracted_files: set[str],
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise LauncherError("The authenticated backup manifest is not an object.")
    if (
        manifest.get("schema") != "pf07.package-local-backup.v1"
        or manifest.get("classification") != "PACKAGE_LOCAL_BACKUP"
        or manifest.get("package_version") != PACKAGE_VERSION
        or manifest.get("volume_schema") != "1"
        or manifest.get("passphrase_stored") is not False
    ):
        raise LauncherError(f"The authenticated backup payload is incompatible with PF07 {PACKAGE_VERSION}.")

    state_rows = manifest.get("state_files")
    volume_rows = manifest.get("volumes")
    if not isinstance(state_rows, list) or not isinstance(volume_rows, list):
        raise LauncherError("The authenticated backup manifest inventories are malformed.")
    if len(state_rows) not in {2, 3} or len(volume_rows) != 3:
        raise LauncherError("The authenticated backup manifest has an unexpected state or volume count.")

    state_by_path: dict[str, dict[str, Any]] = {}
    for row in state_rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "bytes"}:
            raise LauncherError("An authenticated backup state row has an unexpected schema.")
        relative = safe_relative_backup_path(str(row["path"])).as_posix()
        if relative not in {"state/runtime.env", "state/config.json", "state/connected.env"}:
            raise LauncherError("The authenticated backup lists an unexpected state file.")
        if relative in state_by_path:
            raise LauncherError("The authenticated backup contains a duplicate state-file row.")
        target = extracted / Path(*PurePosixPath(relative).parts)
        declared_bytes = row["bytes"]
        if (
            not isinstance(declared_bytes, int)
            or isinstance(declared_bytes, bool)
            or declared_bytes < 0
            or not re.fullmatch(r"[a-f0-9]{64}", str(row["sha256"]))
            or not target.is_file()
            or target.stat().st_size != declared_bytes
            or _sha256_file(target) != row["sha256"]
        ):
            raise LauncherError("An authenticated backup state file failed its declared content binding.")
        state_by_path[relative] = row
    if not {"state/runtime.env", "state/config.json"}.issubset(state_by_path):
        raise LauncherError("The authenticated backup is missing its required runtime or configuration state.")

    restored_runtime = extracted / "state/runtime.env"
    restored_config = extracted / "state/config.json"
    try:
        config = json.loads(restored_config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError("The authenticated backup configuration is unreadable.") from error
    if (
        not isinstance(config, dict)
        or set(config) != {"schema", "mode", "locale"}
        or config.get("schema") != "pf07.package-config.v1"
        or config.get("mode") not in SUPPORTED_MODES
        or config.get("locale") not in SUPPORTED_LOCALES
    ):
        raise LauncherError("The authenticated backup mode or locale is invalid.")
    if config["mode"] == "CONNECTED_MODE" and "state/connected.env" not in state_by_path:
        raise LauncherError("The authenticated backup is missing its connected-mode state.")

    values = _parse_env(restored_runtime)
    if set(values) != REQUIRED_ENV_KEYS:
        raise LauncherError("The authenticated backup runtime state does not match the exact PF07 key set.")
    try:
        port = int(values["PF07_WORDPRESS_PORT"])
        run_id = uuid.UUID(values["ODDROOM_RUN_ID"])
        shop_id = uuid.UUID(values["ODDROOM_SHOP_INSTANCE_ID"].removeprefix("pf07-"))
        subnet = ipaddress.ip_network(values["PF07_NETWORK_SUBNET"], strict=True)
    except (ValueError, KeyError) as error:
        raise LauncherError("The authenticated backup runtime identity is malformed.") from error
    if (
        not 1024 <= port <= 65535
        or str(run_id) != values["ODDROOM_RUN_ID"]
        or values["ODDROOM_SHOP_INSTANCE_ID"] != f"pf07-{shop_id}"
        or values["ODDROOM_PUBLIC_BASE_URL"] != f"http://127.0.0.1:{port}"
        or values["PF07_ADMIN_USER"] != ADMIN_USER
        or values["PF07_HUBSPOT_CONFIGURED"] not in {"true", "false"}
        or values["PF07_SLACK_CONFIGURED"] not in {"true", "false"}
        or not isinstance(subnet, ipaddress.IPv4Network)
        or subnet.prefixlen != 24
        or not subnet.is_private
    ):
        raise LauncherError("The authenticated backup runtime identity is outside the package boundary.")
    expected_webhook = (
        "oddroom-orderops-v1" if config["mode"] == "CONNECTED_MODE" else "oddroom-orderops-demo-v1"
    )
    if values["ODDROOM_WEBHOOK_PATH"] != expected_webhook:
        raise LauncherError("The authenticated backup mode and webhook path do not match.")
    volume_map = _volume_names(values)

    rows: dict[str, dict[str, Any]] = {}
    archive_names: set[str] = set()
    volume_inventory: dict[str, dict[str, int]] = {}
    for row in volume_rows:
        if not isinstance(row, dict) or set(row) != {"logical_name", "archive", "sha256", "bytes"}:
            raise LauncherError("An authenticated backup volume row has an unexpected schema.")
        logical = str(row["logical_name"])
        archive_name = safe_relative_backup_name(str(row["archive"]))
        if logical not in volume_map or logical in rows or archive_name in archive_names:
            raise LauncherError("The authenticated backup contains a duplicate or unexpected volume row.")
        if archive_name != f"{logical}.tar":
            raise LauncherError("The authenticated backup volume archive is not bound to its logical volume.")
        target = extracted / "volumes" / archive_name
        declared_bytes = row["bytes"]
        if (
            not isinstance(declared_bytes, int)
            or isinstance(declared_bytes, bool)
            or declared_bytes < 0
            or not re.fullmatch(r"[a-f0-9]{64}", str(row["sha256"]))
            or not target.is_file()
            or target.stat().st_size != declared_bytes
            or _sha256_file(target) != row["sha256"]
        ):
            raise LauncherError("An authenticated backup volume failed its declared content binding.")
        volume_inventory[logical] = _inspect_volume_archive(target)
        rows[logical] = row
        archive_names.add(archive_name)
    if set(rows) != set(volume_map):
        raise LauncherError("The authenticated backup volume set does not match the PF07 volume schema.")

    expected_files = {
        "BACKUP-MANIFEST.json",
        *state_by_path.keys(),
        *(f"volumes/{name}" for name in archive_names),
    }
    if extracted_files != expected_files:
        raise LauncherError("The authenticated backup outer archive contains unlisted or missing files.")
    if manifest.get("compose_project_hash") != hashlib.sha256(
        values["PF07_COMPOSE_PROJECT"].encode()
    ).hexdigest() or manifest.get("shop_instance_id_hash") != hashlib.sha256(
        values["ODDROOM_SHOP_INSTANCE_ID"].encode()
    ).hexdigest():
        raise LauncherError("The authenticated backup identity hashes do not bind its restored runtime.")

    restored_connected = extracted / "state/connected.env"
    connected_values: dict[str, str] | None = None
    if restored_connected.is_file():
        connected_values = _parse_env(restored_connected)
        if set(connected_values) != CONNECTED_ENV_KEYS:
            raise LauncherError("The authenticated backup connected-mode state does not match its exact key set.")
    return {
        "values": values,
        "config": config,
        "connected_values": connected_values,
        "restored_runtime": restored_runtime,
        "restored_config": restored_config,
        "restored_connected": restored_connected,
        "volume_map": volume_map,
        "rows": rows,
        "volume_inventory": volume_inventory,
    }


def restore(archive_name: str, passphrase: str, confirmation: str) -> dict[str, Any]:
    with _operation_lock(allow_restore_transaction=True):
        selected_archive = Path(archive_name).expanduser().resolve()
        transaction = _read_restore_transaction()
        if transaction is not None:
            if transaction.get("active_container") is not None:
                raise LauncherError(
                    "An interrupted restore container may still be writing. Select Recover service to stop "
                    "that exact container before choosing a recovery archive."
                )
            if transaction.get("state") not in {"PREIMAGE_RESTORE_REQUIRED", "RETRY_RESTORE_REQUIRED"}:
                raise LauncherError(
                    "The protected restore transaction is not ready for another archive. Select Recover service first."
                )
            required = Path(str(transaction.get("required_archive_path", ""))).expanduser().resolve()
            if selected_archive != required:
                raise LauncherError(
                    "This recovery must use the exact archive recorded before interruption: "
                    f"{required}"
                )
            if not selected_archive.is_file():
                raise LauncherError("The exact recorded recovery archive is no longer available.")
            pre_restore_path = transaction.get("pre_restore_backup_path")
            incoming_path = transaction.get("incoming_archive_path")
            if pre_restore_path and selected_archive == Path(str(pre_restore_path)).expanduser().resolve():
                expected_sha256 = str(transaction.get("pre_restore_backup_sha256", ""))
            elif incoming_path and selected_archive == Path(str(incoming_path)).expanduser().resolve():
                expected_sha256 = str(transaction.get("incoming_archive_sha256", ""))
            else:
                raise LauncherError("The protected restore transaction does not bind the selected recovery archive.")
            if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256) or _sha256_file(selected_archive) != expected_sha256:
                raise LauncherError(
                    "The recorded recovery archive path now contains different bytes. Restore the exact recorded archive before retrying."
                )
        result = _restore_locked(
            archive_name,
            passphrase,
            confirmation,
            recovery_transaction=transaction,
        )
        _restore_transaction_path().unlink(missing_ok=True)
        return result


def _restore_locked(
    archive_name: str,
    passphrase: str,
    confirmation: str,
    *,
    recovery_transaction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if confirmation != "RESTORE PF07":
        raise LauncherError("Type RESTORE PF07 exactly to confirm the package-scoped restore.")
    archive_path = Path(archive_name).expanduser().resolve()
    if not archive_path.is_file() or archive_path.is_relative_to(package_root().resolve()):
        raise LauncherError("Choose an existing authenticated backup outside the extracted package directory.")
    selected_archive_sha256 = _sha256_file(archive_path)
    _docker_preflight({})
    tunnel_stopped = _stop_tunnel_processes()
    if not all(tunnel_stopped.values()):
        raise LauncherError("The HTTPS tunnel could not be fully stopped. Retry Disable tunnel before restoring.")
    state_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    predecessor_backup: str | None = None
    predecessor_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="restore-", dir=state_dir()) as temp_name:
        temp = Path(temp_name)
        plaintext = temp / "backup-content.tar"
        _decrypt_backup(archive_path, plaintext, passphrase)
        if _sha256_file(archive_path) != selected_archive_sha256:
            raise LauncherError("The selected backup changed while it was being authenticated. No restore was started.")
        extracted = temp / "extracted"
        extracted.mkdir(mode=0o700)
        extracted_files = _safe_extract_backup(plaintext, extracted)
        try:
            manifest = json.loads((extracted / "BACKUP-MANIFEST.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LauncherError("The authenticated backup manifest is unreadable.") from error
        payload = _validated_restore_payload(manifest, extracted, extracted_files)
        values = payload["values"]
        config = payload["config"]
        connected_values = payload["connected_values"]
        restored_runtime = payload["restored_runtime"]
        restored_connected = payload["restored_connected"]
        volume_map = payload["volume_map"]
        rows = payload["rows"]
        if recovery_transaction is not None:
            selected_is_preimage = bool(
                recovery_transaction.get("pre_restore_backup_path")
                and archive_path
                == Path(str(recovery_transaction["pre_restore_backup_path"])).expanduser().resolve()
            )
            expected_archive_sha = str(
                recovery_transaction.get(
                    "pre_restore_backup_sha256" if selected_is_preimage else "incoming_archive_sha256",
                    "",
                )
            )
            expected_compose_project = str(
                recovery_transaction.get(
                    "pre_restore_target_compose_project"
                    if selected_is_preimage
                    else "incoming_target_compose_project",
                    "",
                )
            )
            expected_shop_hash = str(
                recovery_transaction.get(
                    "pre_restore_target_shop_instance_id_sha256"
                    if selected_is_preimage
                    else "incoming_target_shop_instance_id_sha256",
                    "",
                )
            )
            observed_shop_hash = hashlib.sha256(
                values["ODDROOM_SHOP_INSTANCE_ID"].encode("utf-8")
            ).hexdigest()
            if (
                selected_archive_sha256 != expected_archive_sha
                or values["PF07_COMPOSE_PROJECT"] != expected_compose_project
                or observed_shop_hash != expected_shop_hash
            ):
                raise LauncherError(
                    "The authenticated recovery archive does not match the exact recorded archive and runtime identity."
                )

        current_values = _parse_env(state_dir() / "runtime.env") if (state_dir() / "runtime.env").is_file() else None
        if recovery_transaction is not None:
            recorded_predecessor = recovery_transaction.get("pre_restore_backup_path")
            predecessor_path = (
                Path(str(recorded_predecessor)).expanduser().resolve()
                if recorded_predecessor
                else None
            )
            predecessor_backup = predecessor_path.name if predecessor_path is not None else None
        elif (state_dir() / "runtime.env").is_file():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            predecessor_path = archive_path.parent / f"PF07-Pre-Restore-{stamp}.pf07backup"
            predecessor = _backup_locked(str(predecessor_path), passphrase)
            predecessor_backup = predecessor["filename"]
        predecessor_sha256 = (
            _sha256_file(predecessor_path)
            if predecessor_path is not None and predecessor_path.is_file()
            else None
        )
        volume_phases = {logical: "PENDING" for logical in volume_map}
        incoming_shop_hash = hashlib.sha256(values["ODDROOM_SHOP_INSTANCE_ID"].encode()).hexdigest()
        pre_restore_compose_project = (
            str(recovery_transaction.get("pre_restore_target_compose_project", ""))
            if recovery_transaction is not None
            else (current_values["PF07_COMPOSE_PROJECT"] if current_values is not None else None)
        )
        pre_restore_shop_hash = (
            str(recovery_transaction.get("pre_restore_target_shop_instance_id_sha256", ""))
            if recovery_transaction is not None
            else (
                hashlib.sha256(current_values["ODDROOM_SHOP_INSTANCE_ID"].encode()).hexdigest()
                if current_values is not None
                else None
            )
        )
        _atomic_json(
            _restore_transaction_path(),
            {
                "schema": "pf07.restore-transaction.v1",
                "state": "RESTORE_IN_PROGRESS",
                "incoming_archive_path": str(archive_path),
                "incoming_archive_sha256": _sha256_file(archive_path),
                "pre_restore_backup_path": str(predecessor_path) if predecessor_path is not None else None,
                "pre_restore_backup_sha256": predecessor_sha256,
                "incoming_target_compose_project": values["PF07_COMPOSE_PROJECT"],
                "incoming_target_shop_instance_id_sha256": incoming_shop_hash,
                "pre_restore_target_compose_project": pre_restore_compose_project,
                "pre_restore_target_shop_instance_id_sha256": pre_restore_shop_hash,
                "target_compose_project": values["PF07_COMPOSE_PROJECT"],
                "target_shop_instance_id_sha256": incoming_shop_hash,
                "volume_phases": volume_phases,
                "active_container": None,
                "started_at_utc": _utc_now(),
                "updated_at_utc": _utc_now(),
            },
        )
        with _operation_lock():
            try:
                _set_operation("restore-quiesce", "복원 전에 기존 패키지 writer를 중지하는 중입니다.")
                if current_values:
                    _compose(current_values, ["down", "--remove-orphans"], timeout=300)
                    if _running_project_containers(current_values):
                        raise LauncherError("The current PF07 project still has running containers after shutdown.")
                _compose_with_backup_env(
                    values,
                    restored_runtime,
                    restored_connected if restored_connected.is_file() else None,
                    ["down", "--remove-orphans"],
                )
                if _running_project_containers(values):
                    raise LauncherError("The restored PF07 project still has running containers after shutdown.")
                for logical, volume in volume_map.items():
                    transaction_now = _read_restore_transaction()
                    if transaction_now is None:
                        raise LauncherError("The protected restore transaction record disappeared.")
                    phases = dict(transaction_now.get("volume_phases", {}))
                    phases[logical] = "RESTORING"
                    _update_restore_transaction(
                        active_volume=logical,
                        volume_phases=phases,
                    )
                    _restore_volume(volume, extracted / "volumes" / safe_relative_backup_name(str(rows[logical]["archive"])), values)
                    phases[logical] = "RESTORED"
                    _update_restore_transaction(
                        active_volume=None,
                        volume_phases=phases,
                    )
                _write_runtime_env(state_dir() / "runtime.env", values)
                _atomic_json(
                    state_dir() / "config.json",
                    {"schema": "pf07.package-config.v1", "mode": config["mode"], "locale": config["locale"]},
                )
                if restored_connected.is_file():
                    if connected_values is None:
                        raise LauncherError("The authenticated backup connected-mode state is incomplete.")
                    _write_runtime_env(connected_env_path(), connected_values)
                elif connected_env_path().exists():
                    connected_env_path().unlink()
                _update_restore_transaction(
                    state="RESTORED_START_PENDING",
                    active_container=None,
                    active_volume=None,
                )
                _set_operation("restore-materialized", "인증된 백업을 한 패키지 런타임으로 복원했습니다.", "PASS")
            except Exception as error:
                transaction_now = _read_restore_transaction()
                active_container = transaction_now.get("active_container") if transaction_now else None
                if predecessor_path is not None:
                    required_archive = str(predecessor_path)
                    recovery_state = "PREIMAGE_RESTORE_REQUIRED"
                    recovery = (
                        "After the exact transient restore container is stopped, return to the pre-restore "
                        f"state with Restore backup, {predecessor_path}, and RESTORE PF07."
                    )
                else:
                    required_archive = str(archive_path)
                    recovery_state = "RETRY_RESTORE_REQUIRED"
                    recovery = (
                        "After the exact transient restore container is stopped, retry this same authenticated "
                        f"backup: {archive_path}."
                    )
                _update_restore_transaction(
                    state=recovery_state,
                    required_archive_path=required_archive,
                    failed_at_utc=_utc_now(),
                )
                stop_first = (
                    f" Select Recover service first to stop exact container {active_container}."
                    if active_container
                    else ""
                )
                message = f"Restore stopped before a ready runtime.{stop_first} {recovery} Cause: {error}"
                _set_operation("restore-recovery-required", message, "FAIL")
                raise LauncherError(message) from error
    try:
        runtime = start()
    except Exception as error:
        _update_restore_transaction(
            state="RESTORED_SERVICE_RECOVERY_REQUIRED",
            active_container=None,
            failed_at_utc=_utc_now(),
        )
        backup_note = (
            f" The exact pre-restore backup remains at {predecessor_path}."
            if predecessor_path is not None
            else ""
        )
        message = (
            "The authenticated data was restored, but the service did not return to ready state. "
            f"Select Recover service in this hub.{backup_note} Cause: {error}"
        )
        _set_operation("restore-recovery-required", message, "FAIL")
        raise LauncherError(message) from error
    return {
        "schema": "pf07.restore-result.v1",
        "status": "PASS",
        "archive_filename": archive_path.name,
        "archive_sha256": _sha256_file(archive_path),
        "predecessor_backup_filename": predecessor_backup,
        "one_active_runtime": runtime["ready"],
        "runtime": runtime,
    }


def safe_relative_backup_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise LauncherError("The authenticated backup contains an unsafe state path.")
    return path


def safe_relative_backup_name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9_-]+\.tar", value):
        raise LauncherError("The authenticated backup contains an unsafe volume archive name.")
    return value


def uninstall(
    confirmation: str,
    data_choice: str,
    *,
    backup_output: str | None = None,
    backup_passphrase: str | None = None,
) -> dict[str, Any]:
    with _operation_lock():
        return _uninstall_locked(
            confirmation,
            data_choice,
            backup_output=backup_output,
            backup_passphrase=backup_passphrase,
        )


def _uninstall_locked(
    confirmation: str,
    data_choice: str,
    *,
    backup_output: str | None = None,
    backup_passphrase: str | None = None,
) -> dict[str, Any]:
    if confirmation != "UNINSTALL PF07":
        raise LauncherError("Type UNINSTALL PF07 exactly to confirm package-scoped uninstall.")
    if data_choice not in {"preserve", "remove"}:
        raise LauncherError("Uninstall data choice must be preserve or remove.")
    _require_existing_runtime("removing its runtime resources")
    tunnel_stopped = _stop_tunnel_processes()
    if not all(tunnel_stopped.values()):
        raise LauncherError(
            "The HTTPS tunnel could not be fully stopped. Retry Disable tunnel before removing runtime resources."
        )
    backup_result: dict[str, Any] | None = None
    if backup_output or backup_passphrase:
        if not backup_output or not backup_passphrase:
            raise LauncherError("Both an external backup output and passphrase are required to preserve an encrypted backup.")
        backup_result = _backup_locked(backup_output, backup_passphrase)
    values = ensure_runtime()
    _docker_preflight(values)
    volumes = _volume_names(values)
    if data_choice == "remove":
        for logical_name, volume in volumes.items():
            if _owned_volume_labels(volume, values) is not None:
                _require_owned_volume(volume, logical_name, values)
    with _operation_lock():
        try:
            _set_operation("uninstall", "확인된 패키지 소유 런타임만 제거하는 중입니다.")
            arguments = ["down", "--remove-orphans"]
            if data_choice == "remove":
                arguments.append("--volumes")
            _compose(values, arguments, timeout=300)
            if data_choice == "preserve":
                _set_operation("uninstalled", "패키지 소유 런타임 제거가 완료됐습니다.", "PASS")
        except Exception as error:
            _set_operation("error", str(error), "FAIL")
            raise
    if data_choice == "remove":
        for path in sorted(state_dir().iterdir(), reverse=True):
            if path.name == "operation.lock":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    return {
        "schema": "pf07.uninstall-result.v1",
        "status": "PASS",
        "data_choice": data_choice,
        "compose_project": values["PF07_COMPOSE_PROJECT"],
        "package_files_removed": False,
        "package_owned_volumes_removed": data_choice == "remove",
        "package_local_state_removed": data_choice == "remove",
        "encrypted_backup": backup_result,
        "unrelated_resources_touched": False,
    }


def open_target(target: str) -> str:
    current = status()
    if target not in {"store", "admin"}:
        raise LauncherError("Target must be store or admin.")
    if not current["ready"]:
        raise LauncherError("Start the demo before opening its targets.")
    url = str(current["urls"][target])
    if not webbrowser.open(url, new=2):
        raise LauncherError(f"A browser could not be opened automatically. Open this URL: {url}")
    return url
