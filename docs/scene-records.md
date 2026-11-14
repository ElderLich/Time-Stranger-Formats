# Camera, light and float-channel preservation

The backend preserves native GEOM 316 camera and light records, plus ordered
60SE skeleton float-channel bindings. This is a binary data API. It does not
render lights, play animation, or translate these records into Blender objects.

## Native evidence

The workspace's pinned executable pseudocode establishes these layouts:

| Native function | Evidence used |
| --- | --- |
| `0x1402E05E0` | GEOM camera count at `0x0A`, offset at `0x60`; copies 56-byte records and resolves the first word as a skeleton bone hash. |
| `0x1402E0450` | Light count at `0x08`, offset at `0x58`; copies 240-byte records and resolves the first word as a skeleton bone hash. |
| `0x1402E2D80` | Camera FOV in degrees at `+4`, near at `+12`, far at `+16`, orthographic scale at `+20` and projection flag at `+32`. |
| `0x1405018E0` | FOV is vertical: half-height derives from `tan(FOV/2)`; aspect scales the width. |
| `0x1402E1640` | Float bindings use target hashes and array indices. Material binding decodes `array_index >> 4` as the native uniform ID and the low nibble as component. Camera and light targets have separate index dispatch. |
| `0x1402E2C90` | Parent lookup masks the stored parent word with `0x7FFF`; subtracting `0x7FFF` is incorrect. |

Recovered listings are in the sibling `Time Stranger/src/native/camera-record`,
`camera-lens`, `camera-pose` and `figure-geom` directories. They are reconstructed
pseudocode, not original developer source. The 60SE tables are also checked
against captured GEOM files: count at `+18`, and field-relative array pointers at
`+36` (uint32 indices), `+40` (uint32 hashes), `+44` (uint8 flags).

## Python API

```python
geom = dsts_formats.Geom.from_file(path)
camera = geom.cameras[0]
camera.fov_degrees = 45.0  # vertical degrees
camera.near = 0.1
camera.far = 1000.0
assert len(camera.raw) == 56

channel = dsts_formats.FloatChannel()
channel.name_hash = material.name_hash
channel.array_index = (native_uniform_id << 4) | component
channel.flags = 8
geom.skeleton.float_channels = [channel]
```

`CameraRecord.raw` and `LightRecord.raw` are owned byte snapshots and accept only
56 and 240 bytes respectively. Camera properties expose `name_hash`,
`fov_degrees`, `near`, `far`, `orthographic_scale` and the raw `projection_flag`.
The light API exposes `name_hash` and `raw`; optical fields stay opaque.
Unknown words and runtime pointer slots are retained exactly. New raw records
start zeroed; applications must author a valid native record before use.

Float-channel order, index, hash and flags are preserved exactly. The backend
does not reinterpret unknown flags, deduplicate channels, rename their targets,
or validate whether a particular shader accepts a binding. Renaming a material,
camera or bone requires the caller to update its associated target hashes.
ANIM float samples are separate from these GEOM binding tables.

## Bind-pose preservation

Read GEOMs retain their original inverse bind matrix bytes internally. Export
reuses them when ordered parent indices, transform components and `is_geometry`
values are unchanged. Renaming alone does not invalidate the snapshot. An edited
bind pose recomputes matrices; a singular or non-finite inverse raises an error
instead of silently replacing it with identity, including in diagnostics mode.

Original skeleton parent-pair and lookup arrays are retained when the hierarchy
is unchanged. This includes duplicate pairs and the high-bit flag used by
`chr800`. Editing a flagged hierarchy currently raises an explicit error rather
than dropping flags whose authoring semantics are not yet implemented.

## Checks and remaining limits

Eleven test groups exercise malformed pointers/counts, exact record preservation,
mixed camera/light/mesh files, float-table bounds, high-bit parents, raw snapshots,
known lens edits, inverse bind matrix preservation and singular-pose rejection.
Seven real scene fixtures pass structural read/write/read checks with diagnostic
collection enabled. Every camera/light record, float binding, inverse bind matrix
and parent-pair/table entry is compared against the source bytes:

- `app_0.dx11/ef_b_chr039_bs01.geom`: 11 material float channels.
- `app_0.dx11/ef_b_chr395_bs01.geom`: 2 material float channels.
- `app_0.dx11/cam_chr395_bs01_pc.geom`: camera and FOV float binding.
- `app_0.dx11/chr777.geom`: character float channels.
- `addcont_01.dx11/cam_chr690_bs01_em.geom` and `cam_chr690_bs01_pc.geom`: mixed camera/light records.
- `addcont_01.dx11/dep01t0103p.geom`: light record with scene geometry.

Three generated Leviamon particle GEOMs (`n147_p0492`, `n147_p0608`, `n147_p0724`)
also preserve their native uniform 302/component 0/flag 8 binding exactly.
Reports are in ignored `local/scene-record-corpus.json` and
`local/generated-particle-float-check.json`.

The original deterministic 100-character sample now passes 100/100 structural
round trips in diagnostic-collection mode, with exact inverse bind matrix,
parent-pair/table and float binding comparisons added to the earlier assertions.
Its report is `local/binary-safety-corpus-scene-support.json`.

The reference Blender add-on records unsupported scene/binding sections as
custom properties on imported collections and armatures. Export stops with a
specific message for camera/light records, float channels or flagged parent
tables because that add-on reconstructs fresh backend objects and cannot yet
preserve those sections. The dedicated Time Stranger Importer is maintained
separately. The reference guard's tests do not replace Blender runtime testing.

Mesh controllers remain unsupported and fail even with `set_throw_errors(False)`.
Bounds are still recomputed on export; full-file byte identity, every vertex
attribute and native game acceptance are not claimed by these tests. Original
semantic discrepancies are still available through `get_error_list()`.

```powershell
python tests/test_binary_safety.py --module-dir build-parser/Release
python tests/test_binary_safety.py --module-dir build-parser/Release --corpus PATH_TO_EXTRACTED_DATA --collect-semantic --scene-fixtures --report local/scene-record-corpus.json
```
