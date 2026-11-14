"""Effect BSON bounds, semantic edits, exact retention and attachment guards."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "addon"))
from effect_bson import EffectDocument, END


def fixture(extra=b"opaque", duplicate=False):
    pool = bytearray(b"\0")
    indices = {"": 0}

    def text(value):
        if value not in indices:
            indices[value] = len(pool)
            pool.extend(value.encode("utf8") + b"\0")
        return indices[value]

    def record(name, value):
        key = text(name)
        if isinstance(value, list):
            kind = 1
            payload = struct.pack("<I", len(value)) + b"".join(record(k, v) for k, v in value) + END
        elif type(value) is int:
            kind, payload = 0x10, struct.pack("<i", value)
        elif type(value) is float:
            kind, payload = 0x11, struct.pack("<f", value)
        elif isinstance(value, str):
            kind, payload = 0x14, struct.pack("<I", text(value))
        else:
            kind, payload = 0x7F, value
        high, low = divmod(len(payload) + 8, 65535)
        return struct.pack("<BBHI", kind, high, low, key) + payload

    def effect_set(identity, owner=""):
        return [("common", [("id", identity), ("emitter0", [("dn", "fixture_model")]),
                ("se", [("se_name", "329511"), ("se_offset", 1), ("se_stop", 1),
                        ("se_volume", 1.0), ("se_stream", 1), ("se_fadeout", 0), ("se_3D", 0)]),
                ("bt", [("bt_id", owner), ("bt_pos", ""), ("bt_rot", ""), ("bt_sca", "")])])]

    pairs = [("mf", 230), ("hf", [("hf0", 0), ("hf1", 25)]),
             ("set0", effect_set("owner")), ("set1", effect_set("child", "owner")), ("unknown", extra)]
    if duplicate:
        pairs.append(("mf", 230))
    root = record("", pairs)
    high, low = divmod(len(pool), 65535)
    return b"BSON\x0a\0\0\0" + root + struct.pack("<BBH", 0x20, high, low) + pool + END


class EffectBsonTests(unittest.TestCase):
    def test_preservation_and_typed_fields(self):
        raw = fixture()
        doc = EffectDocument.from_bytes(raw)
        self.assertEqual(doc.to_bytes(), raw)
        self.assertEqual(doc.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(doc.value(("mf",)), 230)
        self.assertEqual(doc.sets[1].attachment_owner, "owner")
        self.assertEqual(doc.sets[0].drawables, ("fixture_model",))
        fields = {f.path: f for f in doc.fields}
        self.assertEqual(fields[("set0", "common", "se", "se_offset")].units, "frames (30 Hz)")
        self.assertNotIn(("unknown",), fields)

    def test_numeric_edit_changes_only_selected_scalar(self):
        raw = fixture()
        doc = EffectDocument.from_bytes(raw)
        node = doc._get(("mf",))
        doc.set_field(("mf",), 240)
        changed = doc.to_bytes()
        self.assertEqual(changed[:node.start + 8], raw[:node.start + 8])
        self.assertEqual(changed[node.end:], raw[node.end:])
        self.assertEqual(EffectDocument.from_bytes(changed).value(("mf",)), 240)
        doc.set_field(("hf", "hf1"), 30)
        self.assertEqual(EffectDocument.from_bytes(doc.to_bytes()).value(("hf", "hf1")), 30)

    def test_new_resource_string_appends_pool_without_rewriting_records(self):
        raw = fixture()
        doc = EffectDocument.from_bytes(raw)
        path = ("set1", "common", "emitter0", "dn")
        node = doc._get(path)
        prefix, pool = bytes(doc._prefix), bytes(doc._pool)
        doc.set_field(path, "new_selected_model")
        self.assertEqual(doc._prefix[:node.start + 8], prefix[:node.start + 8])
        self.assertEqual(doc._prefix[node.end:], prefix[node.end:])
        self.assertEqual(doc._pool[:len(pool)], pool)
        self.assertEqual(EffectDocument.from_bytes(doc.to_bytes()).value(path), "new_selected_model")
        length = len(doc._pool)
        doc.set_field(path, "new_selected_model")
        self.assertEqual(len(doc._pool), length)

    def test_unsupported_and_invalid_edits_do_not_mutate(self):
        doc = EffectDocument.from_bytes(fixture())
        raw = doc.to_bytes()
        cases = [(("unknown",), 2), (("mf",), -2), (("hf", "hf1"), -1),
                 (("set0", "common", "se", "se_stop"), 7),
                 (("set0", "common", "se", "se_volume"), float("nan")),
                 (("set0", "common", "se", "se_volume"), 2.0),
                 (("set0", "common", "se", "se_name"), "not-a-cue"),
                 (("set0", "common", "emitter0", "dn"), "../bad"),
                 (("set0", "common", "emitter0", "dn"), "x" * 32)]
        for path, value in cases:
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                doc.set_field(path, value)
            self.assertEqual(doc.to_bytes(), raw)

    def test_attachment_requires_real_owner_socket_and_acyclic_graph(self):
        doc = EffectDocument.from_bytes(fixture())
        doc.set_attachment("set1", owner_id="owner", position_socket="Head", rotation_socket="Head", scale_socket="", available_sockets=["Head", "Root"])
        self.assertEqual(EffectDocument.from_bytes(doc.to_bytes()).sets[1].position_socket, "Head")
        raw = doc.to_bytes()
        for selected, owner, socket in [("set1", "missing", "Head"), ("set1", "owner", "missing"),
                                         ("set1", "child", "Head"), ("set0", "child", "Head")]:
            with self.subTest(selected=selected, owner=owner, socket=socket), self.assertRaises(ValueError):
                doc.set_attachment(selected, owner_id=owner, position_socket=socket, rotation_socket="", scale_socket="", available_sockets=["Head"])
            self.assertEqual(doc.to_bytes(), raw)

    def test_malformed_prefixes_references_counts_and_duplicate_keys(self):
        raw = fixture()
        for size in range(len(raw)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                EffectDocument.from_bytes(raw[:size])
        for offset, fmt, value in [(20, "<I", 0xFFFFFFFF), (12, "<I", 0xFFFFFFFF), (10, "<H", 7)]:
            changed = bytearray(raw)
            struct.pack_into(fmt, changed, offset, value)
            with self.assertRaises(ValueError):
                EffectDocument.from_bytes(changed)
        doc = EffectDocument.from_bytes(fixture(duplicate=True))
        self.assertEqual(doc.to_bytes(), fixture(duplicate=True))
        with self.assertRaises(ValueError):
            doc.set_field(("mf",), 5)

    def test_extended_length_opaque_records_and_noncanonical_headers_preserve(self):
        raw = fixture(extra=bytes(range(256)) * 300)
        doc = EffectDocument.from_bytes(raw)
        self.assertEqual(doc.to_bytes(), raw)
        doc.set_field(("mf",), 231)
        changed = doc.to_bytes()
        unknown = doc._get(("unknown",))
        self.assertEqual(changed[unknown.start:unknown.end], raw[unknown.start:unknown.end])
        # Native lengths can encode 65535 as high0/low65535 or high1/low0.
        # Find an opaque payload making the record exactly65535 bytes.
        raw = bytearray(fixture(extra=bytes(65527)))
        unknown = EffectDocument.from_bytes(raw)._get(("unknown",))
        raw[unknown.start + 1] = 0
        struct.pack_into("<H", raw, unknown.start + 2, 65535)
        doc = EffectDocument.from_bytes(raw)
        self.assertEqual(doc.to_bytes(), raw)

    def test_atomic_export_and_reopen(self):
        doc = EffectDocument.from_bytes(fixture())
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "edited.bson"
            original_digest = doc.write(output)
            original = output.read_bytes()
            doc.set_field(("set0", "common", "se", "se_stop"), 0)
            with self.assertRaises(ValueError):
                doc.write(output)
            with patch("os.replace", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    doc.write(output, overwrite=True, expected_sha256=original_digest)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [output])
            doc.write(output, overwrite=True, expected_sha256=original_digest)
            self.assertEqual(EffectDocument.read(output).value(("set0", "common", "se", "se_stop")), 0)


if __name__ == "__main__":
    unittest.main()
