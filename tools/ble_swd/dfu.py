# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""Application-only Nordic Legacy DFU for the nice!nano Adafruit bootloader."""
import asyncio
import binascii
from dataclasses import dataclass
import hashlib
import json
import re
import struct
import time
import zipfile

from .protocol import Command, SERVICE_UUID
from .transport import BleTransport


DFU_SERVICE = "00001530-1212-efde-1523-785feabcd123"
DFU_CONTROL = "00001531-1212-efde-1523-785feabcd123"
DFU_PACKET = "00001532-1212-efde-1523-785feabcd123"
DFU_REVISION = "00001534-1212-efde-1523-785feabcd123"
PACKET_SIZE = 20
PRN = 8  # Adafruit's bootloader has eight packet buffers.
APP_START = 0x26000
APP_END = 0xED000


class DfuError(OSError):
    pass


@dataclass(frozen=True)
class ApplicationPackage:
    firmware: bytes
    init_packet: bytes

    @classmethod
    def read(cls, path):
        """Reject incompatible/corrupt packages before entering the bootloader."""
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))["manifest"]
            if set(manifest) != {"application", "dfu_version"} or manifest["dfu_version"] != 0.5:
                raise ValueError("Expected an application-only Legacy DFU 0.5 package")
            app = manifest["application"]
            if not 8 <= archive.getinfo(app["bin_file"]).file_size <= APP_END - APP_START:
                raise ValueError("Application does not fit the SuperMini flash layout")
            if archive.getinfo(app["dat_file"]).file_size != 14:
                raise ValueError("Expected a 14-byte S140 6.1.1 init packet")
            firmware = archive.read(app["bin_file"])
            init_packet = archive.read(app["dat_file"])
        dev_type, revision, version, count, softdevice, crc = struct.unpack("<HHIHHH", init_packet)
        if (dev_type, revision, count, softdevice) != (0x52, 0xFFFF, 1, 0xB6):
            raise ValueError("Package must target nRF52840 / S140 6.1.1")
        if len(firmware) % 4 or binascii.crc_hqx(firmware, 0xFFFF) != crc:
            raise ValueError("Invalid firmware alignment or CRC16")
        expected = dict(application_version=version, device_revision=revision,
                        device_type=dev_type, firmware_crc16=crc, softdevice_req=[softdevice])
        if app["init_packet_data"] != expected:
            raise ValueError("DFU manifest does not match the init packet")
        sp, reset = struct.unpack_from("<II", firmware)
        if not (0x20000000 < sp <= 0x20040000 and sp % 8 == 0
                and reset & 1 and APP_START <= (reset & ~1) < APP_START + len(firmware)):
            raise ValueError("Application vectors do not match the SuperMini memory layout")
        return cls(firmware, init_packet)

    @property
    def sha256(self):
        return hashlib.sha256(self.firmware).hexdigest()


def bootloader_address(app_address):
    # Adafruit cold OTA increments addr[0], the last displayed MAC byte,
    # without carry. CoreBluetooth UUIDs cannot be derived this way.
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", app_address):
        raise ValueError("For a non-MAC device ID, specify ota --dfu-device explicitly")
    return f"{app_address[:-2]}{(int(app_address[-2:], 16) + 1) & 0xFF:02X}"


class LegacyDfu:
    def __init__(self, device, timeout=30, client_factory=None):
        self.device = device
        self.timeout = timeout
        self.client_factory = client_factory
        self.notifications = asyncio.Queue()
        self.disconnected = asyncio.Event()
        self.client = None
        self.channel = None

    def _notification(self, _characteristic, data):
        self.notifications.put_nowait(bytes(data))

    def _disconnected(self, _client):
        self.disconnected.set()
        self.notifications.put_nowait(DfuError("DFU disconnected before completion"))

    async def _next(self):
        try:
            data = await asyncio.wait_for(self.notifications.get(), self.timeout)
        except asyncio.TimeoutError as error:
            raise DfuError("DFU response timeout; transfer was not retried") from error
        if isinstance(data, Exception):
            raise data
        if len(data) == 3 and data[0] == 0x10 and data[2] != 1:
            names = {2: "invalid state", 3: "not supported", 4: "wrong size",
                     5: "CRC mismatch", 6: "operation failed"}
            raise DfuError(f"DFU opcode {data[1]}: {names.get(data[2], str(data[2]))}")
        return data

    async def _response(self, opcode):
        data = await self._next()
        if data != bytes((0x10, opcode, 1)):
            raise DfuError(f"Unexpected DFU response to {opcode}: {data.hex()}")

    async def _write(self, uuid, data):
        await asyncio.wait_for(
            self.channel.write(data) if self.channel is not None and uuid == DFU_PACKET
            else self.client.write_gatt_char(uuid, data, response=(uuid == DFU_CONTROL)), self.timeout)

    async def transfer(self, package, progress=lambda _done, _total: None):
        """Transfer, validate on the device, then activate. Never replay writes."""
        from bleak import BleakClient, BleakError
        factory = self.client_factory or BleakClient
        self.client = factory(self.device, disconnected_callback=self._disconnected)
        try:
            await self.client.connect()
            if not self.client.is_connected:
                raise DfuError("DFU disconnected during connection setup")
            # Bleak may report an abandoned connection before succeeding.
            # Notifications have not been enabled and no DFU command was sent.
            self.disconnected.clear()
            while not self.notifications.empty():
                self.notifications.get_nowait()
            for uuid in (DFU_CONTROL, DFU_PACKET, DFU_REVISION):
                if self.client.services.get_characteristic(uuid) is None:
                    raise DfuError("Selected device does not expose Legacy DFU")
            revision = await self.client.read_gatt_char(DFU_REVISION)
            if bytes(revision) != b"\x08\x00":
                raise DfuError(f"Unsupported Legacy DFU revision: {bytes(revision).hex()}")
            await self.client.start_notify(DFU_CONTROL, self._notification)
            await self._write(DFU_CONTROL, b"\x01\x04")  # Start application update.
            await self._write(DFU_PACKET, struct.pack("<III", 0, 0, len(package.firmware)))
            await self._response(1)  # Flash erase is complete.
            await self._write(DFU_CONTROL, b"\x02\x00")
            await self._write(DFU_PACKET, package.init_packet)
            await self._write(DFU_CONTROL, b"\x02\x01")
            await self._response(2)
            await self._write(DFU_CONTROL, b"\x08" + struct.pack("<H", PRN))
            await self._write(DFU_CONTROL, b"\x03")
            from .bluez_channel import BluezChannel
            # Acquire only after Init is acknowledged: init data and its
            # control command must share one ordered D-Bus write path.
            self.channel = await BluezChannel.acquire(
                self.client, self.client.services.get_characteristic(DFU_PACKET),
                None, self._notification, self.notifications.put_nowait)
            total = len(package.firmware)
            for index, offset in enumerate(range(0, total, PACKET_SIZE), 1):
                chunk = package.firmware[offset:offset + PACKET_SIZE]
                await self._write(DFU_PACKET, chunk)
                done = offset + len(chunk)
                # The final packet produces Receive success, never a PRN,
                # even if it would otherwise fall on a PRN boundary.
                if done < total and index % PRN == 0:
                    data = await self._next()
                    if data != b"\x11" + struct.pack("<I", done):
                        raise DfuError(f"DFU receipt mismatch at byte {done}: {data.hex()}")
                    progress(done, total)
            await self._response(3)  # Final flash write has completed.
            await self._write(DFU_CONTROL, b"\x04")
            await self._response(4)  # Bootloader has checked the firmware CRC.
            progress(total, total)
            try:
                await self._write(DFU_CONTROL, b"\x05")
            except (BleakError, EOFError, OSError):
                # The reset may beat the ATT reply. Success still requires
                # verification of the restarted application by update_bridge.
                if not self.disconnected.is_set():
                    raise
            await asyncio.wait_for(self.disconnected.wait(), self.timeout)
        finally:
            if self.channel is not None:
                self.channel.close()
                self.channel = None
            if self.client.is_connected:
                try:
                    await self.client.disconnect()
                except EOFError:
                    if self.client.is_connected:
                        raise


async def find_device(address, service):
    from bleak import BleakScanner
    device = await BleakScanner.find_device_by_filter(
        lambda device, advert: device.address.lower() == address.lower()
        and service in advert.service_uuids, timeout=30)
    if device is None:
        raise DfuError(f"BLE device {address} with service {service} not found")
    return device


async def update_bridge(address, path, *, dfu_address=None, resume=False):
    package = ApplicationPackage.read(path)
    dfu_address = dfu_address or bootloader_address(address)
    print(f"Application: {len(package.firmware)} bytes, SHA256 {package.sha256}", flush=True)
    if not resume:
        transport = BleTransport(address)
        try:
            await transport.open()
            await transport.request(Command.DFU)
            print(f"Entering BLE DFU: {dfu_address}", flush=True)
        finally:
            await transport.close()
    device = await find_device(dfu_address, DFU_SERVICE)
    print(f"Bootloader: {device.address} {device.name}", flush=True)
    started = time.monotonic()
    last_percent = -10

    def progress(done, total):
        nonlocal last_percent
        percent = done * 100 // total
        if percent >= last_percent + 10 or done == total:
            print(f"DFU {percent}% ({done}/{total} bytes)", flush=True)
            last_percent = percent

    await LegacyDfu(device).transfer(package, progress)
    elapsed = time.monotonic() - started
    print(f"Bootloader CRC verified, activated in {elapsed:.1f} s", flush=True)
    device = await find_device(address, SERVICE_UUID)
    transport = BleTransport(device)
    try:
        await transport.open()
        info = struct.unpack_from("<III", await transport.request(Command.INFO))
        print(f"OTA verified: GW-SWD {device.address}, INFO block={info[0]} "
              f"window={info[1]} SWCLK={info[2]}", flush=True)
    finally:
        await transport.close()
