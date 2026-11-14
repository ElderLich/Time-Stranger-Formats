"""Run with the Python ABI used to build dsts_formats; pass --module-dir to select it."""
import argparse
import gc
import importlib
import importlib.util
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

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


def preserved_sections(data):
    """Independent byte-level oracle for records and ordered float bindings."""
    sections={}
    for name,count_at,offset_at,width in [('lights',8,0x58,240),('cameras',10,0x60,56),('ibpm',12,0x68,48)]:
        count=struct.unpack_from('<H',data,count_at)[0];offset=struct.unpack_from('<Q',data,offset_at)[0]
        sections[name]=[data[offset+i*width:offset+(i+1)*width] for i in range(count)]
    skeleton=struct.unpack_from('<Q',data,0x98)[0];count=struct.unpack_from('<H',data,skeleton+18)[0]
    tables=[]
    for offset,kind,width in [(36,'I',4),(40,'I',4),(44,'B',1)]:
        start=skeleton+offset+struct.unpack_from('<I',data,skeleton+offset)[0]
        tables.append([struct.unpack_from('<'+kind,data,start+width*i)[0] for i in range(count)])
    sections['float_channels']=list(zip(*tables))
    bone_count=struct.unpack_from('<H',data,skeleton+16)[0]
    pair_count=struct.unpack_from('<I',data,skeleton+60)[0]
    sections['parent_pairs']=list(struct.iter_unpack('<HH',data[skeleton+64:skeleton+64+4*pair_count]))
    start=skeleton+28+struct.unpack_from('<I',data,skeleton+28)[0]
    sections['parent_table']=list(struct.unpack_from('<'+'H'*bone_count,data,start))
    # Independent material contract oracle. Texture string offsets can move
    # with layout; compare their resolved names and retain all other bytes.
    material_count=struct.unpack_from('<H',data,6)[0]
    position=struct.unpack_from('<Q',data,0x50)[0]
    strings=struct.unpack_from('<Q',data,0x78)[0]
    materials=[]
    for _ in range(material_count):
        header=data[position:position+0x328];position+=0x328
        uniforms=[]
        for _ in range(header[0x320]):
            raw=data[position:position+32];position+=32
            if struct.unpack_from('<H',raw,18)[0]:uniforms.append(raw)
            else:
                offset,length=struct.unpack_from('<QI',raw)
                uniforms.append((data[strings+offset:strings+offset+length],raw[8:]))
        settings=data[position:position+32*header[0x321]];position+=32*header[0x321]
        materials.append((header,uniforms,settings))
    sections['materials']=materials
    return sections


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
            ('null light table',8,'<H',1), ('null camera table',10,'<H',1),
            ('unsupported controller',mesh+0x70,'<Q',16),
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

    def test_atomic_file_publication_preserves_destination_on_io_failure(self):
        geom = example()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'existing-雪.geom'
            original = b'preserved original'
            output.write_bytes(original)
            for operation in ('replace', 'fsync'):
                with self.subTest(operation=operation):
                    with patch('os.' + operation, side_effect=OSError('injected write failure')):
                        with self.assertRaisesRegex(OSError, 'injected write failure'):
                            geom.to_file(str(output))
                    self.assertEqual(output.read_bytes(), original)
                    self.assertEqual(list(Path(folder).iterdir()), [output])
            geom.to_file(str(output))
            self.assertEqual(output.read_bytes(), geom.to_bytes())

    def test_contiguous_palette_flag_matches_native_upload(self):
        geom=example(); root=geom.skeleton.bones[0]
        children=[]
        for i in range(3):
            bone=formats.Bone();bone.name=f'joint{i}';bone.parent=root;children.append(bone)
        geom.skeleton.bones=[root,*children]
        mesh=geom.meshes[0];mesh.flag_2=True
        # Native memcpy starts at the first stored index, so a nonzero start
        # and a single bone are legitimate; do not ban the optimization.
        for palette in ([children[0]], children[:2], children):
            for bone in children:bone.is_geometry=False
            if len(palette)==1:palette[0].is_geometry=True
            mesh.matrix_palette=palette
            parsed=formats.Geom.from_bytes(geom.to_bytes())
            self.assertTrue(parsed.meshes[0].flag_2)
            self.assertEqual([b.name for b in parsed.meshes[0].matrix_palette],[b.name for b in palette])
        for palette in ([root,children[1]], [children[1],children[0]], [root,root]):
            mesh.matrix_palette=palette
            for collect in (False,True):
                formats.set_throw_errors(not collect)
                with self.subTest(palette=[b.name for b in palette],collect=collect):
                    with self.assertRaisesRegex(RuntimeError,'contiguous ascending'):geom.to_bytes()
                    with tempfile.TemporaryDirectory() as folder:
                        target=Path(folder)/'keep.geom';target.write_bytes(b'keep')
                        with self.assertRaisesRegex(RuntimeError,'contiguous ascending'):geom.to_file(str(target))
                        self.assertEqual(target.read_bytes(),b'keep')
        formats.set_throw_errors(True)
        # Sparse palettes use the gather branch. Keep forensic/native reads
        # available even when a pre-existing file has the invalid fast flag.
        mesh.flag_2=False;mesh.matrix_palette=[root,children[1]]
        raw=bytearray(geom.to_bytes());header=struct.unpack_from('<Q',raw,0x48)[0]
        raw[header+0x31]|=4
        parsed=formats.Geom.from_bytes(bytes(raw))
        self.assertTrue(parsed.meshes[0].flag_2)
        self.assertEqual([b.name for b in parsed.meshes[0].matrix_palette],['root','joint1'])
        with self.assertRaisesRegex(RuntimeError,'contiguous ascending'):parsed.to_bytes()
        parsed.meshes[0].flag_2=False
        self.assertFalse(formats.Geom.from_bytes(parsed.to_bytes()).meshes[0].flag_2)

    def test_parent_pairs_fill_native_simd_groups_safely(self):
        for count in range(1,7):
            skeleton=formats.Skeleton();bones=[]
            for i in range(count):
                bone=formats.Bone();bone.name=f'joint{i}'
                if bones:bone.parent=bones[-1]
                bones.append(bone)
            skeleton.bones=bones
            raw=skeleton.to_bytes();pair_count=struct.unpack_from('<I',raw,60)[0]
            self.assertEqual(pair_count,(count+3)//4*4)
            pairs=list(struct.iter_unpack('<HH',raw[64:64+4*pair_count]))
            expected=[(i,i-1 if i else 0x7fff) for i in range(count)]
            self.assertEqual(pairs,expected+[expected[-1]]*(pair_count-count))
            # Model the native write-local-then-read-parent ordering with
            # nonidentity owner/local translations. A padded (0,0) would lose
            # the owner translation, even though every index remains in range.
            owner=np.eye(4);owner[0,3]=100
            local=[]
            for i in range(count):
                matrix=np.eye(4);matrix[0,3]=i+1;local.append(matrix)
            world=[np.eye(4) for _ in bones]
            for child,parent in pairs:
                world[child]=local[child].copy()
                world[child]=(owner if parent==0x7fff else world[parent])@world[child]
            for i in range(count):self.assertEqual(world[i][0,3],100+(i+1)*(i+2)/2)
            self.assertEqual(formats.Skeleton.from_bytes(raw).to_bytes(),raw)
        # Existing source records, including the physical tail outside a
        # legacy declared count, are preserved rather than silently repaired.
        skeleton=formats.Skeleton();bone=formats.Bone();bone.name='root';skeleton.bones=[bone]
        raw=bytearray(skeleton.to_bytes());struct.pack_into('<I',raw,60,1)
        struct.pack_into('<H',raw,64+4+2,0xffff)
        source=formats.Skeleton.from_bytes(bytes(raw))
        self.assertEqual(source.to_bytes(),raw)
        extra=formats.Bone();extra.name='extra';extra.parent=source.bones[0]
        source.bones=[source.bones[0],extra]
        with self.assertRaisesRegex(RuntimeError,'flagged skeleton'):source.to_bytes()

    def test_camera_light_and_float_metadata_roundtrip(self):
        geom=example()
        camera=formats.CameraRecord();camera.raw=bytes(range(56));camera.name_hash=geom.skeleton.bones[0].name_hash
        camera.fov_degrees=45;camera.near=.1;camera.far=1000;camera.orthographic_scale=5;camera.projection_flag=1
        light=formats.LightRecord();light.raw=bytes(range(240));light.name_hash=camera.name_hash
        geom.cameras=[camera,camera];geom.lights=[light,light]
        channels=[]
        for index,hash_,flags in [(7,camera.name_hash,0),(0xFFFFFFFF,0xABCDEF12,255),(1089,0x12345678,8)]:
            channel=formats.FloatChannel();channel.array_index=index;channel.name_hash=hash_;channel.flags=flags;channels.append(channel)
        geom.skeleton.float_channels=channels
        data=geom.to_bytes();reread=formats.Geom.from_bytes(data)
        self.assertEqual(preserved_sections(data),preserved_sections(reread.to_bytes()))
        self.assertEqual([c.raw for c in reread.cameras],[camera.raw,camera.raw])
        self.assertEqual([v.raw for v in reread.lights],[light.raw,light.raw])
        self.assertEqual(reread.cameras[0].fov_degrees,45)
        self.assertEqual([c.flags for c in reread.skeleton.float_channels],[0,255,8])
        reread.cameras[0].fov_degrees=50
        self.assertEqual(formats.Geom.from_bytes(reread.to_bytes()).cameras[0].fov_degrees,50)
        snapshot=reread.cameras[1].raw;del reread;gc.collect();self.assertEqual(snapshot,camera.raw)
        with self.assertRaises(Exception): camera.raw=bytes(55)
        with self.assertRaises(Exception): light.raw=bytes(239)
        with self.assertRaises(Exception): camera.fov_degrees=float('nan')
        # A known lens edit changes only its native word, preserving opaque data.
        before=camera.raw;camera.fov_degrees=60
        self.assertEqual(before[:4]+before[8:],camera.raw[:4]+camera.raw[8:])

    def test_scene_table_ranges_are_mandatory(self):
        geom=example();camera=formats.CameraRecord();light=formats.LightRecord();channel=formats.FloatChannel()
        geom.cameras=[camera];geom.lights=[light];geom.skeleton.float_channels=[channel]
        data=geom.to_bytes();s=struct.unpack_from('<Q',data,0x98)[0]
        mutations=[('camera overflow',0x60,'<Q',2**64-1),('light overflow',0x58,'<Q',2**64-1),
            ('camera count',10,'<H',65535),('light count',8,'<H',65535),
            ('float count',s+18,'<H',65535),('float indices',s+36,'<I',2**32-1),
            ('float hashes',s+40,'<I',2**32-1),('float flags',s+44,'<I',2**32-1),
            ('null float indices',s+36,'<I',0),('null float hashes',s+40,'<I',0),('null float flags',s+44,'<I',0),
            ('skeleton limit',s+4,'<Q',64)]
        for collect in [False,True]:
            formats.set_throw_errors(not collect)
            for name,at,kind,value in mutations:
                raw=bytearray(data);struct.pack_into(kind,raw,at,value)
                with self.subTest(name=name,collect=collect),self.assertRaises(Exception):formats.Geom.from_bytes(bytes(raw))
        skeleton=geom.skeleton.to_bytes()
        for length in range(len(skeleton)):
            with self.assertRaises(Exception):formats.Skeleton.from_bytes(skeleton[:length])

    def test_original_bind_matrices_survive_unchanged_pose(self):
        geom=formats.Geom();bone=formats.Bone();bone.name='root';geom.skeleton.bones=[bone]
        original=bytearray(geom.to_bytes());offset=struct.unpack_from('<Q',original,0x68)[0]
        struct.pack_into('<f',original,offset+12,13.0)
        formats.set_throw_errors(False)
        source=formats.Geom.from_bytes(bytes(original));source.skeleton.bones[0].name='renamed'
        self.assertEqual(preserved_sections(source.to_bytes())['ibpm'],preserved_sections(original)['ibpm'])
        source.skeleton.bones[0].transform.position=np.array([2,0,0,1],np.float32)
        edited=source.to_bytes();at=struct.unpack_from('<Q',edited,0x68)[0]
        self.assertEqual(struct.unpack_from('<f',edited,at+12)[0],-2.0)
        # A captured zero-scale pose can retain its authored matrix; editing the
        # pose requires recomputation and must never substitute identity.
        s=struct.unpack_from('<Q',original,0x98)[0]
        transform=s+24+struct.unpack_from('<I',original,s+24)[0]
        struct.pack_into('<f',original,transform+32,0.0)
        singular=formats.Geom.from_bytes(bytes(original))
        self.assertEqual(preserved_sections(singular.to_bytes())['ibpm'],preserved_sections(original)['ibpm'])
        singular.skeleton.bones[0].transform.position=np.array([1,0,0,1],np.float32)
        with self.assertRaisesRegex(Exception,'singular'):singular.to_bytes()

    def test_flagged_parent_encoding_and_preservation(self):
        skeleton=formats.Skeleton();a=formats.Bone();b=formats.Bone();a.name='a';b.name='b';b.parent=a;skeleton.bones=[a,b]
        raw=bytearray(skeleton.to_bytes());struct.pack_into('<H',raw,64+4+2,0x8000)
        parsed=formats.Skeleton.from_bytes(bytes(raw))
        self.assertEqual(parsed.bones[1].parent,parsed.bones[0])
        self.assertEqual(parsed.to_bytes()[64:72],raw[64:72])
        parsed.bones[1].parent=None
        with self.assertRaisesRegex(Exception,'flagged skeleton'):parsed.to_bytes()

    def test_reference_addon_export_guard(self):
        spec=importlib.util.spec_from_file_location('export_guard',Path(__file__).parents[1]/'addon/export_guard.py')
        guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        geom=example();owner={};guard.mark_geom_sections(owner,geom);guard.require_supported_export(owner)
        geom.cameras=[formats.CameraRecord()];guard.mark_geom_sections(owner,geom)
        with self.assertRaisesRegex(ValueError,'camera records'):guard.require_supported_export(owner)
        armature={};channel=formats.FloatChannel();geom.skeleton.float_channels=[channel]
        guard.mark_skeleton_sections(armature,geom.skeleton)
        with self.assertRaisesRegex(ValueError,'float-channel bindings'):guard.require_supported_export(armature)

    def test_compact_bind_pose_snapshot_transfer_and_validation(self):
        original=formats.Geom();bone=formats.Bone();bone.name='root';original.skeleton.bones=[bone]
        raw=bytearray(original.to_bytes());at=struct.unpack_from('<Q',raw,0x68)[0];struct.pack_into('<f',raw,at+12,13)
        formats.set_throw_errors(False)
        imported=formats.Geom.from_bytes(bytes(raw));snapshot=imported.bind_pose_snapshot
        self.assertEqual(len(snapshot),116)
        fresh=formats.Geom();fresh.skeleton=formats.Skeleton.from_bytes(imported.skeleton.to_bytes())
        fresh.bind_pose_snapshot=snapshot;del imported;gc.collect()
        self.assertTrue(fresh.bind_pose_snapshot_matches)
        self.assertEqual(preserved_sections(fresh.to_bytes())['ibpm'],preserved_sections(raw)['ibpm'])
        fresh.skeleton.bones[0].name='renamed';self.assertTrue(fresh.bind_pose_snapshot_matches)
        for length in range(1,len(snapshot)):
            with self.assertRaises(Exception):fresh.bind_pose_snapshot=snapshot[:length]
        for offset,kind,value in [(4,'<I',999),(8,'<I',2**32-1),(12,'<i',0),(12,'<i',-2),
                                 (12+52,'<I',2),(12+4,'<f',float('nan')),(12+56,'<f',float('inf'))]:
            bad=bytearray(snapshot);struct.pack_into(kind,bad,offset,value)
            with self.assertRaises(Exception):fresh.bind_pose_snapshot=bytes(bad)
        self.assertEqual(fresh.bind_pose_snapshot,snapshot)  # failed setters are atomic
        fresh.skeleton.bones[0].is_geometry=True;self.assertFalse(fresh.bind_pose_snapshot_matches)
        fresh.skeleton.bones[0].is_geometry=False
        fresh.skeleton.bones[0].transform.position=np.array([2,0,0,1],np.float32)
        self.assertFalse(fresh.bind_pose_snapshot_matches)
        rewritten=fresh.to_bytes();at=struct.unpack_from('<Q',rewritten,0x68)[0]
        self.assertEqual(struct.unpack_from('<f',rewritten,at+12)[0],-2.0)
        fresh.bind_pose_snapshot=b'';self.assertEqual(fresh.bind_pose_snapshot,b'')


def corpus(root, limit, output, collect=False,scene_fixtures=False):
    if scene_fixtures:
        candidates=[root / p for p in ['app_0.dx11/ef_b_chr039_bs01.geom','app_0.dx11/ef_b_chr395_bs01.geom',
            'app_0.dx11/cam_chr395_bs01_pc.geom','app_0.dx11/chr777.geom',
            'addcont_01.dx11/cam_chr690_bs01_em.geom','addcont_01.dx11/cam_chr690_bs01_pc.geom',
            'addcont_01.dx11/dep01t0103p.geom']]
    else:
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
            original_sections=preserved_sections(path.read_bytes())
            assert preserved_sections(rewritten)==original_sections
            assert len(check.meshes)==len(geom.meshes) and len(check.skeleton.bones)==len(geom.skeleton.bones)
            for a,b in zip(geom.meshes,check.meshes):
                assert a.name==b.name and list(a.indices)==list(b.indices)
                assert len(a.vertices)==len(b.vertices) and len(a.matrix_palette)==len(b.matrix_palette)
                for i in {0,len(a.vertices)//2,len(a.vertices)-1}:
                    if i>=0:np.testing.assert_allclose(a.vertices[i].position[:3],b.vertices[i].position[:3],rtol=0,atol=0)
            rows.append({'file':str(path),'ok':True,'meshes':len(geom.meshes),'bones':len(geom.skeleton.bones),
                         'preservedSections':{key:len(value) for key,value in original_sections.items()},
                         'semanticDiagnostics':formats.get_error_list()})
        except Exception as error:rows.append({'file':str(path),'ok':False,'error':str(error)})
    report={'sampled':len(rows),'passed':sum(r['ok'] for r in rows),'collectSemanticDiagnostics':collect,'results':rows}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))
    for row in rows:
        if not row['ok']:print(row['file'],row['error'][:300])
    return report['passed']==report['sampled']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-dir',type=Path,required=True)
    parser.add_argument('--corpus',type=Path)
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--report',type=Path,default=Path('local/binary-safety-corpus.json'))
    parser.add_argument('--collect-semantic',action='store_true')
    parser.add_argument('--scene-fixtures',action='store_true',help='Use seven camera/light/material-float fixtures from the extracted corpus')
    args=parser.parse_args();sys.path.insert(0,str(args.module_dir.resolve()));formats=importlib.import_module('dsts_formats')
    if args.corpus:sys.exit(0 if corpus(args.corpus,args.limit,args.report,args.collect_semantic,args.scene_fixtures) else 1)
    else:unittest.main(argv=[sys.argv[0]])
