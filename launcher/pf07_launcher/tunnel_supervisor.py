from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _owner_start_marker(pid: int, identity_kind: str) -> str | None:
    if identity_kind == "linux-proc-start-ticks" and platform.system() == "Linux":
        try:
            stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            closing_parenthesis = stat_text.rfind(")")
            return stat_text[closing_parenthesis + 1 :].split()[19] if closing_parenthesis >= 0 else None
        except (OSError, ValueError, IndexError):
            return None
    if identity_kind == "windows-creation-time" and os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                creation = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel_time = wintypes.FILETIME()
                user_time = wintypes.FILETIME()
                if not kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(creation),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel_time),
                    ctypes.byref(user_time),
                ):
                    return None
                return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
            finally:
                kernel32.CloseHandle(handle)
        except (AttributeError, OSError, ValueError):
            return None
    if identity_kind == "posix-process-start-time" and os.name != "nt":
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "lstart="],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        marker = result.stdout.strip()
        return marker if result.returncode == 0 and marker else None
    return None


def _owner_matches(owner: dict[str, Any]) -> bool:
    try:
        pid = int(owner["pid"])
        identity_kind = str(owner["identity_kind"])
        expected_marker = str(owner["start_marker"])
    except (KeyError, TypeError, ValueError):
        return False
    return _owner_start_marker(pid, identity_kind) == expected_marker


def _terminate_provider(process: subprocess.Popen[bytes] | None) -> bool:
    if process is None or process.poll() is not None:
        return True
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        else:
            process.terminate()
        process.wait(timeout=8)
        return True
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                )
            else:
                process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return False
    return process.poll() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="PF07 gated tunnel-provider supervisor")
    parser.add_argument("--launch-spec", type=Path, required=True)
    parser.add_argument("--control-file", type=Path, required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    args = parser.parse_args()

    spec = _load_json(args.launch_spec)
    if spec.get("schema") != "pf07.tunnel-supervisor-launch.v1":
        raise ValueError("unsupported tunnel supervisor launch specification")
    command = spec.get("command")
    owner = spec.get("owner")
    nonce = spec.get("authorization_nonce")
    working_directory = spec.get("working_directory")
    provider_log = spec.get("provider_log")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
        or not isinstance(owner, dict)
        or not isinstance(nonce, str)
        or len(nonce) < 32
        or not isinstance(working_directory, str)
        or not isinstance(provider_log, str)
    ):
        raise ValueError("incomplete tunnel supervisor launch specification")

    _atomic_json(
        args.status_file,
        {
            "schema": "pf07.tunnel-supervisor-status.v1",
            "phase": "WAITING_FOR_AUTHORIZATION",
            "provider_pid": None,
        },
    )
    provider: subprocess.Popen[bytes] | None = None
    detached = False
    deadline = time.monotonic() + 60
    try:
        while time.monotonic() < deadline:
            if not _owner_matches(owner):
                return 0
            try:
                control = _load_json(args.control_file)
            except (OSError, json.JSONDecodeError, ValueError):
                time.sleep(0.1)
                continue
            phase = control.get("phase")
            if phase == "STOP":
                return 0
            if phase == "AUTHORIZED" and control.get("authorization_nonce") == nonce:
                break
            time.sleep(0.1)
        else:
            return 0

        with Path(provider_log).open("ab", buffering=0) as log_handle:
            provider = subprocess.Popen(
                command,
                cwd=working_directory,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            _atomic_json(
                args.status_file,
                {
                    "schema": "pf07.tunnel-supervisor-status.v1",
                    "phase": "PROVIDER_RUNNING_OWNER_ATTACHED",
                    "provider_pid": provider.pid,
                },
            )
            while provider.poll() is None:
                try:
                    control = _load_json(args.control_file)
                except (OSError, json.JSONDecodeError, ValueError):
                    control = {}
                phase = control.get("phase")
                if phase == "DETACHED" and control.get("authorization_nonce") == nonce:
                    detached = True
                elif phase == "STOP":
                    _terminate_provider(provider)
                    break
                if not detached and not _owner_matches(owner):
                    _terminate_provider(provider)
                    break
                time.sleep(0.2)
    finally:
        provider_stopped = _terminate_provider(provider)
        _atomic_json(
            args.status_file,
            {
                "schema": "pf07.tunnel-supervisor-status.v1",
                "phase": "STOPPED",
                "provider_pid": provider.pid if provider is not None else None,
                "provider_stopped": provider_stopped,
                "owner_detached": detached,
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
