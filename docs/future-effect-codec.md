# Requirements for a future shared effect codec

**SPRK/SPAK and effect BSON now have bounded maintained Python editing APIs.**
See [current SPRK editing](spark-editing.md) and [effect BSON](effect-bson.md)
for actual coverage.
This document retains the broader requirements exposed by native cinematic
research, including contracts that remain unimplemented. Existing GEOM,
material, animation-adapter and upstream
Named-Blade/Nymic_Razor attribution remain unchanged.

The evidence applies to the captured SPAK version140 and executable SHA-256
`ff9de825a543bf874cfb7e73ed951256d3ce4e8702957afa3b26ca6487a81688`.
The research implementation is in the adjacent `Time Stranger/tools/` project.
Its native material, shader, GPU and game checks are separate from a container
reader passing structural round trips.

## Preservation, authoring and migration are different operations

An unchanged reader/writer must preserve authored scale0, negative scale,
range endpoints, secondary animation channels, opaque bytes, header flags,
chunk prefixes/suffixes and unsupported record payloads where raw retention is
explicitly offered. Zero scale is not malformed merely because it makes a
particle invisible. A raw inspection/preservation facility must not be
advertised as semantic support for editing an unknown node.

An explicit **generated primary-TRS-only profile** may require neutral
secondary transforms because that generator does not author secondary motion.
Its constructor initializes scale to1, not the zero value of freshly allocated
storage. A validator checks that declared profile without rewriting input.
If a field or curve lies outside the profile, reject conversion rather than
erase it or guess its meaning.

A **migration** needs separate authorization and provenance identifying the
known defective producer output. The mounted profile's flags, clock mode and
zero values alone cannot prove that an arbitrary author's zero scale was an
accident. The research `native_spark_defaults.py` is a narrow, explicitly named
idle migration; it must not become an implicit step in a generic reader or
material exporter. Its caller must establish the original generated artifact
and retain the before/after report. Unsupported authored secondary transforms
or channels are rejected by that migration even when a channel's value is0.

## Required common-record representation

All offsets below are relative to the serialized common NODE payload. Fields
between the established ranges remain raw until decoded; do not collapse the
record into a zero-initialized plain TRS structure.

| Payload field | Established representation | Generated primary-only default |
|---|---|---|
|0 /4 /8 |uint16 node kind / uint32 node ID /64-byte fixed name |Explicit kind, unique ID and bounded name |
|72..95 |Primary translation: Xmin,Xmax,Ymin,Ymax,Zmin,Zmax float32 |Six0 values |
|104..127 |Primary rotation ranges, same component pairing |Six0 values |
|136..159 |Primary scale ranges, same component pairing |Six1 values |
|360..383 |Secondary translation ranges |Six0 values |
|392..415 |Secondary rotation ranges |Six0 values |
|424..447 |Secondary scale ranges |**Six1 values** |
|460 |Draw/inheritance flags |Explicit profile choice; preserve opaque bits |
|532 |Serialized flags interpreted/extended by native initialization |Preserve raw value; do not infer neutrality from this value alone |
|536 |Serialized animation reference, sentinel0xFFFFFFFF for none |Validated reference or explicit sentinel |

The reserved/undecoded spans96..103,128..135,160..167,384..391,416..423,
448..455 and other common fields must remain explicit opaque storage. The
current generated profile sets them to captured known defaults; that does not
establish a generic zero-padding requirement for imported effects.

Primary TRS channels are1..3,4..6,7..9. Secondary TRS channels are28..30,
31..33,34..36. A future typed representation should distinguish both sets and
retain exact channel headers, extrapolation mode, interpolation and key
storage. Missing channels are not equivalent to channels that explicitly
animate zero. Range defaults must be evaluated before multiplying primary and
secondary transforms; validating the primary curves alone is insufficient.

## Why the default matters

Native `140358750` recognizes non-neutral secondary scale at424/432/440 and
sets the secondary-scale bit0x8000 at532, then secondary-transform bit0x10000.
`140399480` evaluates channels34..36 or falls back to those stored minima.
`14035CE30` adds the random range difference. `140399BE0` composes secondary
TRS with the primary animated transform. A missing channel plus default0 thus
means actual zero scale, not identity or an unused field. Clearing the whole
common record and restoring only the primary scale caused observed collapse.

Inheritance is independent of that default. In the established mounted
profile, flags460 mask0x70 enables parent TRS and refreshes the current owner
matrix. `140396950` pushes intermediate1168 to the child stack, and
`14039AAC0` applies owner1232 only when producing final624. A future matrix
validator must model both transform stages and the parent/owner order. It must
not apply the owner once per ancestor or silently substitute identity for a
zero authored matrix.

## Validation gates before promoting support

- Validate chunk spans, counts, signed keyframe bounds, animation references,
  child lists, unique node IDs and the supported root graph before editing or
  packaging. Retain unknown data or reject the requested edit explicitly.
- Separate immutable source bytes from derived runtime pointers and flags.
  Native initialization can replace serialized indices with pointers; a
  runtime memory record is not directly serializable file data.
- Make profile selection explicit. Reject unsupported node kinds, partial
  inheritance semantics, secondary curves, stochastic modules or extrapolation
  modes until their authoring/evaluation contracts are implemented. Do not
  describe a partial validator as complete SPAK validation.
- Reuse shared typed ranges and animation records across import/export rather
  than keeping divergent copies in Blender, a particle generator and a packer.
  Keep file-specific layout and API version boundaries explicit.
- Serialize into temporary storage, validate and compare the scoped diff,
  then atomically replace the destination. Preserve original files and reject
  unrecorded input changes. Package only tested platform/CPython ABIs.
- Test full primary/secondary/parent/owner composition, raw authored-zero
  preservation, profile rejection and idempotent explicit migration. Native
  draw/output and in-game appearance still require separate acceptance.

The research regression command is:

```powershell
python "Time Stranger/tools/test_native_spark_authoring_profiles.py"
```

Run it from the modding workspace. Its8 tests cover generated defaults,
intentional zero-scale round trips, the scoped legacy migration, identity
idempotence and rejection of authored secondary curves/ranges/other profiles.
They do not install assets, introduce a backend codec, or establish complete
Leviamon head-ring/cinematic fidelity. Revision12 still has reported visual
defects despite the proven secondary-scale default correction.
