// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include <algorithm>
#include <stdint.h>
using std::min;
inline uint32_t millis() { static uint32_t time = 0; return time++; }
inline void yield() {}
inline void delay(unsigned) {}
