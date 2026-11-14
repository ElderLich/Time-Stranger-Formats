# Time Stranger Formats

**Understand the files. Preserve the details. Build better modding tools.**

A maintained derivative of **[Nymic_Razor / Named-Blade's original parser](https://github.com/Named-Blade/dsts-formats/tree/parser)**.

A C++20 parser and Python backend for *Digimon Story: Time Stranger* geometry,
with Blender adapters and binary format notes. This is the maintained source
home for the backend used by
[Time Stranger Importer](https://github.com/ElderLich/Time-Stranger-Importer).

[Build](#build) · [Use from Python](#use-from-python) · [Format coverage](docs/formats.md) · [Credits](#credits)

## What it does

- Reads and writes `.geom` meshes, vertex attributes, skinning, skeletons and materials.
- Preserves native camera/light records and ordered skeleton float-channel bindings.
- Preserves complete material pass metadata and rejects invalid static texture bindings using typed native descriptors.
- Keeps original inverse bind matrices for unchanged rigs, including through compact project snapshots.
- Checks binary ranges and object references before access; unsupported sections fail explicitly.
- Exposes geometry objects through the compiled `dsts_formats` Python module.
- Generates companion `.nlst` name lists through the reference Blender adapter.
- Edits established SPAK v140 transform ranges, timing, resources and fixed-size
  curves through the dependency-free [SPRK API](docs/spark-editing.md), preserving
  every unrelated source byte.
- Includes ImHex patterns and shader parameter definitions for format research.

This is the format backend. For the complete Blender workflow, animations and
New Century conversion, use **Time Stranger Importer**. Animation serialization
is currently a separate component; this repository does not yet implement every
Time Stranger format. [Coverage and known gaps](docs/formats.md) are tracked explicitly.

## Build

Requirements: **CMake 3.29.3+**, a **C++20 compiler**, and Python development
headers/libraries matching the Python interpreter that will load the extension.
Install `pybind11` in that interpreter's environment.

```powershell
python -m pip install pybind11
cmake -S . -B build -DPython3_EXECUTABLE="C:/path/to/python.exe" -Dpybind11_DIR="C:/path/to/pybind11/share/cmake/pybind11"
cmake --build build --config Release
```

For Blender, match its **embedded Python ABI**, architecture and operating
system. A renamed `.pyd` is not a compatible build. The current importer uses
CPython 3.13 on Windows x64; check the target Blender version before building.

The build produces the native module. Add `-DDSTS_BUILD_REFERENCE_ADDON=ON`
when configuring to also create a reference add-on ZIP. The reference
add-on is useful for development; the maintained user interface lives in
**Time Stranger Importer**. See [build notes](docs/building.md) for integration.

## Use from Python

Add the build output directory containing the extension to `PYTHONPATH`, then:

```python
import dsts_formats

model = dsts_formats.Geom.from_file("chr_example.geom")
print(len(model.meshes), len(model.materials), len(model.skeleton.bones))
model.to_file("chr_example_edited.geom")
```

Camera and light records retain their unknown bytes. Float channels retain
their binding metadata; animation samples belong to the separate ANIM codec.
See the [scene-record API](docs/scene-records.md) for lens editing and saving
bind-pose snapshots in a project.

## Verified scope

The CPython 3.13 Windows x64 backend passes **15 safety test groups**,
**10 material-contract tests** and **3 build/package tests**. A deterministic
100-character sample and seven scene fixtures pass structural round trips,
including exact comparisons of camera/light records, float bindings, inverse
bind matrices, parent tables and complete material pass/parameter records. The consuming importer also passed checks in
**Blender 5.1 and 5.3** with this backend.

These checks do not establish complete format support or game acceptance.
The SPRK API additionally passes eight malformed-input/edit/write-failure tests
and scoped edit/export/reopen checks on three native donors and the retained
Revision 14 actor effect. It does not implement a complete particle simulator.
Mesh controllers and edits to flagged skeleton hierarchies fail explicitly;
bounds are still recomputed on export. The reference add-on blocks exports
that would discard scene or binding metadata. Use the maintained importer for
the complete Blender workflow, and consult [coverage and limits](docs/formats.md)
before editing a new asset type.

## Inside the repository

| Path | Purpose |
| --- | --- |
| `src/geom/` | Geometry reader/writer and binary records |
| `src/python/` | pybind11 bindings |
| `src/utils/` | Math, hashes, binary buffers and errors |
| `addon/` | Reference Blender geometry adapter and name-list writer |
| `notes/` | ImHex patterns and shader parameter table |
| `docs/` | Build guidance, format coverage and provenance |

Generated builds, caches, local game assets and test exports do not belong in
source control. The shader parameter table is an input to the build, not junk.

## Credits

- **Nymic_Razor / Named-Blade** — original parser, Blender adapter and
  [DSTS Formats Parser](https://github.com/Named-Blade/dsts-formats/tree/parser).
- **Senator John, Zeak, Romsstar, Pherakki and the Digimon modding community** —
  related importer work and tools used by the wider project.
- **Hyotan's workshop** — [Time Stranger modding guides](https://hyotan-dev.github.io/dstsworkshop/).

This repository starts from the supplied DSTS Formats Parser source and keeps
its baseline as the first commit. See [provenance](docs/provenance.md) for the
source inventory and attribution. No licence file was present in that source
copy; this maintenance repository does not assign a new licence to upstream code.
