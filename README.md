# Flash Game & Watch over BLE

[![CI](https://github.com/bve/gnw-ble-swd/actions/workflows/ci.yml/badge.svg)](https://github.com/bve/gnw-ble-swd/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)

## 1. The goal: update retro-go without a USB cable

I built this project so I can flash **retro-go on my Game & Watch over Bluetooth**.
An nRF52840 board stays wired inside the console and receives firmware from my
computer. The Game & Watch powers the nRF, so subsequent console updates need
**no USB connection to either board**.

```text
Computer → Bluetooth LE → nRF52840 → five wires → Game & Watch
```

This repository includes the **nRF firmware and the computer-side BLE client**.
I tested it on Linux with a Game & Watch Zelda, STM32H7B0, and 64 MiB MX25U51245
flash. Start with an already unlocked console prepared for retro-go. Initial
console unlocking is outside this guide.

## 2. Prepare an nRF52840 SuperMini and modify its power supply

You need an **nRF52840 SuperMini**, five thin wires, and a computer with Bluetooth
LE and Python 3.10+. The commands below use a Linux/POSIX shell.

### Install the nRF firmware once

Before modifying the board, install the companion firmware using the SuperMini's
USB port. This is the one-time setup; later Game & Watch updates use BLE.
The board needs a compatible Adafruit/nice!nano bootloader with **S140 6.1.1**;
check [bootloader setup](docs/hardware.md#bootloader-requirements) first.

```bash
git clone https://github.com/bve/gnw-ble-swd.git
cd gnw-ble-swd
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/pio run -e supermini -t upload --upload-port /dev/ttyACM0
```

Replace `/dev/ttyACM0` with the SuperMini's serial port. The installed firmware
advertises as **GW-SWD**. Disconnect power before making the hardware changes.

### Change the supply to 1.8 V

I made three changes to the pictured SuperMini:

1. I removed the power-path MOSFET and the diode next to it.
2. I joined the two marked capacitor terminals with solder, connecting **VDD to VDDH**.
3. I powered that joined rail from the Game & Watch's **1.8 V supply**.

**No level shifter is needed in my build:** the nRF and Game & Watch use the same
1.8 V logic level. These direct connections require the modified power circuit.

<details>
<summary>See the board modifications and exact solder points</summary>

![Remove the power-path MOSFET and adjacent diode; join VDD and VDDH for 1.8 V power](docs/images/supermini-1v8-modification.png)

### Solder bridge

I joined these two adjacent capacitor terminals on the MCU-facing side.
**VDD is the upper-right marked terminal; VDDH is the lower-left one.**
Both capacitors stay installed; leave their opposite terminals untouched.

![The orange line joins the VDD and VDDH capacitor terminals](docs/images/supermini-vdd-vddh-solder-bridge.png)

</details>

See [hardware details](docs/hardware.md) for power isolation and USB recovery.
The joined rail must stay at 1.8 V when connected to the console.

## 3. Solder just five wires to the Game & Watch

| Wire | Game & Watch | Modified SuperMini |
| ---: | --- | --- |
| 1 | 1.8 V supply | VDD, already bridged to VDDH |
| 2 | GND | GND |
| 3 | SWDIO | P0.06 / D1 |
| 4 | SWCLK | P0.08 / D0 |
| 5 | NRST | P0.20 / D3 |

These are the only five connections between the boards. **Leave P0.17 / D2
unconnected.** Use the numbered GPIO pins above, not the nRF's own DIO/CLK debug
pads. NRST goes to the Game & Watch reset signal, not the SuperMini reset pin.

Power on the console. It now powers the nRF, and **GW-SWD** should be discoverable
over Bluetooth. No USB cable is needed for the following steps.

## 4. Flash retro-go through BLE

Run these commands from the `gnw-ble-swd` directory. The setup in step 2 already
installed the BLE client dependencies. If you only need the client on another
computer, create `.venv` and install `requirements.txt` there.

### Find your bridge

```bash
.venv/bin/python tools/gnw_ble.py scan
```

Copy the address shown next to **GW-SWD**, then select it:

```bash
export GNW_BLE_DEVICE='AA:BB:CC:DD:EE:FF'
.venv/bin/python tools/gnw_ble.py status
.venv/bin/python tools/gnw_ble.py --frequency 1000000 gnw info
```

Replace the example address with yours. `status` checks the nRF connection;
`gnw info` connects to and resets/halts the console to load the flash helper.
Check that it identifies your console and flash correctly before continuing.

### Send the two retro-go images

Build retro-go separately for your console, flash size, and memory layout.
Its build produces **gw_retro_go_intflash.bin** and
**gw_retro_go_extflash.bin**. Use the matching pair from the same build.

For the **internal bank 1 / external offset 0** layout I use, run:

```bash
.venv/bin/python tools/gnw_ble.py gnw \
  flash bank1 /path/to/gw_retro_go_intflash.bin -- \
  flash ext /path/to/gw_retro_go_extflash.bin -- \
  start bank1
```

Replace both `/path/to/...` entries with your actual image paths. The client
sends the images over BLE, the nRF programs the console through SWD, and
GnWManager verifies the written data before `start bank1` launches retro-go.
Keep the console powered until the command completes successfully. If your
build uses a different bank or external offset, use its corresponding layout.

For each later update, rebuild retro-go and repeat this command. The nRF stays
installed in the console. If communication is unstable, add `--frequency 1000000`
before `gnw`; the default SWD ceiling is 32 MHz.

<details>
<summary>Optional: update the nRF companion itself over BLE</summary>

With `GNW_BLE_DEVICE` set, build the companion application and upload its DFU package:

```bash
.venv/bin/pio run -e supermini
.venv/bin/python tools/gnw_ble.py ota .pio/build/supermini/bridge-dfu.zip
```

This updates the **nRF application**. The retro-go `.bin` images above update the
**Game & Watch**. The DFU package does not replace the bootloader or SoftDevice;
an interrupted single-bank update can require USB recovery.

</details>

## More information

- [Hardware and bootloader details](docs/hardware.md)
- [BLE protocol](docs/protocol.md) and [architecture](docs/architecture.md)
- [Development and tests](CONTRIBUTING.md)
- Client commands: `.venv/bin/python tools/gnw_ble.py --help`

The BLE service has no pairing or authorization requirement; use it in a trusted
radio environment. Project-owned firmware, client, and documentation are licensed
under [GPL-3.0](LICENSE). Nordic SoftDevice remains an external vendor stack;
see [third-party notices](THIRD_PARTY_NOTICES.md). Game & Watch is a Nintendo
trademark; this is an independent community project.
