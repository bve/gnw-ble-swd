# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""Synchronous GnWManager API backed by a private BLE asyncio thread."""
import asyncio
import threading

from gnwmanager.ocdbackend import OCDBackend

from .protocol import BATCH_RECORD, BLOCK_SIZE, CAP_BATCH_WRITE, Command, WORD, BridgeError, check_range
from .transport import BleTransport


def register_number(name):
    names = {"sp": 13, "lr": 14, "pc": 15, "xpsr": 16, "msp": 17, "psp": 18}
    if name in names:
        return names[name]
    if name.startswith("r") and name[1:].isdigit() and 0 <= int(name[1:]) <= 15:
        return int(name[1:])
    raise ValueError(f"Unsupported core register: {name}")


class BleBackend(OCDBackend):
    version = (1, 0, 0)

    def __init__(self, device, frequency=32000000):
        self.transport = BleTransport(device)
        self.frequency = frequency
        self.loop = None
        self.thread = None
        self.pending_writes = bytearray()

    @property
    def probe_name(self):
        return f"SuperMini BLE SWD ({self.transport.device})"

    def _run(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def open(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="ble-swd", daemon=True)
        self.thread.start()
        try:
            self._run(self.transport.open())
            self.set_frequency(self.frequency)
            value = self._run(self.transport.request(Command.CONNECT))
            if len(value) != 4:
                raise BridgeError("Missing SWD IDCODE")
        except BaseException:
            self.close()
            raise
        return self

    def close(self):
        if self.loop is not None:
            try:
                try:
                    if self.transport.failure is None:
                        self.flush()
                finally:
                    self.pending_writes.clear()
                    self._run(self.transport.close())
            finally:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.thread.join()
                self.loop.close()
                self.loop = None

    def read_memory(self, addr, size):
        self.flush()
        return self._run(self.transport.memory(addr, size=size))

    def write_memory(self, addr, data):
        data = bytes(data)
        check_range(addr, len(data))
        # GnWManager's small communication-field writes can share one BLE
        # request. Preserve order and flush before every observation/control
        # operation. Peripheral registers are never deferred.
        if (self.transport.capabilities & CAP_BATCH_WRITE and 0 < len(data) <= 256
                and 0x24000000 <= addr and addr + len(data) <= 0x24100000):
            record = BATCH_RECORD.pack(addr, len(data)) + data
            if len(self.pending_writes) + len(record) > BLOCK_SIZE:
                self.flush()
            self.pending_writes.extend(record)
            return
        self.flush()
        self._run(self.transport.memory(addr, data=bytes(data)))

    def flush(self):
        if self.pending_writes:
            payload = bytes(self.pending_writes)
            self.pending_writes.clear()  # Never replay a batch with unknown status.
            self._run(self.transport.request(Command.BATCH_WRITE, size=len(payload), payload=payload))

    def read_register(self, name):
        self.flush()
        value = self._run(self.transport.request(Command.READ_REGISTER, register_number(name)))
        if len(value) != 4:
            raise BridgeError("Invalid register response")
        return WORD.unpack(value)[0]

    def write_register(self, name, val):
        self.flush()
        self._run(self.transport.request(Command.WRITE_REGISTER, register_number(name), 4, WORD.pack(val)))

    def set_frequency(self, freq):
        if not 100000 <= freq <= 32000000:
            raise ValueError("SWD frequency must be in 100000..32000000 Hz")
        self.flush()
        self._run(self.transport.request(Command.FREQUENCY, freq))

    def reset(self):
        self.flush()
        self._run(self.transport.request(Command.RESET))

    def halt(self):
        self.flush()
        self._run(self.transport.request(Command.HALT))

    def reset_and_halt(self):
        self.flush()
        self._run(self.transport.request(Command.RESET_HALT))

    def resume(self):
        self.flush()
        self._run(self.transport.request(Command.RESUME))

    def start_gdbserver(self, port, logging=True, blocking=True):
        raise NotImplementedError("The BLE bridge provides flashing and memory access, not a GDB server")
