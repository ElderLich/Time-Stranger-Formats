#pragma once

#include <array>
#include <cstdint>
#include <cstring>

namespace dsts::geom {
// Native 0x1402E0450 copies 240-byte records and resolves the first word as a
// bone name hash. Optical fields remain opaque until their meanings are proven.
struct LightRecord {
    static constexpr size_t byte_size=240;
    std::array<uint8_t,byte_size> raw{};
    uint32_t name_hash() const {uint32_t value;std::memcpy(&value,raw.data(),4);return value;}
    void set_name_hash(uint32_t value) {std::memcpy(raw.data(),&value,4);}
};
static_assert(sizeof(LightRecord)==LightRecord::byte_size);
}
