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
- Malformed binary bounds and unsupported sections raise exceptions even
  when optional semantic warnings are collected instead of thrown.

The complete Blender importer is tested separately before replacing its
bundled extension. This repository's reference adapter rejects materials from
old scenes with shifted labels; re-import their source GEOM before exporting.
