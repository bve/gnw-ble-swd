# Source provenance and third-party components

Copyright (C) 2026 bve and contributors.

The companion-specific source, board configuration, build scripts, native tests,
and documentation in this repository are licensed under GNU GPL version 3 only
(`GPL-3.0-only`). See [LICENSE](LICENSE). They were extracted by their author from
the BLE companion portion of a Game & Watch integration and published here as
an independent project. No retro-go or emulator implementation is included.

Dependencies are obtained separately by PlatformIO and keep their own licenses.
This project's GPL notice does not relicense them. Source links below identify
the upstream components; consult the notices in the exact installed package for
the terms applying to each file.

| Component | Version / source | License information |
| --- | --- | --- |
| PlatformIO Core | 6.1.19; [platformio-core](https://github.com/platformio/platformio-core) | Apache-2.0 |
| PlatformIO Nordic nRF52 platform | 10.12.0; [platform-nordicnrf52](https://github.com/platformio/platform-nordicnrf52) | Apache-2.0 |
| Adafruit nRF52 Arduino framework | PlatformIO package 1.10700.0, upstream 1.7.0; [source](https://github.com/adafruit/Adafruit_nRF52_Arduino/tree/1.7.0) | Core LGPL-2.1-or-later; bundled components have individual notices |
| Adafruit Bluefruit52 library | Included in that framework; [source and license](https://github.com/adafruit/Adafruit_nRF52_Arduino/tree/1.7.0/libraries/Bluefruit52Lib) | MIT |
| Adafruit nRF utility | PlatformIO `tool-adafruit-nrfutil`; [source](https://github.com/adafruit/Adafruit_nRFUtil) | Upstream license and notices apply |
| Adafruit nRF52 bootloader | Installed separately; [source](https://github.com/adafruit/Adafruit_nRF52_Bootloader) | Upstream license and bundled-component notices apply |
| Nordic S140 SoftDevice and API | 6.1.1, firmware ID 0x00B6; supplied through the Nordic/Adafruit ecosystem | Nordic vendor license, including hardware-use restrictions; not covered by this project's GPL |

The framework also includes FreeRTOS, TinyUSB, Nordic support code, and other
components with their own notices. The ARM toolchain is installed by PlatformIO
and retains its upstream licenses and runtime exceptions.

The board variant and application linker layout are included here. The linker
also uses `nrf52_common.ld` from the pinned Adafruit framework. All build inputs
needed beyond this repository are resolved by the PlatformIO configuration.

## What is open here

The full project-owned nRF application is available in source form, including
the BLE service, SWD engine, memory engine, diagnostics, and DFU-entry command.
There is no private application source required to build it.

Nordic SoftDevice is a precompiled vendor BLE stack. Its implementation is not
source provided by this repository. The bootloader and SoftDevice are installed
separately and are not included in `bridge-dfu.zip`. Generated application
binaries incorporate framework code, so their distribution must also respect
the relevant dependency notices and terms.

## Hardware illustration

The [1.8 V modification illustration](docs/images/supermini-1v8-modification.png)
was prepared from a SuperMini pinout supplied by the maintainer, with English
annotations added for this project. The original pinout's publisher and license
were not identified; this project's GPL notice does not relicense the underlying
third-party artwork. See [image notes](docs/images/README.md) for its scope and
technical references.

The [solder-bridge close-up](docs/images/supermini-vdd-vddh-solder-bridge.png)
uses an additional crop supplied and marked by the maintainer to identify the
VDD/VDDH capacitor terminals. The English captions and orange connection marker
were added for this documentation; the same underlying-artwork notice applies.
