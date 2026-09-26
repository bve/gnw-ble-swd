# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
import struct
import unittest
import zlib

from tools.ble_swd.protocol import (
    BLOCK_SIZE, VERSION, RESPONSE, WORD, BridgeError, Command,
    ResponseDecoder, check_range, encode_request,
)


def response(sequence=0, data=b"", status=0):
    frame = RESPONSE.pack(VERSION, status, sequence, len(data)) + data
    return frame + WORD.pack(zlib.crc32(frame))


class ProtocolTests(unittest.TestCase):
    def test_every_fragment_boundary(self):
        frame = response(123, bytes(range(256)))
        for cut in range(len(frame) + 1):
            decoder = ResponseDecoder()
            self.assertEqual(decoder.feed(frame[:cut]) + decoder.feed(frame[cut:]),
                             [(123, 0, bytes(range(256)))])

    def test_coalesced_and_empty_responses(self):
        self.assertEqual(ResponseDecoder().feed(response(0xffff) + response(0, b"abc")),
                         [(0xffff, 0, b""), (0, 0, b"abc")])

    def test_corrupted_payload_is_rejected(self):
        frame = bytearray(response(1, b"data"))
        frame[RESPONSE.size] ^= 1
        with self.assertRaisesRegex(BridgeError, "CRC"):
            ResponseDecoder().feed(frame)

    def test_reject_oversized_header_before_buffering_payload(self):
        with self.assertRaisesRegex(BridgeError, "header"):
            ResponseDecoder().feed(RESPONSE.pack(VERSION, 0, 1, BLOCK_SIZE + 1))

    def test_request_vector(self):
        frame = encode_request(Command.WRITE, 0x1234, 0x24000001, 3, b"abc")
        self.assertEqual(frame[:12], bytes.fromhex("010334120100002403000000"))
        self.assertEqual(zlib.crc32(frame[:-4]), struct.unpack("<I", frame[-4:])[0])
        with self.assertRaises(ValueError):
            encode_request(Command.WRITE, 0, 0, 4, b"abc")

    def test_address_wrap_is_rejected(self):
        check_range(0xfffffffc, 4)
        for address, size in [(0xfffffffc, 5), (-1, 4), (0, -1)]:
            with self.assertRaises(ValueError):
                check_range(address, size)


if __name__ == "__main__":
    unittest.main()
