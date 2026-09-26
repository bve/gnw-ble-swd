# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""Exercise the production memory engine against a posted ADIv5 AP model."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class NativeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("g++"), "g++ required for native firmware tests")
    def test_memory_engine(self):
        self.run_native("mem_ap")

    @unittest.skipUnless(shutil.which("g++"), "g++ required for native firmware tests")
    def test_swd_clock_edges(self):
        self.run_native("swd")

    @unittest.skipUnless(shutil.which("g++"), "g++ required for native firmware tests")
    def test_idle_power_timing(self):
        self.run_native("idle_power", sources=[])

    def run_native(self, name, sources=None):
        if sources is None:
            sources = [name]
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            output = str(Path(temp) / f"{name}_test")
            subprocess.run([
                "g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                "-I", str(root / "tests/native/stubs"),
                "-I", str(root / "src"),
                str(root / f"tests/native/test_{name}.cpp"),
                *(str(root / f"src/{source}.cpp") for source in sources), "-o", output,
            ], check=True)
            subprocess.run([output], check=True)


if __name__ == "__main__":
    unittest.main()
