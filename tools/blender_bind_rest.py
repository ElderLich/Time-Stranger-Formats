"""External-fixture Blender check for distinct native bind/rest poses.

Pass --module path/to/dsts_formats.cp313-win_amd64.pyd --source chr189.geom
--output an/absent/directory. This does not install the reference adapter.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

parser = argparse.ArgumentParser()
parser.add_argument('--module', type=Path, required=True)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.output = args.output.resolve()
args.output.mkdir(parents=True, exist_ok=False)
spec = importlib.util.spec_from_file_location('dsts_formats', args.module)
formats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formats)
root = Path(__file__).resolve().parents[1] / 'addon'
name = 'DSTS_reference'
spec = importlib.util.spec_from_file_location(name, root / '__init__.py', submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[name] = addon
sys.modules[name + '.dsts_formats'] = formats
spec.loader.exec_module(addon)
addon.register()
formats.set_throw_errors(False)
raw = args.source.read_bytes()
native = formats.Geom.from_bytes(raw)
collection = addon.import_geom(bpy.context, str(args.source))
rig = next(obj for obj in collection.objects if obj.type == 'ARMATURE')
assert len(collection['DSTS_backend_diagnostics'].splitlines()) == 14
assert len(collection['DSTS_handled_bind_rest_notes'].splitlines()) == 14
worlds = {}
def world(bone):
    if bone.name not in worlds:
        t = bone.transform
        q = t.quaternion
        local = Matrix.LocRotScale(Vector(t.position[:3]), Quaternion((q[3], *q[:3])), Vector(t.scale[:3]))
        worlds[bone.name] = world(bone.parent) @ local if bone.parent else local
    return worlds[bone.name]
axis = Matrix.Rotation(1.5707963267948966, 4, 'X')
offset = struct.unpack_from('<Q', raw, 0x68)[0]
maximum = 0
for index, bone in enumerate(native.skeleton.bones):
    if bone.is_geometry:
        continue
    inverse = Matrix((*[struct.unpack_from('<4f', raw, offset + index * 48 + row * 16)
                        for row in range(3)], (0, 0, 0, 1)))
    expected = axis @ world(bone) @ inverse @ axis.inverted()
    pose = rig.pose.bones[bone.name]
    actual = pose.matrix @ pose.bone.matrix_local.inverted()
    maximum = max(maximum, max(abs(actual[r][c] - expected[r][c]) for r in range(4) for c in range(4)))
assert maximum < 3e-4, maximum
exported = addon.export_geom(collection)
assert exported.bind_pose_snapshot_matches
assert exported.bind_pose_snapshot == native.bind_pose_snapshot
path = args.output / 'chr189.geom'
exported.to_file(str(path))
encoded = path.read_bytes()
at = struct.unpack_from('<Q', encoded, 0x68)[0]
assert encoded[at:at + 48 * len(native.skeleton.bones)] == raw[offset:offset + 48 * len(native.skeleton.bones)]
readback = formats.Geom.from_file(str(path))
assert len(readback.materials) == len(native.materials)
assert [list(readback.materials).index(m.material) for m in readback.meshes] == [list(native.materials).index(m.material) for m in native.meshes]
for a, b in zip(native.skeleton.bones, readback.skeleton.bones):
    for prop in ('position', 'quaternion', 'scale'):
        assert list(getattr(a.transform, prop)) == list(getattr(b.transform, prop))
meshes = [obj for obj in collection.objects if obj.type == 'MESH']
original = meshes[1].data.materials[0]
duplicate = meshes[0].data.materials[0].copy()
meshes[1].data.materials[0] = duplicate
try:
    addon.export_geom(collection)
    raise AssertionError('Copied material identity was accepted')
except ValueError as exc:
    assert 'same native name' in str(exc)
finally:
    meshes[1].data.materials[0] = original
    bpy.data.materials.remove(duplicate)
report = {'status': 'pass', 'source_sha256': hashlib.sha256(raw).hexdigest(),
          'source': str(args.source.resolve()), 'skin_matrix_error': maximum,
          'backend_diagnostics_retained': 14, 'handled_bind_rest_notes': 14,
          'bone_trs_exact': True, 'inverse_bind_bytes_exact': True,
          'material_variants_and_assignments_exact': True, 'copied_material_rejected': True,
          'blender': bpy.app.version_string}
(args.output / 'bind-rest-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS reference bind/rest:', json.dumps(report))
