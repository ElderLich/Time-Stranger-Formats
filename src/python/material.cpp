#include <string>
#include <fstream>

#include "../geom/material.cpp"
#include "bindings.hpp"

using namespace dsts::geom;
using namespace dsts::geom::binary;

PYBIND11_MAKE_OPAQUE(std::vector<dsts::geom::ShaderUniform>)
PYBIND11_MAKE_OPAQUE(std::vector<dsts::geom::ShaderSetting>)

void bind_material(py::module_ &m) {
    py::class_<ShaderParamDef>(m,"ShaderParameter")
        .def_readonly("id",&ShaderParamDef::id)
        .def_property_readonly("name",[](const ShaderParamDef& d){return std::string(d.name);})
        .def_readonly("type_code",&ShaderParamDef::type_code)
        .def_property_readonly("global_scope",[](const ShaderParamDef& d){return bool(d.global_scope);})
        .def_property_readonly("scope",[](const ShaderParamDef& d){return d.global_scope?"global":"material";})
        .def_property_readonly("kind",&shaderParameterKind)
        .def_property_readonly("component_count",[](const ShaderParamDef& d)->py::object{
            if((d.type_code>=1 && d.type_code<=4) || d.type_code==16) return py::int_(d.type_code);
            return py::none();
        })
        .def_readonly("unknown_0x2D",&ShaderParamDef::unknown_0x2D)
        .def_readonly("unknown_0x2F",&ShaderParamDef::unknown_0x2F)
        .def_readonly("unknown_0x30",&ShaderParamDef::unknown_0x30)
        .def_readonly("unknown_0x34",&ShaderParamDef::unknown_0x34);
    m.def("shader_parameter",[](uint32_t id){return shaderParameter(id);},py::arg("id"));
    m.def("shader_parameter",[](const std::string& name){return shaderParameter(name);},py::arg("name"));
    m.def("validate_material_texture_binding",[](uint32_t id){validateMaterialTextureBinding(shaderParameter(id));},py::arg("id"));
    m.def("validate_material_texture_binding",[](const std::string& name){validateMaterialTextureBinding(shaderParameter(name));},py::arg("name"));
    //Shader
    py::class_<dsts::geom::Shader>(m, "Shader")
        .def_property(
            "name",
            &dsts::geom::Shader::getShaderName,
            &dsts::geom::Shader::setShaderName
        )
        .def("__repr__",[](const dsts::geom::Shader &s){ return "<Shader :" + s.getShaderName() + ">";});
    
    //Uniform
    py::class_<dsts::geom::ShaderUniform>(m, "ShaderUniform")
        .def(py::init<>())
        .def_readwrite("unknown_0xC", &dsts::geom::ShaderUniform::unknown_0xC)
        .def_readwrite("unknown_0x14", &dsts::geom::ShaderUniform::unknown_0x14)
        .def_readwrite("unknown_0x18", &dsts::geom::ShaderUniform::unknown_0x18)
        .def_readwrite("unknown_0x1C", &dsts::geom::ShaderUniform::unknown_0x1C)
        .def_property("parameter_id",
            &dsts::geom::ShaderUniform::getParameterId,
            &dsts::geom::ShaderUniform::setParameterId)
        .def_property("parameter_name",
            &dsts::geom::ShaderUniform::getParameterName,
            &dsts::geom::ShaderUniform::setParameterName)
        .def_property_readonly("uniform_type", &dsts::geom::ShaderUniform::uniformType)
        .def_property("float_payload_padding",[](const dsts::geom::ShaderUniform& u) {
            const auto* values=std::get_if<std::vector<float>>(&u.value);
            if(!values || values->empty() || values->size()>4)
                throw py::value_error("Float payload padding requires an initialized numeric uniform");
            const size_t offset=values->size()*sizeof(float);
            return py::bytes(reinterpret_cast<const char*>(u.float_payload.data()+offset),16-offset);
        },[](dsts::geom::ShaderUniform& u,py::bytes padding) {
            const auto* values=std::get_if<std::vector<float>>(&u.value);
            if(!values || values->empty() || values->size()>4)
                throw py::value_error("Float payload padding requires an initialized numeric uniform");
            const size_t offset=values->size()*sizeof(float);
            std::string bytes=padding;
            if(bytes.size()!=16-offset) throw py::value_error("Float payload padding length does not match component count");
            std::memcpy(u.float_payload.data()+offset,bytes.data(),bytes.size());
        })
        .def_property("value",
            [](dsts::geom::ShaderUniform &u) -> py::object {
                return std::visit([&](auto &arg) -> py::object {
                    using T = std::decay_t<decltype(arg)>;

                    if constexpr (std::is_same_v<T, std::string>) {
                        return py::cast(arg);
                    } else {
                        // A vector can be reassigned while Python keeps its array.
                        // Return owned storage; a non-owning capsule cannot make
                        // that old vector allocation safe after reassignment.
                        py::array_t<float> result(arg.size());
                        if (!arg.empty()) {
                            std::memcpy(result.mutable_data(), arg.data(), arg.size() * sizeof(float));
                        }
                        return result;
                    }
                }, u.value);
            },

            [](dsts::geom::ShaderUniform &u, py::object obj) {
                // SETTER
                if (py::isinstance<py::str>(obj)) {
                    u.value = obj.cast<std::string>();
                } else {
                    // Convert any sequence-like object into a vector<float>
                    std::vector<float> vals = obj.cast<std::vector<float>>();
                    if (vals.empty() || vals.size() > 4) {
                        throw py::value_error("A GEOM float uniform needs one to four components");
                    }
                    u.value = std::move(vals);
                }
            })
        .def("__repr__", [](const dsts::geom::ShaderUniform &u){return "<Uniform :" + u.parameter_name + ">";});

    //Setting
    py::class_<dsts::geom::ShaderSetting>(m, "ShaderSetting")
        .def(py::init<>())
        .def_readwrite("unknown_0x12", &dsts::geom::ShaderSetting::unknown_0x12)
        .def_readwrite("unknown_0x14", &dsts::geom::ShaderSetting::unknown_0x14)
        .def_readwrite("unknown_0x18", &dsts::geom::ShaderSetting::unknown_0x18)
        .def_readwrite("unknown_0x1C", &dsts::geom::ShaderSetting::unknown_0x1C)
        .def_property("parameter_id",
            &dsts::geom::ShaderSetting::getParameterId,
            &dsts::geom::ShaderSetting::setParameterId)
        .def_property("parameter_name",
            &dsts::geom::ShaderSetting::getParameterName,
            &dsts::geom::ShaderSetting::setParameterName)
        .def_property("value", [](const dsts::geom::ShaderSetting &s){
            constexpr size_t n = sizeof(s.payload.payload);
            return py::bytes(reinterpret_cast<const char*>(s.payload.payload), n);
        },[](dsts::geom::ShaderSetting &s, py::bytes b){
            constexpr size_t n = sizeof(s.payload.payload);

            py::buffer_info info(py::buffer(b).request());
            size_t input_size = info.size; 
            const uint8_t* src = static_cast<const uint8_t*>(info.ptr);
            uint8_t* value = static_cast<uint8_t*>(s.payload.payload);

            if (input_size >= n) {
                memcpy(value, src, n);
            } else {
                memcpy(value, src, input_size);
                memset(value + input_size, 0, n - input_size);
            }

        })
        .def("__repr__", [](const dsts::geom::ShaderSetting &s){return "<Setting :" + s.parameter_name + ">";});

    py::bind_vector<std::vector<dsts::geom::ShaderUniform>>(m, "ShaderUniformList");
    py::bind_vector<std::vector<dsts::geom::ShaderSetting>>(m, "ShaderSettingList");

    // Material
    py::class_<Material, std::shared_ptr<Material>>(m, "Material")
        .def(py::init<>())
        .def("clone",&Material::clone)
        .def("validate_parameter_types",&Material::validateParameterTypes)
        .def_property_readonly("active_shader_slots",&Material::activeShaderSlots)
        .def_readwrite("unknown_0x314", &Material::unknown_0x314)
        .def_readwrite("unknown_0x318", &Material::unknown_0x318)
        .def_readwrite("unknown_0x31C", &Material::unknown_0x31C)
        .def_readwrite("unknown_0x324", &Material::unknown_0x324)
        .def_readwrite("unknown_0x326", &Material::unknown_0x326)
        .def_property(
            "name",
            [](const Material &m) { return m.name; },
            &Material::setName
        )
        .def_readonly("name_hash", &Material::name_hash)
        .def_readonly("shaders", &Material::shaders)
        .def_property(
            "uniforms",
            make_vector_property(&Material::uniforms).first,
            make_vector_property(&Material::uniforms).second
        )
        .def_property(
            "settings",
            make_vector_property(&Material::settings).first,
            make_vector_property(&Material::settings).second
        )
        .def("__repr__", [](const Material &m){ return "<Material :" + m.name + ">";});
}
