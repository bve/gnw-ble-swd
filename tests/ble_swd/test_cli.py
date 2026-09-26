# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""A target-side verification failure must fail the upload command, too."""
import contextlib
import io
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

from gnwmanager.exceptions import DataError


class CliTests(unittest.TestCase):
    def test_hash_failure_returns_failure_and_closes_ble(self):
        root = Path(__file__).resolve().parents[2]
        with patch.object(sys, "path", [str(root / "tools"), *sys.path]):
            main = runpy.run_path(str(root / "tools/gnw_ble.py"))["main"]
            with tempfile.TemporaryDirectory() as temp:
                image = Path(temp) / "firmware.bin"
                image.write_bytes(bytes(4))
                with patch("ble_swd.backend.BleBackend") as backend, \
                     patch("gnwmanager.gnw.GnW.start_gnwmanager", side_effect=DataError("BAD_HASH_FLASH")), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        main(["--device", "fake", "gnw", "--frequency", "2000000",
                              "flash", "bank1", str(image)])
                    self.assertEqual(error.exception.code, 1)
                    backend.assert_called_once_with("fake", 2000000)
                    backend.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
