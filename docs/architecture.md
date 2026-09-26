# Firmware architecture

The application is built on Adafruit's Arduino nRF52 framework and its Bluefruit
BLE API. PlatformIO obtains the framework and toolchain; no retro-go source tree
or host application is required.

| Component | Responsibility |
| --- | --- |
| `src/main.cpp` | BLE service, framed command processing, link negotiation, diagnostics, and DFU entry |
| `src/protocol.h` | Protocol constants, bounds checks, batch validation, and CRC32 |
| `src/response_queue.h` | Two response buffers and asynchronous notification transmission |
| `src/debug_port.h` | Abstract target debug-port interface |
| `src/swd.h`, `src/swd.cpp` | GPIO SWD framing, reset/direction control, and SPIM3 data transfer |
| `src/mem_ap.h`, `src/mem_ap.cpp` | ADIv5 MEM-AP access and Cortex-M execution/register control |
| `src/idle_power.h` | Idle deadlines, peripheral latency policy, and idle accounting |
| `variants/supermini/` | Nordic GPIO mapping and internal low-frequency RC clock selection |
| `boards/supermini_swd.json` | PlatformIO board, SoftDevice, and upload configuration |
| `bridge.ld` | Application memory layout and isolated SPIM3 TX RAM region |
| `scripts/package_dfu.py` | Application-only Legacy DFU package generation |
| `tests/native/` | Host-compiled production-code tests with peripheral stubs |

## Command processing

BLE receive callbacks append data to a stream buffer and wake the command task.
That task validates complete frames and executes requests in order. A separate
response task sends notifications, allowing response transmission to overlap
the next target operation. Connection generations prevent responses from an old
connection from being delivered to a new one.

Receive and notification work blocks on events rather than polling. Invalid
streams, CRC failures, and target failures stop the session; the client must
reconnect. Acknowledgments occur after the target operation, including posted
write draining and sticky-error checks.

## SWD and memory access

Request, ACK, turnaround, and parity bits use GPIO. At settings of at least
1 MHz, the 32-bit data phase uses SPIM3 EasyDMA, LSB first: SPI mode 2 for reads
and mode 0 for writes. GPIO preserves the final clock level when taking control
back from SPI. Lower settings use GPIO throughout. The configured frequency is
a ceiling; framing and handovers reduce the effective rate.

`bridge.ld` reserves an aligned 8 KiB RAM slave below `0x20010000` for the SPIM3
transmit buffer, isolating CPU RAM accesses during DMA as required by Nordic
anomaly 198. The driver also applies the anomaly 195 workaround when disabling
SPIM3 and bounds DMA waits. Do not remove this reservation merely because the
transmit payload is small.

The memory engine selects AP0, performs posted reads with a final RDBUFF read,
and refreshes TAR at each 1 KiB auto-increment boundary. Unaligned edges use
byte transfers. It checks sticky errors and drains writes before acknowledging
completion. Its AP configuration and core-control registers target Cortex-M;
support for a different debug architecture requires an explicit implementation.

## Idle power behavior

Advertising uses 100 ms intervals for the first ten seconds, then two seconds.
After five seconds without traffic, the firmware permits peripheral latency
and releases SWDIO, SWCLK, DIR, and NRST, disabling GPIO input buffers and SPIM3.
At the requested 15 ms connection interval, latency 65 allows roughly one second
between idle radio events if the central accepts it.

New traffic disables latency skipping locally and restores the active SWD port
without resetting the target. The first command after idle can wait for an idle
radio event. The connection LED is disabled, and the framework disables USB when
VBUS is absent. System ON sleep retains BLE availability; System OFF is not used.
Firmware counters do not measure electrical current. Board regulator, LEDs,
power wiring, and the negotiated radio parameters affect actual consumption.

## Validation boundaries

Native tests exercise the actual SWD and memory implementation through simulated
GPIO, SPI, and AP models. They cover framing edges, parity, DMA timeout, pin
release, posted reads, unaligned accesses, TAR boundaries, sticky errors, batch
validation, and idle timing including timer wraparound. CI also compiles the
complete nRF firmware and checks the generated DFU archive.

These checks do not replace radio, voltage, or bootloader validation on hardware.
The source was extracted from a working Zelda/SuperMini integration, but this
repository does not include its host tools, private logs, or console images.
