// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include "debug_port.h"

namespace bridge {
class MemAp {
public:
    explicit MemAp(DebugPort& port) : port_(port) {}
    Status connect(uint32_t& id);
    Status read(uint32_t address, uint8_t* data, size_t size);
    Status write(uint32_t address, const uint8_t* data, size_t size);
    Status readRegister(uint32_t reg, uint32_t& value);
    Status writeRegister(uint32_t reg, uint32_t value);
    Status halt();
    Status resume();
    Status reset(bool haltAfter);
    bool connected() const { return connected_; }
    void disconnect() { connected_ = false; port_.release(); }
private:
    DebugPort& port_;
    bool connected_ = false;
    static constexpr uint32_t Dhcsr = 0xe000edf0, Dcrsr = 0xe000edf4;
    static constexpr uint32_t Dcrdr = 0xe000edf8, Demcr = 0xe000edfc;
    Status dp(bool read, uint8_t addr, uint32_t& data) { return port_.transfer(false, read, addr, data); }
    Status ap(bool read, uint8_t addr, uint32_t& data) { return port_.transfer(true, read, addr, data); }
    Status writeDp(uint8_t address, uint32_t value) { return dp(false, address, value); }
    Status writeAp(uint8_t address, uint32_t value) { return ap(false, address, value); }
    Status setup(uint32_t address, bool word);
    Status flush();
    Status readWord(uint32_t address, uint32_t& value);
    Status writeWord(uint32_t address, uint32_t value);
    Status wait(uint32_t address, uint32_t mask, uint32_t expected);
};
}
