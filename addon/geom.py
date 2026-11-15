import bpy
import os
import re
import base64
import json
from . import skeleton
from . import mesh
from . import material
from . import utils
from . import dsts_formats
from . import data
from .export_guard import mark_geom_sections, require_supported_export
from .bind_pose import inverse_bind_matrices
from pathlib import Path

def import_geom(context, filepath):
    error_state_old = dsts_formats.get_throw_errors()
    error_list_old = dsts_formats.get_error_list()
    dsts_formats.set_throw_errors(False)
    dsts_formats.set_error_list([])
    try:
        return _import_geom(context, filepath)
    finally:
        dsts_formats.set_throw_errors(error_state_old)
        dsts_formats.set_error_list(error_list_old)


def _import_geom(context, filepath):
    geom = dsts_formats.Geom.from_file(filepath)

    # Create collection
    new_collection = bpy.data.collections.new(name="Geom")
    context.scene.collection.children.link(new_collection)
    mark_geom_sections(new_collection, geom)

    new_collection["unknown_0x10"] = geom.unknown_0x10
    new_collection["unknown_0x30"] = geom.unknown_0x30
    new_collection["unknown_0x34"] = geom.unknown_0x34

    new_collection["CLUT"] = base64.b64encode(bytes(geom.clut)).decode("ascii")
    new_collection['DSTS_bind_pose_snapshot'] = base64.b64encode(geom.bind_pose_snapshot).decode('ascii')

    # Import Skeleton
    armature_obj = skeleton.import_skeleton(geom.skeleton, new_collection, utils.unflop,
                                           inverse_bind_matrices(geom))

    # Import Materials
    blender_materials = {}
    new_collection['DSTS_source_materials'] = json.dumps([
        {'name': mat.name, 'hash': int(mat.name_hash)} for mat in geom.materials])
    # Pre-calculate image path base
    base_path = str(Path(filepath).parent) + os.sep + "images"
    
    for material_index, mat_data in enumerate(geom.materials):
        source_name, source_hash = mat_data.name, int(mat_data.name_hash)
        mat = bpy.data.materials.new(name=mat_data.name)
        # Fix name collision handled by Blender
        mat_data.name = mat.name 
        material.resolve_material(new_collection, mat, mat_data, base_path)
        mat['DSTS_source_material_index'] = material_index
        mat['DSTS_source_material_name'] = source_name
        mat['DSTS_source_name_hash'] = str(source_hash)
        blender_materials[mat_data.name] = mat

    # Import Objects (Optimized)
    for mesh_obj in geom.meshes:
        # The new function handles mesh build, obj creation, linking, materials, and weights
        mesh.import_mesh_object(
            mesh_obj, 
            armature_obj, 
            blender_materials, 
            new_collection
        )
        #handle material vertex buffer layout
        mat = blender_materials[mesh_obj.material.name]
        attr_list = [
            {"count": attr.count, "offset": attr.offset, "atype": attr.atype, "dtype": attr.dtype}
            for attr in mesh_obj.mesh_attributes
        ]
        g_node = next(n for n in mat.node_tree.nodes if n.type == "GROUP" and n.node_tree.name.startswith(f"DSTS_Data-{mat.name}") )
        data_node = next(n for n in g_node.node_tree.nodes if type(n) == data.material_nodes.ShaderDataNode)
        if len(data_node.attributes) == 0:
            data_node.bytes_per_vertex = mesh_obj.bytes_per_vertex
            for attr in attr_list:
                at = data_node.attributes.add()
                at.count, at.offset, at.atype, at.dtype = attr.values()


    error_list = dsts_formats.get_error_list()
    new_collection['DSTS_backend_diagnostics'] = '\n'.join(error_list)
    corrected = {'Inverse bind matrix differs from computed pose: ' + name
                 for name in json.loads(armature_obj.get('DSTS_handled_bind_rest_bones', '[]'))}
    handled = [message for message in error_list if message in corrected]
    error_list = [message for message in error_list if message not in corrected]
    if handled:
        new_collection['DSTS_handled_bind_rest_notes'] = '\n'.join(handled)
        print(f'[DSTS] Preserved {len(handled)} authored bind/rest differences; details retained on collection.')

    if error_list:
        if bpy.app.background:
            print('[DSTS] Import warnings:', '\n'.join(error_list))
        else:
            bpy.ops.wm.show_errors_window('INVOKE_DEFAULT', errors="\n\n".join(error_list))

    return new_collection

def export_geom(collection):
    require_supported_export(collection)
    geom = dsts_formats.Geom()

    geom.unknown_0x10 = collection["unknown_0x10"]
    geom.unknown_0x30 = collection["unknown_0x30"]
    geom.unknown_0x34 = collection["unknown_0x34"]

    geom.clut = base64.b64decode(bytes(collection["CLUT"], "ascii"))

    armatures = [o for o in collection.objects if o.type == "ARMATURE"]
    if not armatures:
        raise ValueError("No armature found in collection")

    geom.skeleton = skeleton.export_skeleton(armatures[0])
    if 'DSTS_bind_pose_snapshot' in collection:
        geom.bind_pose_snapshot = base64.b64decode(collection['DSTS_bind_pose_snapshot'], validate=True)

    object_to_mat, name_to_sources = {}, {}
    source_materials = json.loads(collection.get('DSTS_source_materials', '[]'))
    materials = list({o.data.materials[0] for o in collection.objects if o.type == "MESH"})
    materials.sort(key=lambda mat: int(mat.get('DSTS_source_material_index', len(source_materials))))
    for mat in materials:
        native_name = re.sub(r"(\.[0-9]{3})?$", "", mat.name)
        index = mat.get('DSTS_source_material_index', -1)
        identity = (int(index) if isinstance(index, int) and 0 <= index < len(source_materials)
                    and source_materials[index]['name'] == native_name
                    and mat.get('DSTS_source_material_name') == native_name
                    and str(source_materials[index]['hash']) == mat.get('DSTS_source_name_hash') else None)
        previous = name_to_sources.setdefault(native_name, [])
        if previous and (identity is None or None in previous or identity in previous):
            raise ValueError(f"Materials resolve to the same native name '{native_name}'; rename split materials before export")
        previous.append(identity)
    for mat in materials:
        native_name = re.sub(r"(\.[0-9]{3})?$", "", mat.name)
        mat_data = material.export_material(mat)
        mat_data.name = native_name
        geom.materials.append(mat_data)
        object_to_mat[mat] = mat_data

    for obj in [o for o in collection.objects if o.type == "MESH"]:
        mesh_out = mesh.export_mesh_object(obj, geom.skeleton)
        mesh_out.material = object_to_mat[obj.data.materials[0]]
        geom.meshes.append(mesh_out)

    for obj in [*geom.skeleton.bones] + [*geom.materials] + [*geom.meshes]:
        obj.name = re.sub(r"(\.[0-9]{3})?$", "", obj.name)

    return geom
