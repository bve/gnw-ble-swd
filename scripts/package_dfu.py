# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""Build the same legacy DFU archive for both USB installation and BLE OTA."""
from pathlib import Path
import subprocess

Import("env")


def package(source, target, env):
    directory = Path(env.subst("$BUILD_DIR"))
    tool = Path(env.PioPlatform().get_package_dir("tool-adafruit-nrfutil"))
    subprocess.run(
        [env.subst("$PYTHONEXE"), str(tool / "adafruit-nrfutil.py"), "dfu", "genpkg",
         "--dev-type", "0x0052", "--sd-req", "0x00B6", "--application-version", "1",
         "--application", str(directory / "firmware.hex"), str(directory / "bridge-dfu.zip")],
        check=True,
    )


env.AddPostAction("$BUILD_DIR/${PROGNAME}.hex", package)
