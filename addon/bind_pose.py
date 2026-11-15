"""Read the backend's validated bind snapshot without conflating bind and rest.

DBPS is backend project metadata, not a GEOM binary parser. The source skeleton
TRS can differ from its authored inverse bind matrices (for example face states).
"""
import struct


def inverse_bind_matrices(geom):
    snapshot = bytes(geom.bind_pose_snapshot)
    if not snapshot:
        return None
    if len(snapshot) < 12:
        raise ValueError('Truncated bind-pose snapshot')
    magic, version, count = struct.unpack_from('<III', snapshot)
    if magic != 0x53504244 or version != 1 or len(snapshot) != 12 + count * 104:
        raise ValueError('Unsupported bind-pose snapshot')
    if count != len(geom.skeleton.bones):
        raise ValueError('Bind-pose snapshot bone count differs from skeleton')
    return [struct.unpack_from('<12f', snapshot, 12 + i * 104 + 56)
            for i in range(count)]
