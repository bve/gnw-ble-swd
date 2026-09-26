// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include "WVariant.h"

#define VARIANT_MCK 64000000ul
// RC works on SuperMini revisions both with and without a populated LFXO.
#define USE_LFRC
#define PINS_COUNT 48
#define NUM_DIGITAL_PINS 48
#define NUM_ANALOG_INPUTS 6
#define NUM_ANALOG_OUTPUTS 0
#define PIN_LED1 15
#define LED_BUILTIN PIN_LED1
#define LED_CONN PIN_LED1
#define LED_BLUE PIN_LED1
#define LED_RED PIN_LED1
#define LED_STATE_ON 1
#define PIN_A0 4
#define PIN_A1 5
#define PIN_A2 30
#define PIN_A3 29
#define PIN_A4 31
#define PIN_A5 2
#define PIN_A6 0xff
#define PIN_A7 0xff
#define ADC_RESOLUTION 14
static const uint8_t A0 = PIN_A0, A1 = PIN_A1, A2 = PIN_A2;
static const uint8_t A3 = PIN_A3, A4 = PIN_A4, A5 = PIN_A5;
#define PIN_SERIAL1_RX 8
#define PIN_SERIAL1_TX 6
#define SPI_INTERFACES_COUNT 1
#define PIN_SPI_MISO 10
#define PIN_SPI_MOSI 9
#define PIN_SPI_SCK 20
static const uint8_t SS = 17, MOSI = PIN_SPI_MOSI, MISO = PIN_SPI_MISO, SCK = PIN_SPI_SCK;
#define WIRE_INTERFACES_COUNT 1
#define PIN_WIRE_SDA 17
#define PIN_WIRE_SCL 20
