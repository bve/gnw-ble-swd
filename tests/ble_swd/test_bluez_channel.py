# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
import asyncio
import socket
import sys
import unittest

from tools.ble_swd.bluez_channel import BluezChannel


@unittest.skipUnless(sys.platform == "linux", "BlueZ packet sockets require Linux")
class PacketChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_packet_boundaries_and_disconnect(self):
        incoming, outgoing, failures = [], [], []
        channel = BluezChannel(lambda _char, data: incoming.append(data), failures.append)
        channel.writer, peer_rx = socket.socketpair(type=socket.SOCK_SEQPACKET)
        channel.reader, peer_tx = socket.socketpair(type=socket.SOCK_SEQPACKET)
        for item in (channel.writer, channel.reader, peer_rx, peer_tx):
            item.setblocking(False)
        channel.loop.add_reader(channel.reader.fileno(), channel._readable)
        try:
            for data in (b"header", bytes(range(244)), b"tail"):
                await channel.write(data)
                outgoing.append(await channel.loop.sock_recv(peer_rx, 517))
                await channel.loop.sock_sendall(peer_tx, data)
            await asyncio.sleep(0.01)
            self.assertEqual(incoming, outgoing)
            self.assertEqual([len(data) for data in incoming], [6, 244, 4])
            peer_tx.close()
            await asyncio.sleep(0.01)
            self.assertEqual(len(failures), 1)
            self.assertIsNone(channel.reader)
            self.assertIsNone(channel.writer)
        finally:
            channel.close()
            peer_rx.close()
            peer_tx.close()
