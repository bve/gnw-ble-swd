# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 bve and contributors
"""Repeatable end-to-end RAM benchmark; flash is only read, never written."""
import hashlib
import json
from pathlib import Path
import time

from .backend import BleBackend
from .protocol import Command
from .diagnostics import decode_statistics


def statistics(probe, reset=False):
    data = probe._run(probe.transport.request(Command.STATS, int(reset)))
    return decode_statistics(data)


class Benchmark:
    ADDRESS = 0x240003FD  # Cross word, MEM-AP TAR, and BLE block boundaries.

    def __init__(self, device, *, size=65539, rounds=3):
        if not 4 <= size <= 512 * 1024 or not 1 <= rounds <= 100:
            raise ValueError("Benchmark requires 4..524288 bytes and 1..100 rounds")
        self.device, self.size, self.rounds = device, size, rounds
        self.results = []

    @staticmethod
    def measure(probe, operation, byte_count):
        statistics(probe, reset=True)
        started = time.perf_counter()
        result = operation()
        probe.flush()
        elapsed = time.perf_counter() - started
        stats = statistics(probe)
        return result, dict(seconds=elapsed, kib_s=byte_count / elapsed / 1024, bridge=stats)

    def run(self, frequencies, output=None, interval=None):
        probe = BleBackend(self.device, 1000000)
        original = None
        dirty = False
        try:
            probe.open()
            if interval is not None:
                if not 6 <= interval <= 80:
                    raise ValueError("BLE interval must be 6..80 units of 1.25 ms")
                probe._run(probe.transport.request(Command.LINK, interval))
                time.sleep(1)
            original = probe.read_memory(self.ADDRESS, self.size)
            flash = probe.read_memory(0x08000000, 16384)
            print("Link:", json.dumps(statistics(probe)), flush=True)
            print("Host:", "BlueZ packet sockets" if probe.transport.channel else "Bleak GATT",
                  "write limit", probe.transport.channel.max_write_size if probe.transport.channel
                  else probe.transport.rx.max_write_without_response_size, flush=True)
            for frequency in frequencies:
                probe.set_frequency(frequency)
                if probe.read_memory(0x08000000, len(flash)) != flash:
                    raise ValueError(f"Flash read mismatch at {frequency} Hz")
                for round_number in range(self.rounds):
                    seed = f"GW-SWD {frequency} {round_number}".encode()
                    pattern = hashlib.shake_256(seed).digest(self.size)
                    dirty = True
                    _, write = self.measure(probe, lambda: probe.write_memory(self.ADDRESS, pattern), self.size)
                    actual, read = self.measure(probe, lambda: probe.read_memory(self.ADDRESS, self.size), self.size)
                    if actual != pattern:
                        raise ValueError(f"RAM mismatch at {frequency} Hz, round {round_number + 1}")
                    row = dict(frequency=frequency, round=round_number + 1, size=self.size,
                               requested_interval=interval,
                               sha256=hashlib.sha256(actual).hexdigest(), write=write, read=read)
                    self.results.append(row)
                    if output:
                        Path(output).write_text(json.dumps(self.results, indent=2) + "\n")
                    print(f"{frequency / 1e6:g} MHz #{round_number + 1}: "
                          f"write {write['kib_s']:.1f}, read {read['kib_s']:.1f} KiB/s; SHA256 OK", flush=True)
        finally:
            if probe.loop is not None:
                try:
                    if probe.transport.failure is not None:
                        # Reconnect at the conservative rate for cleanup only.
                        # An uncertain benchmark write is never replayed.
                        probe.close()
                        probe = BleBackend(self.device, 1000000)
                        probe.open()
                    else:
                        probe.set_frequency(1000000)
                    if original is not None and dirty:
                        probe.write_memory(self.ADDRESS, original)
                        if probe.read_memory(self.ADDRESS, self.size) != original:
                            raise ValueError("Benchmark RAM restoration failed")
                    probe.reset()
                    print("Original RAM restored; target reset to installed firmware", flush=True)
                finally:
                    probe.close()
        return self.results
