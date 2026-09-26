# Contributing

Issues and pull requests are welcome. Keep code, comments, documentation, commit
messages, and discussions in this repository in English.

This repository covers the nRF companion firmware and its BLE client in `tools/`.
Keep console firmware, emulators, and games in separate projects. The host client
uses GnWManager for target-specific operations and the documented BLE protocol
to communicate with the nRF firmware.

Before submitting a change, run:

```bash
python3 -m unittest discover -s tests/native -v
python3 -m unittest discover -s tests/ble_swd -v
pio run -e supermini
```

Install `g++` for the native tests and the development requirements for PlatformIO.
Prefer changes with one responsibility, share repeated logic, and remove unused
code. Update the protocol reference when changing observable behavior, preserving
compatibility or introducing an explicit version/capability change.

For hardware reports, include the board revision, bootloader and SoftDevice
versions, host OS/client, measured logic voltage, wiring/level translation, and
reproduction steps. Clearly distinguish native tests, firmware builds, and actual
hardware checks. Do not include credentials, personal device addresses, console
backups, or game images in reports or commits.

Contributions are accepted under the project's GPL-3.0-only license. Preserve
third-party notices and identify the origin and license of imported code.
