# nRF52840 BLE SWD Companion

[![CI](https://github.com/bve/gnw-ble-swd/actions/workflows/ci.yml/badge.svg)](https://github.com/bve/gnw-ble-swd/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)

I built this firmware to use an **nRF52840 SuperMini** as a wireless SWD
companion for my Nintendo Game & Watch. It turns BLE commands into SWD
transactions, exposing target memory, core registers, and execution control
over a documented BLE protocol.

This repository contains **only the nRF companion firmware** and the board files,
build scripts, tests, and documentation needed to develop it. It has no retro-go
or GnWManager build dependency and contains no console firmware, games, or host
application. A compatible BLE client is required to control the bridge; use the
[protocol reference](docs/protocol.md) to integrate your own tools.

```mermaid
flowchart LR
    HOST["Your BLE client"] <-->|"Documented BLE protocol"| NRF["nRF52840 companion"]
    NRF <-->|"SWDIO / SWCLK / NRST"| TARGET["Target MCU"]
```

## Features

- SWD memory and core register access, halt, resume, reset, and reset-and-halt.
- CRC-protected 16 KiB blocks, a four-request window, and batched memory writes.
- SWCLK ceiling from 100 kHz to 32 MHz, with SPIM3 EasyDMA for the fast data phase.
- Requested BLE 2M PHY, MTU 247, data length extension, and a 15 ms interval.
- Link and power diagnostics, plus idle power management that keeps BLE available.
- BLE command to enter the existing Adafruit Legacy DFU bootloader.
- Application-only DFU ZIP generation for USB installation and later BLE updates.

I tested the bridge with my **Game & Watch Zelda, STM32H7B0, and 64 MiB
MX25U51245 external flash**. The SWD memory engine is separate from the BLE
transport, but I have not validated other ARM targets. Target-specific
flash algorithms run in the host/target tooling; this firmware supplies SWD
access. It is not a CMSIS-DAP BLE implementation or a GDB server.

## Wiring

I use the SuperMini board shown below, which I modified to run directly from
my Game & Watch's **1.8 V supply**. **No level shifter is needed in my build:**
the nRF GPIO and the target use the same logic voltage.

I made these hardware modifications:

1. I removed the board's power-path MOSFET and the diode next to it.
2. I joined the two marked capacitor terminals with solder to bridge **VDD and VDDH**;
   see the [close-up below](#solder-bridge).
3. I powered the joined VDD/VDDH rail directly from the Game & Watch's 1.8 V
   supply pin and connected a common ground.

![Modified SuperMini: remove the power-path MOSFET and adjacent diode, join VDD and VDDH, power at 1.8 V, and connect SWD directly](docs/images/supermini-1v8-modification.png)

### Solder bridge

I joined these two adjacent capacitor terminals with solder. With USB above
the MCU, they lie along its upper-left edge, on the ends of the capacitors
facing the MCU: **VDD is the upper-right marked terminal;
VDDH is the lower-left one**. Keep both capacitors installed and join only these
two terminals with solder. Leave their opposite terminals untouched.

![Close-up: solder together the two highlighted capacitor terminals labeled VDD and VDDH; the orange line shows the bridge](docs/images/supermini-vdd-vddh-solder-bridge.png)

The orange line shows the physical solder bridge. The overview's supply inset
shows the same connection electrically. [Image notes](docs/images/README.md).

This puts the nRF52840 in Normal Voltage mode. It is a physical board
modification; no firmware or UICR/REGOUT0 change is required for this supply mode.
See the [Nordic power-supply reference](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/power.html)
and [hardware and bootloader setup](docs/hardware.md) for power and USB details.

| Modified SuperMini connection | Game & Watch connection |
| --- | --- |
| Joined VDD / VDDH | 1.8 V supply |
| GND | Common ground |
| P0.06 / D1 | SWDIO, directly |
| P0.08 / D0 | SWCLK, directly |
| P0.20 / D3 | Target NRST, directly; open-drain |
| P0.17 / D2 | Unconnected; no level translator is used |

Arduino labels in this table refer to the pictured board; use the Nordic GPIO
numbers when checking another revision. An unmodified SuperMini running at
3.3 V cannot use these direct SWD connections to a 1.8 V target.

The firmware expects a compatible Adafruit/nice!nano bootloader with **S140 6.1.1** and
Legacy BLE DFU. The application starts at `0x26000`; neither bootloader nor
SoftDevice images are included in the application package.

## Build and install

Use PlatformIO Core, either installed already or through the development
requirements. The following commands use Python 3.10+ and a POSIX shell:

```bash
git clone https://github.com/bve/gnw-ble-swd.git
cd gnw-ble-swd
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/pio run -e supermini
```

On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\pio.exe`.
In the PlatformIO IDE, open this directory and choose the `supermini` environment.
The platform and framework versions are pinned in [platformio.ini](platformio.ini).

After checking bootloader compatibility, install the application through USB:

```bash
.venv/bin/pio run -e supermini -t upload --upload-port /dev/ttyACM0
```

Replace the serial port for your system. Without `-t upload`, PlatformIO only
builds. The running application advertises as **`GW-SWD`**.

Build outputs are in `.pio/build/supermini/`:

| File | Purpose |
| --- | --- |
| `firmware.elf` | Linked application with debug symbols |
| `firmware.hex` | Application image at its linked flash address |
| `bridge-dfu.zip` | Legacy DFU application package for nRF52840 / S140 6.1.1 |

The DFU archive contains the raw application `.bin`, its init packet, and the
package manifest. The build does not emit a separate `firmware.bin` file.

## BLE integration and updates

The service UUID is `67777a10-80f1-4e94-9b4a-1c3059860001`.
Write requests to the RX characteristic ending in `0002` and subscribe to
responses on the TX characteristic ending in `0003`. See
[the protocol reference](docs/protocol.md) for framing, commands, status codes,
and a complete INFO request example.

A compatible client can send the `DFU` command to release SWD/NRST and restart
the nRF into its existing bootloader. Then transfer `bridge-dfu.zip` with an
Adafruit-compatible **Nordic Legacy DFU** client, using Packet Receipt Notification
**8 or lower**. Nordic nRF DFU on a phone is one option. The bootloader may
advertise as `AdaDFU` and use a different address from the application.

This repository does not include a host uploader. The package updates only the
application; it does not install the bootloader or SoftDevice. Secure DFU and
MCUboot use different formats. Single-bank DFU has no automatic rollback and
can require USB recovery after an interrupted update. Test a complete update
and return to `GW-SWD` before enclosing the hardware.

## Development

Native tests require Python and `g++`; they do not need PlatformIO or BLE hardware:

```bash
python3 -m unittest discover -s tests/native -v
```

Tests exercise the production SWD and memory code with simulated peripherals,
including clock edges, parity, posted reads, address boundaries, error handling,
and idle timing. CI runs these tests and builds the firmware and DFU archive.
See [architecture](docs/architecture.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Limitations and license

The BLE service is currently **open, without pairing or authorization**. A nearby
client can control SWD or request DFU. Use it in a trusted radio environment.
The firmware does not automatically unlock protected targets.

Project-owned source and documentation are licensed under **GNU GPL version 3**
(`GPL-3.0-only`); see [LICENSE](LICENSE). The complete companion application source
is provided here. **Nordic SoftDevice remains a precompiled vendor radio stack**,
not open-source code supplied by this project. Other dependencies retain their
own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Game & Watch is a Nintendo trademark. This is an independent community project.
