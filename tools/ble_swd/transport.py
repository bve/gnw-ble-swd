# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""One asyncio-owned BLE connection with a negotiated acknowledged window."""
import asyncio
from collections import deque

from .protocol import (
    BLOCK_SIZE, WINDOW, RX_UUID, TX_UUID, WORD, Command, BridgeError,
    ResponseDecoder, STATUS_NAMES, check_range, encode_request,
)


class BleTransport:
    def __init__(self, device, timeout=30, client_factory=None):
        self.device = device
        self.timeout = timeout
        self.client_factory = client_factory
        self.client = None
        self.decoder = ResponseDecoder()
        self.pending = {}
        self.sequence = 0
        self.failure = None
        self.rx = None
        self.channel = None
        self.block_size = BLOCK_SIZE
        self.window = WINDOW
        self.capabilities = 0

    def _fail(self, error):
        self.failure = error
        for future in self.pending.values():
            if not future.done():
                future.set_exception(error)

    def _disconnected(self, _client):
        self._fail(BridgeError("BLE disconnected; the operation was not completed"))

    def _notification(self, _characteristic, data):
        try:
            for sequence, status, payload in self.decoder.feed(data):
                future = self.pending.get(sequence)
                if future is None or future.done():
                    raise BridgeError("Unexpected/duplicate response sequence")
                if status:
                    raise BridgeError(STATUS_NAMES.get(status, f"unknown status {status}"))
                future.set_result(payload)
        except BridgeError as error:
            self._fail(error)

    async def open(self):
        if self.client_factory is None:
            from bleak import BleakClient
            self.client_factory = BleakClient
        # Slow standby advertisements need the full discovery/setup timeout,
        # not Bleak's independent 10-second default.
        self.client = self.client_factory(self.device, timeout=self.timeout,
                                          disconnected_callback=self._disconnected)
        try:
            await self.client.connect()
            if not self.client.is_connected:
                raise BridgeError("BLE disconnected during connection setup")
            # BlueZ/Bleak can retry a failed radio connection inside connect(),
            # invoking the disconnect callback for the abandoned attempt.
            # No application request has been sent yet; the new link is valid.
            self.failure = None
            self.rx = self.client.services.get_characteristic(RX_UUID)
            if self.rx is None:
                raise BridgeError("Selected device does not expose the GW-SWD service")
            from .bluez_channel import BluezChannel
            self.channel = await BluezChannel.acquire(
                self.client, self.rx, self.client.services.get_characteristic(TX_UUID),
                self._notification, self._fail)
            if self.channel is None:
                await self.client.start_notify(TX_UUID, self._notification)
            # Some hosts publish the negotiated MTU only after the first events.
            # A smaller MTU still works; always respect the live write limit.
            await asyncio.sleep(0.1)
            info = await self.request(Command.INFO)
            if len(info) < 12 or len(info) % 4:
                raise BridgeError("Invalid bridge capabilities")
            self.block_size = min(WORD.unpack_from(info)[0], BLOCK_SIZE)
            self.window = min(WORD.unpack_from(info, 4)[0], WINDOW)
            self.capabilities = WORD.unpack_from(info, 12)[0] if len(info) >= 16 else 0
            if self.block_size < 4 or self.window < 1:
                raise BridgeError("Invalid bridge block size/window")
        except BaseException as error:
            await self.close()
            if isinstance(error, TimeoutError):
                raise BridgeError(f"BLE connection/setup timed out for {self.device}") from error
            raise

    async def close(self):
        try:
            if self.channel is not None:
                self.channel.close()
                self.channel = None
            if self.client is not None and self.client.is_connected:
                try:
                    await self.client.disconnect()
                except EOFError:
                    # BlueZ may close the D-Bus socket after disconnection but
                    # before returning the Disconnect reply. Only tolerate an
                    # already closed link, never an error during a transfer.
                    if self.client.is_connected:
                        raise
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()  # Consume errors from other pipelined requests.
            self.pending.clear()

    async def _submit(self, command, address=0, size=0, payload=b""):
        if self.failure:
            raise self.failure
        if len(self.pending) >= self.window:
            raise BridgeError("Local request window exceeded")
        sequence = self.sequence
        self.sequence = (self.sequence + 1) & 0xffff
        frame = encode_request(command, sequence, address, size, payload)
        future = asyncio.get_running_loop().create_future()
        self.pending[sequence] = future
        try:
            offset = 0
            while offset < len(frame):
                if self.failure:
                    raise self.failure
                limit = self.channel.max_write_size if self.channel else self.rx.max_write_without_response_size
                count = min(244, limit, len(frame) - offset)
                await asyncio.wait_for(
                    self.channel.write(frame[offset:offset + count]) if self.channel else
                    self.client.write_gatt_char(self.rx, frame[offset:offset + count], response=False),
                    self.timeout,
                )
                offset += count
        except BaseException:
            self.pending.pop(sequence)
            if future.done() and not future.cancelled():
                future.exception()
            else:
                future.cancel()
            self._fail(BridgeError("Request transmission failed; reconnect required"))
            raise
        return sequence

    async def _result(self, sequence):
        try:
            return await asyncio.wait_for(self.pending[sequence], self.timeout)
        except asyncio.TimeoutError as error:
            failure = BridgeError("BLE response timeout; reconnect required (write status unknown)")
            self._fail(failure)
            raise failure from error
        finally:
            self.pending.pop(sequence, None)

    async def request(self, command, address=0, size=0, payload=b""):
        return await self._result(await self._submit(command, address, size, payload))

    async def memory(self, address, *, data=None, size=None):
        writing = data is not None
        size = len(data) if writing else size
        check_range(address, size)
        waiting = deque()
        output = bytearray()
        offset = 0
        while offset < size or waiting:
            while offset < size and len(waiting) < self.window:
                count = min(self.block_size, size - offset)
                sequence = await self._submit(
                    Command.WRITE if writing else Command.READ,
                    address + offset, count, data[offset:offset + count] if writing else b"",
                )
                waiting.append((sequence, 0 if writing else count))
                offset += count
            sequence, expected = waiting.popleft()
            payload = await self._result(sequence)
            if len(payload) != expected:
                failure = BridgeError("Memory response length mismatch")
                self._fail(failure)
                raise failure
            output.extend(payload)
        return bytes(output)
