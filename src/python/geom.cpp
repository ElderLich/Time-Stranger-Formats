#include <string>
#include <fstream>

#include "../geom/geom.cpp"
#include "bindings.hpp"
#include "atomic_file.hpp"

using namespace dsts::geom;
using namespace dsts::geom::binary;

PYBIND11_MAKE_OPAQUE(std::vector<Mesh>)
PYBIND11_MAKE_OPAQUE(std::vector<std::shared_ptr<Material>>)
PYBIND11_MAKE_OPAQUE(std::vector<CameraRecord>)
PYBIND11_MAKE_OPAQUE(std::vector<LightRecord>)

void bind_geom(py::module_ &m) {
    py::bind_vector<std::vector<Mesh>>(m, "MeshList");
    py::bind_vector<std::vector<std::shared_ptr<Material>>>(m, "MaterialList");
    py::bind_vector<std::vector<CameraRecord>>(m, "CameraList");
    py::bind_vector<std::vector<LightRecord>>(m, "LightList");
    py::class_<LightRecord>(m,"LightRecord")
        .def(py::init<>())
        .def_property("raw",[](const LightRecord& light) {
            return py::bytes(reinterpret_cast<const char*>(light.raw.data()),light.raw.size());
        },[](LightRecord& light,py::bytes data) {
            const std::string bytes=data;
            if(bytes.size()!=LightRecord::byte_size) throw std::runtime_error("Light record must contain exactly 240 bytes");
            std::memcpy(light.raw.data(),bytes.data(),bytes.size());
        })
        .def_property("name_hash",&LightRecord::name_hash,&LightRecord::set_name_hash)
        .def_property_readonly("native_type",&LightRecord::native_type)
        .def_property_readonly("native_slot",&LightRecord::native_slot)
        .def_property_readonly("supports_optical_editing",&LightRecord::supports_optical_editing)
        .def_property("color_rgb",&LightRecord::color_rgb,&LightRecord::set_color_rgb)
        .def_property("intensity",&LightRecord::intensity,&LightRecord::set_intensity)
        .def_property("range",&LightRecord::range,&LightRecord::set_range);
    py::class_<CameraRecord>(m,"CameraRecord")
        .def(py::init<>())
        .def_property("raw",[](const CameraRecord& camera) {
            return py::bytes(reinterpret_cast<const char*>(camera.raw.data()),camera.raw.size());
        },[](CameraRecord& camera,py::bytes data) {
            const std::string bytes=data;
            if(bytes.size()!=CameraRecord::byte_size) throw std::runtime_error("Camera record must contain exactly 56 bytes");
            std::memcpy(camera.raw.data(),bytes.data(),bytes.size());
        })
        .def_property("name_hash",&CameraRecord::get<uint32_t,0>,&CameraRecord::set<uint32_t,0>)
        .def_property("fov_degrees",&CameraRecord::get<float,4>,[](CameraRecord& c,float value) {
            if(!std::isfinite(value) || value<=0 || value>=180) throw std::runtime_error("Camera vertical FOV must be between 0 and 180 degrees");
            c.set<float,4>(value);
        })
        .def_property("near",&CameraRecord::get<float,12>,[](CameraRecord& c,float value) {
            if(!std::isfinite(value) || value<=0) throw std::runtime_error("Camera near plane must be positive and finite");
            c.set<float,12>(value);
        })
        .def_property("far",&CameraRecord::get<float,16>,[](CameraRecord& c,float value) {
            if(!std::isfinite(value) || value<=0) throw std::runtime_error("Camera far plane must be positive and finite");
            c.set<float,16>(value);
        })
        .def_property("orthographic_scale",&CameraRecord::get<float,20>,[](CameraRecord& c,float value) {
            if(!std::isfinite(value) || value<=0) throw std::runtime_error("Camera orthographic scale must be positive and finite");
            c.set<float,20>(value);
        })
        .def_property("projection_flag",&CameraRecord::get<uint32_t,32>,&CameraRecord::set<uint32_t,32>);

    py::class_<Geom>(m, "Geom")
        .def(py::init<>())
        .def_property("bind_pose_snapshot",[](const Geom& g){return py::bytes(g.getBindPoseSnapshot());},
            [](Geom& g,py::bytes data){g.setBindPoseSnapshot(static_cast<std::string>(data));})
        .def_property_readonly("bind_pose_snapshot_matches",&Geom::bindPoseSnapshotMatches)
        .def_property_readonly("is_rigid_scene",&Geom::isRigidScene)
        .def_property("authored_bounds",&Geom::getAuthoredBounds,&Geom::setAuthoredBounds)
        .def_property_readonly("authored_bounds_match",&Geom::authoredBoundsMatch)
        .def_readwrite("unknown_0x10", &Geom::unknown_0x10)
        .def_readwrite("unknown_0x30", &Geom::unknown_0x30)
        .def_readwrite("unknown_0x34", &Geom::unknown_0x34)
        .def_property("clut", [](const Geom &g){
            constexpr size_t n = sizeof(g.clut);
            return py::bytes(reinterpret_cast<const char*>(&g.clut),n);
        },[](Geom &g, py::bytes b){
            constexpr size_t n = sizeof(g.clut);

            py::buffer_info info(py::buffer(b).request());
            size_t input_size = info.size; 
            const uint8_t* src = static_cast<const uint8_t*>(info.ptr);
            uint8_t* value = reinterpret_cast<uint8_t*>(&g.clut);

            if(input_size!=n) throw std::runtime_error("CLUT byte length does not match the format");
            memcpy(value,src,n);

        })
        .def_readwrite("skeleton", &Geom::skeleton)
        .def_property("cameras",make_vector_property(&Geom::cameras).first,
            make_vector_property(&Geom::cameras).second)
        .def_property("lights",make_vector_property(&Geom::lights).first,
            make_vector_property(&Geom::lights).second)
        .def_property(
            "meshes",
            make_vector_property(&Geom::meshes).first,
            make_vector_property(&Geom::meshes).second
        )
        .def_property(
            "materials",
            make_vector_property(&Geom::materials).first,
            make_vector_property(&Geom::materials).second
        )
        .def_static("from_bytes", [](py::bytes data, int base){
            Geom geom;
            std::string buf = data;
            std::istringstream f(buf, std::ios::binary);
            geom.read(f, base);
            return geom;
        }, py::arg("data"), py::arg("base")=0)
        .def_static("from_file", [](py::str filename, int base){
            Geom geom;
            std::istringstream f(dsts::python::read_file(filename), std::ios::binary);
            geom.read(f, base);
            return geom;
        }, py::arg("data"), py::arg("base")=0)
        .def("to_bytes", [](Geom &g) {
            MemoryStream f;
            g.write(f);
            return py::bytes(f.str());
        })
        .def("to_file", [](Geom &g, py::str filename){
            MemoryStream staged;
            g.write(staged);
            dsts::python::atomic_write(filename,staged.str());
        })
        .def("copy", &Geom::copy);
}
