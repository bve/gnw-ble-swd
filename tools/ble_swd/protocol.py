# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""Versioned, CRC protected framing, independent of BLE packet boundaries."""
from enum import IntEnum
import struct
import zlib

SERVICE_UUID = "67777a10-80f1-4e94-9b4a-1c3059860001"
RX_UUID = "67777a10-80f1-4e94-9b4a-1c3059860002"
TX_UUID = "67777a10-80f1-4e94-9b4a-1c3059860003"
VERSION = 1
BLOCK_SIZE = 16384
WINDOW = 4
REQUEST = struct.Struct("<BBHII")
RESPONSE = struct.Struct("<BBHI")
WORD = struct.Struct("<I")
BATCH_RECORD = struct.Struct("<II")
CAP_BATCH_WRITE = 1


class Command(IntEnum):
    INFO = 0
    CONNECT = 1
    READ = 2
    WRITE = 3
    READ_REGISTER = 4
    WRITE_REGISTER = 5
    HALT = 6
    RESUME = 7
    RESET = 8
    RESET_HALT = 9
    FREQUENCY = 10
    DFU = 11
    STATS = 12
    LINK = 13
    BATCH_WRITE = 14


class BridgeError(IOError):
    """A failed request; reconnect before issuing any further operations."""


def check_range(address, size):
    if not 0 <= address <= 0xffffffff or size < 0 or address + size > 0x100000000:
        raise ValueError("Memory range is outside the 32-bit address space")


def encode_request(command, sequence, address=0, size=0, payload=b""):
    check_range(address, 0)
    if not 0 <= size <= BLOCK_SIZE:
        raise ValueError("Invalid request size")
    expected = size if command in (Command.WRITE, Command.WRITE_REGISTER, Command.BATCH_WRITE) else 0
    if len(payload) != expected:
        raise ValueError("Payload size does not match request")
    frame = REQUEST.pack(VERSION, command, sequence, address, size) + payload
    return frame + WORD.pack(zlib.crc32(frame))


class ResponseDecoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        while len(self.buffer) >= RESPONSE.size:
            version, status, sequence, size = RESPONSE.unpack_from(self.buffer)
            if version != VERSION or size > BLOCK_SIZE:
                raise BridgeError("Invalid response header; reconnect required")
            end = RESPONSE.size + size
            if len(self.buffer) < end + WORD.size:
                break
            if zlib.crc32(self.buffer[:end]) != WORD.unpack_from(self.buffer, end)[0]:
                raise BridgeError("Response CRC mismatch; reconnect required")
            messages.append((sequence, status, bytes(self.buffer[RESPONSE.size:end])))
            del self.buffer[:end + WORD.size]
        return messages


STATUS_NAMES = {
    1: "invalid command", 2: "request CRC mismatch", 3: "SWD WAIT timeout",
    4: "SWD FAULT / missing target", 5: "SWD parity error",
    6: "target timeout", 7: "SWD is not connected",
}
