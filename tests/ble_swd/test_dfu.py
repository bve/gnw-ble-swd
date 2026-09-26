# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
import binascii
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from tools.ble_swd.dfu import (
    APP_START, ApplicationPackage, DFU_CONTROL, DFU_PACKET, DfuError,
    LegacyDfu, bootloader_address, update_bridge,
)


def make_package(size):
    firmware = struct.pack("<II", 0x20040000, APP_START + 9) + bytes(size - 8)
    init = struct.pack("<HHIHHH", 0x52, 0xFFFF, 1, 1, 0xB6,
                       binascii.crc_hqx(firmware, 0xFFFF))
    return ApplicationPackage(firmware, init)


class FakeBootloader:
    """Legacy DFU peer: asynchronous receive completion, no final PRN."""
    def __init__(self, device, disconnected_callback):
        self.disconnect_callback = disconnected_callback
        self.is_connected = False
        self.services = SimpleNamespace(get_characteristic=lambda uuid: uuid)
        self.state = "idle"
        self.writes = []
        self.data = bytearray()
        self.bad_receipt = False
        self.bad_crc = False
        self.drop_link = False
        self.activated = False

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False
        self.disconnect_callback(self)

    async def read_gatt_char(self, _uuid):
        return b"\x08\x00"

    async def start_notify(self, _uuid, callback):
        self.notify = lambda data: callback(None, data)

    async def write_gatt_char(self, uuid, data, response):
        self.writes.append((uuid, bytes(data)))
        assert response == (uuid == DFU_CONTROL)
        if uuid == DFU_CONTROL:
            if data == b"\x01\x04":
                self.state = "size"
            elif data == b"\x02\x00":
                self.state = "init"
            elif data == b"\x02\x01":
                self.notify(b"\x10\x02\x01")
            elif data[0] == 8:
                self.prn = struct.unpack_from("<H", data, 1)[0]
                assert 1 <= self.prn <= 8
            elif data == b"\x03":
                self.state = "firmware"
                self.packets = 0
            elif data == b"\x04":
                good = binascii.crc_hqx(self.data, 0xFFFF) == self.crc and not self.bad_crc
                self.notify(bytes((0x10, 4, 1 if good else 5)))
            elif data == b"\x05":
                self.activated = True
                await self.disconnect()
        else:
            assert uuid == DFU_PACKET and len(data) <= 20
            if self.state == "size":
                sd, bl, self.size = struct.unpack("<III", data)
                assert sd == bl == 0
                self.notify(b"\x10\x01\x01")
            elif self.state == "init":
                self.crc = struct.unpack_from("<H", data, 12)[0]
            elif self.state == "firmware":
                if self.drop_link:
                    await self.disconnect()
                    raise DfuError("disconnected")
                self.data.extend(data)
                self.packets += 1
                if len(self.data) == self.size:
                    self.notify(b"\x10\x03\x01")
                elif self.packets % self.prn == 0:
                    count = len(self.data) - (4 if self.bad_receipt else 0)
                    self.notify(b"\x11" + struct.pack("<I", count))


class DfuTests(unittest.IsolatedAsyncioTestCase):
    async def transfer(self, size, **options):
        peer = FakeBootloader("fake", lambda _: None)
        for key, value in options.items():
            setattr(peer, key, value)
        self.peer = peer

        def factory(device, disconnected_callback):
            peer.disconnect_callback = disconnected_callback
            return peer

        await LegacyDfu("fake", timeout=0.1, client_factory=factory).transfer(make_package(size))

    async def test_final_packet_on_prn_boundary_and_short_tail(self):
        for size in (320, 324):
            with self.subTest(size=size):
                await self.transfer(size)
                self.assertEqual(self.peer.data, make_package(size).firmware)
                self.assertTrue(self.peer.activated)
                self.assertFalse(self.peer.is_connected)

    async def test_wrong_receipt_stops_before_further_data(self):
        with self.assertRaisesRegex(DfuError, "receipt mismatch"):
            await self.transfer(324, bad_receipt=True)
        self.assertEqual(len(self.peer.data), 160)
        self.assertFalse(self.peer.activated)

    async def test_validation_failure_never_activates(self):
        with self.assertRaisesRegex(DfuError, "CRC mismatch"):
            await self.transfer(324, bad_crc=True)
        self.assertFalse(self.peer.activated)

    async def test_disconnect_does_not_retry(self):
        with self.assertRaisesRegex(DfuError, "disconnected"):
            await self.transfer(324, drop_link=True)
        self.assertEqual(self.peer.writes.count((DFU_CONTROL, b"\x01\x04")), 1)
        self.assertFalse(self.peer.activated)

    async def test_initial_connection_retry_does_not_abort_dfu(self):
        class ReconnectingBootloader(FakeBootloader):
            async def connect(self):
                self.disconnect_callback(self)
                await super().connect()

        updater = LegacyDfu("retry", client_factory=ReconnectingBootloader)
        package = make_package(324)
        await updater.transfer(package)
        self.assertEqual(updater.client.data, package.firmware)
        self.assertTrue(updater.client.activated)
        self.assertEqual(updater.client.writes.count((DFU_CONTROL, b"\x01\x04")), 1)

    async def test_invalid_package_never_connects(self):
        with patch("tools.ble_swd.dfu.ApplicationPackage.read", side_effect=ValueError("CRC")), \
             patch("tools.ble_swd.dfu.BleTransport") as transport:
            with self.assertRaises(ValueError):
                await update_bridge("AA:BB:CC:DD:EE:7B", "invalid.zip")
            transport.assert_not_called()


class PackageTests(unittest.TestCase):
    def test_address_increment_does_not_carry(self):
        self.assertEqual(bootloader_address("AA:BB:CC:DD:EE:7B"), "AA:BB:CC:DD:EE:7C")
        self.assertEqual(bootloader_address("AA:BB:CC:DD:EE:FF"), "AA:BB:CC:DD:EE:00")
        with self.assertRaises(ValueError):
            bootloader_address("CoreBluetooth-UUID")

    def test_package_crc_rejects_corrupt_image(self):
        package = make_package(324)
        manifest = {"manifest": {"dfu_version": 0.5, "application": {
            "bin_file": "firmware.bin", "dat_file": "firmware.dat", "init_packet_data": {
                "application_version": 1, "device_revision": 65535, "device_type": 82,
                "firmware_crc16": binascii.crc_hqx(package.firmware, 0xFFFF),
                "softdevice_req": [182]}}}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "image.zip"
            for corrupt in (False, True):
                with zipfile.ZipFile(path, "w") as archive:
                    image = bytearray(package.firmware)
                    if corrupt:
                        image[-1] ^= 1
                    archive.writestr("firmware.bin", image)
                    archive.writestr("firmware.dat", package.init_packet)
                    archive.writestr("manifest.json", json.dumps(manifest))
                if corrupt:
                    with self.assertRaisesRegex(ValueError, "CRC16"):
                        ApplicationPackage.read(path)
                else:
                    self.assertEqual(ApplicationPackage.read(path), package)
