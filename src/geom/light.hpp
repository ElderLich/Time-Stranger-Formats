#pragma once

#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>

namespace dsts::geom {
// Native 0x1402E0450 copies 240-byte records and resolves the first word as a
// bone name hash. 0x1402E34F0 dispatches types and copies color/intensity;
// 0x1402D3DE0 multiplies type0 RGB by intensity. Type2 multiplies directly;
// type3 is the native sun/directional branch. Other fields remain opaque.
struct LightRecord {
    static constexpr size_t byte_size=240;
    std::array<uint8_t,byte_size> raw{};
    uint32_t name_hash() const {uint32_t value;std::memcpy(&value,raw.data(),4);return value;}
    void set_name_hash(uint32_t value) {std::memcpy(raw.data(),&value,4);}
    template<typename T,size_t Offset> T get() const {
        static_assert(Offset+sizeof(T)<=byte_size);
        T value;std::memcpy(&value,raw.data()+Offset,sizeof(T));return value;
    }
    template<typename T,size_t Offset> void set(T value) {
        static_assert(Offset+sizeof(T)<=byte_size);
        std::memcpy(raw.data()+Offset,&value,sizeof(T));
    }
    uint16_t native_type() const {return get<uint16_t,4>();}
    uint16_t native_slot() const {return get<uint16_t,6>();}
    bool supports_optical_editing() const {
        const auto kind=native_type();return kind==0 || kind==2 || kind==3;
    }
    void require_optical_type() const {
        if(!supports_optical_editing())
            throw std::runtime_error("Optical editing is supported only for native light types 0, 2 and 3; other records remain opaque");
    }
    static void require_nonnegative(float value,const char* label) {
        if(!std::isfinite(value) || value<0) throw std::runtime_error(std::string(label)+" must be finite and nonnegative");
    }
    std::array<float,3> color_rgb() const {
        require_optical_type();return {get<float,40>(),get<float,44>(),get<float,48>()};
    }
    void set_color_rgb(const std::array<float,3>& value) {
        require_optical_type();
        for(const auto component:value) require_nonnegative(component,"Light RGB");
        set<float,40>(value[0]);set<float,44>(value[1]);set<float,48>(value[2]);
    }
    float intensity() const {require_optical_type();return get<float,8>();}
    void set_intensity(float value) {
        require_optical_type();require_nonnegative(value,"Light intensity");set<float,8>(value);
    }
    float range() const {
        if(native_type()!=0) throw std::runtime_error("Range editing is established only for native type0 point lights");
        return get<float,12>();
    }
    void set_range(float value) {
        if(native_type()!=0) throw std::runtime_error("Range editing is established only for native type0 point lights");
        require_nonnegative(value,"Point light range");set<float,12>(value);
    }
};
static_assert(sizeof(LightRecord)==LightRecord::byte_size);
}
