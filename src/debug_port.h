// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include "protocol.h"

namespace bridge {
// Memory access does not depend on Nordic GPIO/DMA details.
class DebugPort {
public:
    virtual ~DebugPort() = default;
    virtual void begin() = 0;
    virtual void release() = 0;
    virtual void reset(bool asserted) = 0;
    virtual void lineReset() = 0;
    virtual Status transfer(bool ap, bool read, uint8_t address, uint32_t& data) = 0;
};
}
