from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "launcher"))

from pf07_launcher.action_contract import (  # noqa: E402
    ACTION_CONTRACT_VERSION,
    PrerequisiteFacts,
    RuntimeFacts,
    classify_prerequisites,
    classify_runtime,
    recovery_action,
)


class LauncherActionContractTest(unittest.TestCase):
    def test_manifest_and_python_contract_share_version(self) -> None:
        manifest = json.loads((ROOT / "packaging/common/action-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(ACTION_CONTRACT_VERSION, manifest["version"])
        self.assertEqual(1, manifest["runtime_topology"]["business_runtime_count"])
        self.assertFalse(manifest["runtime_topology"]["locale_switch_creates_runtime"])

    def test_prerequisite_branches(self) -> None:
        cases = (
            (PrerequisiteFacts(False, False, False, False), "MISSING_PYTHON"),
            (PrerequisiteFacts(True, False, False, False), "MISSING_RUNTIME"),
            (PrerequisiteFacts(True, True, False, True), "RUNTIME_STOPPED"),
            (PrerequisiteFacts(True, True, True, False), "MISSING_COMPOSE"),
            (PrerequisiteFacts(True, True, True, True), "READY"),
        )
        for facts, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, classify_prerequisites(facts))
                self.assertTrue(recovery_action(expected))

    def test_pkg_005_runtime_branches(self) -> None:
        cases = (
            (RuntimeFacts(False, True, False, False), "FIRST_RUN"),
            (RuntimeFacts(False, False, False, False), "PORT_OCCUPIED"),
            (RuntimeFacts(True, True, False, False), "STOPPED"),
            (RuntimeFacts(True, True, True, False), "FAILED_HEALTH"),
            (RuntimeFacts(True, True, True, True), "ALREADY_RUNNING"),
            (RuntimeFacts(True, True, True, True, True), "RERUN_READY"),
        )
        for facts, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, classify_runtime(facts))
                self.assertTrue(recovery_action(expected))

    def test_reset_demo_wpcli_receives_package_administrator_identity(self) -> None:
        compose = (ROOT / "packaging/common/compose.yaml").read_text(encoding="utf-8")
        wpcli = compose.split("\n  wpcli:\n", 1)[1].split("\n  n8n:\n", 1)[0]
        self.assertIn(
            "PF07_ADMIN_USER: ${PF07_ADMIN_USER:?package-local administrator is required}",
            wpcli,
        )

    def test_linux_server_wrapper_resolves_packaged_root(self) -> None:
        wrapper = (ROOT / "packaging/linux/server/pf07-server").read_text(encoding="utf-8")
        self.assertIn('cd -- "$script_dir/.."', wrapper)
        self.assertNotIn('cd -- "$script_dir/../.."', wrapper)


if __name__ == "__main__":
    unittest.main()
