// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#include "swd.h"
#include <cassert>
#include <vector>

TestGpio testGpio;
TestSpi testSpi;
namespace {
constexpr uint32_t Dio = 1u << 6, Clk = 1u << 8;
bool clockHigh = false, output = true, recording = false;
bool stalled = false;
uint32_t latch = 0;
size_t receiveIndex = 0;
unsigned risingEdges = 0;
std::vector<bool> received, transmitted;

void publish() {
    testGpio.IN = receiveIndex < received.size() && received[receiveIndex] ? Dio : 0;
}
void clockLevel(bool high) {
    if (high && !clockHigh && recording) {
        ++risingEdges;
        if (output) transmitted.push_back(latch & Dio);
        else {
            // ADIv5: the target advances SWDIO at each RISING edge.
            ++receiveIndex;
            publish();
        }
    }
    clockHigh = high;
}
void bits(std::vector<bool>& data, uint32_t value, unsigned count) {
    while (count--) { data.push_back(value & 1); value >>= 1; }
}
uint32_t word(const std::vector<bool>& data, size_t offset, unsigned count) {
    uint32_t value = 0;
    for (unsigned i = 0; i < count; ++i) value |= uint32_t(data.at(offset + i)) << i;
    return value;
}
void prepare(bool read, uint32_t value, uint32_t ack = 1, bool badParity = false) {
    received.clear(); transmitted.clear(); receiveIndex = 0; risingEdges = 0;
    received.push_back(true); // Turnaround: no ACK bit yet.
    bits(received, ack, 3);
    if (read && ack == 1) {
        bits(received, value, 32);
        received.push_back(bool(__builtin_parity(value)) ^ badParity);
    }
    received.push_back(false); // Turnaround back to host.
    publish(); recording = true;
}
}

void testGpioWrite(uint32_t mask, bool set) {
    if (set) latch |= mask;
    else latch &= ~mask;
    if (mask & Clk) clockLevel(set);
}
void testGpioDirection(uint32_t pin, bool enabled) {
    if (pin == 6) output = enabled;
}
void testSpiEnable(uint32_t value) {
    if (testSpi.PSEL.SCK != 8) return;
    clockLevel(value ? bool(testSpi.CONFIG & (1u << SPIM_CONFIG_CPOL_Pos)) : bool(latch & Clk));
}
void testSpiStart() {
    if (stalled) return;
    const bool read = testSpi.RXD.MAXCNT != 0;
    const bool idleHigh = testSpi.CONFIG & (1u << SPIM_CONFIG_CPOL_Pos);
    assert(testSpi.CONFIG & 1); // LSB first.
    assert(testSpi.PSEL.SCK == 8);
    uint32_t value = read ? 0 : *reinterpret_cast<uint32_t*>(testSpi.TXD.PTR);
    assert((read ? testSpi.RXD.MAXCNT : testSpi.TXD.MAXCNT) == 4);
    for (unsigned i = 0; i < 32; ++i) {
        if (!read) {
            if ((value >> i) & 1) latch |= Dio;
            else latch &= ~Dio;
        }
        clockLevel(!idleHigh);
        if (read) value |= uint32_t(bool(testGpio.IN & Dio)) << i;
        clockLevel(idleHigh);
    }
    if (read) *reinterpret_cast<uint32_t*>(testSpi.RXD.PTR) = value;
    testSpi.EVENTS_END = 1;
}

int main() {
    using namespace bridge;
    for (uint32_t frequency : {100000u, 1000000u, 8000000u, 16000000u, 32000000u}) {
        for (uint32_t value : {0x6ba02477u, 0x12345678u, 0x80000001u, 0u, ~0u}) {
            recording = false;
            SwdPort port;
            port.begin(); port.frequency(frequency); port.lineReset();
            prepare(true, value);
            uint32_t actual = 0;
            assert(port.transfer(false, true, 0, actual) == Status::Ok);
            assert(actual == value);
            assert(word(transmitted, 0, 8) == 0xa5); // DPIDR read request.
            assert(risingEdges == 48); // No extra edge at GPIO/SPI boundaries.

            prepare(false, value);
            actual = value;
            assert(port.transfer(true, false, 12, actual) == Status::Ok);
            assert(word(transmitted, 0, 8) == 0xbb); // AP DRW write request.
            assert(word(transmitted, 8, 32) == value);
            assert(transmitted.at(40) == bool(__builtin_parity(value)));
            assert(risingEdges == 48);

            prepare(true, value, 1, true);
            assert(port.transfer(false, true, 0, actual) == Status::Parity);
            prepare(true, value, 4);
            assert(port.transfer(false, true, 0, actual) == Status::Fault);
            assert(risingEdges == 15);
            if (frequency >= 1000000) {
                prepare(true, value);
                stalled = true;
                assert(port.transfer(false, true, 0, actual) == Status::Timeout);
                assert(testSpi.TASKS_STOP == 1);
                stalled = false;
            }
            recording = false;
            port.release();
            assert(testSpi.ENABLE.value == 0);
            assert(testSpi.PSEL.SCK == ~0u && testSpi.PSEL.MOSI == ~0u && testSpi.PSEL.MISO == ~0u);
            for (unsigned pin : {6u, 8u, 17u, 20u}) assert(testGpio.PIN_CNF[pin] == 2);
            assert(latch & (1u << 20)); // NRST was released before parking the pins.
            port.begin();
            prepare(true, value);
            assert(port.transfer(false, true, 0, actual) == Status::Ok && actual == value);
        }
    }
}
