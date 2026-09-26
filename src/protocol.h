// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace bridge {
constexpr uint8_t Version = 1;
constexpr size_t BlockSize = 16384;
constexpr size_t Window = 4;
constexpr uint32_t MaxFrequency = 32000000;
constexpr uint32_t CapabilityBatchWrite = 1;
constexpr size_t RequestSize = 12;
constexpr size_t ResponseSize = 8;
enum class Command : uint8_t {
    Info = 0, Connect = 1, Read = 2, Write = 3, ReadRegister = 4,
    WriteRegister = 5, Halt = 6, Resume = 7, Reset = 8,
    ResetHalt = 9, Frequency = 10, Dfu = 11, Stats = 12, Link = 13, BatchWrite = 14
};
enum class Status : uint8_t {
    Ok = 0, Invalid = 1, Crc = 2, Wait = 3, Fault = 4,
    Parity = 5, Timeout = 6, Disconnected = 7
};

inline uint32_t get32(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
inline void put32(uint8_t* p, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) p[i] = value >> (i * 8);
}
inline bool validBatch(const uint8_t* data, size_t size) {
    if (!size) return false;
    while (size) {
        if (size < 8) return false;
        const uint32_t address = get32(data), count = get32(data + 4);
        data += 8; size -= 8;
        if (!count || count > size || uint64_t(address) + count > 0x100000000ULL) return false;
        data += count; size -= count;
    }
    return true;
}
// Same CRC-32/ISO-HDLC as Python zlib.crc32. Nibble table avoids a bit loop.
inline uint32_t crc32(const uint8_t* data, size_t size) {
    static constexpr uint32_t table[16] = {
        0, 0x1db71064, 0x3b6e20c8, 0x26d930ac, 0x76dc4190, 0x6b6b51f4, 0x4db26158, 0x5005713c,
        0xedb88320, 0xf00f9344, 0xd6d6a3e8, 0xcb61b38c, 0x9b64c2b0, 0x86d3d2d4, 0xa00ae278, 0xbdbdf21c
    };
    uint32_t crc = 0xffffffff;
    while (size--) {
        crc ^= *data++;
        crc = (crc >> 4) ^ table[crc & 15];
        crc = (crc >> 4) ^ table[crc & 15];
    }
    return ~crc;
}
inline bool validRequest(Command cmd, uint32_t address, uint32_t size) {
    switch (cmd) {
    case Command::Read: case Command::Write:
        return size > 0 && size <= BlockSize && uint64_t(address) + size <= 0x100000000ULL;
    case Command::ReadRegister: return address <= 20 && size == 0;
    case Command::WriteRegister: return address <= 20 && size == 4;
    case Command::Frequency: return address >= 100000 && address <= MaxFrequency && size == 0;
    case Command::Stats: return address <= 2 && size == 0;
    case Command::Link: return address >= 6 && address <= 80 && size == 0;
    case Command::BatchWrite: return address == 0 && size >= 9 && size <= BlockSize;
    case Command::Info: case Command::Connect: case Command::Halt: case Command::Resume:
    case Command::Reset: case Command::ResetHalt: case Command::Dfu:
        return address == 0 && size == 0;
    default: return false;
    }
}
}
