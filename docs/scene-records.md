# Camera, light and float-channel preservation

The backend preserves native GEOM 316 camera and light records, plus ordered
60SE skeleton float-channel bindings. Verified light types now expose bounded
RGB/intensity and point-range editing. This is a binary data API. It does not
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
The light API exposes `name_hash`, `raw` and the bounded optical fields below.
Unknown words and runtime pointer slots are retained exactly. New raw records
start zeroed; applications must author a valid native record before use.

Float-channel order, index, hash and flags are preserved exactly. The backend
does not reinterpret unknown flags, deduplicate channels, rename their targets,
or validate whether a particular shader accepts a binding. Renaming a material,
camera or bone requires the caller to update its associated target hashes.
ANIM float samples are separate from these GEOM binding tables.

## Verified light fields

`LightRecord.native_type` and `native_slot` expose the native uint16 fields at
offsets4/6 read-only. For types0/2/3, `supports_optical_editing` is true and
`color_rgb` edits the three float32 values at40/44/48, while `intensity` edits
the multiplier at8. Type0 additionally exposes `range` at12. Setters validate
all components before mutation, require finite nonnegative values and retain
all other bytes. They allow intentional zero and RGB values above1; no implicit
gamma conversion or HDR clamping is applied. Imported out-of-profile values
remain raw-preservable instead of being normalized.

The evidence is in the existing `figure-geom` native listings:

| Function | Established behavior |
| --- | --- |
| `0x1402E34F0` | Dispatches the native uint16 type at +4; type0 copies point data, type2 directly multiplies RGB40 by intensity8, type3 supplies the bone Z direction and RGB/intensity to the directional renderer. Type4 follows a distinct environment record path. |
| `0x1402E2F90` | Type0 gets its world position from the bound bone; copies intensity8/RGB40 and scales range12 by the length of the bone's first matrix axis. |
| `0x1402D3DE0` | Builds point-light GPU records; multiplies source intensity and RGB, retains the range alongside world position and uses it in spatial bounds. |
| `0x1402E1640` | Light float-channel indices0/1/2 bind offsets40/44/48; index3 binds offset8. Indices4..6 bind56/60/64 but their additional optical meaning is not exposed. |

The local inventory examined15,640 GEOM headers: type0 appeared1,520 times,
type2 140, type3 154, type4 209 and type7 seven. Types1/5 were found in runtime
branches but have no fixture in that inventory, so their optical setters remain
unsupported. The native `d0101sun.geom` family independently corroborates type3
as directional/sun. Type0 has position/range without orientation, establishing
the point-light interpretation. Type2 is retained as native type2; its extra
color vector and position-derived environment direction must not be flattened
into a generic Blender point light. Type4 is not an ordinary light.

```python
light = geom.lights[selected_index]
if light.supports_optical_editing:
    light.color_rgb = (1.0, 0.5, 0.0)
    light.intensity = 2.0
if light.native_type == 0:
    light.range = 10.0
```

New arbitrary lights, changing type/slot, cone parameters, attenuation law,
shadow fields and physical watt/exposure equivalence are not established.
Blender preview must identify its limits and preserve native values separately.
Directional axis/sign conversion needs a verified preview adapter; do not assume
Blender's emission direction matches the stored native bone axis.

`tests/test_binary_safety.py` verifies scoped changes, raw retention, HDR/zero
values and atomic rejection of malformed edits/unsupported types. The local
`light-edit-validation.json` report records successful edit/export/re-import of
four records in three actual fixtures: DLC `ef_b_chr689_bs01.geom` (type0),
`d0101l.geom` (types2/0), and `d0101sun.geom` (type3). Every unedited light byte
survives. Source files and live mods are unchanged; game behavior of these new
edited fixtures is not yet accepted.

```powershell
python tools/audit_light_records.py --module-dir build-parser/Release --report local/light-edit-validation.json PATH_TO_LIGHT_GEOM
```

## Bind-pose preservation

Read GEOMs retain their original inverse bind matrix bytes internally. Export
reuses them when ordered parent indices, transform components and `is_geometry`
values are unchanged. Renaming alone does not invalidate the snapshot. An edited
bind pose recomputes matrices; a singular or non-finite inverse raises an error
instead of silently replacing it with identity, including in diagnostics mode.

Applications that rebuild backend objects can persist `geom.bind_pose_snapshot`
as bytes (for example, base64 in a Blender collection property), then assign it
to the rebuilt GEOM. The compact `DBPS` version 1 metadata contains only the
ordered pose and original matrices: 12 header bytes plus 104 bytes per bone.
It excludes mesh, material and texture data. Loading validates exact lengths,
parent references/cycles, finite transforms/matrices and geometry flags before
replacing any existing snapshot. `b''` clears it.
`geom.bind_pose_snapshot_matches` reports whether the current pose still matches.
The write-time comparison remains mandatory after attaching a snapshot.
For an untouched Blender rig, reuse the exact imported native transform values
after checking that the Blender rest matrices and parents have not changed;
floating-point round trips can otherwise invalidate the snapshot.

Original skeleton parent-pair and lookup arrays are retained when the hierarchy
is unchanged. This includes duplicate pairs and the high-bit flag used by
`chr800`. Editing a flagged hierarchy currently raises an explicit error rather
than dropping flags whose authoring semantics are not yet implemented.
To retain this metadata while rebuilding a skeleton, persist its compact
`skeleton.to_bytes()` result and initialize with `Skeleton.from_bytes(...)`
before replacing its `bones` and `float_channels` with the reconstructed data.
The inverse bind snapshot does not include these skeleton table flags.

## Checks and remaining limits

Twelve test groups exercise malformed pointers/counts, exact record preservation,
mixed camera/light/mesh files, float-table bounds, high-bit parents, raw snapshots,
known lens edits, inverse bind matrix preservation and singular-pose rejection.
Snapshot transfer also tests truncated data, invalid flags/parents, non-finite
values, atomic rejection, rename tolerance and invalidation after pose edits.
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
