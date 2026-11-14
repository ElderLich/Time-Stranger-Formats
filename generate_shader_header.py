"""Generate shader_params_bin.h from shader_params.bin.

Replaces the xxd -i | sed pipeline in CMakeLists.txt so the build works
on Windows without requiring Unix tools.

Usage: python generate_shader_header.py <input.bin> <output.h>
"""
from pathlib import Path
import argparse
import struct


def validate(data: bytes) -> None:
    if not data or len(data) % 56:
        raise ValueError("Shader table must contain complete 56-byte records")
    ids: set[int] = set()
    for offset in range(0, len(data), 56):
        parameter_id = struct.unpack_from("<I", data, offset)[0]
        if parameter_id in ids or parameter_id > 0xFFFF:
            raise ValueError(f"Invalid or duplicate parameter ID {parameter_id}")
        ids.add(parameter_id)
        raw_name = data[offset + 24:offset + 56]
        if b"\0" not in raw_name:
            raise ValueError(f"Parameter {parameter_id} has no terminated name")
        if not raw_name.split(b"\0", 1)[0].decode("ascii"):
            raise ValueError(f"Parameter {parameter_id} has an empty name")


def generate(source: Path, target: Path) -> None:
    data = source.read_bytes()
    validate(data)
    body = ",\n".join("  " + ", ".join(f"0x{b:02x}" for b in data[i:i + 16])
                       for i in range(0, len(data), 16))
    target.write_text("#pragma once\n\nconstexpr unsigned char shader_params_bin[] = {\n"
                      + body + "\n};\n"
                      + f"constexpr unsigned int shader_params_bin_len = {len(data)};\n",
                      encoding="ascii", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    generate(args.source, args.target)
