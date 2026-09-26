# Hardware illustration

Asset: [supermini-1v8-modification.png](supermini-1v8-modification.png).

The maintainer supplied the original black SuperMini pinout and described the
working modification: remove the power-path MOSFET and adjacent diode, join VDD
and VDDH, and power the nRF from the Game & Watch's 1.8 V rail with common ground.

The annotated illustration was produced using the built-in `imagegen` tool.
It is an explanatory illustration, not a PCB fabrication drawing. The physical
VDDH jumper landing point was not supplied, so the inset represents the electrical
connection only. Locate the actual net by continuity on the specific board.

## Final edit brief

Annotate the supplied SuperMini front/back illustration in English. Mark the
power-path MOSFET and the adjacent diode for removal. Identify the rear VDD and
GND test pads. Show VDD joined to VDDH in a separate electrical inset supplied
from Game & Watch 1.8 V, without inventing a physical VDDH solder point. Include
the direct SWD mapping: P0.06/D1 to SWDIO, P0.08/D0 to SWCLK, P0.20/D3 to NRST
(open-drain), and P0.17/D2 unconnected. State that no level shifter is needed for
this modified board. Omit the unrelated full pinout labels and stock charging
instructions, and keep the removal marks and connection labels clearly readable.

## References

- [Nordic nRF52840 power supply documentation](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/power.html)
  specifies Normal Voltage mode with VDD and VDDH joined.
- [SuperMini board reverse engineering](https://github.com/sasodoma/nrf52840-promicro)
  provides the matching power-path layout used to check the component locations.
- [Third-party notices](../../THIRD_PARTY_NOTICES.md#hardware-illustration) describe
  the underlying pinout artwork's provenance.
