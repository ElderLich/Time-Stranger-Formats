# Format coverage and research queue

This inventory describes the imported baseline. Improvements must cite a
reproducible test or a native/extracted-file observation before changing a
field's interpretation.

| Area | Baseline support | Work to complete |
| --- | --- | --- |
| GEOM meshes | Read/write vertex attributes, indices and material assignments | Validate all offsets, counts, palette and material indices before access |
| Skeleton | Bones, hierarchy, inverse bind poses | Preserve indexed float channels; validate hierarchy references |
| Materials | Shader keys, uniform and setting records | Verify parameter names against the correct game version and binding domain |
| Cameras | Explicitly unsupported | Implement the observed 56-byte native camera records and associated float channels |
| Lights | Explicitly unsupported | Recover record layout and preservation rules from files/native loader |
| Mesh controllers | Explicitly unsupported | Establish bounded records and exact round-trip behavior |
| NLST | Reference add-on writes name lists | Validate type coverage and deterministic ordering |
| ANIM | Not implemented here | Currently supplied by the importer's separate animation serializer |
| SPRK / effect BSON | Not implemented here | Native cinematic tooling is being researched separately |
| Math | X-mirror operation implemented | Audit documented mirror-Y/mirror-Z TODO against actual coordinate requirements |

## Known risk in the baseline

The existing reader trusts several file lengths and indices. Some unsupported
sections are assertions which can be configured as warnings; exporting such a
file may discard data. These need explicit checks before the backend can claim
safe preservation of arbitrary GEOM files.

Shader parameter labels also need a version/domain audit: the stored table and
the current runtime table use different labels at some numeric values. Raw
identifiers must remain unchanged until the mapping is proven. Guessing a
global offset would corrupt material meaning.

## Acceptance for a format change

1. Record the input version and the binary/native evidence for the layout.
2. Test the smallest representative valid file and malformed/truncated variants.
3. Read, write and re-read real external fixtures; compare semantic values and
   any unknown bytes promised to be preserved.
4. Run the consuming Blender importer's checks before replacing its backend.

An unresolved field stays explicitly unknown. A successful parse alone does
not prove that the game accepts an exported asset.
