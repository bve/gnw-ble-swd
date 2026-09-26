# Hardware illustrations

Assets:

- [supermini-1v8-modification.png](supermini-1v8-modification.png): modification overview.
- [supermini-vdd-vddh-solder-bridge.png](supermini-vdd-vddh-solder-bridge.png): exact solder points.
- [game-watch-debug-headers.svg](game-watch-debug-headers.svg): five-hole Mario and
  seven-hole Zelda debug headers, viewed from the component side.

I used the black SuperMini pinout to illustrate my working modification:
I removed the power-path MOSFET and adjacent diode, joined VDD and VDDH, and
powered the nRF from my Game & Watch's 1.8 V rail with common ground. I marked
the two adjacent capacitor terminals I joined with solder in a close-up.

I used the built-in `imagegen` tool to prepare the annotated illustrations.
The overview's inset represents the electrical supply connection. The close-up
uses clean VDD and VDDH labels and orange outlines at my solder points, joined
by a short orange bridge: upper-right VDD and lower-left VDDH, both on the
MCU-facing ends of the two adjacent capacitors. These are the solder points on
my board revision; check continuity when adapting the modification to another board.

## Overview edit brief

Annotate my SuperMini front/back reference illustration in English. Mark the
power-path MOSFET and the adjacent diode for removal. Identify the rear VDD and
GND test pads. Show VDD joined to VDDH in a separate electrical inset supplied
from Game & Watch 1.8 V, without inventing a physical VDDH solder point. Include
the direct SWD mapping: P0.06/D1 to SWDIO, P0.08/D0 to SWCLK, P0.20/D3 to NRST
(open-drain), and P0.17/D2 unconnected. State that no level shifter is needed for
this modified board. Omit the unrelated full pinout labels and stock charging
instructions, and keep the removal marks and connection labels clearly readable.

## Solder-bridge close-up edit brief

Preserve the board close-up and the exact two solder points I marked.
Remove all handwritten arrows and labels. Add crisp VDD and VDDH
label boxes with thin leaders to the correct terminals, orange terminal outlines,
and a short thicker orange bridge joining them. Keep component placement and
the bridge location unchanged. Use English title and captions: join these two
highlighted terminals with solder; they face the MCU; the modified SuperMini
uses 1.8 V from Game & Watch without a level shifter.

## Game & Watch header diagram

I drew this vector schematic to show the two header layouts and the five holes
used by the bridge. It is not to scale. The small PCB triangle marks pin 1;
the first five holes are NRST, SWDIO, GND, VDD, and SWCLK on both layouts.
I use VDD at pin 4 as the 1.8 V supply for my modified nRF. The Zelda header's
extra two holes are unused by this project and stay unconnected.

I checked the layout against the board photos and the
[Game & Watch backup connector reference](https://github.com/ghidraninja/game-and-watch-backup#connecting-the-debugger).
The SVG is original artwork for this repository, licensed under GPL-3.0-only.

## References

- [Nordic nRF52840 power supply documentation](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/power.html)
  specifies Normal Voltage mode with VDD and VDDH joined.
- [SuperMini board reverse engineering](https://github.com/sasodoma/nrf52840-promicro)
  provides the matching power-path layout used to check the component locations.
- [Third-party notices](../../THIRD_PARTY_NOTICES.md#hardware-illustration) describe
  the underlying pinout artwork's provenance.
