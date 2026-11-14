# Shader parameter names and numeric identities

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
unrecognized build is rejected. Its output uses the parser's normalized
`uint32 id; byte reserved[20]; char name[32]` record, with reserved bytes zeroed.
Those bytes are not asserted to reproduce the native runtime structure.

The backend exposes `shader_parameter_schema = "dsts-native-ff9de825"` so
consumers can identify this correction. The reference Blender adapter uses
numeric IDs for texture roles and stores them on imported nodes. Existing
scenes imported with the old labels must be re-imported before export; it does
not silently reinterpret saved labels with the corrected table.
