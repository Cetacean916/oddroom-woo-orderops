from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "launcher"))

from pf07_launcher import core  # noqa: E402
from pf07_launcher.tunnel_proxy import TunnelProxy  # noqa: E402


class PackageStateBoundaryTest(unittest.TestCase):
    def test_package_entrypoints_keep_python_bytecode_out_of_distribution_tree(self) -> None:
        entrypoints = (
            "launcher/bin/pf07",
            "launcher/bin/pf07-hub",
            "packaging/linux/PF07-Launcher",
            "packaging/linux/pf07",
            "packaging/linux/server/pf07-server",
            "packaging/macos/pf07",
            "packaging/macos/PF07 Launcher.app/Contents/MacOS/PF07-OrderOps",
            "packaging/windows/pf07.cmd",
            "packaging/windows/Start-PF07.ps1",
        )
        for relative in entrypoints:
            with self.subTest(entrypoint=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("PYTHONDONTWRITEBYTECODE", text)

        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            shutil.copytree(
                ROOT / "launcher/pf07_launcher",
                root / "launcher/pf07_launcher",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            (root / "launcher/bin").mkdir(parents=True)
            shutil.copy2(ROOT / "launcher/bin/pf07", root / "launcher/bin/pf07")
            result = subprocess.run(
                [str(root / "launcher/bin/pf07"), "--help"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(any(root.rglob("__pycache__")))
            self.assertFalse(any(root.rglob("*.pyc")))

    def test_status_does_not_create_first_run_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            with patch.object(core, "package_root", return_value=root):
                value = core.status()
            self.assertEqual("FIRST_RUN", value["runtime_state"])
            self.assertFalse((root / ".pf07").exists())

    def test_port_failure_does_not_leave_partial_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            with (
                patch.object(core, "package_root", return_value=root),
                patch.object(core, "_select_port", side_effect=core.LauncherError("occupied")),
            ):
                with self.assertRaisesRegex(core.LauncherError, "occupied"):
                    core.ensure_runtime()
            self.assertFalse((root / ".pf07").exists())

    def test_missing_runtime_precedes_identity_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            with (
                patch.object(core, "package_root", return_value=root),
                patch.object(core, "_docker_preflight", side_effect=core.LauncherError("missing runtime")),
            ):
                with self.assertRaisesRegex(core.LauncherError, "missing runtime"):
                    core.start()
            self.assertFalse((root / ".pf07").exists())

    def test_start_reconnects_ready_runtime_without_reprovisioning(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            state = root / ".pf07"
            state.mkdir()
            (state / "runtime.env").write_text("PF07_COMPOSE_PROJECT=pf07-test\n", encoding="utf-8")
            ready_status = {"ready": True, "runtime_state": "ALREADY_RUNNING"}
            with (
                patch.object(core, "package_root", return_value=root),
                patch.object(core, "_docker_preflight") as docker_preflight,
                patch.object(core, "ensure_runtime", return_value={"PF07_COMPOSE_PROJECT": "pf07-test"}),
                patch.object(core, "_synchronize_runtime_mode", side_effect=lambda values: values),
                patch.object(core, "status", side_effect=[dict(ready_status), dict(ready_status)]) as status,
                patch.object(core, "_set_operation") as set_operation,
                patch.object(core, "_prepare_verified_downloads") as prepare_downloads,
                patch.object(core, "_compose") as compose,
            ):
                result = core.start()

            self.assertEqual("RERUN_READY", result["start_disposition"])
            self.assertEqual(2, status.call_count)
            docker_preflight.assert_called_once_with({})
            set_operation.assert_called_once_with(
                "ready", "이미 실행 중인 상점과 관리자 화면에 다시 연결했습니다.", "PASS"
            )
            prepare_downloads.assert_not_called()
            compose.assert_not_called()

    def test_first_run_diagnostics_does_not_create_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            with (
                patch.object(core, "package_root", return_value=root),
                patch.object(
                    core,
                    "preflight",
                    return_value={"container_runtime": {"compose_ready": False}},
                ),
                patch.object(core, "status", return_value={"runtime_state": "FIRST_RUN", "ready": False}),
                patch.object(core, "_manifest_verification", return_value={"status": "PASS"}),
            ):
                value = core.diagnostics()
            self.assertEqual([], value["compose_ps"])
            self.assertFalse((root / ".pf07").exists())

    def test_tunnel_off_state_is_not_reported_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            tunnel = root / ".pf07/tunnel"
            tunnel.mkdir(parents=True)
            (tunnel / "state.json").write_text(
                json.dumps({"state": "OFF", "provider": "cloudflared"}) + "\n",
                encoding="utf-8",
            )
            with patch.object(core, "package_root", return_value=root):
                value = core.tunnel_status()
            self.assertEqual("OFF", value["state"])

    def test_diagnostics_aliases_nested_package_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name).resolve()
            value = {"Labels": f"working_dir={root}", "Mounts": [{"Source": str(root / ".pf07")}]}
            with patch.object(core, "package_root", return_value=root):
                aliased = core._alias_package_paths(value)
            self.assertEqual("working_dir=[PACKAGE_ROOT]", aliased["Labels"])
            self.assertEqual("[PACKAGE_ROOT]/.pf07", aliased["Mounts"][0]["Source"])

    def test_diagnostics_aliases_compose_abbreviated_user_home_mounts(self) -> None:
        abbreviated = str(Path.home().resolve()) + "/t…"
        with tempfile.TemporaryDirectory() as directory_name, patch.object(
            core, "package_root", return_value=Path(directory_name)
        ):
            aliased = core._alias_package_paths({"Mounts": "volume," + abbreviated})
        self.assertEqual("volume,[USER_HOME]/t…", aliased["Mounts"])


class TunnelRoutePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        policy = json.loads((ROOT / "packaging/network/tunnel-route-allowlist.json").read_text(encoding="utf-8"))
        cls.proxy = object.__new__(TunnelProxy)
        cls.proxy.public_routes = tuple(policy["public_routes"])
        cls.proxy.denied_routes = tuple(policy["denied_routes"])

    def test_store_and_protected_admin_routes_are_allowed(self) -> None:
        for path in ("/", "/shop/", "/product/quiet-utility/", "/wp-admin/", "/wp-login.php"):
            with self.subTest(path=path):
                self.assertTrue(self.proxy.route_allowed(path))

    def test_only_storefront_rest_route_is_allowed(self) -> None:
        self.assertTrue(self.proxy.route_allowed("/wp-json/wc/store/v1/products"))
        self.assertFalse(self.proxy.route_allowed("/wp-json/wp/v2/users"))

    def test_internal_and_traversal_routes_are_denied(self) -> None:
        for path in ("/.pf07/runtime.env", "/n8n/", "/metrics", "/wp-content/%2e%2e/.pf07/runtime.env"):
            with self.subTest(path=path):
                self.assertFalse(self.proxy.route_allowed(path))


if __name__ == "__main__":
    unittest.main()
