# BLE SWD protocol, version 1

This is a project-specific byte-stream protocol, not CMSIS-DAP over BLE.
[src/protocol.h](../src/protocol.h) defines framing limits, command IDs,
validation rules, status codes, and CRC calculation.

## GATT service

| Item | UUID | Properties |
| --- | --- | --- |
| Service | `67777a10-80f1-4e94-9b4a-1c3059860001` | Advertised by `GW-SWD` |
| RX | `67777a10-80f1-4e94-9b4a-1c3059860002` | Write / write without response |
| TX | `67777a10-80f1-4e94-9b4a-1c3059860003` | Notify |

Subscribe to TX before sending requests. GATT chunks are at most the negotiated
ATT MTU minus three bytes, capped at 244 bytes. A frame can span multiple chunks
or share a chunk with another frame. Accumulate a byte stream and decode by the
header's payload length, not by notification boundaries.

Only one central connection is supported. Security permissions are open; the
service does not require pairing or authenticate a client.

## Frames

All multi-byte fields are unsigned and little-endian. Version is `1`.

| Request field | Size in bytes |
| --- | ---: |
| Version | 1 |
| Command | 1 |
| Sequence | 2 |
| Address / command argument | 4 |
| Size | 4 |
| Payload | `size` for WRITE, WRITE_REGISTER, or BATCH_WRITE; otherwise 0 |
| CRC32 | 4 |

| Response field | Size in bytes |
| --- | ---: |
| Version | 1 |
| Status | 1 |
| Echoed sequence | 2 |
| Payload size | 4 |
| Payload | As specified by payload size |
| CRC32 | 4 |

CRC covers the entire header and payload, excluding the CRC field itself.
It is CRC-32/ISO-HDLC, matching Python `zlib.crc32`: reflected polynomial
`0xEDB88320`, initial state `0xFFFFFFFF`, final XOR `0xFFFFFFFF`.
The check value for ASCII `123456789` is `0xCBF43926`.

Use distinct sequence numbers for outstanding requests and correlate responses
by sequence. The bridge echoes sequences; it does not deduplicate requests.
The advertised window is four complete requests. Wait for a response before
exceeding that many outstanding requests, even when using GATT writes without
response. A successful response acknowledges the whole operation, not one BLE chunk.

## Commands

Unless specified below, address and size must be zero and there is no request
payload. Empty successful responses have payload size zero.

| ID | Command | Request | Successful response |
| ---: | --- | --- | --- |
| 0 | INFO | No arguments | Four u32: block size, window, maximum SWCLK setting, capabilities |
| 1 | CONNECT | No arguments | SWD DPIDR as u32; connects under reset and halts the target |
| 2 | READ | Address; size 1–16384 | Requested bytes |
| 3 | WRITE | Address; size 1–16384; data payload | Empty |
| 4 | READ_REGISTER | Register selector in address; size 0 | Register value as u32 |
| 5 | WRITE_REGISTER | Register selector in address; size 4; value as u32 | Empty |
| 6 | HALT | No arguments | Empty |
| 7 | RESUME | No arguments | Empty |
| 8 | RESET | No arguments | Empty |
| 9 | RESET_HALT | No arguments | Empty |
| 10 | FREQUENCY | Frequency ceiling in address, 100000–32000000 Hz | Empty |
| 11 | DFU | No arguments | Empty, then the nRF restarts into BLE DFU |
| 12 | STATS | Address 0, 1, or 2 | Diagnostics described below |
| 13 | LINK | Desired interval in address, 6–80 units of 1.25 ms | Empty; actual negotiation is asynchronous |
| 14 | BATCH_WRITE | Address 0; size 9–16384; records as below | Empty after all writes complete |

INFO returns `16384, 4, 32000000, 1`. Capability bit 0 means BATCH_WRITE support.
INFO, STATS, LINK, and FREQUENCY do not establish a target SWD session. Read INFO
first, optionally choose FREQUENCY, then CONNECT before target operations.
CONNECT is intrusive: it resets and halts the target. RESUME continues execution;
RESET restarts the installed target firmware.

Register selectors 0–15 map to R0–R15, with SP=13, LR=14, PC=15. Selectors 16,
17, and 18 access xPSR, MSP, and PSP. The firmware accepts selectors through 20
and passes them to the Cortex-M debug register interface; unsupported/reserved
selectors remain target-dependent.

A BATCH_WRITE payload consists of repeated `address u32, length u32, data[length]`
records. Lengths must be nonzero; every record and its 32-bit address range is
validated before the first write. Writes execute in order. A target failure can
still leave a partially executed batch; it is not a transaction or rollback mechanism.

## Diagnostic payloads

STATS address 0 returns 14 u32 fields in this order:

```text
version, mtu, interval_units, phy, data_length,
read_bytes, read_us, write_bytes, write_us,
tx_bytes, tx_us, rx_bytes, rx_us, tx_busy
```

STATS address 1 clears transfer counters before taking the same snapshot.
STATS address 2 returns a separate 14-u32 power snapshot:

```text
version, idle_timeout_ms, negotiated_slave_latency, idle_entries,
last_idle_ms, total_idle_ms, worker_wakeups, advertising_interval_units,
usb_enabled, spim_enabled, gpio_swdio, gpio_swclk, gpio_dir, gpio_nrst
```

Both snapshot versions are `1`. `interval_units` uses 1.25 ms units and
`advertising_interval_units` uses 0.625 ms units. Hardware enable and GPIO fields
are raw Nordic register values. PHY uses the Nordic bit values (1=1M, 2=2M).
Counters are unsigned 32-bit values and can wrap. Overlapping RX, SWD, and TX
times must not be added as though they were sequential. Reading diagnostics
wakes the radio, so idle counters describe completed idle periods.

## Errors and reconnection

| Status | Meaning |
| ---: | --- |
| 0 | Success |
| 1 | Invalid command/argument |
| 2 | Request CRC mismatch |
| 3 | SWD WAIT timeout |
| 4 | SWD FAULT or missing target |
| 5 | SWD parity error |
| 6 | Target/DMA timeout |
| 7 | SWD session not connected |

An invalid frame header or receive overflow can disconnect without a response.
On a command error the bridge releases the target and stops processing further
requests until a new BLE connection. On any timeout, malformed response, CRC
failure, or nonzero status, fail pending operations and reconnect before sending
more commands. There is no safe assumption that an unacknowledged write did not
execute; do not automatically replay writes, batches, resets, or DFU commands.

## Complete INFO example

After subscribing to TX, send this 16-byte request for INFO, sequence 1:

```text
01 00 01 00 00 00 00 00 00 00 00 00 3e e1 b2 0f
```

It fits in a single GATT write even at MTU 23. Accumulate the response until the
8-byte header, declared payload, and 4-byte CRC are complete. Expect version 1,
status 0, sequence 1, payload length 16, and the four INFO values above. Verify
the response CRC before trusting its values. This operation does not touch SWD.

For entering the bootloader, the DFU command with sequence 1 is:

```text
01 0b 01 00 00 00 00 00 00 00 00 00 7a 66 93 2c
```

Send it only when intentionally updating the companion. After its response,
the application releases the target and resets with `GPREGRET=0xA8`. The
bootloader uses its own Nordic Legacy DFU service and packet format; subsequent
firmware transfer does not use this SWD protocol.
