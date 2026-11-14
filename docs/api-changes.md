# Backend 0.2 compatibility notes

- Shader parameter names now match the supported native executable. Numeric
  IDs retain their original meaning. Consumers should use IDs for texture
  roles and retain them when exporting Blender nodes.
- `ShaderUniform.value` returns an owned NumPy snapshot. Edit it and assign it
  back (`uniform.value = values`); mutating a returned array no longer writes
  into the backend object. Keeping the old array alive across object deletion
  or reassignment is safe.
- `ShaderSetting.value` and `Geom.clut` return owned bytes. Use their setters
  to replace values. Float uniforms accept one to four components.
- Newly constructed material and setting metadata is initialized, rather
  than containing uninitialized memory.
- Typed descriptors are available through `shader_parameter(id_or_name)` and
  identified by `shader_descriptor_schema = "dsts-parameter-descriptor-v1"`.
  Special native type codes remain opaque; component counts are only claimed
  for verified numeric types. See [shader parameters](shader-parameters.md).
- GEOM export rejects a static texture assigned to a numeric, matrix,
  render-state or global-only descriptor before opening the output file.
  `validate_material_texture_binding` exposes the same guard to consumers.
  `Material.validate_parameter_types()` adds explicit numeric/setting checks.
- `Material.clone()` independently copies all fourteen shader slots and every
  material field. Uniform/setting trailer words are exposed as
  `unknown_0x14`, `unknown_0x18` and `unknown_0x1C`; default-mismatch reader
  diagnostics remain unchanged. `active_shader_slots` reports source indices.
- Numeric uniforms retain all sixteen original payload bytes, including unused
  nonzero words. `float_payload_padding` exposes only the unused tail; preserve
  it after assigning `value` when reconstructing an imported uniform. Its setter
  requires exactly `16 - 4 * len(value)` bytes and leaves active values intact.
- Malformed binary bounds and unsupported sections raise exceptions even
  when optional semantic warnings are collected instead of thrown.

The complete Blender importer is tested separately before replacing its
bundled extension. This repository's reference adapter rejects materials from
old scenes with shifted labels; re-import their source GEOM before exporting.
