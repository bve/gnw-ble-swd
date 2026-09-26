# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
import asyncio
import struct
import unittest

from tools.ble_swd.backend import BleBackend
from tools.ble_swd.protocol import CAP_BATCH_WRITE, Command, BridgeError


class FakeTransport:
    def __init__(self):
        self.capabilities = CAP_BATCH_WRITE
        self.calls = []
        self.fail = False

    async def request(self, command, address=0, size=0, payload=b""):
        self.calls.append((command, address, size, payload))
        if self.fail:
            raise BridgeError("uncertain write")
        return b""

    async def memory(self, addr, *, data=None, size=None):
        self.calls.append(("memory", addr, data, size))
        return bytes(size or 0)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.probe = BleBackend("fake")
        self.probe.transport = FakeTransport()
        self.probe._run = asyncio.run

    def test_batch_preserves_order_and_flushes_before_read(self):
        self.probe.write_memory(0x24000008, b"ABCD")
        self.probe.write_memory(0x24000000, b"data")
        self.assertEqual(self.probe.transport.calls, [])
        self.probe.read_memory(0x24000000, 4)
        batch, read = self.probe.transport.calls
        self.assertEqual(batch, (Command.BATCH_WRITE, 0, 24,
            struct.pack("<II", 0x24000008, 4) + b"ABCD" +
            struct.pack("<II", 0x24000000, 4) + b"data"))
        self.assertEqual(read[0], "memory")

    def test_peripheral_access_is_not_deferred(self):
        self.probe.write_memory(0x24000000, b"data")
        self.probe.write_memory(0xE000EDF0, b"regs")
        self.assertEqual([call[0] for call in self.probe.transport.calls], [Command.BATCH_WRITE, "memory"])
        self.assertFalse(self.probe.pending_writes)

    def test_error_does_not_replay_batch(self):
        self.probe.write_memory(0x24000000, b"data")
        self.probe.transport.fail = True
        with self.assertRaises(BridgeError):
            self.probe.flush()
        self.probe.flush()
        self.assertEqual(len(self.probe.transport.calls), 1)

    def test_legacy_firmware_and_control_barrier(self):
        self.probe.transport.capabilities = 0
        self.probe.write_memory(0x24000000, b"data")
        self.assertEqual(self.probe.transport.calls[0][0], "memory")
        self.probe.transport.capabilities = CAP_BATCH_WRITE
        self.probe.write_memory(0x24000000, b"data")
        self.probe.resume()
        self.assertEqual([call[0] for call in self.probe.transport.calls[-2:]], [Command.BATCH_WRITE, Command.RESUME])
