# Native effect BSON editing API 1

`addon/effect_bson.py` is the authoritative pure-Python module and imports the
atomic output helper from `spark.py`. Importer consumes identical source files.
The container is **MVGL BSON v10**, not MongoDB BSON. The implementation promotes
the existing research parser while adding bounded nesting, immutable structure,
source-exact record retention, typed fields and safe writing.

## Native evidence and edit scope

The evidence targets executable SHA256
`ff9de825a543bf874cfb7e73ed951256d3ce4e8702957afa3b26ca6487a81688`:

| Contract | Native evidence | API support |
| --- | --- | --- |
| Container/version | `0x140431A60`, lengths `0x140431C70` | bounded objects, count/child coverage, extended base65535 lengths, string references |
| Duration and hit frames | root `0x140CCB120`, update `0x140CC2C10`, hit lookup `0x140232060` | `mf`, `hf.hf0` through `hf.hf7` |
| Sound fields | reader `0x140CCBAA0`, start `0x140CBA280`, cleanup `0x140CBA150` | cue ID, offset, stop, fadeout, volume, stream, spatial flag |
| Drawable names | `0x140CD0B80` copies `dn` into32 bytes | existing emitter basename, at most31 bytes |
| Inter-set sockets | `0x140CCBAA0` reads `bt_id/pos/rot/sca`, `0x140CBD470` resolves owner and locators | existing owner/position/rotation/scale strings with caller-supplied actual socket inventory |

Timing is **30Hz frames**, independent of a SPRK's selected frame rate.
`mf=-1` is indefinite effect lifetime. Hit frames are separate indexed event
timings; changing `mf` does not automatically change the battle timetable,
actor motion or camera duration. The API does not invent such synchronization.

`se_name` is the packed native sound ID, not the bank-local Ryo cue ID. The
reference conversion keeps native329511 and bank-local9511. Public UI must
offer user-selected mappings and bank validation; this module never supplies
Leviamon defaults. Sound fade fields govern cleanup policy, not audio resampling.

## Public API

```python
from effect_bson import EffectDocument

effect = EffectDocument.read("selected.bson")
for field in effect.fields:
    print(field.path, field.label, field.value, field.value_type, field.units)
for effect_set in effect.sets:
    print(effect_set.name, effect_set.id, effect_set.drawables)

effect.set_field(("mf",), 120)
effect.set_field(("set0", "common", "se", "se_offset"), 3)
effect.write("edited.bson")
```

`from_bytes`, `to_bytes`, `source_sha256` and `value(path)` support project
snapshots and inspection. `fields` contains source-ordered immutable
`EffectField(path, label, value, value_type, units)` entries for supported
source-present fields. `sets` provides immutable summaries with names, IDs,
drawables, sound identity/start and attachment owner/sockets. Unknown fields
can be preserved and inspected but cannot be edited via `set_field`.

`set_field` validates types, finite values and supported limits before writing
the existing scalar. Boolean values are integer0/1, sound gain is0..1, and
non-duration frame fields are nonnegative int32. Existing out-of-profile values
are retained unchanged; the importer must compare actual edits before calling
setters. Adding/deleting fields or changing object ordering is not supported.

`set_attachment(set_name, owner_id=..., position_socket=..., rotation_socket=...,
scale_socket=..., available_sockets=...)` edits existing inter-set attachment
records after validating a unique owner, real socket names and cycle freedom.
The caller must supply the chosen owner's actual imported native NLST/rig
names. Empty per-axis names retain native fallback behavior; they are not
interpreted as a fabricated bone. Names must fit the native31-byte UTF-8 limit.
External caster/target aliases are not resolved and remain unsupported edits.
The method stages all four changes before publishing them in the document.

Scalar edits patch four existing payload bytes. String edits patch the existing
index and append to the retained pool. Original object lengths, noncanonical
extended-length encoding, order, unknown primitive payloads and unused pool
strings remain exact. The reader rejects malformed spans, unterminated or
invalid referenced strings, incorrect known scalar widths and nesting beyond128.
Ambiguous duplicate keys can be preserved, but edits through ambiguous paths fail.

`write` uses the same no-clobber default, explicit overwrite, expected-SHA256
guard and failure cleanup as the [SPRK writer](spark-editing.md).

## Evidence and remaining release work

Eight tests cover preserved unknown records, fixed numeric patches, appended
resource strings, invalid/unsupported fields, socket/owner/cycle guards,
malformed prefixes/counts/indices, extended objects and IO failure protection.
The local report `local/effect-bson-validation.json` records exact preservation
and duration edit/export/reopen of `ef_b_chr395_bs01.bson` (10 sets),
`ef_b_chr039_bs01.bson` (3 sets), and retained Revision14's root (248 sets).
Every unrelated byte and source file remained unchanged.

This is a bounded maintained editor API, not full skill playback acceptance.
Event creation/deletion, emitter/controller fields, external actors/targets,
concurrent display/cast clocks, lights, complete renderer/particle preview,
scene lifecycle and full effect-package dependency validation remain release
blockers. In-game behavior of the newly edited fields has not been accepted.

```powershell
python tests/test_effect_bson.py
python tools/audit_effect_bson.py PATH_TO_EFFECT.bson --report local/effect-bson-validation.json
```
