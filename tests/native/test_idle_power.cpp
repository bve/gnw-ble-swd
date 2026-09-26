// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#include "idle_power.h"
#include <cassert>

int main() {
    using bridge::IdlePower;
    IdlePower power;
    // Recent work postpones sleep; wrap of millis must not cause premature sleep.
    assert(power.remaining(6000, 5000) == 4000);
    assert(power.remaining(10000, 5000) == 0);
    assert(power.remaining(0x10, 0xfffffff0) == 4968);
    power.sleep(0xfffffff0);
    power.sleep(0); // Repeated idle handling must not reset the start time.
    power.wake(0x10);
    power.wake(0x20);
    assert(!power.sleeping() && power.entries() == 1);
    assert(power.lastMs() == 32 && power.totalMs() == 32);
    power.sleep(100); power.wake(5100);
    assert(power.entries() == 2 && power.totalMs() == 5032);
    // Every supported benchmark interval must remain within BLE's latency and
    // supervision limits, with no more than one second between idle events.
    for (unsigned interval = 6; interval <= 80; ++interval) {
        const unsigned latency = IdlePower::latency(interval);
        assert(latency <= 499);
        assert((latency + 1) * interval <= 800);
        assert(2 * (latency + 1) * interval * 125 < 400 * 1000);
    }
    assert(IdlePower::latency(0) == 0 && IdlePower::latency(3200) == 0);
}
