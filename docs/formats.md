# Format coverage and tested limits

Current coverage builds on **[Nymic_Razor / Named-Blade's original parser](https://github.com/Named-Blade/dsts-formats/tree/parser)**.
It targets the captured **GEOM version 316** and its embedded **60SE skeleton**.
Field interpretations require reproducible extracted-file or native evidence;
unknown fields remain explicitly unknown.

| Area | Implemented | Limits |
| --- | --- | --- |
| GEOM meshes | Bounded reads/writes of vertex attributes, indices, palettes, material references and names; [contiguous-palette flag validation](mesh-palettes.md) on export | Supported triangle lists/strips and 16-bit indices; up to four influences. Unsupported layouts/controllers fail explicitly. |
| Skeleton hierarchy | Validated references and cycles; native high-bit parent decoding; exact original parent-pair/lookup tables when topology is unchanged | Edits to a captured flagged hierarchy are rejected rather than dropping its flags. |
| Inverse bind matrices | Original bytes retained while ordered parents, native transforms and geometry flags are unchanged | Edited poses recompute matrices; singular/non-finite inverses fail instead of falling back to identity. |
| Project snapshots | Compact validated `Geom.bind_pose_snapshot` bytes and a match-status property | Caller must retain the snapshot and exact source transforms for an unchanged rig. Snapshot data is project metadata, not a game format. |
| Skeleton float channels | Ordered uint32 indices, uint32 target hashes and uint8 flags preserved | Binding metadata only; no ANIM samples. Target renames and shader compatibility remain caller responsibilities. |
| Materials | All fourteen shader slots, opaque headers, uniform/setting records; 791 typed native descriptors; independent material cloning and static texture guards | Parameter schema is pinned; special type codes stay opaque. Shader linkage and runtime pass output compatibility require separate checks. |
| Cameras | Exact 56-byte records, bone hash and verified FOV/near/far/orthographic-scale/projection fields | Other words remain opaque; no camera animation player or Blender camera conversion here. |
| Lights | Exact 240-byte records and bone hash | Optical parameters remain opaque; no light renderer or Blender light conversion here. |
| CLUT | Full color-table byte preservation with length-checked assignment | Python reads return owned snapshots. |
| Mesh controllers | Explicitly unsupported | Mandatory rejection even when collecting semantic diagnostics. |
| NLST | Reference add-on writes companion name lists | Not a general NLST parser; broader type coverage and ordering need separate validation. |
| ANIM | Not implemented here | Time Stranger Importer supplies its separate animation serializer. |
| SPRK / effect BSON | Not implemented here | Native cinematic tooling lives in the separate research project. [Future codec requirements](future-effect-codec.md) distinguish raw preservation from generated-profile defaults and explicit migrations. |
| Math | Existing transforms and X-mirror; safe inverse failure | Mirror-Y/mirror-Z TODOs have not been promoted to supported behavior. |

The [scene-record documentation](scene-records.md) lists native functions,
record offsets, APIs and fixture names. The [shader-parameter documentation](shader-parameters.md)
records the pinned table, loader evidence and reproduction tool.

## Safety and preservation contract

Binary ranges, lengths, types, cross references and hierarchy checks run before
allocations or indexing. Malformed input raises a catchable exception. Optional
`set_throw_errors(False)` collects semantic disagreements such as source bounds
that differ from recomputed bounds; it does not bypass mandatory safety checks
or authorize dropping an unsupported section. Inspect `get_error_list()` after
using collection mode.

File export serializes and validates before opening an existing destination, so
invalid objects do not truncate it. A later disk-write failure is still possible;
the file API is not an atomic replacement operation. Python mesh/material/CLUT
snapshots own their storage and stay valid after deleting or resizing the source.

Exact preservation applies to the documented records and unchanged source bind
metadata. The writer still recomputes bounds and rebuilds other layout sections.
Whole-file byte identity and every vertex attribute are not covered by the
current corpus assertions. A successful parse or round trip does not prove
native game acceptance.

## Backend and reference Blender add-on

The backend can preserve scene records directly. The reference adapter in
`addon/` reconstructs fresh objects from Blender and has a narrower export scope:
it marks imported camera/light records, float-channel bindings and flagged
parent tables, then blocks export with a specific explanation if it would lose
them. Its guard and packaging tests are not a full Blender runtime certification.

The separately maintained **Time Stranger Importer** uses this backend and owns
the production Blender workflow. Its Blender 5.1 and 5.3 checks passed with the
final CPython 3.13 Windows x64 module, including float/ANIM round trips, material
renaming, exact source IBPM retention, stale-pose invalidation, flagged hierarchy
preservation/rejection, and New Century conversion. This does not imply support
for every future Blender 5.x Python ABI or native game acceptance of all exports.

## Validation record

Validated on 2026-11-14 with CPython 3.13.14, pybind11 3.0.4 and MSVC 19.44:

- **13 safety groups:** truncated/malformed binaries, checked array APIs, scene
  records, parent flags, bind-matrix snapshots, singular edits and reference
  add-on export guards, and mandatory contiguous-palette fast-path validation.
- **10 material-contract tests:** all typed descriptors, invalid static texture
  rejection, explicit numeric/setting checks, independent complete material
  cloning, exact pass/metadata round trips including nonzero unused numeric
  payload bytes, value ownership and invalid keys.
- **3 build/package tests:** typed shader-table validation and archive contents.
- **100/100 deterministic character fixtures:** structural read/write/read with
  semantic diagnostics collected; exact IBPM, float-binding and parent-table
  comparisons, plus complete material headers, all fourteen shader descriptors,
  numeric/setting records and resolved texture metadata. Mesh/bone counts,
  names, topology, palette/vertex counts and three positions per mesh are checked.
- **7/7 scene fixtures:** exact camera/light/float/IBPM/parent and material
  records, including native material-float effects and mixed camera/light files.
- **3 generated Leviamon particle fixtures:** exact native material float bindings.
- **Leviamon donor and current actor:** exact material records, including the
  nonzero unused numeric payload words that revealed the earlier preservation gap.

Detailed local reports remain under ignored `local/`; proprietary fixtures are
not distributed. See [binary safety](binary-safety.md) for the initial milestone
and [scene records](scene-records.md) for subsequent coverage.

```powershell
python tests/test_binary_safety.py --module-dir build-parser/Release
python tests/test_material_contract.py --module-dir build-parser/Release
python tests/test_build_tools.py
python tests/test_binary_safety.py --module-dir build-parser/Release --corpus PATH_TO_EXTRACTED_DATA --collect-semantic --limit 100 --report local/binary-safety-corpus-scene-support.json
python tests/test_binary_safety.py --module-dir build-parser/Release --corpus PATH_TO_EXTRACTED_DATA --collect-semantic --scene-fixtures --report local/scene-record-corpus.json
```

For another format or variant, record its version/evidence, test malformed and
minimal valid inputs, compare promised preserved bytes on real files, then run
the consuming importer's checks before replacing its backend.
