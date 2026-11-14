"""Material metadata and Python buffer ownership regressions."""

import argparse
import gc
import importlib
import json
from pathlib import Path
import sys
import struct
import tempfile
import unittest


class Materials(unittest.TestCase):
    def setUp(self):
        formats.set_throw_errors(True)

    def test_verified_parameter_names(self):
        table = json.loads((Path(__file__).parents[1] / 'notes/shader-parameters.json').read_text())
        self.assertEqual(formats.shader_parameter_schema, 'dsts-native-ff9de825')
        for row in table['parameters']:
            uniform = formats.ShaderUniform()
            uniform.parameter_id = row['id']
            self.assertEqual(uniform.parameter_name, row['name'])
            uniform.parameter_name = row['name']
            self.assertEqual(uniform.parameter_id, row['id'])

    def test_native_typed_descriptors(self):
        table = json.loads((Path(__file__).parents[1] / 'notes/shader-parameters.json').read_text())
        self.assertEqual(formats.shader_descriptor_schema, 'dsts-parameter-descriptor-v1')
        for row in table['parameters']:
            descriptor = formats.shader_parameter(row['id'])
            self.assertEqual(descriptor.name, row['name'])
            self.assertEqual(formats.shader_parameter(row['name']).id, row['id'])
            for key in ('type_code', 'global_scope', 'unknown_0x2D', 'unknown_0x2F', 'unknown_0x30', 'unknown_0x34'):
                self.assertEqual(getattr(descriptor, key), row[key])
            with self.assertRaises(AttributeError):
                descriptor.type_code = 0
        for identifier, kind, components, scope in [(24,'texture',None,'material'),
                (25,'vector',4,'material'),(7,'scalar',1,'material'),
                (304,'matrix',16,'global'),(123,'render_state',None,'global')]:
            descriptor = formats.shader_parameter(identifier)
            self.assertEqual((descriptor.kind,descriptor.component_count,descriptor.scope),(kind,components,scope))
        for invalid in (65535,'NotANativeParameter'):
            with self.assertRaises(RuntimeError): formats.shader_parameter(invalid)

    def test_texture_binding_guard_is_mandatory_on_export(self):
        for identifier in (24,27,303): formats.validate_material_texture_binding(identifier)
        for identifier in (25,7,304,123,47):
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(RuntimeError,'material-scoped texture'):
                    formats.validate_material_texture_binding(identifier)
                geom = formats.Geom(); material = formats.Material(); material.name = 'invalid'
                uniform = formats.ShaderUniform(); uniform.parameter_id = identifier; uniform.value = 'texture'
                material.uniforms = [uniform]; geom.materials = [material]
                # Collection mode may not disable this protection or truncate a file.
                formats.set_throw_errors(False)
                with tempfile.TemporaryDirectory() as folder:
                    target=Path(folder)/'existing.geom';target.write_bytes(b'keep')
                    with self.assertRaisesRegex(RuntimeError,'material-scoped texture'): geom.to_file(str(target))
                    self.assertEqual(target.read_bytes(),b'keep')

    def test_explicit_numeric_type_validation(self):
        material=formats.Material();uniform=formats.ShaderUniform();uniform.parameter_id=25
        uniform.value=[1,1,1,1];material.uniforms=[uniform];material.validate_parameter_types()
        uniform.value=[1];material.uniforms=[uniform]
        with self.assertRaisesRegex(RuntimeError,'component count'):material.validate_parameter_types()
        uniform.parameter_id=24;material.uniforms=[uniform]
        with self.assertRaisesRegex(RuntimeError,'component count'):material.validate_parameter_types()
        material.uniforms=[];setting=formats.ShaderSetting();setting.parameter_id=127;material.settings=[setting]
        material.validate_parameter_types();setting.parameter_id=25;material.settings=[setting]
        with self.assertRaisesRegex(RuntimeError,'render-state'):material.validate_parameter_types()

    def test_material_clone_and_binary_pass_metadata_preservation(self):
        material=formats.Material();material.name='donor'
        for key,value in [('unknown_0x314',0x11223344),('unknown_0x318',0x55667788),
                          ('unknown_0x31C',0x99aabbcc),('unknown_0x324',0x641),('unknown_0x326',0x100)]:
            setattr(material,key,value)
        slots=[0,1,2,3,4,5,6,8,9,10,13]
        for slot in slots:material.shaders[slot].name=f'{slot+1:06d}'+'000000'*13
        uniform=formats.ShaderUniform();uniform.parameter_id=25;uniform.value=[.1,.2,.3,.4]
        texture=formats.ShaderUniform();texture.parameter_id=24;texture.value='donor_texture';texture.unknown_0xC=71
        setting=formats.ShaderSetting();setting.parameter_id=126;setting.value=struct.pack('<4I',32774,17,18,19);setting.unknown_0x12=23
        for record in (uniform,texture,setting):
            record.unknown_0x14=0x12345678;record.unknown_0x18=0x87654321;record.unknown_0x1C=0xabcdef01
        material.uniforms=[uniform,texture];material.settings=[setting]
        split=material.clone();split.name='split';self.assertEqual(split.active_shader_slots,slots)
        self.assertEqual(split.unknown_0x324,0x641);self.assertEqual(split.unknown_0x326,0x100)
        split.uniforms[1].value='split_texture';split.settings[0].unknown_0x14=42
        split.shaders[0].name='000099'+'000000'*13
        self.assertEqual(material.uniforms[1].value,'donor_texture')
        self.assertEqual(material.settings[0].unknown_0x14,0x12345678)
        self.assertNotEqual(split.shaders[0].name,material.shaders[0].name)
        geom=formats.Geom();geom.materials=[material,split]
        data=geom.to_bytes();formats.set_throw_errors(False);reread=formats.Geom.from_bytes(data);encoded=reread.to_bytes()
        # Exact whole material region includes all fourteen pass keys, the five
        # opaque headers, numeric/texture payloads, settings and opaque words.
        start=struct.unpack_from('<Q',data,0x50)[0];other=struct.unpack_from('<Q',encoded,0x50)[0]
        size=2*(0x328+3*0x20)
        self.assertEqual(data[start:start+size],encoded[other:other+size])
        self.assertEqual(reread.materials[0].active_shader_slots,slots)
        self.assertEqual(reread.materials[0].uniforms[0].unknown_0x18,0x87654321)

    def test_float_snapshot_survives_reassignment_and_owner_deletion(self):
        uniform = formats.ShaderUniform()
        uniform.value = [1, .5, .25, 1]
        snapshot = uniform.value
        uniform.value = 'replacement_texture'
        del uniform
        gc.collect()
        self.assertEqual(snapshot.tolist(), [1, .5, .25, 1])
        snapshot[0] = 4
        self.assertEqual(snapshot.tolist(), [4, .5, .25, 1])

    def test_float_length_checked_before_binary_write(self):
        uniform = formats.ShaderUniform()
        for value in ([], [1, 2, 3, 4, 5]):
            with self.assertRaises(ValueError):
                uniform.value = value

    def test_setting_snapshot_is_owned_and_initialized(self):
        setting = formats.ShaderSetting()
        self.assertEqual(bytes(setting.value), bytes(16))
        setting.value = bytes(range(16))
        snapshot = setting.value
        setting.value = bytes(16)
        del setting
        gc.collect()
        self.assertEqual(bytes(snapshot), bytes(range(16)))

    def test_invalid_shader_key_does_not_partially_mutate(self):
        material = formats.Material()
        shader = material.shaders[0]
        original = shader.name
        with self.assertRaises(RuntimeError):
            shader.name = '000001' + '000000' * 12 + '&&&&&&'
        self.assertEqual(shader.name, original)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-dir', required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.module_dir.resolve()))
    formats = importlib.import_module('dsts_formats')
    unittest.main(argv=[sys.argv[0]])
