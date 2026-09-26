// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#pragma once
#include <Arduino.h>
#include <queue.h>
#include "protocol.h"

namespace bridge {
// Each slot has one owner: the SWD worker, TX task, or free-slot queue.
// Keep completed data immutable while BLE sends it and SWD fills the next slot.
class ResponseQueue {
    static constexpr size_t Slots = 2;
public:
    struct Frame {
        uint32_t generation;
        size_t size;
        Command command;
        uint8_t data[ResponseSize + BlockSize + 4];
    };
    using Sender = void (*)(void*, const Frame&);

    bool begin(Sender sender, void* context) {
        sender_ = sender; context_ = context;
        free_ = xQueueCreate(Slots, sizeof(Frame*));
        ready_ = xQueueCreate(Slots, sizeof(Frame*));
        if (!free_ || !ready_) return false;
        for (auto& frame : frames_) {
            auto* item = &frame;
            xQueueSend(free_, &item, 0);
        }
        return xTaskCreate(run, "ble-tx", 512, this, TASK_PRIO_NORMAL, nullptr) == pdPASS;
    }
    Frame* acquire(uint32_t generation, Command command) {
        Frame* frame = nullptr;
        if (xQueueReceive(free_, &frame, pdMS_TO_TICKS(10000)) != pdTRUE) return nullptr;
        frame->generation = generation;
        frame->command = command;
        return frame;
    }
    void submit(Frame* frame, size_t size) {
        frame->size = size;
        // A slot was removed from free_; ready_ therefore always has room.
        xQueueSend(ready_, &frame, 0);
    }
    bool idle() const { return uxQueueMessagesWaiting(free_) == Slots; }
private:
    Frame frames_[Slots];
    QueueHandle_t free_ = nullptr, ready_ = nullptr;
    Sender sender_ = nullptr;
    void* context_ = nullptr;
    static void run(void* self) {
        auto& queue = *static_cast<ResponseQueue*>(self);
        for (;;) {
            Frame* frame;
            if (xQueueReceive(queue.ready_, &frame, portMAX_DELAY) == pdTRUE) {
                queue.sender_(queue.context_, *frame);
                xQueueSend(queue.free_, &frame, 0);
            }
        }
    }
};
}
