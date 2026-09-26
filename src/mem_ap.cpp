// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#include "mem_ap.h"
#include <Arduino.h>
#define TRY(expr) do { const auto status = (expr); if (status != Status::Ok) return status; } while (0)

namespace bridge {
Status MemAp::connect(uint32_t& id) {
    connected_ = false;
    port_.begin();
    // Connect under hardware reset works even when the application sleeps or
    // repurposes SWD. Reset is always released, including every error path.
    port_.reset(true);
    delay(2);
    port_.lineReset();
    Status status = dp(true, 0, id);
    if (status == Status::Ok && (id == 0 || id == 0xffffffff)) status = Status::Fault;
    if (status == Status::Ok) status = writeDp(0, 0x1e); // sticky error clear
    if (status == Status::Ok) status = writeDp(8, 0); // AP0, register bank 0
    if (status == Status::Ok) status = writeDp(4, 0x50000000); // debug + system power
    uint32_t value = 0;
    const uint32_t deadline = millis() + 500;
    while (status == Status::Ok) {
        status = dp(true, 4, value);
        if ((value & 0xa0000000) == 0xa0000000) break;
        if (int32_t(millis() - deadline) >= 0) { status = Status::Timeout; break; }
        yield();
    }
    connected_ = status == Status::Ok;
    if (connected_) status = writeWord(Dhcsr, 0xa05f0003);
    if (status == Status::Ok) status = writeWord(Demcr, 1); // reset vector catch
    port_.reset(false);
    if (status == Status::Ok) status = wait(Dhcsr, 1u << 17, 1u << 17);
    if (status == Status::Ok) status = writeWord(Demcr, 0);
    if (status != Status::Ok) disconnect();
    return status;
}

Status MemAp::setup(uint32_t address, bool word) {
    if (!connected_) return Status::Disconnected;
    // Cortex-M7 AHB-AP: privileged data, debug software enabled, increment single.
    TRY(writeAp(0, 0x23000010 | (word ? 2 : 0)));
    return writeAp(4, address);
}

Status MemAp::flush() {
    uint32_t value = 0;
    TRY(dp(true, 12, value)); // Drain posted writes before acknowledging BLE.
    TRY(dp(true, 4, value));
    if (value & 0xb2) { // STICKYORUN, STICKYCMP, STICKYERR, WDATAERR
        writeDp(0, 0x1e);
        return Status::Fault;
    }
    return Status::Ok;
}

Status MemAp::read(uint32_t address, uint8_t* data, size_t size) {
    while (size) {
        const bool word = !(address & 3) && size >= 4;
        const size_t unit = word ? 4 : 1;
        // ADIv5 TAR auto-increment wraps at 1 KiB. Reprogram TAR at every boundary.
        size_t count = min(size_t(1024 - (address & 1023)), size);
        count = word ? count / 4 : 1;
        TRY(setup(address, word));
        uint32_t value = 0;
        TRY(ap(true, 12, value)); // First AP read is posted, result is stale.
        for (size_t i = 0; i < count; ++i) {
            if (i + 1 < count) { TRY(ap(true, 12, value)); }
            else { TRY(dp(true, 12, value)); }
            if (word) put32(data, value);
            else *data = value >> ((address & 3) * 8);
            data += unit; address += unit; size -= unit;
        }
    }
    return flush();
}

Status MemAp::write(uint32_t address, const uint8_t* data, size_t size) {
    while (size) {
        const bool word = !(address & 3) && size >= 4;
        const size_t unit = word ? 4 : 1;
        size_t count = min(size_t(1024 - (address & 1023)), size);
        count = word ? count / 4 : 1;
        TRY(setup(address, word));
        while (count--) {
            uint32_t value = word ? get32(data) : uint32_t(*data) << ((address & 3) * 8);
            TRY(ap(false, 12, value));
            data += unit; address += unit; size -= unit;
        }
        TRY(flush());
    }
    return Status::Ok;
}

Status MemAp::readWord(uint32_t address, uint32_t& value) {
    uint8_t data[4];
    TRY(read(address, data, 4));
    value = get32(data);
    return Status::Ok;
}
Status MemAp::writeWord(uint32_t address, uint32_t value) {
    uint8_t data[4]; put32(data, value);
    return write(address, data, 4);
}
Status MemAp::wait(uint32_t address, uint32_t mask, uint32_t expected) {
    const uint32_t deadline = millis() + 500;
    do {
        uint32_t value = 0;
        TRY(readWord(address, value));
        if ((value & mask) == expected) return Status::Ok;
        yield();
    } while (int32_t(millis() - deadline) < 0);
    return Status::Timeout;
}
Status MemAp::halt() {
    TRY(writeWord(Dhcsr, 0xa05f0003));
    return wait(Dhcsr, 1u << 17, 1u << 17);
}
Status MemAp::resume() {
    TRY(writeWord(Dhcsr, 0xa05f0001));
    return wait(Dhcsr, 1u << 17, 0);
}
Status MemAp::readRegister(uint32_t reg, uint32_t& value) {
    TRY(writeWord(Dcrsr, reg));
    TRY(wait(Dhcsr, 1u << 16, 1u << 16));
    return readWord(Dcrdr, value);
}
Status MemAp::writeRegister(uint32_t reg, uint32_t value) {
    TRY(writeWord(Dcrdr, value));
    TRY(writeWord(Dcrsr, reg | (1u << 16)));
    return wait(Dhcsr, 1u << 16, 1u << 16);
}
Status MemAp::reset(bool haltAfter) {
    uint32_t demcr = 0;
    TRY(readWord(Demcr, demcr));
    TRY(writeWord(Demcr, haltAfter ? demcr | 1 : demcr & ~1u));
    if (haltAfter) TRY(writeWord(Dhcsr, 0xa05f0003));
    else TRY(writeWord(Dhcsr, 0xa05f0001));
    port_.reset(true); delay(2); port_.reset(false);
    delay(2);
    Status status = haltAfter ? wait(Dhcsr, 1u << 17, 1u << 17) : Status::Ok;
    Status restore = writeWord(Demcr, demcr);
    return status == Status::Ok ? restore : status;
}
}
