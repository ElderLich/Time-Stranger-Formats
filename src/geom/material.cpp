#pragma once

#include <bit>
#include <cstdint>
#include <variant>

#include "../utils/hash.cpp"
#include "binary/material.hpp"

namespace dsts::geom
{
    constexpr auto shaderParamDefs = std::bit_cast<std::array<binary::ShaderParamDef, binary::shaderParamNum>>(shader_params_bin);
    static const std::unordered_map<uint32_t, std::string_view> shaderParamMap = [] {
        std::unordered_map<uint32_t, std::string_view> m;
        m.reserve(shaderParamDefs.size());
        for (auto &p : shaderParamDefs)
            m.emplace(p.id, p.name);
        return m;
    }();

    inline const binary::ShaderParamDef& shaderParameter(uint32_t id) {
        auto found=std::find_if(shaderParamDefs.begin(),shaderParamDefs.end(),
            [id](const auto& descriptor){return descriptor.id==id;});
        if(found==shaderParamDefs.end()) throw std::runtime_error("Unknown native shader parameter ID");
        return *found;
    }

    inline const binary::ShaderParamDef& shaderParameter(const std::string& name) {
        auto found=std::find_if(shaderParamDefs.begin(),shaderParamDefs.end(),
            [&name](const auto& descriptor){return name==descriptor.name;});
        if(found==shaderParamDefs.end()) throw std::runtime_error("Unknown native shader parameter name");
        return *found;
    }

    inline std::string shaderParameterKind(const binary::ShaderParamDef& descriptor) {
        switch(descriptor.type_code) {
            case 0:return "texture";
            case 1:return "scalar";
            case 2:case 3:case 4:return "vector";
            case 16:return "matrix";
            case 100:return "render_state";
            default:return "opaque";
        }
    }

    inline void validateMaterialTextureBinding(const binary::ShaderParamDef& descriptor) {
        if(descriptor.type_code!=0 || descriptor.global_scope)
            throw std::runtime_error(std::string("Material texture ")+descriptor.name+
                " requires a material-scoped texture descriptor (not numeric, matrix, render state or global-only)");
    }

    class ShaderUniform {
        public:
            std::string parameter_name;
            uint16_t parameter_id = 0;

            std::variant<std::vector<float>, std::string> value;
            // GEOM reserves sixteen payload bytes even for one-component
            // uniforms. Native donor files can carry nonzero unused words.
            std::array<uint8_t,16> float_payload{};

            //unks
            uint32_t unknown_0xC = 0;
            uint32_t unknown_0x14 = 0xFFFFFFFF;
            uint32_t unknown_0x18 = 0xFFFFFFFF;
            uint32_t unknown_0x1C = 0xFFFFFF;

            ShaderUniform() = default;

            const std::string& getParameterName() const { return parameter_name; }
            uint16_t getParameterId() const { return parameter_id; }

            void setParameterId(uint16_t id) {
                auto it = shaderParamMap.find(id);
                if (it == shaderParamMap.end()) {
                    throw std::runtime_error("Invalid parameter_id: no matching name");
                }
                parameter_id = id;
                parameter_name = std::string(it->second);
            }

            void setParameterName(const std::string& name) {
                auto it = std::find_if(
                    shaderParamMap.begin(), shaderParamMap.end(),
                    [&](auto& p){ return p.second == name; });

                if (it == shaderParamMap.end()) {
                    throw std::runtime_error("Invalid parameter_name: no matching id");
                }
                parameter_name = name;
                parameter_id = it->first;
            } 

            std::string uniformType() {
                return std::visit([](auto &&arg) -> std::string {
                    using T = std::decay_t<decltype(arg)>;
                    if constexpr (std::is_same_v<T, std::string>)
                        return "texture";
                    else
                        return "float";
                }, value);
            }
    };

    class ShaderSetting {
        public:
            std::string parameter_name;
            uint16_t parameter_id = 0;

            //unks
            binary::Payload payload{};
            uint16_t unknown_0x12 = 0;
            uint32_t unknown_0x14 = 0xFFFFFFFF;
            uint32_t unknown_0x18 = 0xFFFFFFFF;
            uint32_t unknown_0x1C = 0xFFFFFF;

            ShaderSetting() = default;

            const std::string& getParameterName() const { return parameter_name; }
            uint16_t getParameterId() const { return parameter_id; }

            void setParameterId(uint16_t id) {
                auto it = shaderParamMap.find(id);
                if (it == shaderParamMap.end()) {
                    throw std::runtime_error("Invalid parameter_id: no matching name");
                }
                parameter_id = id;
                parameter_name = std::string(it->second);
            }

            void setParameterName(const std::string& name) {
                auto it = std::find_if(
                    shaderParamMap.begin(), shaderParamMap.end(),
                    [&](auto& p){ return p.second == name; });

                if (it == shaderParamMap.end()) {
                    throw std::runtime_error("Invalid parameter_name: no matching id");
                }
                parameter_name = name;
                parameter_id = it->first;
            } 
    };

    class Shader {
        public:
            static constexpr std::size_t NameSize = 14;
            std::array<uint32_t, NameSize> name_data{};

            Shader() = default;

            std::string getShaderName() const {
                std::string name;

                for (std::size_t i = 0; i < NameSize; ++i) {
                    if (i != 0 && i % 3 == 0) {
                        name += "_";
                    }
                    name += encode(name_data[i]);
                }

                return name;
            }

            void setShaderName(const std::string& encodedName) {
                static const std::string alphabet = "0123456789abcdefghijklmnopqrstuvwxyz#$[]{}+@=&";

                // Remove underscores
                std::string cleanName = encodedName;
                cleanName.erase(std::remove(cleanName.begin(), cleanName.end(), '_'), cleanName.end());

                // Check length
                if (cleanName.length() != NameSize * 6) {
                    throw std::runtime_error("Encoded name has invalid length");
                }

                // Check allowed characters
                for (char c : cleanName) {
                    if (alphabet.find(c) == std::string::npos) {
                        throw std::runtime_error(std::string("Invalid character in encoded name: ") + c);
                    }
                }

                // Decode atomically: an invalid later segment must not leave
                // a partially changed shader key behind.
                std::array<uint32_t, NameSize> decoded{};
                for (std::size_t i = 0; i < NameSize; ++i) {
                    std::string segment = cleanName.substr(i * 6, 6);

                    // Decode to uint64_t first to safely check overflow
                    uint64_t value = 0;
                    for (char c : segment) {
                        value *= 46;
                        size_t index = alphabet.find(c);
                        value += static_cast<uint64_t>(index);
                    }

                    // Check if it fits in uint32_t
                    if (value > static_cast<uint64_t>(std::numeric_limits<uint32_t>::max())) {
                        throw std::runtime_error("Segment value exceeds uint32_t range");
                    }

                    decoded[i] = static_cast<uint32_t>(value);
                }
                name_data = decoded;
            }

        private:
            static std::string encode(uint32_t n) {
                static const std::string alphabet =
                    "0123456789abcdefghijklmnopqrstuvwxyz#$[]{}+@=&";

                std::string encoded;

                uint32_t value = n;

                // Base-46 conversion
                if (value == 0) {
                    encoded = "0";
                } else {
                    while (value > 0) {
                        uint32_t digit = value % 46;
                        value /= 46;
                        encoded.insert(encoded.begin(), alphabet[digit]);
                    }
                }

                // Pad to 6 characters
                if (encoded.length() < 6) {
                    encoded.insert(0, 6 - encoded.length(), alphabet[0]);
                }

                return encoded;
            }
            static uint32_t decode(const std::string& str) {
                static const std::string alphabet =
                    "0123456789abcdefghijklmnopqrstuvwxyz#$[]{}+@=&";

                uint32_t value = 0;
                for (char c : str) {
                    value *= 46;
                    size_t index = alphabet.find(c);
                    if (index != std::string::npos) {
                        value += static_cast<uint32_t>(index);
                    } else {
                        throw std::runtime_error("Invalid character in encoded name");
                    }
                }
                return value;
            }
    };

    class Material {
        public:
            uint32_t unknown_0x314 = 0;
            uint32_t unknown_0x318 = 0;
            uint32_t unknown_0x31C = 0;
            uint16_t unknown_0x324 = 0;
            uint16_t unknown_0x326 = 0;

            uint32_t name_hash = 0;
            std::string name;

            std::array<Shader, 14> shaders;
            std::vector<ShaderUniform> uniforms;
            std::vector<ShaderSetting> settings;

            void setName(std::string newName){
                name = newName;
                name_hash = crc32((const uint8_t*)name.data(),name.length());
            }

            // A split material owns all pass descriptors and opaque metadata.
            // Copying only its visible texture/color fields loses native passes.
            std::shared_ptr<Material> clone() const {
                return std::make_shared<Material>(*this);
            }

            std::vector<size_t> activeShaderSlots() const {
                std::vector<size_t> slots;
                for(size_t i=0;i<shaders.size();++i)
                    if(std::any_of(shaders[i].name_data.begin(),shaders[i].name_data.end(),
                        [](uint32_t word){return word!=0;})) slots.push_back(i);
                return slots;
            }

            void validateParameterTypes() const {
                for(const auto& uniform:uniforms) {
                    const auto& descriptor=shaderParameter(uniform.parameter_id);
                    if(const auto* values=std::get_if<std::vector<float>>(&uniform.value)) {
                        if(descriptor.type_code<1 || descriptor.type_code>4 ||
                            values->size()!=descriptor.type_code)
                            throw std::runtime_error(std::string("Material numeric uniform ")+descriptor.name+
                                " does not match its native component count or supported GEOM payload type");
                    } else validateMaterialTextureBinding(descriptor);
                }
                for(const auto& setting:settings)
                    if(shaderParameter(setting.parameter_id).type_code!=100)
                        throw std::runtime_error("Material setting is not a native render-state descriptor");
            }
    };
}
