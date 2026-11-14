#pragma once

#include "../utils/checked_binary.hpp"

namespace dsts::geom {
// Validate binary ranges and cross references before the legacy object decoder
// allocates from counts or uses an index. No optional diagnostics can bypass this.
inline void validateGeomBinary(std::istream& stream, int base) {
    if(base<0) throw std::runtime_error("Negative GEOM base");
    dsts::CheckedBinary input(stream,static_cast<uint64_t>(base));
    const auto h=input.object<binary::GeomHeader>(0,"GEOM header");
    if(h.version!=316) throw std::runtime_error("Unsupported GEOM version (expected 316)");
    if(h.light_count) throw std::runtime_error("GEOM lights are not supported");
    if(h.camera_count) throw std::runtime_error("GEOM cameras are not supported");
    input.range(h.skeleton_offset,h.skeleton_file_size,1,"Embedded skeleton");
    Skeleton skeleton; skeleton.read(stream,h.skeleton_offset,static_cast<uint64_t>(base));
    if(h.ibpm_count!=skeleton.bones.size()) throw std::runtime_error("Inverse bind matrix count does not match skeleton");
    input.range(h.ibpm_offset,h.ibpm_count,sizeof(binary::Ibpm),"Inverse bind matrices");
    input.range(h.clut_offset,1,sizeof(binary::Clut),"Color table");
    const auto names=input.object<binary::NameTableHeader>(h.name_table_offset,"Name table");
    const auto bones=input.array<uint64_t>(names.bone_name_offsets_offset,names.bone_name_count,"Bone name offsets");
    const auto materials=input.array<uint64_t>(names.material_name_offsets_offset,names.material_name_count,"Material name offsets");
    for(auto offset:bones) input.string(dsts::checkedAdd(h.strings_offset,offset,"Bone name"),"Bone name");
    for(auto offset:materials) input.string(dsts::checkedAdd(h.strings_offset,offset,"Material name"),"Material name");
    const auto meshes=input.array<binary::MeshHeader>(h.mesh_offset,h.mesh_count,"Mesh headers");
    for(const auto& mesh:meshes) {
        if(mesh.controller_offset) throw std::runtime_error("Mesh controllers are not supported");
        if(mesh.index_type!=0) throw std::runtime_error("Unsupported mesh index encoding");
        if(mesh.primitive_type!=binary::Triangles && mesh.primitive_type!=binary::Triangle_strip)
            throw std::runtime_error("Unsupported mesh primitive");
        if(mesh.primitive_type==binary::Triangles && mesh.index_count%3)
            throw std::runtime_error("Triangle list index count is not divisible by three");
        if(mesh.material_idx>=h.material_count) throw std::runtime_error("Mesh material index is out of range");
        if(!mesh.matrix_palette_count) throw std::runtime_error("Meshes without a matrix palette are not supported");
        if(mesh.vertex_groups_per_vertex>4) throw std::runtime_error("More than four vertex influences are not supported");
        const auto palette=input.array<uint32_t>(mesh.matrix_palette_offset,mesh.matrix_palette_count,"Matrix palette");
        for(auto index:palette) if(index>=skeleton.bones.size()) throw std::runtime_error("Matrix palette bone index is out of range");
        const auto attributes=input.array<binary::MeshAttribute>(mesh.attributes_offset,mesh.attribute_count,"Vertex attributes");
        validateVertexLayout(attributes,mesh.bytes_per_vertex);
        const auto position=std::find_if(attributes.begin(),attributes.end(),[](const auto& a){return a.atype==binary::Position;});
        if(position==attributes.end() || (position->dtype!=binary::Float && position->dtype!=binary::Float_alias) ||
           position->count<(mesh.vertex_groups_per_vertex==1 ? 4 : 3))
            throw std::runtime_error("Unsupported or incomplete mesh position attribute");
        if(mesh.vertex_groups_per_vertex>1) {
            for(auto type:{binary::Index,binary::Weight}) {
                const auto attribute=std::find_if(attributes.begin(),attributes.end(),[type](const auto& a){return a.atype==type;});
                if(attribute==attributes.end() || attribute->count!=mesh.vertex_groups_per_vertex)
                    throw std::runtime_error("Vertex influence count does not match its attributes");
            }
        }
        input.range(mesh.vertices_offset,mesh.vertex_count,mesh.bytes_per_vertex,"Vertex buffer");
        const auto indices=input.array<uint16_t>(mesh.indices_offset,mesh.index_count,"Mesh indices");
        for(auto index:indices) if(index>=mesh.vertex_count) throw std::runtime_error("Mesh vertex index is out of range");
        if(mesh.name_hash && mesh.name_offset) input.string(dsts::checkedAdd(h.strings_offset,mesh.name_offset,"Mesh name"),"Mesh name");
    }
    uint64_t position=h.material_offset;
    for(size_t i=0;i<h.material_count;++i) {
        const auto material=input.object<binary::MaterialHeader>(position,"Material header");
        position=dsts::checkedAdd(position,sizeof(material),"Material data");
        const auto uniforms=input.array<binary::ShaderUniform>(position,material.uniform_count,"Shader uniforms");
        position=dsts::checkedAdd(position,uniforms.size()*sizeof(binary::ShaderUniform),"Shader settings");
        input.range(position,material.setting_count,sizeof(binary::ShaderSetting),"Shader settings");
        position=dsts::checkedAdd(position,material.setting_count*sizeof(binary::ShaderSetting),"Next material");
        for(const auto& uniform:uniforms) {
            if(uniform.float_count>4) throw std::runtime_error("Shader uniform exceeds its four-float payload");
            if(!uniform.float_count) {
                const auto offset=dsts::checkedAdd(h.strings_offset,uniform.payload.texture.texture_name_offset,"Texture name");
                input.range(offset,static_cast<uint64_t>(uniform.payload.texture.texture_name_length)+1,1,"Texture name");
                const auto name=input.string(offset,"Texture name");
                if(name.size()!=uniform.payload.texture.texture_name_length) throw std::runtime_error("Texture name length mismatch");
            }
        }
    }
    stream.clear();
}
}
