# Native matrix-palette fast path

The GEOM implementation retains the upstream work of
[Named-Blade / Nymic_Razor](https://github.com/Named-Blade/dsts-formats/tree/parser).
This interpretation adds native/runtime evidence for one existing mesh flag;
other mesh bits remain opaque.

For GEOM316, the mesh-header byte at `+0x31` contains `flag_2` (`0x04`).
Native functions `1402DE620` and `1402DEC00` copy that byte into the Figure's
per-mesh flags array at `Figure+432`. In `1402E63A0`, the bit selects the
MatrixPalette upload path:

- Set: upload `palette_count` consecutive 48-byte matrices starting at the
  skeleton matrix indexed by `palette[0]`.
- Clear: gather each 48-byte matrix using every serialized palette index.

The fast path therefore requires an ascending contiguous skeleton-index list.
A single bone and a nonzero starting index are valid. Sparse, reordered or
duplicate entries are invalid under this flag, even when all indices are
individually within the skeleton and every vertex uses a valid local index.

The writer now rejects that inconsistent combination before opening a file,
including in semantic-diagnostic collection mode. It does not silently clear
the flag, reorder bones or change vertex indices. Reading retains the original
flag and palette so an existing file can be inspected and deliberately repaired.
Clearing the fast flag preserves a sparse palette's intended gather behavior;
this should be a caller's explicit correction, not a generic import mutation.

## Reproduced failure

The generated Leviamon `body_2_effect` had `flag_2` set and a sparse 20-bone
palette. Its live GPU palette instead contained skeleton indices20 through39.
All11 of those matrices available in a simultaneous body draw matched exactly.
The measured white pixel came from glow primitive372: the triangle expected
unmirrored `Bone039`/`Bone047`, but the fast path supplied mirrored
`Bone048(mirrored)`/`Bone049(mirrored)`. Native upload arithmetic predicted its
captured post-VS clip coordinates within `4.81e-7`. Vertex and index buffers
were byte-identical to the serialized mesh. Thus ordinary parser/index bounds
checks and offline correct-palette skinning did not detect the runtime error.

The separate research project's isolated correction clears one bit in each
actor GEOM and changes no material, shader, bone, binding, vertex, animation or
layout. In-game verification remains separate from the captured-frame proof.
Proprietary capture/assets are not distributed with this repository.

## Validation

`test_contiguous_palette_flag_matches_native_upload` covers nonzero starts,
single-bone and multi-bone contiguous palettes, rejection of sparse/reordered/
duplicate palettes, diagnostic-mode enforcement, preservation of an existing
destination after rejection, and forensic reading of a pre-existing invalid
combination. The other safety/material/package regressions remain applicable.

The rebuilt CPython3.13 Windows x64 backend passed all13 safety groups,10 material
tests and3 build/package tests. The deterministic100-character corpus and7 scene
fixtures still pass with documented semantic diagnostics collected. The failed
Leviamon input is readable but rejected on write; its isolated flag-clear
candidate passes write validation. Blender packaging/in-game acceptance are
separate downstream checks.

This writer-only check changes no Python API or ABI. A rebuilt backend is needed
by clients to obtain the guard; it does not certify a previously bundled binary.
