# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
import asyncio
import struct
import unittest
import zlib
from types import SimpleNamespace
from unittest.mock import patch

from tools.ble_swd.protocol import (
    BLOCK_SIZE, CAP_BATCH_WRITE, REQUEST, RESPONSE, VERSION, WORD, Command, BridgeError,
)
from tools.ble_swd.transport import BleTransport


class FakePeripheral:
    """Consumes byte streams using the firmware wire contract, with delayed ACKs."""
    def __init__(self, device, disconnected_callback, timeout=10):
        self.disconnected_callback = disconnected_callback
        self.timeout = timeout
        self.is_connected = False
        self.rx = SimpleNamespace(max_write_without_response_size=20)
        self.services = SimpleNamespace(get_characteristic=lambda _: self.rx)
        self.incoming = bytearray()
        self.memory = bytearray(3 * BLOCK_SIZE)
        self.received = []
        self.outstanding = 0
        self.max_outstanding = 0
        self.window = 2
        self.capabilities = None
        self.status = 0
        self.silent = False

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False
        self.disconnected_callback(self)

    async def start_notify(self, uuid, callback):
        self.callback = callback

    async def write_gatt_char(self, characteristic, data, response):
        assert not response
        assert len(data) <= self.rx.max_write_without_response_size
        self.incoming.extend(data)
        while len(self.incoming) >= REQUEST.size:
            version, command, sequence, address, size = REQUEST.unpack_from(self.incoming)
            assert version == VERSION
            payload_size = size if command in (Command.WRITE, Command.WRITE_REGISTER) else 0
            end = REQUEST.size + payload_size
            if len(self.incoming) < end + 4:
                break
            assert zlib.crc32(self.incoming[:end]) == WORD.unpack_from(self.incoming, end)[0]
            payload = bytes(self.incoming[REQUEST.size:end])
            del self.incoming[:end + 4]
            if command == Command.INFO:
                reply = struct.pack("<III", BLOCK_SIZE, self.window, 8000000)
                if self.capabilities is not None:
                    reply += WORD.pack(self.capabilities)
            elif command == Command.WRITE:
                self.memory[address:address + size] = payload
                reply = b""
            elif command == Command.READ:
                reply = bytes(self.memory[address:address + size])
            else:
                reply = b""
            self.received.append((command, address, size))
            if not self.silent:
                frame = RESPONSE.pack(VERSION, self.status, sequence, len(reply)) + reply
                frame += WORD.pack(zlib.crc32(frame))
                self.outstanding += 1
                self.max_outstanding = max(self.max_outstanding, self.outstanding)
                asyncio.get_running_loop().call_later(0.001, self.respond, frame)

    def respond(self, frame):
        self.outstanding -= 1
        # Deliberately unrelated to ATT MTU: notification fragmentation can vary.
        for offset in range(0, len(frame), 37):
            self.callback(None, frame[offset:offset + 37])


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = BleTransport("fake", timeout=0.1, client_factory=FakePeripheral)
        await self.transport.open()
        self.device = self.transport.client

    async def asyncTearDown(self):
        await self.transport.close()

    async def test_pipelined_unaligned_roundtrip_with_small_mtu(self):
        data = bytes(range(251)) * 150
        await self.transport.memory(3, data=data)
        actual = await self.transport.memory(3, size=len(data))
        self.assertEqual(actual, data)
        self.assertEqual(self.device.max_outstanding, 2)
        self.assertEqual(len(self.transport.pending), 0)

    async def test_large_mtu_and_sequence_wrap(self):
        self.device.rx.max_write_without_response_size = 244
        self.transport.sequence = 0xffff
        await self.transport.memory(0, data=bytes(2 * BLOCK_SIZE))
        self.assertEqual(self.transport.sequence, 1)

    async def test_four_requests_and_extended_capabilities(self):
        def factory(device, disconnected_callback, timeout):
            peer = FakePeripheral(device, disconnected_callback, timeout)
            peer.window = 4
            peer.capabilities = CAP_BATCH_WRITE
            peer.memory = bytearray(bytes(range(256)) * 320)
            return peer

        transport = BleTransport("extended", client_factory=factory)
        try:
            await transport.open()
            self.assertEqual(transport.window, 4)
            self.assertEqual(transport.capabilities, CAP_BATCH_WRITE)
            data = await transport.memory(0, size=4 * BLOCK_SIZE)
            self.assertEqual(data, transport.client.memory[:len(data)])
            self.assertEqual(transport.client.max_outstanding, 4)
        finally:
            await transport.close()

    async def test_fault_prevents_followup_writes(self):
        self.device.status = 4
        with self.assertRaisesRegex(BridgeError, "FAULT"):
            await self.transport.request(Command.HALT)
        count = len(self.device.received)
        with self.assertRaises(BridgeError):
            await self.transport.memory(0, data=b"danger")
        self.assertEqual(len(self.device.received), count)

    async def test_setup_timeout_uses_configured_deadline_and_closes_link(self):
        class SlowPeripheral(FakePeripheral):
            async def connect(self):
                self.is_connected = True
                raise TimeoutError

        transport = BleTransport("slow", timeout=30, client_factory=SlowPeripheral)
        with self.assertRaisesRegex(BridgeError, "connection/setup timed out for slow"):
            await transport.open()
        self.assertEqual(transport.client.timeout, 30)
        self.assertFalse(transport.client.is_connected)

    async def test_timeout_is_not_silently_retried(self):
        self.device.silent = True
        with self.assertRaisesRegex(BridgeError, "timeout"):
            await self.transport.memory(0, data=b"data")
        self.assertEqual(self.device.received[-1], (Command.WRITE, 0, 4))
        with self.assertRaises(BridgeError):
            await self.transport.request(Command.HALT)

    async def test_disconnect_wakes_waiter(self):
        self.device.silent = True
        task = asyncio.create_task(self.transport.request(Command.HALT))
        await asyncio.sleep(0.01)
        await self.device.disconnect()
        with self.assertRaisesRegex(BridgeError, "disconnected"):
            await task

    async def test_abandoned_radio_connection_does_not_poison_new_link(self):
        class ReconnectingPeripheral(FakePeripheral):
            async def connect(self):
                self.disconnected_callback(self)
                await super().connect()

        transport = BleTransport("retry", client_factory=ReconnectingPeripheral)
        try:
            await transport.open()
            self.assertIsNone(transport.failure)
            await transport.memory(0, data=b"once")
            self.assertEqual(transport.client.memory[:4], b"once")
            self.assertEqual(sum(command == Command.WRITE for command, _, _ in
                                 transport.client.received), 1)
        finally:
            await transport.close()

    async def test_zero_length_does_not_send(self):
        count = len(self.device.received)
        self.assertEqual(await self.transport.memory(1, size=0), b"")
        await self.transport.memory(1, data=b"")
        self.assertEqual(len(self.device.received), count)

    async def test_disconnect_eof_after_link_closed(self):
        async def disconnect():
            self.device.is_connected = False
            raise EOFError

        pending = asyncio.get_running_loop().create_future()
        self.transport.pending[123] = pending
        with patch.object(self.device, "disconnect", disconnect):
            await self.transport.close()
        self.assertTrue(pending.cancelled())
        self.assertFalse(self.transport.pending)

    async def test_disconnect_eof_with_live_link_is_not_hidden(self):
        async def disconnect():
            raise EOFError

        with patch.object(self.device, "disconnect", disconnect):
            with self.assertRaises(EOFError):
                await self.transport.close()


if __name__ == "__main__":
    unittest.main()
