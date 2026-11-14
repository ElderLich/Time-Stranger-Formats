"""Synthetic PHYS semantics, invalid layouts, and transactional exports."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ADDON = Path(__file__).parents[1] / 'addon'
if str(ADDON) not in sys.path:
    sys.path.insert(0, str(ADDON))
import physics
import spark


def fixture():
    data = bytearray(744)
    struct.pack_into('<6I4Q', data, 0, 0x50485953, 2, 3, 3, 2, 2, 56, 288, 480, 608)
    for i in range(3):
        at = 56 + i*76
        struct.pack_into('<3f4f4f2I', data, at, 1, 2, 3, 0, 0, 0, 1, .2, .3, .6, 0, i, 1)
        data[at+52:at+59] = b'body_%d\0' % i
    data[284:288] = b'KEEP'
    struct.pack_into('<3Q', data, 288, 312, 336, 352)
    struct.pack_into('<II3f2H', data, 312, 0, 0xABCD, 2, 3, 4, 0, 1)
    struct.pack_into('<IIf2H', data, 336, 1, 0xABCD, 5, 1, 0)
    struct.pack_into('<4I6f4Q', data, 352, 2, 0xABCD, 3, 1, *([17]*6), 424, 436, 472, 474)
    struct.pack_into('<3I', data, 424, 0, 1, 2)
    struct.pack_into('<9f', data, 436, 0, 0, 0, 1, 0, 0, 0, 1, 0)
    struct.pack_into('<2H', data, 472, 0, 1)
    for at, name in ((480, b'floor'), (544, b'wall'), (608, b'object_0'), (672, b'object_1')):
        data[at:at+len(name)] = name
    data[736:] = b'opaque!!'
    return bytes(data)


class PhysicsTests(unittest.TestCase):
    def test_typed_exact_preservation(self):
        raw = fixture()
        doc = physics.PhysicsDocument.from_bytes(raw)
        self.assertEqual(doc.to_bytes(), raw)
        self.assertEqual(doc.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(doc.bodies[2].name, 'body_2')
        self.assertEqual(doc.bodies[0].rotation_xyzw, (0, 0, 0, 1))
        self.assertEqual(doc.shapes[0].half_extents, (2, 3, 4))
        self.assertEqual(doc.shapes[1].radius, 5)
        self.assertEqual(doc.shapes[2].triangles, ((0, 1, 2),))
        self.assertEqual(doc.table_a, ('floor', 'wall'))

    def test_scoped_body_edit_and_failed_edit_is_transactional(self):
        raw = fixture()
        doc = physics.PhysicsDocument.from_bytes(raw)
        doc.set_body(0, position=(9, 8, 7))
        modified = doc.to_bytes()
        self.assertEqual(modified[:56], raw[:56])
        self.assertEqual(modified[68:], raw[68:])
        self.assertEqual(physics.PhysicsDocument.from_bytes(modified).bodies[0].position, (9, 8, 7))
        with self.assertRaises(ValueError):
            doc.set_body(0, position=(1, 2, 3), rotation_xyzw=(0, 0, 0, 0))
        self.assertEqual(doc.to_bytes(), modified)

    def test_primitive_edits_and_associations(self):
        doc = physics.PhysicsDocument.from_bytes(fixture())
        doc.set_box(0, half_extents=(6, 7, 8))
        doc.set_sphere(1, radius=2)
        doc.set_shape_associations(0, table_a_index=1, table_b_index=0)
        doc.set_body(0, mass=2, shape_index=1, rotation_xyzw=(0, 1, 0, 0), name='edited')
        doc.set_table_name('a', 1, 'stone')
        reloaded = physics.PhysicsDocument.from_bytes(doc.to_bytes())
        self.assertEqual(reloaded.shapes[0], physics.Box((6, 7, 8), 1, 0))
        self.assertEqual(reloaded.shapes[1].radius, 2)
        self.assertEqual(reloaded.bodies[0].shape_index, 1)
        self.assertEqual(reloaded.bodies[0].mass, 2)
        self.assertEqual(reloaded.table_a[1], 'stone')
        self.assertEqual(doc.to_bytes()[316:320], fixture()[316:320])

    def test_existing_mesh_edits_preserve_unrelated_data(self):
        raw = fixture()
        doc = physics.PhysicsDocument.from_bytes(raw)
        doc.set_vertex(2, 1, (3, 4, 5))
        doc.set_triangle(2, 0, (2, 1, 0))
        doc.set_shape_associations(2, triangle_index=0, table_a_index=1, table_b_index=0)
        changed = doc.to_bytes()
        allowed = set(range(448, 460)) | set(range(424, 436)) | set(range(472, 476))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(raw, changed)) if a != b))
        reloaded = physics.PhysicsDocument.from_bytes(changed)
        self.assertEqual(reloaded.shapes[2].vertices[1], (3, 4, 5))
        self.assertEqual(reloaded.shapes[2].triangles[0], (2, 1, 0))
        self.assertEqual(reloaded.shapes[2].table_a_indices, (1,))

    def test_mesh_batch_validates_once_and_failed_array_retains_document(self):
        raw = fixture()
        doc = physics.PhysicsDocument.from_bytes(raw)
        vertices = ((8, 0, 0), (1, 7, 0), (0, 1, 6))
        with patch.object(doc, '_apply', wraps=doc._apply) as apply:
            doc.set_mesh(2, vertices=vertices, triangles=((2, 0, 1),), table_a_indices=(1,), table_b_indices=(0,))
            apply.assert_called_once()
        self.assertEqual(doc.shapes[2].vertices, vertices)
        self.assertEqual(doc.shapes[2].triangles, ((2, 0, 1),))
        self.assertEqual(doc.to_bytes()[:424], raw[:424])
        self.assertEqual(doc.to_bytes()[476:], raw[476:])
        changed = doc.to_bytes()
        for edits in (dict(vertices=vertices[:2]), dict(triangles=((0, 1, 3),)),
                      dict(vertices=vertices, table_a_indices=(2,)), dict(table_b_indices=())):
            with self.assertRaises(ValueError):
                doc.set_mesh(2, **edits)
            self.assertEqual(doc.to_bytes(), changed)

    def test_invalid_layouts_and_data_rejected(self):
        changes = [(0, '<I', 0), (4, '<I', 3), (8, '<I', 4),
                   (24, '<Q', 8), (32, '<Q', 99999999), (288, '<Q', 8),
                   (312, '<I', 3), (396, '<I', 99999999), (400, '<Q', 312),
                   (424, '<I', 3), (472, '<H', 2), (100, '<I', 3),
                   (56, '<f', float('nan')), (320, '<f', -1), (344, '<f', float('inf'))]
        for offset, fmt, value in changes:
            with self.subTest(offset=offset, fmt=fmt):
                damaged = bytearray(fixture())
                struct.pack_into(fmt, damaged, offset, value)
                with self.assertRaises(ValueError):
                    physics.PhysicsDocument.from_bytes(damaged)
        for length in (0, 55, 300, 500):
            with self.assertRaises(ValueError):
                physics.PhysicsDocument.from_bytes(fixture()[:length])

    def test_edit_rejections_do_not_mutate(self):
        doc = physics.PhysicsDocument.from_bytes(fixture())
        edits = [lambda: doc.set_box(1, half_extents=(1, 2, 3)),
                 lambda: doc.set_sphere(1, radius=-1),
                 lambda: doc.set_body(-1, mass=1),
                 lambda: doc.set_body(0, mass=float('inf')),
                 lambda: doc.set_body(0, position=(1e100, 2, 3)),
                 lambda: doc.set_body(0, name='x'*24),
                 lambda: doc.set_body(0, name='x\0y'),
                 lambda: doc.set_body(0, shape_index=True),
                 lambda: doc.set_vertex(2, 3, (1, 2, 3)),
                 lambda: doc.set_triangle(2, 0, (0, 1, 3)),
                 lambda: doc.set_shape_associations(2, triangle_index=1, table_a_index=0),
                 lambda: doc.set_shape_associations(0, table_a_index=2),
                 lambda: doc.set_table_name('x', 0, 'new')]
        for edit in edits:
            with self.assertRaises(ValueError):
                edit()
            self.assertEqual(doc.to_bytes(), fixture())

    def test_full_width_shipped_body_name_stays_bounded(self):
        raw = bytearray(fixture())
        raw[108:132] = b'a'*24
        doc = physics.PhysicsDocument.from_bytes(raw)
        self.assertEqual(doc.bodies[0].name, 'a'*24)
        self.assertEqual(doc.to_bytes(), bytes(raw))

    def test_atomic_export_no_clobber_and_stale_guard(self):
        doc = physics.PhysicsDocument.from_bytes(fixture())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.phys'
            self.assertEqual(doc.write(path), hashlib.sha256(fixture()).hexdigest())
            with self.assertRaises(ValueError):
                doc.write(path)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            doc.set_box(0, half_extents=(7, 8, 9))
            with self.assertRaises(ValueError):
                doc.write(path, overwrite=True, expected_sha256='0'*64)
            self.assertEqual(path.read_bytes(), fixture())
            doc.write(path, overwrite=True, expected_sha256=before)
            self.assertEqual(physics.PhysicsDocument.read(path).shapes[0].half_extents, (7, 8, 9))

    def test_atomic_failed_replace_preserves_file(self):
        doc = physics.PhysicsDocument.from_bytes(fixture())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.phys'
            doc.write(path)
            doc.set_sphere(1, radius=8)
            with patch.object(spark.os, 'replace', side_effect=OSError('test failure')):
                with self.assertRaises(OSError):
                    doc.write(path, overwrite=True)
            self.assertEqual(path.read_bytes(), fixture())
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
