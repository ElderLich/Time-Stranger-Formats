"""Run with the Python ABI used to build dsts_formats; pass --module-dir to select it."""
import argparse
import gc
import importlib
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

import numpy as np


def example():
    geom = formats.Geom()
    bone = formats.Bone(); bone.name = 'root'
    geom.skeleton.bones = [bone]
    material = formats.Material(); material.name = 'material'
    uniform = formats.ShaderUniform(); uniform.parameter_id = 25
    uniform.value = np.array([1, .5, .25, 1], dtype=np.float32)
    material.uniforms = [uniform]; geom.materials = [material]
    mesh = formats.Mesh(); mesh.name = 'triangle'; mesh.material = material; mesh.matrix_palette = [bone]
    mesh.set_vertex_count(3)
    mesh.set_position(np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32))
    mesh.set_index(np.zeros((3, 1), dtype=np.uint8))
    mesh.set_weight(np.ones((3, 1), dtype=np.float16))
    mesh.indices = [0, 1, 2]; mesh.primitive = 1
    geom.meshes = [mesh]
    return geom


class SafetyTests(unittest.TestCase):
    def setUp(self):
        formats.set_throw_errors(True)

    def test_synthetic_roundtrip_and_vertex_layout(self):
        before = example(); encoded = before.to_bytes(); after = formats.Geom.from_bytes(encoded)
        self.assertEqual(len(after.meshes), 1)
        self.assertEqual(list(after.meshes[0].indices), [0, 1, 2])
        np.testing.assert_array_equal(after.meshes[0].vertices[1].position[:3], [1, 0, 0])
        self.assertEqual(after.materials[0].uniforms[0].parameter_name, 'DiffuseColor')
        self.assertEqual(formats.Geom.from_bytes(after.to_bytes()).meshes[0].name, 'triangle')
        self.assertEqual(formats.Geom.from_bytes(b'prefix-prefix---'+encoded,16).meshes[0].name,'triangle')
        # Empty defaults also produce a complete, readable object.
        self.assertEqual(len(formats.Geom.from_bytes(formats.Geom().to_bytes()).meshes), 0)

    def test_all_truncated_prefixes_are_errors(self):
        data = example().to_bytes()
        for size in range(len(data)):
            with self.subTest(size=size), self.assertRaises(Exception):
                formats.Geom.from_bytes(data[:size])

    def test_malformed_offsets_counts_and_indices(self):
        data = example().to_bytes()
        mesh = struct.unpack_from('<Q', data, 0x48)[0]
        names = struct.unpack_from('<Q', data, 0x90)[0]
        skeleton = struct.unpack_from('<Q', data, 0x98)[0]
        material = struct.unpack_from('<Q', data, 0x50)[0]
        palette = struct.unpack_from('<Q', data, mesh + 0x10)[0]
        indices = struct.unpack_from('<Q', data, mesh + 8)[0]
        attributes = struct.unpack_from('<Q', data, mesh + 0x20)[0]
        mutations = [('version', 0, '<I', 999), ('offset overflow', 0x48, '<Q', 2**64-1),
            ('unsupported lights',8,'<H',1), ('unsupported camera',10,'<H',1),
            ('unsupported controller',mesh+0x70,'<Q',16), ('unsupported float channels',skeleton+0x12,'<H',1),
            ('name count', names, '<I', 2**32-1), ('stride zero', mesh+0x2c, '<H', 0),
            ('vertex count', mesh+0x44, '<I', 2**32-1), ('attribute capacity', attributes+2, '<H', 5),
            ('attribute stride', attributes+6, '<H', 65535), ('dtype', attributes+4, '<H', 65535),
            ('palette', palette, '<I', 1), ('index', indices, '<H', 3),
            ('material index', mesh+0x40, '<I', 1), ('uniform count', material+0x328+0x12, '<H', 5),
            ('parent pair count', skeleton+0x3c, '<I', 2**32-1), ('parent cycle', skeleton+0x40+2, '<H', 0)]
        for collect in [False, True]:
            formats.set_throw_errors(not collect)
            for name, offset, kind, value in mutations:
                changed = bytearray(data); struct.pack_into(kind, changed, offset, value)
                with self.subTest(name=name, collect=collect), self.assertRaises(Exception):
                    formats.Geom.from_bytes(bytes(changed))
        for base in [-1, len(data)+1, 2**31-1]:
            with self.assertRaises(Exception): formats.Geom.from_bytes(data, base)

    def test_standalone_skeleton_bounds_and_cycles(self):
        skeleton = example().skeleton
        encoded = skeleton.to_bytes()
        self.assertEqual(len(formats.Skeleton.from_bytes(encoded).bones), 1)
        unnamed = formats.Skeleton.from_bytes(encoded)
        self.assertFalse(unnamed.bones[0].name)
        self.assertNotEqual(unnamed.bones[0].name_hash, 0)
        self.assertEqual(formats.Skeleton.from_bytes(unnamed.to_bytes()).bones[0].name_hash, unnamed.bones[0].name_hash)
        for size in range(len(encoded)):
            with self.assertRaises(Exception): formats.Skeleton.from_bytes(encoded[:size])
        bone = skeleton.bones[0]; bone.parent = bone
        with self.assertRaisesRegex(Exception, 'cycle'): skeleton.to_bytes()
        with self.assertRaisesRegex(Exception, 'cycle'): _ = bone.transform_actual
        bone.parent = None

    def test_mesh_raw_buffers_and_array_shapes(self):
        mesh = formats.Mesh(); mesh.set_vertex_count(3)
        with self.assertRaises(Exception): formats.VertexAttribute('float', 5)
        with self.assertRaises(Exception): mesh.unpack_vertices([], 0, b'')
        desc = formats.MeshAttribute(); desc.atype = 'position'; desc.dtype = 'float'; desc.count = 3; desc.offset = 0
        with self.assertRaises(Exception): mesh.unpack_vertices([desc], 12, b'abc')
        desc.count = 5
        with self.assertRaises(Exception): mesh.unpack_vertices([desc], 12, bytes(12))
        for method, data in [('set_position', np.zeros((4,3),np.float32)),
                             ('set_normal',np.zeros((4,3),np.float16)),
                             ('set_color',np.zeros((4,4),np.uint8)),
                             ('set_tangent',np.zeros((4,4),np.float16)),
                             ('set_index',np.zeros((4,1),np.uint8)),
                             ('set_weight',np.zeros((4,1),np.float16))]:
            with self.subTest(method=method), self.assertRaises(Exception): getattr(mesh,method)(data)
        with self.assertRaises(Exception): mesh.set_uv(0,np.zeros((3,2),np.float32))
        with self.assertRaises(Exception): mesh.set_uv(1,np.zeros((4,2),np.float32))
        data=np.arange(18,dtype=np.float16).reshape(3,6)[:,::2]
        mesh.set_normal(data)
        np.testing.assert_array_equal(mesh.vertices[1].normal,data[1])
        snapshot=mesh.vertices[1].normal; mesh.set_vertex_count(0); gc.collect()
        np.testing.assert_array_equal(snapshot,data[1])

    def test_write_validation_preserves_existing_file(self):
        geom = example(); geom.meshes[0].matrix_palette = []
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'existing.geom'; output.write_bytes(b'original')
            with self.assertRaises(Exception): geom.to_file(str(output))
            self.assertEqual(output.read_bytes(),b'original')
        geom = example()
        with self.assertRaises(Exception):
            geom.materials[0].uniforms[0].value=np.arange(5,dtype=np.float32)
            geom.to_bytes()
        geom = example(); geom.meshes[0].material=None
        with self.assertRaises(Exception): geom.to_bytes()
        geom = example(); copied=geom.clut; del geom;gc.collect()
        self.assertEqual(len(copied),0x41c)
        with self.assertRaises(Exception): formats.Geom().clut=b'short'


def corpus(root, limit, output, collect=False):
    candidates = sorted(root.rglob('chr*.geom'))
    random.Random(316).shuffle(candidates)
    rows=[]
    formats.set_throw_errors(not collect)
    for path in candidates[:limit]:
        formats.set_error_list([])
        try:
            geom=formats.Geom.from_file(str(path))
            rewritten=geom.to_bytes()
            check=formats.Geom.from_bytes(rewritten)
            assert len(check.meshes)==len(geom.meshes) and len(check.skeleton.bones)==len(geom.skeleton.bones)
            for a,b in zip(geom.meshes,check.meshes):
                assert a.name==b.name and list(a.indices)==list(b.indices)
                assert len(a.vertices)==len(b.vertices) and len(a.matrix_palette)==len(b.matrix_palette)
                for i in {0,len(a.vertices)//2,len(a.vertices)-1}:
                    if i>=0:np.testing.assert_allclose(a.vertices[i].position[:3],b.vertices[i].position[:3],rtol=0,atol=0)
            rows.append({'file':str(path),'ok':True,'meshes':len(geom.meshes),'bones':len(geom.skeleton.bones),
                         'semanticDiagnostics':formats.get_error_list()})
        except Exception as error:rows.append({'file':str(path),'ok':False,'error':str(error)})
    report={'sampled':len(rows),'passed':sum(r['ok'] for r in rows),'collectSemanticDiagnostics':collect,'results':rows}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))
    for row in rows:
        if not row['ok']:print(row['file'],row['error'][:300])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-dir',type=Path,required=True)
    parser.add_argument('--corpus',type=Path)
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--report',type=Path,default=Path('local/binary-safety-corpus.json'))
    parser.add_argument('--collect-semantic',action='store_true')
    args=parser.parse_args();sys.path.insert(0,str(args.module_dir.resolve()));formats=importlib.import_module('dsts_formats')
    if args.corpus:corpus(args.corpus,args.limit,args.report,args.collect_semantic)
    else:unittest.main(argv=[sys.argv[0]])
