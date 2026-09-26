# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
import struct
import unittest
from unittest.mock import AsyncMock, call, patch

from tools.ble_swd.diagnostics import bridge_status, decode_statistics
from tools.ble_swd.protocol import BridgeError, Command


class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_observation_never_connects_to_target(self):
        transport = AsyncMock()
        awake = struct.pack("<14I", 1, *([0] * 13))
        after = struct.pack("<14I", 1, 5000, 65, 1, 3000, 3000, 4, 3200, 0, 0, 2, 2, 2, 2)
        transport.request.side_effect = [awake, awake, after]
        with patch("tools.ble_swd.diagnostics.BleTransport", return_value=transport), \
             patch("tools.ble_swd.diagnostics.asyncio.sleep", new_callable=AsyncMock) as sleep:
            result = await bridge_status("bridge", 8)
        self.assertEqual(transport.request.await_args_list,
                         [call(Command.STATS), call(Command.STATS, 2), call(Command.STATS, 2)])
        self.assertEqual(result["after_idle"]["idle_entries"], 1)
        sleep.assert_awaited_once_with(8)
        transport.close.assert_awaited_once()

    async def test_failure_closes_connection(self):
        transport = AsyncMock()
        transport.request.side_effect = BridgeError("disconnected")
        with patch("tools.ble_swd.diagnostics.BleTransport", return_value=transport):
            with self.assertRaises(BridgeError):
                await bridge_status("bridge")
        transport.close.assert_awaited_once()

    async def test_bad_values_are_rejected(self):
        for data in (b"", struct.pack("<14I", 2, *([0] * 13))):
            with self.assertRaises(BridgeError):
                decode_statistics(data)
        for interval in (-1, 61, float("nan")):
            with self.assertRaises(ValueError):
                await bridge_status("bridge", interval)
