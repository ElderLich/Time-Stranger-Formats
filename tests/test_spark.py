"""Synthetic semantic edits and exact-byte preservation; no game assets needed."""
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("spark", Path(__file__).parents[1] / "addon/spark.py")
spark = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = spark
spec.loader.exec_module(spark)


def chunk(tag, payload, prefix=b"opaque-prefix", suffix=b"opaque-tail"):
    start = 16 + len(prefix)
    end = start + len(payload)
    return struct.pack("<4sIII", tag, end + len(suffix), start, end) + prefix + payload + suffix


def fixture():
    header = bytearray(b"SPAK" + bytes(20))
    struct.pack_into("<4H", header, 8, 140, 2, 1, 1)
    header[16:24] = bytes([30, 1, 19, 20, 21, 22, 23, 24])
    root = bytearray(552)
    model = bytearray(680)
    for payload, identity, kind in ((root, 7, 0), (model, 12, 4)):
        struct.pack_into("<H", payload, 0, kind)
        struct.pack_into("<I", payload, 4, identity)
        payload[8:12] = b"test"
        for at in spark.TRANSFORM_FIELDS.values():
            struct.pack_into("<6f", payload, at, *([1.0] * 6))
        payload[96:104] = b"opaque!!"
        struct.pack_into("<2h", payload, 472, -1, -1)
        struct.pack_into("<I", payload, 520, spark.NONE)
        struct.pack_into("<I", payload, 536, spark.NONE)
    struct.pack_into("<I", root, 520, 0)
    struct.pack_into("<I", root, 528, 1)
    struct.pack_into("<I", model, 536, 0)
    struct.pack_into("<6f", model, 424, -2, -2, 0, 0, 1, 1)
    anim = bytearray(16 + 8 + 24 + 48)
    struct.pack_into("<H", anim, 0, 1)
    anim[2:16] = b"animation_meta"
    struct.pack_into("<I", anim, 16, 0)
    struct.pack_into("<I", anim, 20, 0xAABBCCDD)
    struct.pack_into("<HBBHHffII", anim, 24, 1, 93, 0, 2, 42, 2, 4, 0xFFFFFFFF, 123)
    anim[48:72] = spark.Key(1, 1, 2).pack()
    anim[72:96] = spark.Key(10, 0, 4).pack()
    return bytes(header) + chunk(b"NODE", root) + chunk(b"NODE", model) + chunk(b"ANIM", anim) + chunk(b"NLST", struct.pack("<I", 12)) + struct.pack("<4sIII", b"TERM", 16, 0x11223344, 0x55667788)


class SparkTests(unittest.TestCase):
    def test_exact_preservation_and_typed_values(self):
        raw = fixture()
        doc = spark.SparkDocument.from_bytes(raw).validate_editable()
        self.assertEqual(doc.to_bytes(), raw)
        self.assertEqual(doc.nodes[7].children, (12,))
        self.assertEqual(doc.nodes[12].secondary_scale.low, (-2, 0, 1))
        self.assertEqual(doc.nodes[12].animation_index, 0)
        self.assertEqual(doc.nodes[7].lifetime_range, (-1, -1))
        self.assertEqual(doc.fps, 30)
        self.assertEqual(doc.clock_mode, 1)
        self.assertEqual(doc.channels(0)[0].sample(5.5), 3)

    def test_transform_edit_has_exact_scoped_diff(self):
        raw = fixture()
        doc = spark.SparkDocument.from_bytes(raw)
        at = doc._node_chunks[12].start + 72
        doc.set_transform(12, "primary", "translation", [2, 3, 4], [5, 6, 7])
        changed = doc.to_bytes()
        self.assertEqual(changed[:at], raw[:at])
        self.assertEqual(changed[at + 24:], raw[at + 24:])
        self.assertEqual(spark.SparkDocument.from_bytes(changed).nodes[12].primary_translation.high, (5, 6, 7))
        self.assertEqual(doc.nodes[12].secondary_scale.low, (-2, 0, 1))
        before = doc.to_bytes()
        for values in ([1, 2], [float("nan"), 0, 0], [1e99, 0, 0]):
            with self.assertRaises(ValueError):
                doc.set_transform(12, "primary", "translation", values)
        with self.assertRaises(ValueError):
            doc.set_transform(12, "primary", "translation", [1, 2, 3], [0, 2, 3])
        self.assertEqual(doc.to_bytes(), before)

    def test_timing_and_resources(self):
        doc = spark.SparkDocument.from_bytes(fixture())
        doc.set_timing(12, delay_range=(5, 9), lifetime_range=(30, 60))
        doc.set_resource(12, "model", "user_selected")
        self.assertEqual(doc.nodes[12].delay_range, (5, 9))
        self.assertEqual(doc.nodes[12].lifetime_range, (30, 60))
        before = doc.to_bytes()
        with self.assertRaises(ValueError):
            doc.set_timing(12, delay_range=(1, 2), lifetime_range=(-1, 1))
        with self.assertRaises(ValueError):
            doc.set_resource(12, "model", "../../elsewhere")
        with self.assertRaises(ValueError):
            doc.set_resource(12, "socket", "head")
        self.assertEqual(doc.to_bytes(), before)

    def test_key_edit_retains_header_and_offset_metadata(self):
        raw = fixture()
        doc = spark.SparkDocument.from_bytes(raw)
        old = doc.channels(0)[0]
        doc.set_channel_keys(0, 1, [spark.Key(2, 1, 10), spark.Key(12, 0, 30)])
        current = doc.channels(0)[0]
        self.assertEqual(current.header[:8], old.header[:8])
        self.assertEqual(current.header[16:], old.header[16:])
        self.assertEqual(current.sample(7), 20)
        at = doc._animations[0].start
        self.assertEqual(doc.to_bytes()[at:at + 24], raw[at:at + 24])
        before = doc.to_bytes()
        with self.assertRaises(ValueError):
            doc.set_channel_keys(0, 1, [spark.Key(2, 1, 4)])
        with self.assertRaises(ValueError):
            doc.set_channel_keys(0, 1, [spark.Key(2, 2, 4), spark.Key(12, 0, 4)])
        self.assertEqual(doc.to_bytes(), before)

    def test_unsupported_interpolation_and_extrapolation_preserve(self):
        raw = bytearray(fixture())
        parsed = spark.SparkDocument.from_bytes(raw)
        start = parsed._animations[0].start + 24
        for offset, value in ((start + 3, 3), (start + 24 + 2, 9)):
            changed = bytearray(raw)
            changed[offset] = value
            doc = spark.SparkDocument.from_bytes(changed)
            self.assertEqual(doc.to_bytes(), changed)
            with self.assertRaises(ValueError):
                doc.channels(0)[0].sample(2)
            with self.assertRaises(ValueError):
                doc.set_channel_keys(0, 1, [spark.Key(2, 1, 4), spark.Key(12, 0, 4)])

    def test_truncated_and_malformed_storage(self):
        raw = fixture()
        for length in range(len(raw)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                spark.SparkDocument.from_bytes(raw[:length])
        doc = spark.SparkDocument.from_bytes(raw)
        cases = [(10, "<H", 9), (14, "<H", 9), (doc._node_chunks[12].start + 4, "<I", 7),
                 (doc._animations[0].start + 16, "<I", 0xFFFFFFFF),
                 (doc._animations[0].start + 24 + 4, "<H", 65535),
                 (doc._animations[0].start + 72, "<h", 1)]
        for offset, fmt, value in cases:
            changed = bytearray(raw)
            struct.pack_into(fmt, changed, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                spark.SparkDocument.from_bytes(changed)

    def test_graph_cycles_missing_and_unknown_are_rejected_for_edits(self):
        raw = fixture()
        doc = spark.SparkDocument.from_bytes(raw)
        cases = [(doc._lists[0].start, "<I", 999),
                 (doc._lists[0].start, "<I", 7),
                 (doc._node_chunks[12].start, "<H", 31),
                 (doc._node_chunks[12].start + 536, "<I", 20)]
        for offset, fmt, value in cases:
            changed = bytearray(raw)
            struct.pack_into(fmt, changed, offset, value)
            preserved = spark.SparkDocument.from_bytes(changed)
            self.assertEqual(preserved.to_bytes(), changed)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                preserved.set_transform(7, "primary", "translation", (0, 0, 0))
        preserved = spark.SparkDocument.from_bytes(raw + b"opaque tail")
        self.assertEqual(preserved.to_bytes(), raw + b"opaque tail")
        with self.assertRaises(ValueError):
            preserved.set_timing(7, delay_range=(0, 0))

    def test_atomic_write_protects_destinations_and_cleans_failures(self):
        doc = spark.SparkDocument.from_bytes(fixture())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "edited.sprk"
            digest = doc.write(path)
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                doc.write(path)
            with self.assertRaises(ValueError):
                doc.write(path, overwrite=True, expected_sha256="0" * 64)
            doc.set_transform(12, "primary", "translation", (5, 6, 7))
            original = path.read_bytes()
            for name in ("replace", "fsync"):
                with patch.object(spark.os, name, side_effect=OSError("injected")):
                    with self.assertRaises(OSError):
                        doc.write(path, overwrite=True, expected_sha256=digest)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(list(Path(folder).iterdir()), [path])
            doc.write(path, overwrite=True, expected_sha256=digest)
            self.assertEqual(spark.SparkDocument.read(path).nodes[12].primary_translation.low, (5, 6, 7))


if __name__ == "__main__":
    unittest.main()
