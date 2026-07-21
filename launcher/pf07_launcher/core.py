from __future__ import annotations

import json
import hashlib
import hmac
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
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Any, Iterator

from .action_contract import PrerequisiteFacts, RuntimeFacts, classify_prerequisites, classify_runtime, recovery_action


ADMIN_USER = "pf07-operator"
ADMIN_EMAIL = "pf07-admin@example.com"
DEFAULT_WORDPRESS_PORT = 19081
STATE_DIR_NAME = ".pf07"
UPDATE_FENCE_NAME = "UPDATE-FENCE.json"
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
WORDPRESS_IMAGE_REFERENCE = "wordpress@sha256:d40b86dbdfcfad808a2029acf6543c670c4a61c29f70b9d24605e7d0b31ab83d"
TASK_RUNNER_IMAGE_REFERENCE = "pf07-task-runners:2.25.7-json-bigint-1.0.0-pf07v1"
TASK_RUNNER_IMAGE_CONTRACT = "n8n-2.25.7-json-bigint-1.0.0-pf07v1"
BACKUP_MAGIC = b"PF07-AUTHENTICATED-BACKUP-V1\n"
BACKUP_KDF_ITERATIONS = 600_000


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, mode)
    os.replace(temp, path)


def _set_operation(phase: str, message: str, result: str = "IN_PROGRESS") -> None:
    _atomic_json(
        state_dir() / "operation.json",
        {"phase": phase, "message": message, "result": result, "updated_at_utc": _utc_now()},
    )


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


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
    for port in range(DEFAULT_WORDPRESS_PORT, DEFAULT_WORDPRESS_PORT + 100):
        if _port_available(port):
            return port
    raise LauncherError("No free loopback port was found for the local store.")


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
                "oddroom-orderops-connected-v1" if selected_mode() == "CONNECTED_MODE" else "oddroom-orderops-demo-v1"
            )
            migrated = True
        for key in ("PF07_HUBSPOT_CONFIGURED", "PF07_SLACK_CONFIGURED"):
            if key not in values:
                values[key] = "false"
                migrated = True
        if migrated:
            _write_runtime_env(env_path, values)
        missing = sorted(REQUIRED_ENV_KEYS - values.keys())
        if missing:
            raise LauncherError("Package-local runtime material is incomplete: " + ", ".join(missing))
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
        "PF07_SLACK_CONFIGURED": "false",
        "PF07_WORDPRESS_PORT": str(port),
    }
    _write_runtime_env(env_path, values)
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
    expected = "oddroom-orderops-connected-v1" if selected_mode() == "CONNECTED_MODE" else "oddroom-orderops-demo-v1"
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
        "hubspot_alias": values.get("HUBSPOT_CREDENTIAL_ALIAS", "PF07HubSpotRuntime1"),
        "slack_alias": values.get("SLACK_CREDENTIAL_ALIAS", "PF07SlackRuntime1"),
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


def _connection_json(url: str, token: str, label: str, *, method: str = "GET") -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=b"" if method == "POST" else None,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "PF07-Package-Launcher/1.0",
        },
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
    return {
        "hubspot": {"status": "PASS", "http_status": hubspot_status, "pipeline_and_stage": "MATCH"},
        "slack": {"status": "PASS", "http_status": slack_status, "authentication": "PASS"},
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
        )
    except FileNotFoundError as error:
        raise LauncherError(f"Required executable is unavailable: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise LauncherError(f"Command timed out after {timeout} seconds: {command[0]}") from error
    if check and result.returncode != 0:
        detail = _redact(result.stdout or "", values).strip()
        raise LauncherError(f"Command failed ({result.returncode}).\n{detail}")
    return result


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
    return _run(command, values, check=check, timeout=timeout)


def _wp(values: dict[str, str], arguments: list[str], *, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return _compose(
        values,
        ["--profile", "tools", "run", "--rm", "-T", "wpcli", *arguments],
        check=check,
        timeout=timeout,
    )


def _url_ready(url: str, timeout: float = 3.0) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "PF07-Package-Launcher/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def _wait_for_url(url: str, seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _url_ready(url):
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
def _operation_lock() -> Iterator[None]:
    lock_path = state_dir() / "operation.lock"
    descriptor: int | None = None
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(descriptor, f"{os.getpid()}\n{_utc_now()}\n".encode("ascii"))
    except FileExistsError as error:
        raise LauncherError("Another PF07 start or stop operation is already running.") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def start() -> dict[str, Any]:
    # A missing or stopped runtime must not create package identity or secrets.
    _docker_preflight({})
    package_state_existed = (state_dir() / "runtime.env").is_file()
    values = _synchronize_runtime_mode(ensure_runtime())
    with _operation_lock():
        try:
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
                        "--title=OddRoom OrderOps Demo",
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

            _set_operation("storefront", "Quiet Utility 상점과 운영 화면을 준비하는 중입니다.")
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
            _compose(values, ["stop", "worker", "task-runners", "n8n"], check=False, timeout=180)
            _provision_n8n(values)
            _ensure_task_runner_image(values)
            _compose(values, ["up", "-d", "n8n", "task-runners", "worker"], timeout=900)
            _wait_for_n8n(values, 180)

            _set_operation("verify", "상점, 관리자, n8n, 작업자 대상을 확인하는 중입니다.")
            _wait_for_url(values["ODDROOM_PUBLIC_BASE_URL"], 120)
            _wait_for_url(values["ODDROOM_PUBLIC_BASE_URL"] + "/wp-admin/", 120)
            result = status()
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
        if config_path.is_file():
            try:
                candidate = json.loads(config_path.read_text(encoding="utf-8"))
                if candidate.get("mode") in SUPPORTED_MODES and candidate.get("locale") in SUPPORTED_LOCALES:
                    config = {"mode": candidate["mode"], "locale": candidate["locale"]}
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "schema": "pf07.launcher-status.v1",
            "mode": config["mode"],
            "locale": config["locale"],
            "ready": False,
            "runtime_state": "FIRST_RUN",
            "recovery_action": recovery_action("FIRST_RUN"),
            "services": [],
            "store_reachable": False,
            "admin_reachable": False,
            "n8n_reachable": False,
            "worker_running": False,
            "task_runner_running": False,
            "connected_setup": {
                "configured": False,
                "hubspot_alias": "PF07HubSpotRuntime1",
                "slack_alias": "PF07SlackRuntime1",
                "storage": "PACKAGE_PROTECTED_LOCAL",
                "connection_test": "NOT_RUN",
            },
            "urls": {"store": None, "admin": None},
            "admin_user": ADMIN_USER,
            "compose_project": None,
            "tunnel": tunnel_status(),
            "operation": None,
            "checked_at_utc": _utc_now(),
        }
    values = _synchronize_runtime_mode(ensure_runtime())
    services: list[str] = []
    if shutil.which("docker") is not None:
        result = _compose(values, ["ps", "--status", "running", "--services"], check=False, timeout=30)
        if result.returncode == 0:
            services = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    base = values["ODDROOM_PUBLIC_BASE_URL"]
    store_reachable = _url_ready(base)
    admin_reachable = _url_ready(base + "/wp-admin/")
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
    ready = store_reachable \
        and admin_reachable \
        and n8n_reachable \
        and worker_running \
        and task_runner_running \
        and {"db", "wordpress", "n8n", "task-runners", "worker"}.issubset(services)
    runtime_state = classify_runtime(
        RuntimeFacts(
            package_state_exists=package_state_existed,
            requested_port_available=True if services else _port_available(int(values["PF07_WORDPRESS_PORT"])),
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
    current = status()
    if not current["ready"] or selected_mode() != "DEMO_MODE":
        raise LauncherError("Start the ready DEMO_MODE runtime before selecting a delivery scenario.")
    values = ensure_runtime()
    return _command_json(_wp(values, ["oddroom-orderops", "demo-scenario", scenario]))


def reset_demo(confirmation: str) -> dict[str, Any]:
    if confirmation != "RESET PF07 DEMO":
        raise LauncherError("Type RESET PF07 DEMO exactly to confirm the package-scoped reset.")
    current = status()
    if not current["ready"] or selected_mode() != "DEMO_MODE":
        raise LauncherError("Start the ready DEMO_MODE runtime before resetting demo data.")
    values = ensure_runtime()
    return _command_json(
        _wp(values, ["oddroom-orderops", "reset-demo", "--confirm=RESET PF07 DEMO"], timeout=300)
    )


def set_mode(mode: str) -> dict[str, Any]:
    mode = mode.strip().upper()
    if mode not in SUPPORTED_MODES:
        raise LauncherError("Mode must be DEMO_MODE or CONNECTED_MODE.")
    if mode == "CONNECTED_MODE":
        _connected_values(required=True)
    current_config = ensure_config()
    _atomic_json(
        state_dir() / "config.json",
        {"schema": "pf07.package-config.v1", "mode": mode, "locale": current_config["locale"]},
    )
    values = ensure_runtime()
    values["ODDROOM_WEBHOOK_PATH"] = (
        "oddroom-orderops-connected-v1" if mode == "CONNECTED_MODE" else "oddroom-orderops-demo-v1"
    )
    _write_runtime_env(state_dir() / "runtime.env", values)
    running = status()["services"]
    if not {"db", "wordpress"}.issubset(running):
        return status()
    with _operation_lock():
        try:
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
        except Exception as error:
            _set_operation("error", str(error), "FAIL")
            raise


def configure_connected(configuration: dict[str, str]) -> dict[str, Any]:
    values = {
        "HUBSPOT_RUNTIME_TOKEN": _validate_token(configuration.get("hubspot_token", ""), "HubSpot token"),
        "HUBSPOT_PIPELINE_ID": _validate_identifier(configuration.get("hubspot_pipeline_id", ""), "HubSpot pipeline"),
        "HUBSPOT_INITIAL_STAGE_ID": _validate_identifier(configuration.get("hubspot_initial_stage_id", ""), "HubSpot initial stage"),
        "HUBSPOT_CREDENTIAL_ALIAS": _validate_identifier(
            configuration.get("hubspot_alias", "PF07HubSpotRuntime1"),
            "HubSpot alias",
            r"[A-Za-z][A-Za-z0-9._-]{2,63}",
        ),
        "SLACK_BOT_TOKEN": _validate_token(configuration.get("slack_token", ""), "Slack token"),
        "SLACK_CHANNEL_ID": _validate_identifier(
            configuration.get("slack_channel_id", ""),
            "Slack channel",
            r"[CG][A-Z0-9]{8,20}",
        ),
        "SLACK_CREDENTIAL_ALIAS": _validate_identifier(
            configuration.get("slack_alias", "PF07SlackRuntime1"),
            "Slack alias",
            r"[A-Za-z][A-Za-z0-9._-]{2,63}",
        ),
    }
    tests = _test_connected_services(values)
    _write_runtime_env(connected_env_path(), values)
    runtime = ensure_runtime()
    runtime["PF07_HUBSPOT_CONFIGURED"] = "true"
    runtime["PF07_SLACK_CONFIGURED"] = "true"
    _write_runtime_env(state_dir() / "runtime.env", runtime)
    runtime_status = set_mode("CONNECTED_MODE")
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
    values = ensure_runtime()
    config = {"schema": "pf07.package-config.v1", "mode": selected_mode(), "locale": locale}
    _atomic_json(state_dir() / "config.json", config)
    current = status()
    if {"db", "wordpress"}.issubset(current["services"]):
        with _operation_lock():
            _set_operation("language", "표시 언어를 같은 데모 런타임에 적용하는 중입니다.")
            _apply_locale(values)
            _wp(values, ["oddroom-orderops", "setup-storefront"])
            _set_operation("ready", "상점과 관리자 화면을 열 수 있습니다.", "PASS")
    return status()


def stop() -> dict[str, Any]:
    values = ensure_runtime()
    tunnel_result = _stop_tunnel_processes()
    with _operation_lock():
        _set_operation("stop", "패키지 컨테이너를 중지하는 중입니다.")
        _compose(values, ["stop"], timeout=180)
        _set_operation("stopped", "데모가 중지됐습니다. 로컬 데이터는 보존됩니다.", "PASS")
    result = status()
    result["tunnel_stopped"] = all(tunnel_result.values())
    return result


def restart() -> dict[str, Any]:
    """Restart the one package-owned stack without changing its identity."""
    values = ensure_runtime()
    with _operation_lock():
        _set_operation("restart", "패키지 런타임을 같은 ID로 다시 시작하는 중입니다.")
        _compose(values, ["stop"], check=False, timeout=180)
    result = start()
    result["recovery_operation"] = "RESTART"
    return result


def recover() -> dict[str, Any]:
    """Reconnect stopped services or reconcile an unhealthy package-owned stack."""
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
    return {
        "schema": "pf07.diagnostics.v1",
        "package_version": "1.0.0",
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
    }


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


def _process_start_ticks(pid: int) -> int | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        return int(fields[21])
    except (OSError, ValueError, IndexError):
        return None


def _process_record(process: subprocess.Popen[bytes], role: str, token: str) -> dict[str, Any]:
    ticks = _process_start_ticks(process.pid)
    if ticks is None:
        raise LauncherError(f"The package-owned {role} process did not remain active.")
    return {"pid": process.pid, "start_ticks": ticks, "role": role, "command_token": token}


def _process_matches(record: dict[str, Any]) -> bool:
    try:
        pid = int(record["pid"])
        ticks = int(record["start_ticks"])
        token = str(record["command_token"])
    except (KeyError, TypeError, ValueError):
        return False
    if _process_start_ticks(pid) != ticks:
        return False
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace")
    except OSError:
        return False
    return bool(token) and token in command


def _terminate_process(record: dict[str, Any]) -> bool:
    if not _process_matches(record):
        return False
    pid = int(record["pid"])
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if not _process_matches(record):
            return True
        time.sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    return not _process_matches(record)


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
            "route_policy_sha256": value.get("route_policy_sha256"),
            "provider_executable": value.get("provider_executable"),
            "credential_storage": (
                "NOT_REQUIRED_FOR_QUICK_TUNNEL"
                if value.get("provider") == "cloudflared"
                else "EXTERNAL_PROVIDER_CONFIG_NOT_COPIED"
            ),
            "recovery_action": "ENABLE_TUNNEL",
        }
    running = all(_process_matches(value.get(name, {})) for name in ("proxy_process", "provider_process"))
    state = "ON" if value.get("state") == "ON" and running else "FAILED"
    public_base = value.get("public_base") if state == "ON" else None
    return {
        "schema": "pf07.tunnel-status.v1",
        "state": state,
        "provider": value.get("provider", "ngrok"),
        "public_base": public_base,
        "store_url": public_base + "/" if public_base else None,
        "admin_url": public_base + "/wp-admin/" if public_base else None,
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
    provider = _terminate_process(value.get("provider_process", {})) or not _process_matches(
        value.get("provider_process", {})
    )
    proxy = _terminate_process(value.get("proxy_process", {})) or not _process_matches(value.get("proxy_process", {}))
    value.update({"state": "OFF", "stopped_at_utc": _utc_now()})
    _atomic_json(path, value)
    return {"provider_stopped": provider, "proxy_stopped": proxy}


def tunnel_on(
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
    _stop_tunnel_processes()
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
    provider_handle = provider_log.open("wb", buffering=0)
    proxy_process: subprocess.Popen[bytes] | None = None
    provider_process: subprocess.Popen[bytes] | None = None
    runtime_values = ensure_runtime()
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
            env={**os.environ, "PYTHONPATH": str(package_root() / "launcher")},
            stdin=subprocess.DEVNULL,
            stdout=proxy_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
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
        provider_process = subprocess.Popen(
            command,
            cwd=package_root(),
            stdin=subprocess.DEVNULL,
            stdout=provider_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        public_base: str | None = None
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
        _atomic_json(
            public_base_file,
            {"public_base": public_base, "local_base": str(local["urls"]["store"]).rstrip("/")},
        )
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
        value = {
            "schema": "pf07.tunnel-runtime.v1",
            "state": "ON",
            "provider": provider,
            "public_base": public_base,
            "local_base": str(local["urls"]["store"]).rstrip("/"),
            "route_policy_sha256": _sha256_file(route_policy),
            "provider_executable": provider_identity,
            "credential_source": (
                "EXTERNAL_PROVIDER_CONFIG_NOT_COPIED" if provider == "ngrok" else "NOT_REQUIRED_FOR_QUICK_TUNNEL"
            ),
            "proxy_process": _process_record(proxy_process, "route-proxy", "pf07_launcher.tunnel_proxy"),
            "provider_process": _process_record(provider_process, provider, f"127.0.0.1:{proxy_port}"),
            "validation": {
                "store_status": home_status,
                "anonymous_admin_status": admin_status,
                "anonymous_admin_denied": admin_denied,
                "internal_endpoint_status": internal_status,
                "internal_endpoint_denied": internal_status == 404,
            },
            "started_at_utc": _utc_now(),
        }
        _atomic_json(_tunnel_state_path(), value)
        return tunnel_status() | {"validation": value["validation"], "local_runtime_survived": status()["ready"]}
    except Exception as error:
        if provider_process is not None and provider_process.poll() is None:
            os.killpg(provider_process.pid, signal.SIGTERM)
        if proxy_process is not None and proxy_process.poll() is None:
            os.killpg(proxy_process.pid, signal.SIGTERM)
        local_survived = status()["ready"]
        safe_error = _redact_provider_failure(str(error), runtime_values, config)
        _atomic_json(
            _tunnel_state_path(),
            {
                "schema": "pf07.tunnel-runtime.v1",
                "state": "FAILED",
                "provider": provider,
                "public_base": None,
                "route_policy_sha256": _sha256_file(route_policy),
                "provider_executable": provider_identity,
                "failure": safe_error,
                "local_runtime_survived": local_survived,
                "recovery_action": "CHECK_PROVIDER_INSTALL_NETWORK_OR_CREDENTIAL_THEN_RETRY",
                "failed_at_utc": _utc_now(),
            },
        )
        raise LauncherError(
            f"HTTPS tunnel failed while local PF07 remained ready={str(local_survived).lower()}. "
            f"Check the provider installation, network, and credential when applicable, then retry. Cause: {safe_error}"
        ) from error
    finally:
        proxy_handle.close()
        provider_handle.close()


def tunnel_off(confirmation: str) -> dict[str, Any]:
    if confirmation != "DISABLE PF07 TUNNEL":
        raise LauncherError("Type DISABLE PF07 TUNNEL exactly to confirm tunnel shutdown.")
    stopped = _stop_tunnel_processes()
    local_ready = status()["ready"]
    return {
        "schema": "pf07.tunnel-stop-result.v1",
        "status": "PASS" if all(stopped.values()) else "PARTIAL",
        "state": "OFF",
        **stopped,
        "local_runtime_ready": local_ready,
        "public_exposure_active": False,
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
        command = [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "openssl",
            "--mount",
            f"type=bind,source={directory},target=/work",
            WORDPRESS_IMAGE_REFERENCE,
            *container_arguments,
        ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
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
        "package_version": "1.0.0",
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
        return []
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _volume_names(values: dict[str, str]) -> dict[str, str]:
    project = values["PF07_COMPOSE_PROJECT"]
    if not re.fullmatch(r"pf07pkg-[a-f0-9]{12}", project):
        raise LauncherError("The package Compose project does not match the protected PF07 naming boundary.")
    return {name: f"{project}_{name}" for name in ("mariadb_data", "wordpress_data", "n8n_data")}


def _archive_volume(volume: str, output: Path, values: dict[str, str]) -> None:
    inspect = _run(["docker", "volume", "inspect", volume], values, check=False, timeout=30)
    if inspect.returncode != 0:
        raise LauncherError(f"The package-owned volume is missing: {volume}")
    command = [
        "docker",
        "run",
        "--rm",
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
    with output.open("xb") as destination:
        result = subprocess.run(command, cwd=package_root(), stdout=destination, stderr=subprocess.PIPE, check=False)
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
    inspect = _run(
        ["docker", "volume", "inspect", "--format", '{{ index .Labels "com.docker.compose.project" }}', volume],
        values,
        check=False,
        timeout=30,
    )
    if inspect.returncode == 0:
        owner = inspect.stdout.strip()
        if owner and owner != values["PF07_COMPOSE_PROJECT"]:
            raise LauncherError(f"Refusing to replace a volume outside the package project: {volume}")
    else:
        _run(["docker", "volume", "create", *labels, volume], values, timeout=30)
    command = [
        "docker",
        "run",
        "--rm",
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
    result = subprocess.run(command, cwd=package_root(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if result.returncode != 0:
        raise LauncherError(f"Could not restore package volume {volume}: {_redact(result.stdout, values)[-1000:]}")


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
    return _run(command, values, check=check, timeout=600)


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
    checked = 0
    for raw_line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            expected, relative = raw_line.split(maxsplit=1)
        except ValueError as error:
            raise LauncherError("The selected package checksum file is malformed.") from error
        relative = relative.lstrip("* ")
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file() or _sha256_file(target) != expected:
            raise LauncherError(f"The selected package failed integrity verification: {relative}")
        checked += 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError("The selected package artifact manifest is unreadable.") from error
    if manifest.get("schema") != "pf07.artifact-manifest.v1":
        raise LauncherError("The selected package artifact manifest is incompatible.")
    if not isinstance(manifest.get("build_id"), str) or not manifest["build_id"].startswith("pf07-build-"):
        raise LauncherError("The selected package build identity is invalid.")
    return {
        "artifact_id": manifest.get("artifact_id"),
        "package_version": manifest.get("package_version"),
        "build_id": manifest["build_id"],
        "artifact_manifest_sha256": _sha256_file(manifest_path),
        "files_verified": checked,
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
        return []
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


def controlled_update(predecessor_name: str, confirmation: str) -> dict[str, Any]:
    """Move one running pre-release state to this exact reviewed package without a second writer."""
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
    if current_identity["package_version"] != predecessor_identity["package_version"]:
        raise LauncherError("This controlled update supports only the reviewed 1.0.0 pre-release lineage.")
    if current_identity["build_id"] == predecessor_identity["build_id"]:
        raise LauncherError("The selected predecessor already has this build identity.")

    predecessor_state = predecessor_root / STATE_DIR_NAME
    predecessor_runtime = predecessor_state / "runtime.env"
    predecessor_connected = predecessor_state / "connected.env"
    if not predecessor_runtime.is_file() or not (predecessor_state / "config.json").is_file():
        raise LauncherError("Start the predecessor package successfully before updating it.")
    if (predecessor_state / UPDATE_FENCE_NAME).exists():
        raise LauncherError("The selected predecessor has already been fenced by an update.")
    if (predecessor_state / "operation.lock").exists() or (predecessor_state / "update.lock").exists():
        raise LauncherError("The predecessor is busy. Let its current operation finish, then retry the update.")
    predecessor_values = _parse_env(predecessor_runtime)
    missing = sorted(REQUIRED_ENV_KEYS - predecessor_values.keys())
    if missing:
        raise LauncherError("The predecessor runtime state is incomplete: " + ", ".join(missing))
    _volume_names(predecessor_values)

    current_state = state_dir()
    if (current_state / "runtime.env").exists():
        raise LauncherError("The successor package already owns runtime state; use a clean extraction for update.")
    if current_state.exists():
        unexpected = sorted(
            path.name for path in current_state.iterdir() if path.name not in {"config.json", "operation.json"}
        )
        if unexpected:
            raise LauncherError("The successor package contains unexpected local state: " + ", ".join(unexpected))

    stage = current_root / f".pf07-update-stage-{uuid.uuid4().hex}"
    successor_preimage = current_root / f".pf07-update-preimage-{uuid.uuid4().hex}"
    lock_path = predecessor_state / "update.lock"
    lock_descriptor: int | None = None
    running_before: list[str] = []
    state_installed = False
    predecessor_resumed = False
    try:
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(lock_descriptor, f"{os.getpid()}\n{_utc_now()}\n".encode("ascii"))
        os.close(lock_descriptor)
        lock_descriptor = None
        shutil.copytree(
            predecessor_state,
            stage,
            ignore=shutil.ignore_patterns("operation.json", "operation.lock", "update.lock", UPDATE_FENCE_NAME, "tunnel"),
        )
        for candidate in stage.rglob("*"):
            if candidate.is_symlink():
                raise LauncherError("The predecessor state contains an unsupported symbolic link.")
        running_before = _running_services_at_root(
            predecessor_root,
            predecessor_values,
            predecessor_runtime,
            predecessor_connected,
        )
        _stop_tunnel_processes(predecessor_state)
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
        if current_state.exists():
            os.replace(current_state, successor_preimage)
        os.replace(stage, current_state)
        state_installed = True
        migration_record = {
            "schema": "pf07.controlled-update-migration.v1",
            "status": "IN_PROGRESS",
            "from_build_id": predecessor_identity["build_id"],
            "to_build_id": current_identity["build_id"],
            "package_version": current_identity["package_version"],
            "migration_id": "controlled-pre-release-content-rebind-v1",
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
        runtime = start()
        current_values = ensure_runtime()
        _wp(current_values, ["option", "update", "oddroom_orderops_package_build_id", current_identity["build_id"]])
        migration_record.update({"status": "PASS", "completed_at_utc": _utc_now()})
        _atomic_json(current_state / "controlled-update.json", migration_record)
        active_counts = {
            service: _project_service_container_count(current_values, service)
            for service in ("wordpress", "n8n", "worker")
        }
        if not runtime["ready"] or active_counts != {"wordpress": 1, "n8n": 1, "worker": 1}:
            raise LauncherError("The successor did not establish exactly one active business runtime.")
        _atomic_json(
            predecessor_state / UPDATE_FENCE_NAME,
            {
                "schema": "pf07.predecessor-update-fence.v1",
                "status": "FENCED",
                "successor_build_id": current_identity["build_id"],
                "successor_artifact_manifest_sha256": current_identity["artifact_manifest_sha256"],
                "created_at_utc": _utc_now(),
                "recovery_action": "USE_SUCCESSOR_PACKAGE",
            },
        )
        if successor_preimage.exists():
            shutil.rmtree(successor_preimage)
        return {
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
            "predecessor_outbound_calls_during_quiescence": 0,
            "active_service_container_counts": active_counts,
            "one_active_runtime": True,
            "predecessor_fenced": True,
            "runtime": runtime,
        }
    except Exception as error:
        try:
            if state_installed and (current_state / "runtime.env").is_file():
                current_values = _parse_env(current_state / "runtime.env")
                _compose(current_values, ["down", "--remove-orphans"], check=False, timeout=300)
            if state_installed and current_state.exists():
                shutil.rmtree(current_state)
            if successor_preimage.exists():
                os.replace(successor_preimage, current_state)
            if running_before:
                resumed = _compose_at_root(
                    predecessor_root,
                    predecessor_values,
                    predecessor_runtime,
                    predecessor_connected if predecessor_connected.is_file() else None,
                    ["up", "-d", *running_before],
                    check=False,
                    timeout=900,
                )
                predecessor_resumed = resumed.returncode == 0
        except Exception:
            predecessor_resumed = False
        raise LauncherError(
            "Controlled update failed; predecessor runtime resumed="
            f"{str(predecessor_resumed).lower()}. Use the predecessor recover action if needed. Cause: {error}"
        ) from error
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        lock_path.unlink(missing_ok=True)
        if stage.exists():
            shutil.rmtree(stage)


def backup(requested: str | None, passphrase: str) -> dict[str, Any]:
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
            try:
                _set_operation("backup-quiesce", "백업 중 외부 쓰기를 막기 위해 패키지 작업자를 중지하는 중입니다.")
                if running_before:
                    _compose(values, ["stop"], timeout=240)
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
                    "package_version": "1.0.0",
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
            finally:
                if running_before:
                    restart_result = _compose(values, ["up", "-d", *running_before], check=False, timeout=900)
                    resumed = restart_result.returncode == 0
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


def _safe_extract_backup(plaintext: Path, destination: Path) -> None:
    with tarfile.open(plaintext, "r") as archive:
        members = archive.getmembers()
        for member in members:
            relative = PurePath(member.name)
            if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                raise LauncherError("The authenticated backup contains an unsafe archive member.")
        archive.extractall(destination, filter="data")


def restore(archive_name: str, passphrase: str, confirmation: str) -> dict[str, Any]:
    if confirmation != "RESTORE PF07":
        raise LauncherError("Type RESTORE PF07 exactly to confirm the package-scoped restore.")
    archive_path = Path(archive_name).expanduser().resolve()
    if not archive_path.is_file() or archive_path.is_relative_to(package_root().resolve()):
        raise LauncherError("Choose an existing authenticated backup outside the extracted package directory.")
    _docker_preflight({})
    _stop_tunnel_processes()
    state_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    predecessor_backup: str | None = None
    with tempfile.TemporaryDirectory(prefix="restore-", dir=state_dir()) as temp_name:
        temp = Path(temp_name)
        plaintext = temp / "backup-content.tar"
        _decrypt_backup(archive_path, plaintext, passphrase)
        extracted = temp / "extracted"
        extracted.mkdir(mode=0o700)
        _safe_extract_backup(plaintext, extracted)
        manifest = json.loads((extracted / "BACKUP-MANIFEST.json").read_text(encoding="utf-8"))
        if manifest.get("schema") != "pf07.package-local-backup.v1" or manifest.get("package_version") != "1.0.0":
            raise LauncherError("The authenticated backup payload is incompatible with PF07 1.0.0.")
        for row in manifest.get("state_files", []):
            target = extracted / safe_relative_backup_path(str(row["path"]))
            if not target.is_file() or _sha256_file(target) != row["sha256"]:
                raise LauncherError("An authenticated backup state file failed content verification.")
        for row in manifest.get("volumes", []):
            target = extracted / "volumes" / safe_relative_backup_name(str(row["archive"]))
            if not target.is_file() or _sha256_file(target) != row["sha256"]:
                raise LauncherError("An authenticated backup volume failed content verification.")
        restored_runtime = extracted / "state/runtime.env"
        restored_config = extracted / "state/config.json"
        if not restored_runtime.is_file() or not restored_config.is_file():
            raise LauncherError("The authenticated backup does not contain the required package state.")
        values = _parse_env(restored_runtime)
        missing = sorted(REQUIRED_ENV_KEYS - values.keys())
        if missing:
            raise LauncherError("The authenticated backup runtime state is incomplete: " + ", ".join(missing))
        _volume_names(values)
        config = json.loads(restored_config.read_text(encoding="utf-8"))
        if config.get("mode") not in SUPPORTED_MODES or config.get("locale") not in SUPPORTED_LOCALES:
            raise LauncherError("The authenticated backup mode or locale is invalid.")
        if (state_dir() / "runtime.env").is_file():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            predecessor_path = archive_path.parent / f"PF07-Pre-Restore-{stamp}.pf07backup"
            predecessor = backup(str(predecessor_path), passphrase)
            predecessor_backup = predecessor["filename"]
        current_values = _parse_env(state_dir() / "runtime.env") if (state_dir() / "runtime.env").is_file() else None
        with _operation_lock():
            _set_operation("restore-quiesce", "복원 전에 기존 패키지 writer를 중지하는 중입니다.")
            if current_values:
                _compose(current_values, ["down", "--remove-orphans"], check=False, timeout=300)
            restored_connected = extracted / "state/connected.env"
            _compose_with_backup_env(values, restored_runtime, restored_connected if restored_connected.is_file() else None, ["down", "--remove-orphans"], check=False)
            volume_map = _volume_names(values)
            rows = {str(row["logical_name"]): row for row in manifest["volumes"]}
            if set(rows) != set(volume_map):
                raise LauncherError("The authenticated backup volume set does not match the PF07 volume schema.")
            for logical, volume in volume_map.items():
                _restore_volume(volume, extracted / "volumes" / safe_relative_backup_name(str(rows[logical]["archive"])), values)
            _write_runtime_env(state_dir() / "runtime.env", values)
            _atomic_json(
                state_dir() / "config.json",
                {"schema": "pf07.package-config.v1", "mode": config["mode"], "locale": config["locale"]},
            )
            if restored_connected.is_file():
                connected_values = _parse_env(restored_connected)
                if CONNECTED_ENV_KEYS - connected_values.keys():
                    raise LauncherError("The authenticated backup connected-mode state is incomplete.")
                _write_runtime_env(connected_env_path(), connected_values)
            elif connected_env_path().exists():
                connected_env_path().unlink()
            _set_operation("restore-materialized", "인증된 백업을 한 패키지 런타임으로 복원했습니다.", "PASS")
    runtime = start()
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
    if confirmation != "UNINSTALL PF07":
        raise LauncherError("Type UNINSTALL PF07 exactly to confirm package-scoped uninstall.")
    if data_choice not in {"preserve", "remove"}:
        raise LauncherError("Uninstall data choice must be preserve or remove.")
    _stop_tunnel_processes()
    backup_result: dict[str, Any] | None = None
    if backup_output or backup_passphrase:
        if not backup_output or not backup_passphrase:
            raise LauncherError("Both an external backup output and passphrase are required to preserve an encrypted backup.")
        backup_result = backup(backup_output, backup_passphrase)
    values = ensure_runtime()
    _docker_preflight(values)
    _volume_names(values)
    with _operation_lock():
        _set_operation("uninstall", "확인된 패키지 소유 런타임만 제거하는 중입니다.")
        arguments = ["down", "--remove-orphans"]
        if data_choice == "remove":
            arguments.append("--volumes")
        _compose(values, arguments, timeout=300)
        _set_operation("uninstalled", "패키지 소유 런타임 제거가 완료됐습니다.", "PASS")
    if data_choice == "remove":
        for path in sorted(state_dir().iterdir(), reverse=True):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        state_dir().rmdir()
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
