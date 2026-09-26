# Hardware illustration

Assets:

- [supermini-1v8-modification.png](supermini-1v8-modification.png): modification overview.
- [supermini-vdd-vddh-solder-bridge.png](supermini-vdd-vddh-solder-bridge.png): exact solder points.

The maintainer supplied the original black SuperMini pinout and described the
working modification: remove the power-path MOSFET and adjacent diode, join VDD
and VDDH, and power the nRF from the Game & Watch's 1.8 V rail with common ground.
The maintainer subsequently supplied a close-up marking the two adjacent
capacitor terminals used to join VDD and VDDH with solder.

The annotated illustrations were produced using the built-in `imagegen` tool.
The overview's inset represents the electrical supply connection. The close-up
preserves the maintainer's blue pad markings and adds a short orange bridge
between them: upper-right VDD and lower-left VDDH, both on the MCU-facing ends
of the two adjacent capacitors. These are the solder points on the pictured
revision; check continuity when adapting the modification to another board.

## Overview edit brief

Annotate the supplied SuperMini front/back illustration in English. Mark the
power-path MOSFET and the adjacent diode for removal. Identify the rear VDD and
GND test pads. Show VDD joined to VDDH in a separate electrical inset supplied
from Game & Watch 1.8 V, without inventing a physical VDDH solder point. Include
the direct SWD mapping: P0.06/D1 to SWDIO, P0.08/D0 to SWCLK, P0.20/D3 to NRST
(open-drain), and P0.17/D2 unconnected. State that no level shifter is needed for
this modified board. Omit the unrelated full pinout labels and stock charging
instructions, and keep the removal marks and connection labels clearly readable.

## Solder-bridge close-up edit brief

Preserve the supplied close-up and its original blue arrows and VDD/VDDH labels.
Add only a short orange line between the two blue-marked adjacent capacitor
terminals. Keep component placement unchanged. Add English title and captions
outside the board image: join these two terminals with solder; they face the MCU;
the modified SuperMini uses 1.8 V from Game & Watch without a level shifter.

## References

- [Nordic nRF52840 power supply documentation](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/power.html)
  specifies Normal Voltage mode with VDD and VDDH joined.
- [SuperMini board reverse engineering](https://github.com/sasodoma/nrf52840-promicro)
  provides the matching power-path layout used to check the component locations.
- [Third-party notices](../../THIRD_PARTY_NOTICES.md#hardware-illustration) describe
  the underlying pinout artwork's provenance.
