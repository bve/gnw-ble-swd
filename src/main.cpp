// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 bve and contributors
#include <bluefruit.h>
#include <nrf_nvic.h>
#include <stream_buffer.h>
#include <semphr.h>
#include "mem_ap.h"
#include "swd.h"
#include "response_queue.h"
#include "idle_power.h"

namespace {
using namespace bridge;
// Wire UUIDs (Nordic byte order); Python uses the conventional string order.
const uint8_t serviceUuid[16] = {0x01,0x00,0x86,0x59,0x30,0x1c,0x4a,0x9b,0x94,0x4e,0xf1,0x80,0x10,0x7a,0x77,0x67};
const uint8_t rxUuid[16] =      {0x02,0x00,0x86,0x59,0x30,0x1c,0x4a,0x9b,0x94,0x4e,0xf1,0x80,0x10,0x7a,0x77,0x67};
const uint8_t txUuid[16] =      {0x03,0x00,0x86,0x59,0x30,0x1c,0x4a,0x9b,0x94,0x4e,0xf1,0x80,0x10,0x7a,0x77,0x67};

class BleBridge {
public:
    void begin();
    void poll();
    static BleBridge* instance;
private:
    SwdPort port_;
    MemAp target_{port_};
    BLEService service_{serviceUuid};
    BLECharacteristic rx_{rxUuid}, tx_{txUuid};
    StreamBufferHandle_t incoming_ = nullptr;
    SemaphoreHandle_t rxWake_ = nullptr, txWake_ = nullptr;
    volatile uint32_t generation_ = 0;
    volatile bool overflow_ = false;
    volatile uint16_t mtu_ = 23;
    volatile uint16_t connection_ = BLE_CONN_HANDLE_INVALID;
    volatile uint32_t interval_ = 0, phy_ = 0, dataLength_ = 27;
    volatile uint32_t latency_ = 0, activityMs_ = 0;
    IdlePower power_;
    uint32_t rxWakeups_ = 0;
    uint32_t session_ = 0;
    volatile uint32_t txFailedGeneration_ = 0xffffffff;
    bool failed_ = false;
    struct {
        uint32_t readBytes = 0, readUs = 0, writeBytes = 0, writeUs = 0;
        uint32_t txBytes = 0, txUs = 0, rxBytes = 0, rxUs = 0, txBusy = 0;
    } stats_;
    uint8_t request_[RequestSize + BlockSize + 4];
    ResponseQueue responses_;
    bool alive(uint32_t generation) const {
        return generation == generation_ && txFailedGeneration_ != generation && Bluefruit.connected() && !overflow_;
    }
    bool alive() const { return alive(session_); }
    bool receive(uint8_t* data, size_t size);
    static bool allowLatency(uint16_t connection, bool allow) {
        ble_opt_t option{};
        option.gap_opt.slave_latency_disable.conn_handle = connection;
        option.gap_opt.slave_latency_disable.disable = !allow;
        return sd_ble_opt_set(BLE_GAP_OPT_SLAVE_LATENCY_DISABLE, &option) == NRF_SUCCESS;
    }
    void waitForWork();
    bool send(const ResponseQueue::Frame& frame);
    void transmit(const ResponseQueue::Frame& frame);
    Status execute(Command command, uint32_t address, uint32_t size, uint8_t* output, size_t& returned);
};
BleBridge* BleBridge::instance = nullptr;
BleBridge bridgeDevice;

void BleBridge::begin() {
    instance = this;
    port_.begin();
    port_.frequency(MaxFrequency);
    port_.release();
    // Buffer the negotiated request window, including framing overhead.
    incoming_ = xStreamBufferCreate(Window * (RequestSize + BlockSize + 4) + 244, 1);
    rxWake_ = xSemaphoreCreateBinary();
    txWake_ = xSemaphoreCreateBinary();
    if (!incoming_ || !rxWake_ || !txWake_ || !responses_.begin([](void* self, const ResponseQueue::Frame& frame) {
        static_cast<BleBridge*>(self)->transmit(frame);
    }, this)) { while (true) delay(1000); }
    Bluefruit.autoConnLed(false);
    Bluefruit.configPrphConn(247, 100, 16, 16);
    Bluefruit.begin(1, 0);
    nrf_gpio_cfg_default(PIN_LED1); // Off regardless of a clone's LED polarity.
    Bluefruit.setName("GW-SWD");
    Bluefruit.setTxPower(4);
    Bluefruit.Periph.setConnInterval(IdlePower::FastInterval, IdlePower::FastInterval);
    Bluefruit.Periph.setConnSlaveLatency(IdlePower::latency(IdlePower::FastInterval));
    Bluefruit.Periph.setConnSupervisionTimeout(400);
    // Run in the BLE task, in order with writes (not deferred Ada callbacks).
    Bluefruit.setEventCallback([](ble_evt_t* event) {
        if (event->header.evt_id == BLE_GAP_EVT_CONNECTED) {
            instance->connection_ = event->evt.gap_evt.conn_handle;
            instance->mtu_ = 23;
            instance->activityMs_ = millis();
            ++instance->generation_;
            auto* connection = Bluefruit.Connection(event->evt.gap_evt.conn_handle);
            // The central initiates ATT MTU exchange. Concurrent exchanges
            // make this BSP retain the peer's 517-byte offer instead of min.
            connection->requestDataLengthUpdate();
            connection->requestPHY(BLE_GAP_PHY_2MBPS);
            // PPCP alone is advisory; BlueZ can reuse an older interval.
            connection->requestConnectionParameter(IdlePower::FastInterval,
                IdlePower::latency(IdlePower::FastInterval), 400);
            allowLatency(instance->connection_, false);
            xSemaphoreGive(instance->rxWake_);
        } else if (event->header.evt_id == BLE_GAP_EVT_DISCONNECTED) {
            instance->connection_ = BLE_CONN_HANDLE_INVALID;
            ++instance->generation_;
            xSemaphoreGive(instance->rxWake_);
            xSemaphoreGive(instance->txWake_);
        } else if (event->header.evt_id == BLE_GATTS_EVT_HVN_TX_COMPLETE) {
            instance->activityMs_ = millis();
            xSemaphoreGive(instance->txWake_);
        } else if (event->header.evt_id == BLE_GATTS_EVT_EXCHANGE_MTU_REQUEST ||
                   event->header.evt_id == BLE_GATTC_EVT_EXCHANGE_MTU_RSP) {
            auto* connection = Bluefruit.Connection(event->evt.common_evt.conn_handle);
            if (connection) instance->mtu_ = min(uint16_t(247), connection->getMtu());
        }
        if (event->header.evt_id == BLE_GAP_EVT_CONNECTED)
            instance->latency_ = event->evt.gap_evt.params.connected.conn_params.slave_latency;
        else if (event->header.evt_id == BLE_GAP_EVT_CONN_PARAM_UPDATE)
            instance->latency_ = event->evt.gap_evt.params.conn_param_update.conn_params.slave_latency;
        // Copy connection fields in the BLE task while its owner is alive.
        if (auto* connection = Bluefruit.Connection(event->evt.common_evt.conn_handle)) {
            instance->interval_ = connection->getConnectionInterval();
            instance->phy_ = connection->getPHY();
            instance->dataLength_ = connection->getDataLength();
        }
    });
    service_.begin();
    rx_.setProperties(CHR_PROPS_WRITE_WO_RESP | CHR_PROPS_WRITE);
    rx_.setPermission(SECMODE_OPEN, SECMODE_OPEN);
    rx_.setMaxLen(244);
    rx_.setWriteCallback([](uint16_t, BLECharacteristic*, uint8_t* data, uint16_t size) {
        instance->activityMs_ = millis();
        if (xStreamBufferSend(instance->incoming_, data, size, 0) != size) instance->overflow_ = true;
        xSemaphoreGive(instance->rxWake_);
    }, false); // Direct BLE task callback preserves ordering and avoids heap copies.
    rx_.begin();
    tx_.setProperties(CHR_PROPS_NOTIFY);
    tx_.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
    tx_.setMaxLen(244);
    tx_.begin();
    Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
    Bluefruit.Advertising.addService(service_);
    Bluefruit.Advertising.addName(); // Fits in the primary advertisement.
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.setInterval(IdlePower::AdvFast, IdlePower::AdvSlow);
    Bluefruit.Advertising.setFastTimeout(IdlePower::AdvFastSeconds);
    Bluefruit.Advertising.start(0);
}

void BleBridge::waitForWork() {
    TickType_t timeout = portMAX_DELAY;
    if (alive() && responses_.idle() && !power_.sleeping()) {
        const uint32_t remaining = power_.remaining(millis(), activityMs_);
        if (remaining) timeout = max(TickType_t(1), pdMS_TO_TICKS(remaining));
        else if (allowLatency(connection_, true)) {
            port_.release(); // Park SWD without discarding the MEM-AP session.
            power_.sleep(millis());
        }
        else timeout = pdMS_TO_TICKS(1000); // Failed negotiation must not spin.
    }
    // The token is retained if an event arrives between checking the stream
    // and blocking. No lost wake-up, and no periodic 1 ms polling in standby.
    xSemaphoreTake(rxWake_, timeout);
    ++rxWakeups_;
}

bool BleBridge::receive(uint8_t* data, size_t size) {
    const uint32_t started = micros();
    const size_t expected = size;
    uint32_t deadline = millis() + 10000;
    while (size && alive()) {
        size_t received = xStreamBufferReceive(incoming_, data, size, 0);
        data += received; size -= received;
        if (received) deadline = millis() + 10000;
        const int32_t remaining = int32_t(deadline - millis());
        if (remaining <= 0) return false;
        if (!received && size && alive())
            xSemaphoreTake(rxWake_, max(TickType_t(1), pdMS_TO_TICKS(remaining)));
    }
    stats_.rxUs += micros() - started;
    stats_.rxBytes += expected - size;
    return size == 0 && alive();
}
bool BleBridge::send(const ResponseQueue::Frame& frame) {
    const uint32_t started = micros();
    const size_t size = frame.size;
    size_t offset = 0;
    const uint32_t deadline = millis() + 10000;
    while (offset < size && alive(frame.generation)) {
        uint16_t count = min(size - offset, min(size_t(mtu_ - 3), size_t(244)));
        // Use the SoftDevice queue directly: no BLEConnection pointer remains
        // live in this task while the BLE task can delete it on disconnect.
        ble_gatts_hvx_params_t notification{};
        notification.handle = tx_.handles().value_handle;
        notification.type = BLE_GATT_HVX_NOTIFICATION;
        notification.p_len = &count;
        notification.p_data = frame.data + offset;
        uint32_t result = sd_ble_gatts_hvx(connection_, &notification);
        if (result == NRF_SUCCESS) offset += count;
        else if (result == NRF_ERROR_RESOURCES) {
            ++stats_.txBusy;
            const int32_t remaining = int32_t(deadline - millis());
            if (remaining <= 0) return false;
            xSemaphoreTake(txWake_, max(TickType_t(1), pdMS_TO_TICKS(remaining)));
        }
        else return false;
        if (int32_t(millis() - deadline) >= 0) return false;
    }
    stats_.txUs += micros() - started;
    stats_.txBytes += offset;
    return offset == size && alive(frame.generation);
}

void BleBridge::transmit(const ResponseQueue::Frame& frame) {
    // Frames from disconnected clients never enter a new connection.
    if (alive(frame.generation)) {
        if (!send(frame)) {
            txFailedGeneration_ = frame.generation;
            if (frame.generation == generation_ && Bluefruit.connected()) Bluefruit.disconnect(connection_);
        } else if (frame.command == Command::Dfu) {
            delay(100); // The ACK was queued; allow it to leave the radio.
            sd_power_gpregret_clr(0, 0xff);
            sd_power_gpregret_set(0, 0xa8);
            sd_nvic_SystemReset();
        }
    }
    // The lower-priority command task runs after this slot is returned to free_.
    xSemaphoreGive(rxWake_);
}

Status BleBridge::execute(Command command, uint32_t address, uint32_t size, uint8_t* output, size_t& returned) {
    uint32_t value = 0;
    Status status = Status::Ok;
    switch (command) {
    case Command::Info:
        put32(output, BlockSize); put32(output + 4, Window);
        put32(output + 8, MaxFrequency); put32(output + 12, CapabilityBatchWrite); returned = 16; break;
    case Command::Connect:
        status = target_.connect(value); put32(output, value); returned = 4; break;
    case Command::Read: {
        const uint32_t started = micros();
        status = target_.read(address, output, size); returned = size;
        stats_.readUs += micros() - started; stats_.readBytes += size;
        break;
    }
    case Command::Write: {
        const uint32_t started = micros();
        status = target_.write(address, request_ + RequestSize, size);
        stats_.writeUs += micros() - started; stats_.writeBytes += size;
        break;
    }
    case Command::BatchWrite: {
        const uint8_t* cursor = request_ + RequestSize;
        if (!validBatch(cursor, size)) return Status::Invalid;
        const uint32_t started = micros();
        while (size && status == Status::Ok) {
            const uint32_t destination = get32(cursor), count = get32(cursor + 4);
            status = target_.write(destination, cursor + 8, count);
            stats_.writeBytes += count;
            cursor += 8 + count; size -= 8 + count;
        }
        stats_.writeUs += micros() - started;
        break;
    }
    case Command::ReadRegister:
        status = target_.readRegister(address, value); put32(output, value); returned = 4; break;
    case Command::WriteRegister: status = target_.writeRegister(address, get32(request_ + RequestSize)); break;
    case Command::Halt: status = target_.halt(); break;
    case Command::Resume: status = target_.resume(); break;
    case Command::Reset: status = target_.reset(false); break;
    case Command::ResetHalt: status = target_.reset(true); break;
    case Command::Frequency: status = port_.frequency(address); break;
    case Command::Dfu: target_.disconnect(); break;
    case Command::Link: {
        const ble_gap_conn_params_t params = {uint16_t(address), uint16_t(address),
            IdlePower::latency(address), 400};
        if (sd_ble_gap_conn_param_update(connection_, &params) != NRF_SUCCESS) status = Status::Invalid;
        break;
    }
    case Command::Stats: {
        if (address == 2) {
            // Read-only power diagnostics. This command wakes the radio, so
            // report completed sleep periods rather than a misleading live flag.
            const uint32_t values[] = {1, IdlePower::TimeoutMs, latency_, power_.entries(),
                power_.lastMs(), power_.totalMs(), rxWakeups_, Bluefruit.Advertising.getInterval(),
                NRF_USBD->ENABLE, NRF_SPIM3->ENABLE, NRF_P0->PIN_CNF[6],
                NRF_P0->PIN_CNF[8], NRF_P0->PIN_CNF[17], NRF_P0->PIN_CNF[20]};
            for (size_t i = 0; i < sizeof(values) / sizeof(values[0]); ++i) put32(output + i * 4, values[i]);
            returned = sizeof(values); break;
        }
        taskENTER_CRITICAL();
        if (address) stats_ = {};
        const uint32_t values[] = {1, mtu_, interval_, phy_, dataLength_,
            stats_.readBytes, stats_.readUs, stats_.writeBytes, stats_.writeUs,
            stats_.txBytes, stats_.txUs, stats_.rxBytes, stats_.rxUs, stats_.txBusy};
        taskEXIT_CRITICAL();
        for (size_t i = 0; i < sizeof(values) / sizeof(values[0]); ++i) put32(output + i * 4, values[i]);
        returned = sizeof(values); break;
    }
    default: return Status::Invalid;
    }
    return status;
}

void BleBridge::poll() {
    if (session_ != generation_ || overflow_) {
        power_.wake(millis());
        target_.disconnect();
        // Consumer drains instead of resetting a stream buffer while BLE writes.
        while (xStreamBufferReceive(incoming_, request_, sizeof(request_), 0)) {}
        failed_ = overflow_;
        session_ = generation_;
        if (overflow_ && Bluefruit.connected()) Bluefruit.disconnect(Bluefruit.connHandle());
        overflow_ = false;
    }
    if (!alive() || failed_ || !xStreamBufferBytesAvailable(incoming_)) { waitForWork(); return; }
    if (power_.sleeping()) {
        if (!allowLatency(connection_, false)) { failed_ = true; target_.disconnect(); return; }
        if (target_.connected()) port_.begin(); // No reset/line reset on wake.
        power_.wake(millis());
    }
    if (!receive(request_, RequestSize)) { failed_ = true; target_.disconnect(); return; }
    const auto command = static_cast<Command>(request_[1]);
    uint32_t address = get32(request_ + 4), size = get32(request_ + 8);
    if (request_[0] != Version || !validRequest(command, address, size)) {
        // Cannot safely resynchronize a malformed byte stream. Close it.
        failed_ = true;
        target_.disconnect();
        Bluefruit.disconnect(Bluefruit.connHandle());
        return;
    }
    const size_t payloadSize = command == Command::Write || command == Command::WriteRegister ||
        command == Command::BatchWrite ? size : 0;
    if (!receive(request_ + RequestSize, payloadSize + 4)) { failed_ = true; target_.disconnect(); return; }
    Status status = crc32(request_, RequestSize + payloadSize) == get32(request_ + RequestSize + payloadSize)
        ? Status::Ok : Status::Crc;
    auto* frame = responses_.acquire(session_, command);
    if (!frame) { failed_ = true; target_.disconnect(); return; }
    uint8_t* response = frame->data;
    size_t returned = 0;
    if (status == Status::Ok && alive()) status = execute(command, address, size, response + ResponseSize, returned);
    else if (!alive()) status = Status::Disconnected;
    if (status != Status::Ok) { returned = 0; failed_ = true; target_.disconnect(); }
    response[0] = Version; response[1] = static_cast<uint8_t>(status);
    response[2] = request_[2]; response[3] = request_[3];
    put32(response + 4, returned);
    put32(response + ResponseSize + returned, crc32(response, ResponseSize + returned));
    if (command == Command::Dfu) {
        if (status != Status::Ok) frame->command = Command::Info;
        failed_ = true; // Do not accept target operations while entering DFU.
    }
    responses_.submit(frame, ResponseSize + returned + 4);
}
}

void setup() { bridgeDevice.begin(); }
void loop() { bridgeDevice.poll(); }
