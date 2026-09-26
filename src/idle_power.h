// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include <stdint.h>

namespace bridge {
// Sleep policy is independent of the radio driver. Only the command task
// changes state; BLE callbacks provide the latest activity timestamp.
class IdlePower {
public:
    static constexpr uint32_t TimeoutMs = 5000;
    static constexpr uint16_t FastInterval = 12; // 15 ms, in 1.25 ms units.
    static constexpr uint16_t AdvFast = 160, AdvSlow = 3200; // 100 ms / 2 s.
    static constexpr uint16_t AdvFastSeconds = 10;
    static uint16_t latency(uint16_t interval) {
        // At most ~1 s between idle radio events; 4 s supervision timeout
        // remains strictly greater than twice the effective interval.
        return interval && interval < 800 ? uint16_t(800 / interval - 1) : 0;
    }
    uint32_t remaining(uint32_t now, uint32_t activity) const {
        const uint32_t elapsed = now - activity; // Also works across millis wrap.
        return elapsed >= TimeoutMs ? 0 : TimeoutMs - elapsed;
    }
    bool sleeping() const { return sleeping_; }
    void sleep(uint32_t now) {
        if (sleeping_) return;
        sleeping_ = true; since_ = now; ++entries_;
    }
    void wake(uint32_t now) {
        if (!sleeping_) return;
        lastMs_ = now - since_; totalMs_ += lastMs_;
        sleeping_ = false;
    }
    uint32_t entries() const { return entries_; }
    uint32_t lastMs() const { return lastMs_; }
    uint32_t totalMs() const { return totalMs_; }
private:
    bool sleeping_ = false;
    uint32_t since_ = 0, entries_ = 0, lastMs_ = 0, totalMs_ = 0;
};
}
