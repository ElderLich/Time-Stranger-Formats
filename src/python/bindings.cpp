#include "bindings.hpp"
#include "skeleton.cpp"
#include "mesh.cpp"
#include "material.cpp"
#include "geom.cpp"

PYBIND11_MODULE(dsts_formats, m) {
    m.attr("__version__") = "0.2.0";
    m.attr("shader_parameter_schema") = "dsts-native-ff9de825";
    m.attr("shader_descriptor_schema") = "dsts-parameter-descriptor-v1";
    header_bindings(m);
    bind_skeleton(m);
    bind_mesh(m);
    bind_material(m);
    bind_geom(m);
}
