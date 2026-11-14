# SPRK source-preserving editing API 1

`addon/spark.py` is the authoritative dependency-free Python module. Importer
vendors that file unchanged as `src/spark.py`; it must not maintain a parallel
serializer. Native GEOM remains the compiled backend; ordinary skeletal ANIM
and companion NLST continue to use the existing Importer serializers. The ANIM
and NLST chunks described here are embedded **SPAK** records, not those separate
skeletal formats.

The implementation promotes the existing research readers and native evidence:
SPAK loader `0x14036B040`, common fields `0x140358750`, ranges `0x14035CE30`,
primary/secondary channels `0x14035A010`, texture reader `0x14035A0F0`, and
material texture links `0x140377CD0`. The pinned executable SHA256 is
`ff9de825a543bf874cfb7e73ed951256d3ce4e8702957afa3b26ca6487a81688`.
Preserve the project's Named-Blade/Nymic_Razor and other upstream credits.

## Public contract

```python
from spark import SparkDocument, Key

effect = SparkDocument.read("selected.sprk")
for node in effect.nodes.values():
    print(node.id, node.kind, node.name, node.children, node.editable)

# Select an actual imported ID in the application's UI; no actor-specific IDs.
effect.set_transform(selected_id, "primary", "translation", (1, 2, 3))
effect.set_timing(selected_id, delay_range=(3, 3), lifetime_range=(30, 30))
effect.write("edited.sprk")  # Refuses an existing destination by default.
```

`from_bytes`, `to_bytes`, `source_sha256`, `fps` and `clock_mode` support saved
project data and provenance. `nodes` returns immutable snapshots. Six
`VectorRange` fields have `low`, `high` and `deterministic`: primary and secondary
translation, rotation and scale. The module's `CAPABILITIES`, `COMMON_KINDS`,
`TRANSFORM_FIELDS` and `EDITABLE_CHANNELS` expose its bounded supported scope.

Kinds 0/2/3/4 have common range/timing editing. Rotation is in degrees; delay and
lifetime are signed 16-bit frames. Infinite lifetime is exactly `(-1, -1)`.
Imported zero/negative scales, flags, random endpoints and opaque data are never
normalized. This API does not apply generated-profile defaults or migrations.
Timing edits require nonnegative delays and either finite nonnegative or fully
infinite lifetime endpoints. Failed setters do not partially mutate a record.

`set_resource(id, field, stem)` edits existing Model4 `model`/`motion`, texture9
`texture`, or material10 first `shader` names. Resource paths are basenames;
dependency existence and shader compatibility still require package validation.
It is not a new shader compiler or material-family authoring API.

`channels(animation_index)` returns immutable header/key snapshots.
`set_channel_keys(index, id, keys)` supports existing clamped constant/linear
channels with unchanged key counts. Frames must strictly increase and fit
int16; values/tangents must be finite float32. Source channel headers, offset
tables and padding remain intact except the explicit min/max value words.
An edit must be supported for every node sharing the animation. Primary TRS
IDs are 1..9; secondary TRS IDs are 28..36. Supported source-backed extra IDs
include sprite color112..115/frame140, model color149..152, texture rect136..139,
and material clock66/custom146. These IDs do not establish complete preview of
the associated shader or random module. Bezier/other extrapolation can be
preserved but editing/evaluation is explicitly rejected.

`validate_editable()` checks counts, bounded spans, unique IDs, known reference
types, the single native type0 root, cycle freedom and reachability. Imported
root IDs need not be zero. Unknown node kinds/chunks and trailing data remain
byte-preservable but prevent semantic edits. All chunk prefixes/suffixes,
terminal header words and untouched key/header bytes survive exactly.

`write(path, overwrite=False, expected_sha256=None)` reparses before output,
writes and syncs a sibling temporary file, and atomically publishes. Existing
destinations require explicit overwrite. A supplied SHA256 catches cooperative
stale writes; it is not an interprocess lock. No-clobber publication uses a hard
link and fails safely where the filesystem does not support it. Failed writes
or publication preserve the previous destination and clean temporary files.

## Verified scope and release blockers

Eight tests cover exact opaque preservation, authored negative/zero scale,
scoped edits, malformed/truncated input, reference/cycle rejection, unsupported
curve retention/rejection and injected IO/publication failures. The local
`local/spark-validation.json` records exact preservation and scoped
edit/export/reopen on four actual files:

| Fixture | Nodes | Byte preservation / edited re-import |
| --- | ---: | --- |
| `ef_b_chr395_bs01_p01.sprk` | 5 | pass |
| `ef_b_chr227_bs01_p02.sprk` | 7 | pass |
| `ef_b_chr004_bs01_p01.sprk` | 7 | pass |
| retained Revision14 `chr39511.sprk` | 348 | pass |

These audits used temporary outputs; source/live files were unchanged. They do
not prove game behavior of the new edits. A complete particle editor, source
emitter simulation, birth/random modules, node creation/deletion/reference
rewiring, parent/socket owner changes, full native preview, semantic lights,
collision editing and full effect-package export remain release blockers.

```powershell
python tests/test_spark.py
python tools/audit_spark.py PATH_TO_EFFECT.sprk --report local/spark-validation.json
```
