# Backend 0.2 compatibility notes

- `Mesh.name_is_external` identifies a zero mesh name offset in a native GEOM.
  `Mesh.set_external_name(name_hash, spelling)` retains that layout and checks
  a supplied NLST spelling against the native hash. Omit the spelling to
  preserve an unresolved hash. Assigning `Mesh.name` writes a new inline name.

- `Geom.to_file` and `Skeleton.to_file` share the same atomic writer after serialization,
  buffered writing, flush and sync. IO failures propagate without truncating the
  previous file. Existing replacement behavior remains explicit in this API.
- Dependency-free `addon/spark.py` exposes API version 1 for bounded SPAK v140
  semantic editing. It is shipped as identical source in the maintained
  importer; it does not change the C++ extension ABI. See [SPRK API](spark-editing.md).
- `addon/effect_bson.py` adds source-preserving existing effect field edits and
  validated inter-set attachments. It reuses the SPRK module's atomic output
  helper. See [effect BSON API](effect-bson.md) for boundaries and evidence.
- `LightRecord` adds readonly `native_type`, `native_slot`, and
  `supports_optical_editing`; `color_rgb`/`intensity` edits are type-gated to0/2/3,
  and `range` to0. Other types remain exact raw records and reject these edits.
  Native float-channel indices0..2 address RGB; index3 addresses intensity.

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
