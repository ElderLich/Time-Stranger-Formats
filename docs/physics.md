# Native PHYS collision editing

`addon.physics.PhysicsDocument` reads the game's standalone `.phys` resources,
exposes collision bodies and shapes, and writes bounded edits to existing
records. It is independent of Blender. Unchanged documents round-trip exactly;
only the selected fields change. Padding, reserved fields, and trailing bytes
remain byte-for-byte intact. The source extraction is never rewritten by the
codec unless the caller explicitly selects that path and opts into replacement.

Supported editing APIs:

- `read(path)` / `from_bytes(data)`, `to_bytes()`, and
  `write(path, overwrite=False, expected_sha256=None)`.
- `bodies`: immutable `Body(position, rotation_xyzw, mass, shape_index, name)`
  views. `set_body(index, position=..., rotation_xyzw=..., mass=...,
  shape_index=..., name=...)` updates selected fields. Quaternions use native
  `(x, y, z, w)` order; the codec does not silently normalize them.
- `shapes`: immutable `Box`, `Sphere`, or `TriangleMesh` views. Box extents are
  half extents in native coordinates, sphere dimensions are radii, and triangle
  meshes expose existing float3 vertices and uint32 vertex-index triples.
- `set_box(index, half_extents=...)`, `set_sphere(index, radius=...)`,
  `set_vertex(shape_index, vertex_index, position)`, and
  `set_triangle(shape_index, triangle_index, vertices)`.
- `set_mesh(index, vertices=..., triangles=..., table_a_indices=...,
  table_b_indices=...)` applies selected existing arrays in one validated
  transaction. Counts must stay unchanged. Use it when exporting many edited
  vertices/faces so the document is reparsed once per shape.
- `table_a` and `table_b`: fixed-width source name tables. Their native indexing
  is established; full gameplay meaning is not yet established, so the public
  API deliberately retains neutral names. `set_table_name('a' | 'b', index,
  name)` edits an existing name. `set_shape_associations(index,
  table_a_index=..., table_b_index=..., triangle_index=...)` updates a primitive
  association or one triangle's associations. Mesh calls require a triangle
  index. Bodies reference existing shapes through `shape_index`.

Writes use the shared `spark.atomic_write`: default no-clobber publication,
explicit replacement, optional stale-destination SHA256 verification, fsync,
and atomic publication. Each edit validates a candidate before updating the
document, so an invalid multi-field edit leaves the document unchanged.
`source_sha256` identifies the imported snapshot, and `write()` returns the
published output's SHA256.

Unknown shape kinds, other versions, overlapping/aliased records, invalid
offsets/counts/references, nonfinite values, negative mass or dimensions, and
zero quaternions are rejected. Names must fit the existing field, with a NUL
terminator on newly assigned names. Shipped full-width names are bounded when
read and preserved unchanged. Adding/removing shapes, bodies, triangles,
vertices, or name-table entries is not implemented. Body material scalars and
flags, six unused mesh-header floats, new shape kinds, and graph rebuilding
remain release work; they are not exposed as guessed semantic controls.

## Native evidence

The evidence is from executable SHA256
`ff9de825a543bf874cfb7e73ed951256d3ce4e8702957afa3b26ca6487a81688`.
Recovered assembly is local research, not original source code.

`0x1403B7420` appends `.phys` to the requested resource name. At
`0x1403B756F` it accepts version 2. At `0x1403B760E` through `0x1403B762F`
it rebases four file-relative 64-bit offsets. The little-endian file header is
`SYHP`, numeric magic `0x50485953`; the native loader checks the version rather
than the magic, while this codec checks both.

| Field | Header offset | Record representation |
| --- | --- | --- |
| Body count / body array | 8 / 24 | 76 bytes per body |
| Shape count / pointer array | 12 / 32 | File-relative uint64 shape offsets |
| Table A count / array | 16 / 40 | 64-byte source names |
| Table B count / array | 20 / 48 | 64-byte source names |

The native loader allocates by body count but constructs bodies using shape
count. Every audited source has equal counts; the codec requires equality.
Body position is float3 at 0, quaternion float4 at 12, mass float at 40,
shape index uint32 at 44, and name24 at 52. The setter calls at
`0x1403B7B9B`, `0x1403B7BC9`, and `0x1403B7BEE` establish name, translation,
and rotation. The mass argument reaches rigid-body construction in
`0x1403ACAA0`, where nonzero mass requests inertia.

Shape dispatch at `0x1403B76F2` establishes kinds 0, 1, and 2. Kind 0 passes
the float3 at +8 through the Bullet box construction calculation: local
scale times half extents minus the collision margin. This matches the
[upstream Bullet box constructor](https://github.com/bulletphysics/bullet3/blob/master/src/BulletCollision/CollisionShapes/btBoxShape.cpp)
and native shape enum value 0 matches
[Bullet's box enum](https://github.com/bulletphysics/bullet3/blob/master/src/BulletCollision/BroadphaseCollision/btBroadphaseProxy.h).
No Bullet implementation code is copied here; upstream authors retain credit.
Kind 1 calls `0x1403A9420` with float radius +8; the recovered constructor
explicitly assigns the `btSphereShape` vtable. Kind 2 calls `0x1403A99E0`
with vertex count +8, triangle count +12, triangle-index buffer +40 and
vertex buffer +48. That constructor copies both buffers with 12-byte strides.
The mesh name-index arrays at +56/+64 contain one uint16 per triangle.
Primitive name indices are uint16 at +20/+22 for boxes and +12/+14 for spheres.

The six floats at mesh-header +16..39 are not read by this native loader and
are not source AABBs. For example, `d0101c` stores the same vector twice there,
while its vertices span a substantially different box. `0x1403A99E0` constructs
a fresh mesh interface from the vertex/index buffers. `0x1403D91F0` obtains its
local AABB from that interface or recalculates it through `0x1403D9540`; then
`0x1403DDE00` builds the BVH through the mesh callback. The alternate constructor
path invokes `0x1403C35A0` to update extrema. Consequently the current native
path derives collision bounds from edited vertices; the opaque header floats
remain untouched. This is native-loading evidence, not an in-game edit test.

## Verification and remaining acceptance

Ten synthetic regressions cover typed box/sphere/mesh edits, associations,
exact unrelated-byte preservation, rejected malformed/unsupported sources,
transactional edits, full-width source names, no-clobber/stale guards, and
failed-replace preservation. Run:

```text
python -m unittest discover -s tests -p test_physics.py -v
```

The local corpus audit parsed **1,976** base-game and DLC `.phys` files with
**2,912 boxes** and **3,061 triangle meshes**, with zero failures and exact
unchanged-byte round-trips. No native sphere fixture was present; sphere
support has constructor evidence and a synthetic fixture, not in-game fixture
acceptance. Four actual files were edited into an isolated output directory,
atomically exported, reparsed, and checked for exact scoped differences:
`d0101p`, `d0101c`, `d0101elv00`, and DLC `d50wall02`. Original files retained
their hashes. Local evidence lives under
`Time Stranger/local/phys-native/codec-audit/report.json`, generated by
`Time Stranger/tools/verify_physics_corpus.py`.

These are codec and source-file checks. Blender collision editing, dependency
packaging, and intended in-game collision/trigger behavior require their own
acceptance. No edited collision file from this audit was installed in the game.
