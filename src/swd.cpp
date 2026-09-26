// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#include "swd.h"

namespace bridge {
namespace {
// The linker reserves the complete 8 KiB AHB slave for this word. This
// implements Nordic anomaly 198 without blocking SoftDevice interrupts.
uint32_t dmaTxWord __attribute__((section(".swd_dma"), aligned(4)));
void disableSpi() {
    NRF_SPIM3->ENABLE = 0;
#ifdef NRF52840_XXAA
    // Nordic anomaly 195: release SPIM3 resources after disabling it.
    *reinterpret_cast<volatile uint32_t*>(0x4002f004) = 1;
#endif
}
}
void SwdPort::begin() {
    nrf_gpio_pin_clear(Clk);
    nrf_gpio_pin_set(Reset); // Open drain: start released, never drive NRST high.
    nrf_gpio_cfg(Clk, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_DISCONNECT,
                 NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_H0H1, NRF_GPIO_PIN_NOSENSE);
    nrf_gpio_cfg(Reset, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_DISCONNECT,
                 NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_S0D1, NRF_GPIO_PIN_NOSENSE);
    nrf_gpio_cfg_output(Dir);
    direction(true);
    // SPIM3 is private to this application, not used by SoftDevice/USB.
    disableSpi();
    NRF_SPIM3->CONFIG = SPIM_CONFIG_ORDER_LsbFirst << SPIM_CONFIG_ORDER_Pos;
    NRF_SPIM3->PSEL.SCK = Clk;
    NRF_SPIM3->PSEL.MOSI = 0xffffffff;
    NRF_SPIM3->PSEL.MISO = 0xffffffff;
}

void SwdPort::release() {
    disableSpi();
    NRF_SPIM3->PSEL.SCK = 0xffffffff;
    NRF_SPIM3->PSEL.MOSI = 0xffffffff;
    NRF_SPIM3->PSEL.MISO = 0xffffffff;
    reset(false);
    // High impedance, no pulls, input buffers disconnected: a floating or
    // powered-down target must not keep the digital input buffers consuming.
    // An external DIR pull-down handles the optional level translator.
    nrf_gpio_cfg_default(Clk);
    nrf_gpio_cfg_default(Dio);
    nrf_gpio_cfg_default(Dir);
    nrf_gpio_cfg_default(Reset);
}

Status SwdPort::frequency(uint32_t hz) {
    if (hz < 100000 || hz > MaxFrequency) return Status::Invalid;
    // GPIO framing is slower than the selected ceiling. Only 32 data bits use
    // EasyDMA. Round SPI DOWN; never exceed the requested SWCLK frequency.
    fast_ = hz >= 1000000;
    NRF_SPIM3->FREQUENCY = hz >= 32000000 ? SPIM_FREQUENCY_FREQUENCY_M32 :
                          hz >= 16000000 ? SPIM_FREQUENCY_FREQUENCY_M16 :
                          hz >= 8000000 ? SPIM_FREQUENCY_FREQUENCY_M8 :
                          hz >= 4000000 ? SPIM_FREQUENCY_FREQUENCY_M4 :
                          hz >= 2000000 ? SPIM_FREQUENCY_FREQUENCY_M2 : SPIM_FREQUENCY_FREQUENCY_M1;
    // A NOP loop takes at least 3 CPU cycles per iteration; conservative ceiling.
    delayCycles_ = hz >= 4000000 ? 0 : (64000000u / (2 * hz) + 2) / 3;
    return Status::Ok;
}

void SwdPort::reset(bool asserted) {
    if (asserted) NRF_P0->OUTCLR = 1u << Reset;
    else NRF_P0->OUTSET = 1u << Reset;
}

void SwdPort::direction(bool output) {
    if (output) {
        // Disconnect the translator's nRF output before driving the nRF pin.
        NRF_P0->OUTSET = 1u << Dir;
        __NOP(); __NOP(); __NOP();
        nrf_gpio_cfg(Dio, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_DISCONNECT,
                     NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_H0H1, NRF_GPIO_PIN_NOSENSE);
    } else {
        nrf_gpio_cfg_input(Dio, NRF_GPIO_PIN_NOPULL);
        NRF_P0->OUTCLR = 1u << Dir;
        __NOP(); __NOP(); __NOP();
    }
}

void SwdPort::writeBits(uint32_t value, unsigned count) {
    while (count--) { writeBit(value & 1); value >>= 1; }
}
uint32_t SwdPort::readBits(unsigned count) {
    uint32_t value = 0;
    for (unsigned i = 0; i < count; ++i) value |= uint32_t(readBit()) << i;
    return value;
}

Status SwdPort::payload(bool read, uint32_t& value) {
    if (!fast_) {
        if (read) value = readBits(32);
        else writeBits(value, 32);
        return Status::Ok;
    }
    // Read: mode 2 starts HIGH, samples on falling edges, advances the target
    // on rising edges. Write: mode 0 starts LOW, target samples rising edges.
    // Keep the GPIO latch equal to the final SPI clock level so disabling
    // SPIM does not introduce an extra edge before the GPIO parity bit.
    if (read) NRF_P0->OUTSET = 1u << Clk;
    else NRF_P0->OUTCLR = 1u << Clk;
    NRF_SPIM3->CONFIG = (SPIM_CONFIG_ORDER_LsbFirst << SPIM_CONFIG_ORDER_Pos) |
        ((read ? SPIM_CONFIG_CPOL_ActiveLow : SPIM_CONFIG_CPOL_ActiveHigh) << SPIM_CONFIG_CPOL_Pos);
    NRF_SPIM3->PSEL.MISO = read ? Dio : 0xffffffff;
    NRF_SPIM3->PSEL.MOSI = read ? 0xffffffff : Dio;
    NRF_SPIM3->RXD.PTR = reinterpret_cast<uintptr_t>(&value);
    NRF_SPIM3->RXD.MAXCNT = read ? 4 : 0;
    if (!read) dmaTxWord = value;
    NRF_SPIM3->TXD.PTR = reinterpret_cast<uintptr_t>(&dmaTxWord);
    NRF_SPIM3->TXD.MAXCNT = read ? 0 : 4;
    NRF_SPIM3->EVENTS_END = 0;
    NRF_SPIM3->ENABLE = SPIM_ENABLE_ENABLE_Enabled;
    __DMB(); // Publish the RAM word before EasyDMA reads it.
    NRF_SPIM3->TASKS_START = 1;
    unsigned remaining = 4096;
    while (!NRF_SPIM3->EVENTS_END && --remaining) {} // Radio interrupts stay enabled.
    if (!remaining) {
        NRF_SPIM3->TASKS_STOP = 1;
        disableSpi();
        return Status::Timeout; // Keep the BLE command loop recoverable.
    }
    __DMB(); // Make the DMA-written word visible to the compiler/CPU.
    disableSpi();
    NRF_SPIM3->PSEL.MISO = NRF_SPIM3->PSEL.MOSI = 0xffffffff;
    return Status::Ok;
}

void SwdPort::lineReset() {
    direction(true);
    writeBits(0xffffffff, 32); writeBits(0xffffffff, 32);
    writeBits(0xe79e, 16); // JTAG-to-SWD selection.
    writeBits(0xffffffff, 32); writeBits(0xffffffff, 32);
    writeBits(0, 8);
}

Status SwdPort::attempt(bool ap, bool read, uint8_t address, uint32_t& data) {
    uint8_t fields = uint8_t(ap) | uint8_t(read) << 1 | (address & 12);
    uint8_t request = 0x81 | (fields << 1) | (__builtin_parity(fields) << 5);
    writeBits(request, 8);
    // Change direction during the falling edge preceding turnaround.
    NRF_P0->OUTCLR = 1u << Clk;
    direction(false);
    readBit();
    uint32_t ack = readBits(3);
    Status result = Status::Ok;
    if (ack == 1 && read) {
        result = payload(true, data);
        if (result != Status::Ok) return result;
        if (readBit() != bool(__builtin_parity(data))) result = Status::Parity;
        readBit();
        NRF_P0->OUTCLR = 1u << Clk;
        direction(true);
    } else {
        if (ack != 1 && ack != 2 && ack != 4) {
            // Unknown ACK: let any target data phase finish before driving DIO.
            readBits(32); readBit();
        }
        readBit(); // Turnaround back to host, also on WAIT/FAULT.
        NRF_P0->OUTCLR = 1u << Clk;
        direction(true);
        if (ack == 1) {
            result = payload(false, data);
            if (result != Status::Ok) return result;
            writeBit(__builtin_parity(data));
        } else {
            result = ack == 2 ? Status::Wait : Status::Fault;
        }
    }
    // Consecutive transfers supply the AP's clocks; MEM-AP drains writes with
    // RDBUFF before acknowledging them. Two idle clocks park DIO low here.
    writeBits(0, 2);
    return result;
}

Status SwdPort::transfer(bool ap, bool read, uint8_t address, uint32_t& data) {
    const uint32_t deadline = millis() + 100;
    Status result;
    do {
        result = attempt(ap, read, address, data);
        if (result != Status::Wait) return result;
        yield();
    } while (int32_t(millis() - deadline) < 0);
    return Status::Wait;
}
}
