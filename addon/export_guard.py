"""Explicit limits of the reference Blender reconstruction path."""

PROPERTY = 'DSTS_unsupported_export_sections'


def require_supported_export(owner):
    reason = owner.get(PROPERTY, '')
    if reason:
        raise ValueError('Reference add-on cannot preserve ' + reason +
                         ' during Blender reconstruction. Keep the original file or use the backend preservation API.')


def mark_geom_sections(collection, geom):
    sections = []
    for label, values in [('camera records', geom.cameras), ('light records', geom.lights),
                          ('float-channel bindings', geom.skeleton.float_channels)]:
        if values:
            sections.append(label)
    if sections:
        collection[PROPERTY] = ', '.join(sections)


def mark_skeleton_sections(armature, skeleton):
    import struct
    sections = []
    if skeleton.float_channels:
        sections.append('float-channel bindings')
    # The backend retains these bits, but this add-on rebuilds a new Skeleton.
    raw = skeleton.to_bytes()
    count = struct.unpack_from('<I', raw, 60)[0]
    if any(struct.unpack_from('<H', raw, 64 + i*4 + 2)[0] & 0x8000 for i in range(count)):
        sections.append('flagged skeleton parent records')
    if sections:
        armature[PROPERTY] = ', '.join(sections)
