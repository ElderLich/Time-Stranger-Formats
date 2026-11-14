"""Material metadata and Python buffer ownership regressions."""

import argparse
import gc
import importlib
import json
from pathlib import Path
import sys
import unittest


class Materials(unittest.TestCase):
    def test_verified_parameter_names(self):
        table = json.loads((Path(__file__).parents[1] / 'notes/shader-parameters.json').read_text())
        self.assertEqual(formats.shader_parameter_schema, 'dsts-native-ff9de825')
        for row in table['parameters']:
            uniform = formats.ShaderUniform()
            uniform.parameter_id = row['id']
            self.assertEqual(uniform.parameter_name, row['name'])
            uniform.parameter_name = row['name']
            self.assertEqual(uniform.parameter_id, row['id'])

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
