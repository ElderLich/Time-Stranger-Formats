"""Validate the distributed table and ensure packaging excludes local build junk."""

import importlib.util
from pathlib import Path
import tempfile
import json
import struct
import unittest
import zipfile

ROOT = Path(__file__).parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildTools(unittest.TestCase):
    def test_parameter_table_rejects_bad_records(self):
        generator = load(ROOT / 'generate_shader_header.py')
        data = (ROOT / 'notes/shader_params.bin').read_bytes()
        generator.validate(data)
        for invalid in (b'', data[:-1], data + data[:56], data[:24] + b'x' * 32 + data[56:]):
            with self.assertRaises(ValueError):
                generator.validate(invalid)

    def test_typed_table_matches_manifest_and_rejects_bad_metadata(self):
        generator = load(ROOT / 'generate_shader_header.py')
        data = (ROOT / 'notes/shader_params.bin').read_bytes()
        manifest=json.loads((ROOT/'notes/shader-parameters.json').read_text())
        self.assertEqual(len(data),56*len(manifest['parameters']))
        for offset,row in zip(range(0,len(data),56),manifest['parameters'],strict=True):
            values=struct.unpack_from('<I4BII8x32s',data,offset)
            self.assertEqual(values,(row['id'],int(row['global_scope']),row['unknown_0x2D'],
                row['type_code'],row['unknown_0x2F'],row['unknown_0x30'],row['unknown_0x34'],
                row['name'].encode('ascii').ljust(32,b'\0')))
        for offset,value in [(4,2),(16,1)]:
            bad=bytearray(data);bad[offset]=value
            with self.assertRaises(ValueError):generator.validate(bytes(bad))
        bad=bytearray(data);bad[56+24:112]=bad[24:56]
        with self.assertRaises(ValueError):generator.validate(bytes(bad))

    def test_archive_has_one_relative_root_and_no_caches(self):
        packager = load(ROOT / 'tools/package_addon.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            addon = root / 'addon'; addon.mkdir()
            (addon / '__init__.py').write_text('# source')
            (addon / '__pycache__').mkdir()
            (addon / '__pycache__/old.py').write_text('# junk')
            (addon / 'model.geom').write_bytes(b'local fixture')
            module = root / 'dsts_formats.cp313-win_amd64.pyd'
            module.write_bytes(b'packaging fixture, not an executable module')
            output = root / 'dist/addon.zip'
            self.assertEqual(packager.package(addon, module, output), 2)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ['dsts_formats/__init__.py', 'dsts_formats/' + module.name])


if __name__ == '__main__':
    unittest.main()
