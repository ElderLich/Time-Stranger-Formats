"""Rebuild the normalized parameter table from the verified native executable.

Only normalized parameter definitions and the executable fingerprint are stored.
Unknown builds require a new verified profile. Native descriptor flags retain
their exact values; uninterpreted fields are not assigned invented semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXE_SHA256 = "ff9de825a543bf874cfb7e73ed951256d3ce4e8702957afa3b26ca6487a81688"
TABLE_VA = 0x141AC4F00
TABLE_COUNT = 791


def extract(executable: Path, output: Path) -> dict:
    data = executable.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXE_SHA256:
        raise ValueError("Unrecognized executable; verify the shader-table layout before adding a profile")
    pe = struct.unpack_from("<I", data, 60)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Expected a PE executable")
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    image_base = struct.unpack_from("<Q", data, pe + 24 + 24)[0]
    rva = TABLE_VA - image_base
    table_offset = None
    for index in range(count):
        section = pe + 24 + optional_size + 40 * index
        _virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", data, section + 8)
        if virtual_address <= rva and rva + TABLE_COUNT * 56 <= virtual_address + raw_size:
            table_offset = raw_offset + rva - virtual_address
            break
    if table_offset is None:
        raise ValueError("Shader table is not wholly inside a file-backed PE section")
    ids: set[int] = set()
    normalized = bytearray()
    parameters = []
    for index in range(TABLE_COUNT):
        record = data[table_offset + index * 56:table_offset + (index + 1) * 56]
        parameter_id = struct.unpack_from("<I", record, 40)[0]
        name_bytes = record[8:40]
        if b"\0" not in name_bytes or parameter_id > 0xFFFF or parameter_id in ids:
            raise ValueError(f"Invalid shader parameter record {index}")
        name = name_bytes.split(b"\0", 1)[0].decode("ascii")
        if not name:
            raise ValueError(f"Empty shader parameter name at {index}")
        ids.add(parameter_id)
        scope, unknown_45, type_code, unknown_47 = record[44:48]
        if scope not in (0, 1):
            raise ValueError(f"Invalid shader parameter scope at {index}")
        unknown_48, unknown_52 = struct.unpack_from('<II', record, 48)
        parameters.append({"id": parameter_id, "name": name,
                           "global_scope": bool(scope), "type_code": type_code,
                           "unknown_0x2D": unknown_45, "unknown_0x2F": unknown_47,
                           "unknown_0x30": unknown_48, "unknown_0x34": unknown_52})
        normalized.extend(struct.pack("<I4BII8x32s", parameter_id, scope, unknown_45,
                                      type_code, unknown_47, unknown_48, unknown_52,
                                      name.encode("ascii")))
    manifest = {"executable_sha256": EXE_SHA256, "table_va": hex(TABLE_VA).upper().replace("0X", "0x"),
                "native_record_bytes": 56, "native_name_offset": 8, "native_id_offset": 40,
                "native_scope_offset": 44, "native_type_code_offset": 46,
                "normalized_schema": "dsts-parameter-descriptor-v1",
                "generated_table_sha256": hashlib.sha256(normalized).hexdigest(), "parameters": parameters}
    output.mkdir(parents=True, exist_ok=True)
    (output / "shader_params.bin").write_bytes(normalized)
    (output / "shader-parameters.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = extract(args.executable, args.output)
    print(f"Extracted {len(result['parameters'])} parameters; SHA-256 {result['generated_table_sha256']}")
