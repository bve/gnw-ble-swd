# Wiring and bootloader setup

## Target and GPIO numbering

The validated target is a Game & Watch Zelda with STM32H7B0 and MX25U51245
64 MiB flash. Flash access goes through the STM32 and GnWManager's RAM helper;
the companion does not need wires to the console's external flash chip.

GPIO names below are Nordic port/pin numbers. Check the pinout of your exact
SuperMini revision. Its own SWD programming pads are inputs for programming the
nRF52840, not outputs for programming the console.

## A SuperMini with 3.3 V GPIO

Use two SN74AXC1T45 translators, one for bidirectional SWDIO and one for SWCLK.
Measure the target voltage before wiring; Game & Watch logic is approximately
1.8 V. Power the SuperMini from its intended USB/battery supply.

| Connection | Wiring |
| --- | --- |
| P0.06 | SWDIO translator A; translator B to target SWDIO |
| P0.08 | SWCLK translator A; translator B to target SWCLK |
| P0.17 | SWDIO translator DIR; high transmits, low receives |
| P0.20 | Target NRST; firmware uses open-drain without an internal pull-up |
| SuperMini 3.3 V | Both translators' VCCA |
| Console Vtarget | Both translators' VCCB |
| Common GND | Both boards and both translators |

Tie the SWCLK translator's DIR to VCCA. Add a 47–100 kOhm pull-down to the
SWDIO translator's DIR so the target side is an input while the nRF resets.
Decouple each translator supply with 100 nF. See the
[TI SN74AXC1T45 datasheet](https://www.ti.com/lit/ds/symlink/sn74axc1t45.pdf).

Check that NRST is pulled up to Vtarget; add a 10 kOhm pull-up if the target does
not already provide one. The bridge uses Nordic GPIO drive mode `S0D1`: it drives
reset low or releases it. An inverting MOSFET is not part of this wiring.
See the [Nordic GPIO reference](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/gpio.html).

Do not connect the SuperMini's 3.3 V supply to the console's 1.8 V rail or drive
SWDIO/SWCLK directly at 3.3 V. Vtarget supplies only the translators' low-voltage
side. Both boards must be powered while communicating. Keep SWD wires short with
a nearby ground return; BSS138 I2C level-shifter modules are unsuitable here.

## Direct wiring with verified 1.8 V nRF VDD

If the nRF chip's **actual VDD** is compatible with the target voltage, SWDIO and
SWCLK can be connected directly. Connect P0.06 to SWDIO, P0.08 to SWCLK, P0.20 to
NRST, and common ground. P0.17 is unused in this arrangement.

The nRF52840's normal-voltage VDD range is 1.7–3.6 V. In high-voltage mode,
VDDH requires 2.5–5.5 V and REGOUT0 controls VDD. Feeding a clone's BAT pin with
1.8 V does not establish that its GPIO operate correctly at 1.8 V. Verify the
board's power circuit and measure VDD with and without USB connected. Do not
connect two regulator outputs together. If powering the companion from the
console, verify that the rail supports its radio current demand.
See the [Nordic POWER reference](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/power.html).

The bridge does not alter UICR or REGOUT0. Its firmware cannot make arbitrary
SuperMini hardware safe for direct 1.8 V wiring.

## Bootloader requirements

The application expects:

- An Adafruit/nice!nano-compatible nRF52840 bootloader with Legacy BLE DFU.
- Nordic **S140 6.1.1**, firmware ID `0x00B6`.
- Application flash from `0x26000` up to, but not including, `0xED000`.
- A bootloader LFCLK configuration compatible with the board's oscillator hardware.

SuperMini clones ship with different bootloaders. A USB UF2 drive alone does not
prove compatibility. Zephyr/MCUboot and Secure DFU use different application and
update formats.

1. Connect USB and double-tap the SuperMini reset button. If a UF2 drive appears,
   save `INFO_UF2.TXT` and inspect its board, bootloader, and SoftDevice versions.
2. Reuse a compatible installed bootloader. Hardware validation used a
   nice!nano 0.6.0 bootloader with S140 6.1.1.
3. If replacement is necessary, follow the board-specific
   [nice!nano recovery instructions](https://nicekeyboards.com/docs/nice-nano/troubleshooting/)
   and [Adafruit bootloader documentation](https://github.com/adafruit/Adafruit_nRF52_Bootloader).
   Select the correct board and SoftDevice combination. An `_nosd` UF2 does not
   install a missing SoftDevice. Some factory bootloaders require an external SWD
   programmer connected to the nRF for the first installation.
4. Install the application through USB:

   ```bash
   .venv/bin/pio run -e supermini -t upload --upload-port /dev/ttyACM0
   ```

The application uses the internal low-frequency RC oscillator, so it does not
require a populated 32.768 kHz crystal. The bootloader has its own clock setup;
verify that BLE DFU also works on a crystal-less board.

Before enclosing the hardware, complete one full BLE application update and
confirm that `GW-SWD` returns. Keep USB reset/recovery accessible. The build
packages contain the application only and do not install or replace the
bootloader or SoftDevice.
