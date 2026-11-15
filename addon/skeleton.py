import bpy
import mathutils
from mathutils import Matrix, Vector
import sys
import statistics
import math
import json
from . import dsts_formats
from .export_guard import mark_skeleton_sections, require_supported_export

def import_skeleton(skeleton, target_collection=None, coordinate_remap=None, inverse_bind_matrices=None):
    """
    Imports a Skeleton object into Blender as an armature.
    Bone transforms are parent-relative authored rest transforms. When available,
    inverse bind matrices define the distinct skin bind pose.

    Leaf bones (no children) will get a tail offset equal to the median bone length
    to keep proportions consistent.
    """

    # Create Armature Data and Object
    armature_data = bpy.data.armatures.new("Skeleton")
    armature_obj = bpy.data.objects.new("Geom", armature_data)
    mark_skeleton_sections(armature_obj, skeleton)
    
    # Link to the target collection, fallback to current collection
    if target_collection is not None:
        target_collection.objects.link(armature_obj)
    else:
        bpy.context.collection.objects.link(armature_obj)

    # Set the new armature as active and switch to Edit Mode
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT')

    bone_map = {}

    # ---------------------------------------------------------
    # Coordinate remapping helper
    # ---------------------------------------------------------
    def apply_remap_matrix(matrix):
        """Applies a coordinate remap matrix if provided."""
        if coordinate_remap is None:
            return matrix
        if callable(coordinate_remap):
            return coordinate_remap(matrix)
        elif isinstance(coordinate_remap, mathutils.Matrix):
            return coordinate_remap @ matrix
        return matrix

    # ---------------------------------------------------------
    # Build global (bind) transforms
    # ---------------------------------------------------------
    def local_matrix(bone):
        """Calculates the bone's local transformation matrix."""
        q = bone.transform.quaternion
        p = bone.transform.position
        s = bone.transform.scale

        # Note: The quaternion is assumed to be (x,y,z,w) in the source data, 
        # converted to Blender's (w,x,y,z) order here.
        pos = mathutils.Vector(p[:3])
        scl = mathutils.Vector(s[:3])
        quat = mathutils.Quaternion((q[3], q[0], q[1], q[2])) 

        mat_loc = mathutils.Matrix.Translation(pos)
        mat_rot = quat.to_matrix().to_4x4()
        mat_scl = mathutils.Matrix.Diagonal((*scl, 1.0))
        # Local matrix composition: Translation * Rotation * Scale (T * R * S)
        return mat_loc @ mat_rot @ mat_scl

    global_mats = {}

    def compute_global(bone):
        """Recursively computes the global bind pose matrix for a bone."""
        if bone.name in global_mats:
            return global_mats[bone.name]
        if bone.parent:
            parent_mat = compute_global(bone.parent)
            global_mats[bone.name] = parent_mat @ local_matrix(bone)
        else:
            global_mats[bone.name] = local_matrix(bone)
        return global_mats[bone.name]

    # Compute global matrices for all bones
    for bone in skeleton.bones:
        compute_global(bone)

    bind_mats = dict(global_mats)
    if inverse_bind_matrices is not None:
        if len(inverse_bind_matrices) != len(skeleton.bones):
            raise ValueError('Inverse bind matrix count differs from skeleton')
        for bone, values in zip(skeleton.bones, inverse_bind_matrices):
            if bone.is_geometry:
                continue
            inverse = Matrix((values[0:4], values[4:8], values[8:12], (0, 0, 0, 1)))
            bind = inverse.inverted()
            # Blender edit bones cannot encode scale/shear. Refuse to pretend
            # their normalized rest matrix represents a scaled native bind.
            rotation = bind.to_quaternion().to_matrix().to_4x4()
            rotation.translation = bind.translation
            if max(abs(bind[r][c] - rotation[r][c]) for r in range(4) for c in range(4)) > 1e-4:
                raise ValueError('Reference adapter cannot represent a scaled or sheared bind matrix: ' + bone.name)
            bind_mats[bone.name] = bind

    # ---------------------------------------------------------
    # Create edit bones
    # ---------------------------------------------------------
    for bone in skeleton.bones:
        edit_bone = armature_data.edit_bones.new(bone.name)
        bone_map[edit_bone.name] = edit_bone
        # Ensure the name is updated in the source object for later lookups
        bone.name = edit_bone.name 

    # ---------------------------------------------------------
    # Compute head positions and children map
    # ---------------------------------------------------------
    head_positions = {}
    children_map = {}
    for bone in skeleton.bones:
        # Apply remap to the global matrix before extracting the position
        gmat = apply_remap_matrix(bind_mats[bone.name])
        head_positions[bone.name] = gmat.to_translation()
        if bone.parent:
            children_map.setdefault(bone.parent.name, []).append(bone.name)

    # Compute lengths of bones with children (to find median length)
    bone_lengths = []
    for bone_name, edit_bone in bone_map.items():
        child_names = children_map.get(bone_name, [])
        if child_names:
            # Average vector to children
            avg = mathutils.Vector((0, 0, 0))
            for cname in child_names:
                avg += head_positions[cname]
            avg /= len(child_names)
            length = (avg - head_positions[bone_name]).length
            if length > 0:
                bone_lengths.append(length)

    # Use median length for leaf bones (no children)
    median_length = statistics.median(bone_lengths) if bone_lengths else 0.1
    median_length = median_length if median_length > 0.1 else 0.1

    # ---------------------------------------------------------
    # Assign heads, tails, parents, and roll
    # ---------------------------------------------------------
    for bone in skeleton.bones:
        edit_bone = bone_map[bone.name]

        if bone.parent:
            edit_bone.parent = bone_map[bone.parent.name]

        # 2. Assign Head
        edit_bone.head = mathutils.Vector((0, 0, 0))
        edit_bone.tail = mathutils.Vector((0, 0, median_length))

        gmat = apply_remap_matrix(bind_mats[bone.name])
        edit_bone.matrix = gmat

    # Exit Edit Mode
    bpy.ops.object.mode_set(mode='OBJECT')

    # Native deformation is rest_world @ inverse_bind. Keep rest scale in the
    # pose, since assigning it to an edit bone silently discards that scale.
    if inverse_bind_matrices is not None:
        handled_bind_rest = []
        for bone in skeleton.bones:
            pose = armature_obj.pose.bones[bone.name]
            parent_args = {}
            if bone.parent:
                parent_args = {
                    'parent_matrix': apply_remap_matrix(global_mats[bone.parent.name]),
                    'parent_matrix_local': armature_data.bones[bone.parent.name].matrix_local,
                }
            pose.matrix_basis = pose.bone.convert_local_to_pose(
                apply_remap_matrix(global_mats[bone.name]), pose.bone.matrix_local,
                invert=True, **parent_args)
            if max(abs(pose.matrix_basis[r][c] - Matrix.Identity(4)[r][c])
                   for r in range(4) for c in range(4)) > 1e-4:
                handled_bind_rest.append(bone.name)
        bpy.context.view_layer.update()
        armature_obj['DSTS_handled_bind_rest_bones'] = json.dumps(handled_bind_rest)

    
    # Add custom geometry flag to Bone data (in Pose Mode/Object Mode)
    source_indices = {bone.name: index for index, bone in enumerate(skeleton.bones)}
    for bone in skeleton.bones:
        blender_bone = armature_data.bones[bone.name]
        blender_bone["DSTS_geometry"] = bone.is_geometry
        blender_bone['DSTS_source_bone_index'] = source_indices[bone.name]
        blender_bone['DSTS_source_rest'] = json.dumps({
            'matrix': [value for row in blender_bone.matrix_local for value in row],
            'parent': source_indices[bone.parent.name] if bone.parent else -1,
            'position': [float(v) for v in bone.transform.position],
            'quaternion': [float(v) for v in bone.transform.quaternion],
            'scale': [float(v) for v in bone.transform.scale],
        })

        rna_prop = blender_bone.id_properties_ui("DSTS_geometry")
        rna_prop.update(
            description="Marks this bone as geometry",
            default=bone.is_geometry
        )

    inverse_remap = apply_remap_matrix(Matrix.Identity(4)).inverted()
    armature_obj['DSTS_source_export_transform'] = [value for row in inverse_remap for value in row]
    return armature_obj

def export_skeleton(skeleton_obj, coord_transform = Matrix.Rotation(math.radians(-90), 4, 'X')):
    require_supported_export(skeleton_obj)
    skeleton = skeleton_obj.data
    skeleton_out = dsts_formats.Skeleton()
    original_transform = skeleton_obj.get('DSTS_source_export_transform', [])
    current_transform = [value for row in coord_transform for value in row]
    matching_transform = len(original_transform) == 16 and all(
        abs(a - b) < 1e-6 for a, b in zip(original_transform, current_transform))

    name_to_bone = {}
    for bone in skeleton.bones:
        bone_out = dsts_formats.Bone()
        bone_out.name = bone.name
        name_to_bone[bone.name] = bone_out

    for bone in skeleton.bones:
        bone_out = name_to_bone[bone.name]

        if bone.parent is None:
            mat = coord_transform @ bone.matrix_local
        else:
            bone_out.parent = name_to_bone[bone.parent.name]
            parent_mat = coord_transform @ bone.parent.matrix_local
            mat = parent_mat.inverted() @ (coord_transform @ bone.matrix_local)

        position, quaternion, scale = mat.decompose()

        bone_out.transform.position = position.to_4d()
        bone_out.transform.quaternion = (quaternion.x,quaternion.y,quaternion.z,quaternion.w)
        bone_out.transform.scale = scale.to_4d()

        # Preserve exact authored rest TRS for untouched bind bones. In
        # particular, Blender rest matrices cannot carry chr189's 0.1 scale.
        if matching_transform and 'DSTS_source_rest' in bone:
            original = json.loads(bone['DSTS_source_rest'])
            current_matrix = [value for row in bone.matrix_local for value in row]
            parent_index = bone.parent.get('DSTS_source_bone_index', -2) if bone.parent else -1
            parent_unchanged = bone.parent is None or (
                'DSTS_source_rest' in bone.parent and
                [value for row in bone.parent.matrix_local for value in row] ==
                json.loads(bone.parent['DSTS_source_rest'])['matrix'])
            if current_matrix == original['matrix'] and parent_index == original['parent'] and parent_unchanged:
                bone_out.transform.position = original['position']
                bone_out.transform.quaternion = original['quaternion']
                bone_out.transform.scale = original['scale']

        bone_out.is_geometry = bone.get("DSTS_geometry", False)

        skeleton_out.bones.append(bone_out)

    return skeleton_out
