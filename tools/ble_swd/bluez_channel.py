# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""BlueZ GATT sockets: avoid a D-Bus round trip for each ATT packet."""
import asyncio
import socket
import sys

from .protocol import BridgeError


class BluezChannel:
    def __init__(self, notification, failure):
        self.notification = notification
        self.failure = failure
        self.writer = None
        self.reader = None
        self.max_write_size = 20
        self.loop = asyncio.get_running_loop()

    @classmethod
    async def acquire(cls, client, rx, tx, notification, failure):
        if sys.platform != "linux":
            return None
        from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
        from dbus_fast import Message, MessageType
        backend = getattr(client, "_backend", None)
        if not isinstance(backend, BleakClientBlueZDBus):
            return None
        channel = cls(notification, failure)
        try:
            for characteristic, method, attribute in (
                (rx, "AcquireWrite", "writer"), (tx, "AcquireNotify", "reader"),
            ):
                if characteristic is None:
                    continue
                # Backend-specific objects are confined to this adapter;
                # the application protocol and other platforms use Bleak.
                reply = await backend._bus.call(Message(
                    destination="org.bluez", path=characteristic.obj[0],
                    interface="org.bluez.GattCharacteristic1", member=method,
                    signature="a{sv}", body=[{}]))
                if reply.message_type == MessageType.ERROR:
                    if reply.error_name in ("org.bluez.Error.NotSupported", "org.freedesktop.DBus.Error.UnknownMethod"):
                        channel.close()
                        return None
                    raise BridgeError(f"BlueZ {method}: {reply.error_name}: {reply.body}")
                packet_socket = socket.socket(fileno=reply.unix_fds[reply.body[0]])
                packet_socket.setblocking(False)
                setattr(channel, attribute, packet_socket)
                if attribute == "writer":
                    channel.max_write_size = min(244, reply.body[1] - 3)
            if channel.reader is not None:
                channel.loop.add_reader(channel.reader.fileno(), channel._readable)
            return channel
        except BaseException:
            channel.close()
            raise

    def _readable(self):
        try:
            while True:
                data = self.reader.recv(517)
                if not data:
                    raise BridgeError("BLE notification socket closed")
                self.notification(None, data)
        except BlockingIOError:
            pass
        except OSError as error:
            self.close()
            self.failure(BridgeError(f"BLE packet channel failed: {error}"))

    async def write(self, data):
        # BlueZ returns SOCK_SEQPACKET: each send is one complete ATT value.
        # Kernel backpressure suspends the coroutine without polling/replays.
        await self.loop.sock_sendall(self.writer, data)

    def close(self):
        if self.reader is not None:
            self.loop.remove_reader(self.reader.fileno())
            self.reader.close()
            self.reader = None
        if self.writer is not None:
            self.writer.close()
            self.writer = None
