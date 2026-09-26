# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""Read bridge diagnostics without connecting to or stopping the STM32."""
import asyncio
import struct

from .protocol import Command, BridgeError
from .transport import BleTransport

STAT_FIELDS = ("version", "mtu", "interval_units", "phy", "data_length",
               "read_bytes", "read_us", "write_bytes", "write_us",
               "tx_bytes", "tx_us", "rx_bytes", "rx_us", "tx_busy")
POWER_FIELDS = ("version", "idle_timeout_ms", "negotiated_slave_latency", "idle_entries",
                "last_idle_ms", "total_idle_ms", "worker_wakeups", "advertising_interval_units",
                "usb_enabled", "spim_enabled", "gpio_swdio", "gpio_swclk", "gpio_dir", "gpio_nrst")


def decode_statistics(data, fields=STAT_FIELDS):
    if len(data) != 4 * len(fields):
        raise BridgeError("Unsupported bridge statistics response")
    values = dict(zip(fields, struct.unpack(f"<{len(fields)}I", data)))
    if values["version"] != 1:
        raise BridgeError("Unsupported bridge statistics version")
    return values


async def bridge_status(device, idle_seconds=0):
    if not 0 <= idle_seconds <= 60:
        raise ValueError("Idle observation must be between 0 and 60 seconds")
    transport = BleTransport(device)
    try:
        await transport.open()
        result = {"link": decode_statistics(await transport.request(Command.STATS))}
        result["power"] = decode_statistics(await transport.request(Command.STATS, 2), POWER_FIELDS)
        if idle_seconds:
            await asyncio.sleep(idle_seconds)
            result["after_idle"] = decode_statistics(await transport.request(Command.STATS, 2), POWER_FIELDS)
        return result
    finally:
        await transport.close()
