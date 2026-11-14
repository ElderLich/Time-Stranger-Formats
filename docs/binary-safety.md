# Binary safety milestone

The GEOM 316 reader validates byte ranges, counts and cross references before
allocating arrays or indexing objects. Malformed data raises a Python exception;
it must not terminate the host process through a C++ assertion. Setting
`set_throw_errors(False)` collects optional semantic diagnostics only. It cannot
disable bounds checks or permit an unsupported section to be silently discarded.

## Changes

- Checked reads cover headers, relative offsets, skeleton arrays and parent
  graphs, strings, mesh layouts, palettes, indices and material payloads.
- Parent cycles and invalid references are rejected before linking bones.
  World transforms use an iterative walk instead of recursive traversal.
- Vertex layouts reject zero strides, invalid types/counts, duplicate attributes,
  truncated buffers and mismatched influence descriptors. Writes validate object
  membership, index ranges, attribute consistency and finite positions.
- The writer rebuilds the serialized vertex descriptor and stride after its
  single-influence packing step. Previously it packed against a stale layout.
- Name tables no longer contain leading empty entries from resizing and then
  appending. Standalone skeleton writes preserve hashes when names are absent.
- File exports serialize and validate before opening an existing destination.
  Invalid objects therefore do not truncate that file. Disk-write failures still
  raise an exception; this is not an atomic replacement API.
- Memory output seeking and growth no longer depend on null pointer arithmetic
  or narrowing offsets through `pbump(int)`.
- Python mesh arrays and CLUT reads return snapshots with owned storage. Retained
  arrays remain valid after resizing or deleting their source object. Update
  data through the setters; mutating a returned array does not edit the mesh.
  Array setters validate row/component counts and copy strided inputs correctly.

## Explicit limits

At this milestone, lights, cameras, mesh controllers and skeleton float channels
are rejected even in diagnostic-collection mode. They are not round-tripped by
the inherited object model. Unknown primitive/index encodings and unsupported
vertex layouts also fail explicitly. Nonzero GEOM read bases are supported;
nonzero write bases are rejected.

Existing semantic checks compare stored inverse bind poses and bounds against
recomputed values. Some original game files disagree with those assumptions.
Collection mode allows inspection with those diagnostics; it is not evidence
that rewriting those files preserves every native semantic. The current writer
recomputes inverse bind poses and bounds. Byte-identical GEOM preservation and
in-game acceptance are outside this milestone's validation.

## Validation (2026-11-14)

Built `dsts_formats.cp313-win_amd64.pyd` with CPython 3.13.14, pybind11 3.0.4 and
Visual Studio 2022/MSVC 19.44. All six test groups in
`tests/test_binary_safety.py` pass, including every truncated prefix of a valid
synthetic GEOM/skeleton, malicious lengths/offsets/indices in both diagnostic
modes, unsupported-section rejection, array lifetime and strided-input checks,
parent cycles, single-influence round trips and preservation of existing files
after invalid export attempts.

A deterministic sample of 100 `chr*.geom` files from the extracted base, patch
and DLC corpus was selected by sorting paths and shuffling with seed 316.

| Mode | Structural round trips | Rejected |
| --- | ---: | --- |
| Strict semantic errors | 54 | 42 existing bind-pose/bounds disagreements; 4 float-channel files |
| Collect semantic diagnostics | 96 | 4 float-channel files |

The four unsupported files were `app_0.dx11/chr777.geom`, `chr800.geom`,
`chr096.geom` and `chr195.geom`. The 96 round trips checked mesh/bone counts,
mesh names, topology, palette counts, vertex counts and three sampled positions
per mesh. This does not constitute full byte/attribute or native runtime parity.
Local detailed reports are under ignored `local/binary-safety-corpus*.json`.

Run with the same Python ABI used to build the extension:

```powershell
python tests/test_binary_safety.py --module-dir build-parser/Release
python tests/test_binary_safety.py --module-dir build-parser/Release --corpus PATH_TO_EXTRACTED_DATA --limit 100 --collect-semantic --report local/binary-safety-corpus-warnings.json
```
