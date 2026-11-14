#pragma once

#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>

namespace dsts::geom {
// Native 0x1402E05E0 copies exactly 56 bytes. Keep unknown words and runtime
// pointer slots opaque, instead of normalizing them or assigning guessed names.
class CameraRecord {
public:
    static constexpr size_t byte_size=56;
    std::array<uint8_t,byte_size> raw{};

    template<class T,size_t Offset> T get() const {
        static_assert(Offset+sizeof(T)<=byte_size);
        T value;std::memcpy(&value,raw.data()+Offset,sizeof(T));return value;
    }
    template<class T,size_t Offset> void set(T value) {
        static_assert(Offset+sizeof(T)<=byte_size);
        std::memcpy(raw.data()+Offset,&value,sizeof(T));
    }
};
static_assert(sizeof(CameraRecord)==CameraRecord::byte_size);
}
