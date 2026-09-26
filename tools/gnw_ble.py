#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""Run existing GnWManager commands through a SuperMini BLE SWD bridge."""
import argparse
import asyncio
import json
import os
import sys

from ble_swd.protocol import SERVICE_UUID, Command


async def scan():
    from bleak import BleakScanner
    devices = await BleakScanner.discover(timeout=5, return_adv=True)
    for device, advert in devices.values():
        if SERVICE_UUID in advert.service_uuids:
            print(f"{device.address}  {advert.local_name or device.name or 'GW-SWD'}")


async def enter_dfu(device):
    from ble_swd.transport import BleTransport
    transport = BleTransport(device)
    try:
        await transport.open()
        await transport.request(Command.DFU)
        print("nRF entering Adafruit BLE DFU. Upload bridge-dfu.zip with Nordic nRF DFU (PRN <= 8).")
    finally:
        await transport.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=os.environ.get("GNW_BLE_DEVICE"), help="BLE address/UUID (or GNW_BLE_DEVICE)")
    parser.add_argument("--frequency", type=int, default=32000000, help="SWCLK ceiling in Hz; default 32000000")
    parser.add_argument("action", choices=("scan", "dfu", "ota", "bench", "status", "gnw"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="GnWManager arguments, including command chains with --")
    args = parser.parse_args(argv)
    if args.action == "scan":
        asyncio.run(scan())
        return
    if args.action == "gnw" and (not args.arguments or args.arguments == ["--help"]):
        from gnwmanager.cli.main import app
        app.help_print([])
        return
    if not args.device:
        parser.error("Specify --device or GNW_BLE_DEVICE (find it with scan)")
    if args.action == "dfu":
        asyncio.run(enter_dfu(args.device))
        return
    if args.action == "status":
        from ble_swd.diagnostics import bridge_status
        status = argparse.ArgumentParser(prog=f"{parser.prog} status", description="Read bridge power/link status without touching the STM32")
        status.add_argument("--idle-seconds", type=float, default=0, help="Observe connected standby for 0..60 seconds")
        options = status.parse_args(args.arguments)
        print(json.dumps(asyncio.run(bridge_status(args.device, options.idle_seconds)), indent=2))
        return
    if args.action == "ota":
        from ble_swd.dfu import update_bridge
        ota = argparse.ArgumentParser(prog=f"{parser.prog} ota", description="Update the nRF application over BLE and verify restart")
        ota.add_argument("package", help="bridge-dfu.zip")
        ota.add_argument("--dfu-device", help="Bootloader address/UUID; default: application MAC + 1 in last byte")
        ota.add_argument("--resume", action="store_true", help="Device is already in DFU: restart the transfer from byte zero")
        update = ota.parse_args(args.arguments)
        asyncio.run(update_bridge(args.device, update.package, dfu_address=update.dfu_device, resume=update.resume))
        return
    if args.action == "bench":
        from ble_swd.benchmark import Benchmark
        bench = argparse.ArgumentParser(prog=f"{parser.prog} bench", description="Verify and measure RAM transfers; flash is only read")
        bench.add_argument("--frequencies", type=int, nargs="+", default=[args.frequency])
        bench.add_argument("--rounds", type=int, default=3)
        bench.add_argument("--size", type=int, default=65539)
        bench.add_argument("--json", help="Save timing and link statistics")
        bench.add_argument("--interval", type=int, help="Request BLE interval in 1.25 ms units (6..80)")
        test = bench.parse_args(args.arguments)
        Benchmark(args.device, size=test.size, rounds=test.rounds).run(test.frequencies, test.json, test.interval)
        return
    from ble_swd.backend import BleBackend
    from gnwmanager.gnw import GnW
    from gnwmanager.cli.main import app, main as gnw_main
    command, bound, _ = app.meta.parse_args(args.arguments, exit_on_error=False)
    if command is not gnw_main:
        command(*bound.args, **bound.kwargs)
        return
    frequency = bound.arguments.get("frequency", args.frequency)
    with BleBackend(args.device, frequency) as backend:
        # Parse GnWManager's own global flags as well as chained commands.
        # Inject the backend through its supported GnW parameter, without
        # monkey-patching the installed package or registry.
        bound.arguments["gnw"] = GnW(backend)
        # Keep GnWManager's nonzero exit status on flash/hash/connection errors.
        # The context manager still closes BLE when GnWManager raises SystemExit.
        bound.arguments["exit_on_error"] = True
        command(*bound.args, **bound.kwargs)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TimeoutError) as error:
        print(f"BLE SWD: {error}", file=sys.stderr)
        sys.exit(1)
