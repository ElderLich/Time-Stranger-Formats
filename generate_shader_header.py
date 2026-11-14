"""Generate shader_params_bin.h from shader_params.bin.

Replaces the xxd -i | sed pipeline in CMakeLists.txt so the build works
on Windows without requiring Unix tools.

Usage: python generate_shader_header.py <input.bin> <output.h>
"""
import sys

input_file = sys.argv[1]
output_file = sys.argv[2]

with open(input_file, "rb") as f:
    data = f.read()

chunk_size = 16
lines = []
for i in range(0, len(data), chunk_size):
    chunk = data[i : i + chunk_size]
    lines.append("  " + ", ".join(f"0x{b:02x}" for b in chunk))

hex_body = ",\n".join(lines)

header = (
    f"constexpr unsigned char shader_params_bin[] = {{\n"
    f"{hex_body}\n"
    f"}};\n"
    f"constexpr unsigned int shader_params_bin_len = {len(data)};\n"
)

with open(output_file, "w", newline="\n") as f:
    f.write(header)
