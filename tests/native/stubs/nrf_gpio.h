// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include <stdint.h>

// Register adapters let the production SWD driver run against a clocked peer.
void testGpioWrite(uint32_t mask, bool set);
void testGpioDirection(uint32_t pin, bool output);
void testSpiEnable(uint32_t value);
void testSpiStart();

struct TestGpioWrite {
    bool set;
    void operator=(uint32_t mask) { testGpioWrite(mask, set); }
};
struct TestGpio {
    TestGpioWrite OUTSET{true}, OUTCLR{false};
    uint32_t IN = 0;
    uint32_t PIN_CNF[32]{};
};
struct TestSpiEnable {
    uint32_t value = 0;
    void operator=(uint32_t next) { value = next; testSpiEnable(next); }
};
struct TestSpiStart {
    void operator=(uint32_t value) { if (value) testSpiStart(); }
};
struct TestSpi {
    TestSpiEnable ENABLE;
    TestSpiStart TASKS_START;
    uint32_t TASKS_STOP = 0;
    uint32_t CONFIG = 0, FREQUENCY = 0, EVENTS_END = 0;
    struct { uint32_t SCK = ~0u, MOSI = ~0u, MISO = ~0u; } PSEL;
    struct Buffer { uintptr_t PTR = 0; uint32_t MAXCNT = 0; } RXD, TXD;
};
extern TestGpio testGpio;
extern TestSpi testSpi;
#define NRF_P0 (&testGpio)
#define NRF_SPIM3 (&testSpi)
inline void __NOP() {}
inline void __DMB() {}
constexpr unsigned NRF_GPIO_PIN_DIR_OUTPUT = 1;
constexpr unsigned NRF_GPIO_PIN_DIR_INPUT = 0;
constexpr unsigned NRF_GPIO_PIN_INPUT_DISCONNECT = 0;
constexpr unsigned NRF_GPIO_PIN_NOPULL = 0;
constexpr unsigned NRF_GPIO_PIN_H0H1 = 0;
constexpr unsigned NRF_GPIO_PIN_S0D1 = 6;
constexpr unsigned NRF_GPIO_PIN_NOSENSE = 0;
constexpr unsigned SPIM_CONFIG_ORDER_Pos = 0;
constexpr unsigned SPIM_CONFIG_ORDER_LsbFirst = 1;
constexpr unsigned SPIM_CONFIG_CPOL_Pos = 2;
constexpr unsigned SPIM_CONFIG_CPOL_ActiveLow = 1;
constexpr unsigned SPIM_CONFIG_CPOL_ActiveHigh = 0;
constexpr unsigned SPIM_ENABLE_ENABLE_Enabled = 7;
constexpr unsigned SPIM_FREQUENCY_FREQUENCY_M1 = 1000000;
constexpr unsigned SPIM_FREQUENCY_FREQUENCY_M2 = 2000000;
constexpr unsigned SPIM_FREQUENCY_FREQUENCY_M4 = 4000000;
constexpr unsigned SPIM_FREQUENCY_FREQUENCY_M8 = 8000000;
inline void nrf_gpio_pin_set(uint32_t pin) { testGpioWrite(1u << pin, true); }
inline void nrf_gpio_pin_clear(uint32_t pin) { testGpioWrite(1u << pin, false); }
inline void nrf_gpio_cfg(uint32_t pin, unsigned direction, unsigned, unsigned, unsigned, unsigned) {
    testGpioDirection(pin, direction == NRF_GPIO_PIN_DIR_OUTPUT);
}
inline void nrf_gpio_cfg_output(uint32_t pin) { testGpioDirection(pin, true); }
inline void nrf_gpio_cfg_input(uint32_t pin, unsigned) { testGpioDirection(pin, false); }
inline void nrf_gpio_cfg_default(uint32_t pin) {
    testGpio.PIN_CNF[pin] = 2; // Input buffer disconnected, no pulls, input direction.
    testGpioDirection(pin, false);
}

constexpr unsigned SPIM_FREQUENCY_FREQUENCY_M16 = 16000000;
constexpr unsigned SPIM_FREQUENCY_FREQUENCY_M32 = 32000000;
