# Four-lane native parent-pair layout

This extends the upstream Named-Blade / Nymic_Razor parser with a native runtime
contract found during the separate Leviamon conversion research. It does not
change the source transform or animation coordinate conventions.

Native `140364850` evaluates `(pair_count+3)>>2` groups of four `(child,parent)`
records. Every lane executes, including physical records beyond a declared count
that is not a multiple of four. The function first writes the child's local
matrix, then reads the parent matrix. Zero-filled alignment therefore encodes
`(0,0)` self-parent operations rather than inert padding. On a one-bone Figure,
those operations replace its owner-transformed root with the local matrix
squared. The captured broken Model4 palette matched that calculation bit-for-bit.

Two original base-game one-bone donors, `t0109traffic01d.geom` and
`t0109traffic01e.geom`, use a declared count of four and four `(0,0x7FFF)` root
pairs. Both place transforms at skeleton-relative80, after the64-byte header and
16-byte physical pair span. Larger native hierarchies also contain repeated
valid entries in their declared pair arrays.

## Authoring and preservation

For a fresh or regenerated unflagged hierarchy, the writer repeats its final
valid pair until the count is a multiple of four and includes those repeats in
the declared count. A valid pair's parent is distinct from its child, or is the
owner sentinel `0x7FFF`, so repeating the assignment does not replace the parent
with the child's local matrix. Parent lookup entries still refer to the original
semantic assignments. This does not change skeleton bone order or count.

Unchanged imports retain their declared pair array and lookup table. The reader
now also retains the physical rounded tail beyond a legacy nonmultiple count;
rewriting an unchanged hierarchy preserves that tail. A flagged physical tail
receives the same unsupported-hierarchy-edit rejection as flagged declared pairs.
The rounded physical range must fit the supplied skeleton data.

Reading or preserving an old file does **not** certify runtime safety. In
particular, an already generated file containing `(0,0)` padding is not silently
repaired on import. Its caller must use an explicit bounded migration. An exact
byte package workflow must check the physical rounded parent lanes itself; it
cannot rely on the authoring correction to alter copied bytes. The known319-file
idle migration changes the declared count1 to4 and three existing root padding
pairs, exactly7bytes per file, without moving any section. It deliberately does
not expand to the103-bone actor or unrelated cinematics.

## Regression coverage

`test_parent_pairs_fill_native_simd_groups_safely` covers one through six bones,
nonidentity owner/local matrices, idempotent repeated root/child evaluation,
read/write preservation, a legacy count with a distinct physical tail, and
rejection of unsupported flagged-tail hierarchy edits. No original donor data
is distributed. Existing semantic-diagnostic collection is separate from native
runtime acceptance; Blender clients need a rebuilt matching backend.
