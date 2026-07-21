from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "launcher"))

from pf07_launcher.core import LauncherError, _decrypt_backup, _encrypt_backup  # noqa: E402


class BackupEnvelopeTest(unittest.TestCase):
    def test_round_trip_and_authentication_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            plaintext = directory / "plain.tar"
            archive = directory / "backup.pf07backup"
            restored = directory / "restored.tar"
            plaintext.write_bytes((b"PF07 protected payload\n" * 4096) + bytes(range(256)))
            header = _encrypt_backup(plaintext, archive, "correct horse battery staple")
            self.assertEqual("HMAC-SHA256-ENCRYPT_THEN_MAC", header["authentication"])
            _decrypt_backup(archive, restored, "correct horse battery staple")
            self.assertEqual(plaintext.read_bytes(), restored.read_bytes())

            with self.assertRaisesRegex(LauncherError, "authentication failed"):
                _decrypt_backup(archive, directory / "wrong.tar", "wrong horse battery staple")

            tampered = bytearray(archive.read_bytes())
            tampered[len(tampered) // 2] ^= 1
            changed = directory / "tampered.pf07backup"
            changed.write_bytes(tampered)
            with self.assertRaisesRegex(LauncherError, "authentication failed"):
                _decrypt_backup(changed, directory / "tampered.tar", "correct horse battery staple")


if __name__ == "__main__":
    unittest.main()
