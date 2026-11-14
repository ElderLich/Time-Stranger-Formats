# Shader parameter identities and typed descriptors

The imported table paired numeric IDs with the following entry's name. For
example, ID 24 was labelled `DiffuseColor` even though the native loader binds
it as `ColorSampler`. The last record had an empty name. Changing labels by
guessing a constant offset would also mishandle gaps in the enum.

The corrected table contains **791 ID/name pairs** from the native executable
whose SHA-256 is recorded in `notes/shader-parameters.json`. IDs come from each
record's explicit enum field, not its array position.

| ID | Correct name | Previous label |
| --- | --- | --- |
| 24 | ColorSampler | DiffuseColor |
| 25 | DiffuseColor | DiffuseAlpha |
| 27 | NormalSampler | Bumpiness |
| 123 | alpha_func | alpha_test_enable |
| 124 | alpha_test_enable | blend_func |
| 127 | blend_enable | cull_face |
| 303 | EmissiveSampler | LightPixelProj |

Native evidence: the 56-byte records at VA `0x141AC4F00` contain a name at
offset 8 and a 32-bit enum at offset 40. GEOM render-state loader
`0x1402E4360` reads setting IDs directly: 123 selects alpha comparison,
124 alpha-test enable, 125 blend factors, 126 blend equation, and 127 blend
enable. There is no implicit +1 conversion in that path. SPAK uniform resolver
`0x14035ADA0` independently maps 24 to ColorSampler and 27 to NormalSampler.

Reproduce from a local copy of the supported executable:

```powershell
python tools/extract_shader_parameters.py 'path/to/Digimon Story Time Stranger.exe' --output local/parameters
```

The extractor checks the executable fingerprint and table structure. An
unrecognized build is rejected. The normalized record contains `uint32 id`, the twelve bytes from native
offsets 44–55, eight zero reserved bytes and `char name[32]`. It is not the
native runtime record and contains no runtime pointer/hash prefix. The JSON
manifest identifies this layout as `dsts-parameter-descriptor-v1`.

The backend exposes `shader_parameter_schema = "dsts-native-ff9de825"` so
consumers can identify this correction. The reference Blender adapter uses
numeric IDs for texture roles and stores them on imported nodes. Existing
scenes imported with the old labels must be re-imported before export; it does
not silently reinterpret saved labels with the corrected table.

## Types and scope

`shader_parameter(id_or_name)` returns an owned, read-only `ShaderParameter`.
It exposes `id`, `name`, `type_code`, `global_scope`, `scope`, `kind` and
`component_count`. Native offset 44 is the global-scope flag; offset 46 is a
type code, **not an unconditional float count**. Known codes are texture 0,
scalar/vector 1–4, matrix 16 and render state 100. Other codes remain `opaque`
with no claimed component count. The remaining descriptor fields retain their
native values as `unknown_0x2D`, `unknown_0x2F`, `unknown_0x30` and
`unknown_0x34`; their meaning is not inferred from names. A non-global descriptor
does not by itself promise that any value can be authored as a GEOM uniform.

```python
parameter = dsts_formats.shader_parameter(304)
assert (parameter.name, parameter.kind, parameter.component_count) == (
    "LightPixelProj", "matrix", 16)
assert parameter.global_scope
dsts_formats.validate_material_texture_binding(303)  # EmissiveSampler: valid
dsts_formats.validate_material_texture_binding(304)  # raises: matrix/global
```

`validate_material_texture_binding(id_or_name)` rejects numeric, matrix,
render-state and global-only descriptors. GEOM writing applies this guard
before opening its output file, even in semantic-diagnostic collection mode.
Reading remains available for inspecting an existing invalid conversion.
`Material.validate_parameter_types()` additionally checks numeric uniforms
against the supported 1–4 native component counts and checks setting types.
That stricter check is explicit: existing opaque metadata is preserved rather
than silently reinterpreted or discarded. It does not validate reflected DXBC
resources, register linkage, pass output types or the runtime scene provider.

The material texture guard promotes the research check that found a dissolve
texture incorrectly assigned to LightPixelProj 304. Global textures such as
BackBufferSampler require an engine scene input, not a static GEOM texture.
Native resolvers `0x14035E950`, `0x14035ED30` and `0x14035F5D0` establish the
name/ID binding paths; the descriptor fields were independently compared with
all 791 captured native records and reproduced from the fingerprinted executable.

## Material and pass preservation

`Material.clone()` creates an independent copy of all fourteen ordered shader
descriptors, numeric/texture uniforms, settings and the five opaque header
fields. `active_shader_slots` reports populated source slots without assigning
them interchangeable behavior. Uniforms and settings expose the retained
`unknown_0x14`, `unknown_0x18` and `unknown_0x1C` words to consumers, so a Blender
save/reload or material split need not reset them. Reader diagnostics for
non-default trailer words remain unchanged.

Do not rebuild a split material from just its visible color and texture nodes.
Source slot presence affects native renderer flags (`0x1402E1220`), and native
pass selection (`0x1402E63A0`) gives auxiliary slots different output contracts.
The backend preserves those descriptors; it does not decide which custom
shader can replace a given pass or prove rendering in game.
