# Native bind and rest poses

The reference Blender adapter preserves the distinction reported in upstream
[issue #4](https://github.com/Named-Blade/dsts-formats/issues/4). The extracted
`chr189.geom` has 167 bones. Fourteen facial bones have authored rest scale 0.1,
while their inverse bind matrices describe unit-scale bind bones. Their
translations and rotations agree within floating-point precision. Overwriting
either representation with the other loses native deformation information.

The existing backend already preserves both arrays through its compact
`bind_pose_snapshot` API. Its mismatch diagnostics remain intact. This change
does not alter the C++ parser, weaken strict validation, or rebuild the backend.

The reference adapter now builds Blender skin bind bones from those matrices and
places the authored native rest transforms in the pose. It retains exact native
TRS and the original inverse-bind snapshot for an untouched geometry export.
Successfully represented bind/rest differences become retained import notes;
other backend diagnostics remain warnings. Blender edit bones cannot represent
scaled or sheared bind matrices, so the reference adapter rejects that unsupported
case explicitly. This adapter does not import native animations.

Native duplicate material names also remain distinct by their original table
indices and material objects. Export no longer merges those variants by name.
User-created copies sharing an original identity remain an export error until
they receive distinct native names.

`tools/blender_bind_rest.py` runs against an external model fixture and an
explicit native module. The Blender 5.3 chr189 check verifies native skinning
matrices, all 167 exact authored TRS records, original inverse-bind bytes, all 16
material variants and mesh assignments, and rejection of copied material
identities. It retains all 14 original backend diagnostics. Source geometry and
generated assets are not committed.

The maintained Time Stranger Importer uses a narrower animation-compatible
uniform leaf-scale correction layer. It keeps source animation deltas unchanged
and separately verifies NLA composition, active actions and animation export.
That workflow is not implemented by this minimal reference adapter.
