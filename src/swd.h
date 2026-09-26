// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include "debug_port.h"
#include <Arduino.h>
#include <nrf_gpio.h>

namespace bridge {
// All signals are on P0. DIR controls a SN74AXC1T45 (A=nRF, B=STM32).
// NRST connects directly to the target: open drain, low asserts reset.
class SwdPort : public DebugPort {
public:
    void begin() override;
    void release() override;
    Status frequency(uint32_t hz);
    void reset(bool asserted) override;
    void lineReset() override;
    Status transfer(bool ap, bool read, uint8_t address, uint32_t& data) override;
private:
    static constexpr uint32_t Dio = 6, Clk = 8, Dir = 17, Reset = 20;
    uint32_t delayCycles_ = 0;
    bool fast_ = true;
    void direction(bool output);
    void pause() const __attribute__((always_inline)) {
        for (uint32_t i = 0; i < delayCycles_; ++i) __NOP();
    }
    void writeBit(bool value) __attribute__((always_inline)) {
        NRF_P0->OUTCLR = 1u << Clk;
        if (value) NRF_P0->OUTSET = 1u << Dio;
        else NRF_P0->OUTCLR = 1u << Dio;
        pause();
        NRF_P0->OUTSET = 1u << Clk;
        pause();
    }
    bool readBit() __attribute__((always_inline)) {
        NRF_P0->OUTCLR = 1u << Clk;
        pause();
        // SW-DP changes its output at the rising edge. Capture the current
        // bit while SWCLK is low, before advancing the target to the next bit.
        const bool value = (NRF_P0->IN & (1u << Dio)) != 0;
        NRF_P0->OUTSET = 1u << Clk;
        pause();
        return value;
    }
    void writeBits(uint32_t value, unsigned count);
    uint32_t readBits(unsigned count);
    Status payload(bool read, uint32_t& value);
    Status attempt(bool ap, bool read, uint8_t address, uint32_t& data);
};
}
