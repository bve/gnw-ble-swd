// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#include "mem_ap.h"
#include <assert.h>
#include <array>
#include <map>
#include <vector>

using namespace bridge;

class FakePort : public DebugPort {
public:
    std::map<uint32_t, uint8_t> memory;
    std::vector<uint32_t> tarWrites;
    unsigned drains = 0;
    bool heldReset = false, released = false, failId = false, sticky = false;
    uint32_t tar = 0, csw = 0, posted = 0;
    void begin() override {}
    void release() override { released = true; heldReset = false; }
    void reset(bool asserted) override { heldReset = asserted; }
    void lineReset() override {}
    Status transfer(bool ap, bool read, uint8_t address, uint32_t& value) override {
        if (!ap) {
            if (!read) return Status::Ok;
            if (address == 0) {
                if (failId) return Status::Fault;
                value = 0x6ba02477;
            } else if (address == 4) value = 0xf0000000 | (sticky ? 0x20 : 0);
            else if (address == 12) { value = posted; ++drains; }
            return Status::Ok;
        }
        if (address == 0 && !read) { csw = value; return Status::Ok; }
        if (address == 4 && !read) { tar = value; tarWrites.push_back(value); return Status::Ok; }
        assert(address == 12);
        const unsigned count = (csw & 7) == 2 ? 4 : 1;
        uint32_t result = 0;
        for (unsigned i = 0; i < count; ++i) {
            const unsigned shift = ((tar + i) & 3) * 8;
            if (read) result |= uint32_t(memory[tar + i]) << shift;
            else memory[tar + i] = value >> shift;
        }
        // DHCSR reports halt and register transfer ready in this model.
        if (read && tar == 0xe000edf0) result |= 0x30000;
        if (read) { value = posted; posted = result; }
        tar = (tar & ~1023u) | ((tar + count) & 1023u);
        return Status::Ok;
    }
};

int main() {
    assert(crc32(reinterpret_cast<const uint8_t*>("123456789"), 9) == 0xcbf43926);
    assert(validRequest(Command::Read, 0xfffffffc, 4));
    assert(!validRequest(Command::Read, 0xfffffffc, 5));
    assert(!validRequest(Command::Write, 0, BlockSize + 1));
    assert(!validRequest(Command::Dfu, 1, 0));
    assert(!validRequest(Command::Frequency, 0, 0));
    assert(validRequest(Command::Frequency, 32000000, 0));
    assert(validRequest(Command::Stats, 1, 0));
    assert(validRequest(Command::Stats, 2, 0));
    assert(!validRequest(Command::Stats, 3, 0));
    assert(validRequest(Command::Link, 12, 0));
    assert(!validRequest(Command::Link, 5, 0));
    uint8_t batch[24] = {};
    put32(batch, 0x24000001); put32(batch + 4, 4);
    put32(batch + 12, 0x24000009); put32(batch + 16, 4);
    assert(validBatch(batch, sizeof(batch)));
    assert(!validBatch(batch, sizeof(batch) - 1));
    put32(batch + 16, 5);
    assert(!validBatch(batch, sizeof(batch)));
    put32(batch + 16, 4); put32(batch + 12, 0xfffffffd);
    assert(!validBatch(batch, sizeof(batch)));

    FakePort port;
    MemAp target(port);
    uint32_t id = 0;
    assert(target.connect(id) == Status::Ok);
    assert(id == 0x6ba02477 && !port.heldReset);
    port.tarWrites.clear();
    std::array<uint8_t, 3007> input{}, output{};
    for (size_t i = 0; i < input.size(); ++i) input[i] = i * 37;
    constexpr uint32_t address = 0x240003fd;
    assert(target.write(address, input.data(), input.size()) == Status::Ok);
    // Unaligned head, then word bursts crossing three TAR wrap boundaries.
    assert(port.tarWrites[0] == address && port.tarWrites[3] == 0x24000400);
    assert(port.memory.count(address - 1) == 0);
    assert(port.memory.count(address + input.size()) == 0);
    assert(target.read(address, output.data(), output.size()) == Status::Ok);
    assert(input == output);
    assert(port.drains > 0);
    port.sticky = true;
    assert(target.write(address, input.data(), 4) == Status::Fault);
    target.disconnect();
    assert(port.released && !port.heldReset);
    assert(target.read(address, output.data(), 4) == Status::Disconnected);

    FakePort bad;
    bad.failId = true;
    MemAp broken(bad);
    assert(broken.connect(id) == Status::Fault);
    assert(!bad.heldReset && bad.released);
}
