"""Small bmesh helpers shared by the model builders."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector


def link(obj, col_name="Meshes"):
    col = bpy.data.collections.get(col_name)
    if col is None:
        col = bpy.data.collections.new(col_name)
        bpy.context.scene.collection.children.link(col)
    col.objects.link(obj)
    return obj


def obj_from_bm(name, bm, col_name="Meshes", smooth=True, auto_smooth_deg=None):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth()
    obj = bpy.data.objects.new(name, me)
    link(obj, col_name)
    if auto_smooth_deg is not None:
        set_auto_smooth(obj, auto_smooth_deg)
    return obj


def set_auto_smooth(obj, angle_deg=35.0):
    """Blender >= 4.1: 'smooth by angle' = sharp edges above the angle."""
    me = obj.data
    me.shade_smooth()
    import bmesh as _bm
    bm = _bm.new()
    bm.from_mesh(me)
    lim = math.radians(angle_deg)
    for e in bm.edges:
        if len(e.link_faces) == 2:
            if e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) > lim:
                e.smooth = False
        else:
            e.smooth = False
    bm.to_mesh(me)
    bm.free()


def capsule(bm, radius, length, segs=12, rings=4, matrix=Matrix.Identity(4), r_end=None):
    """Capsule along +Y from 0 to `length` (hemisphere centres at 0 / length)."""
    r_end = radius if r_end is None else r_end
    verts_rows = []
    # bottom hemisphere
    for i in range(rings, 0, -1):
        a = (i / rings) * math.pi / 2
        verts_rows.append((-math.sin(a) * radius, math.cos(a) * radius))
    verts_rows.append((0.0, radius))
    verts_rows.append((length, r_end))
    for i in range(1, rings + 1):
        a = (i / rings) * math.pi / 2
        verts_rows.append((length + math.sin(a) * r_end, math.cos(a) * r_end))
    rows = []
    bottom = bm.verts.new(matrix @ Vector((0, -radius, 0)))
    top = bm.verts.new(matrix @ Vector((0, length + r_end, 0)))
    for y, r in verts_rows:
        row = []
        for j in range(segs):
            t = 2 * math.pi * j / segs
            row.append(bm.verts.new(matrix @ Vector((math.cos(t) * r, y, math.sin(t) * r))))
        rows.append(row)
    for j in range(segs):
        j2 = (j + 1) % segs
        bm.faces.new((bottom, rows[0][j2], rows[0][j]))
        bm.faces.new((top, rows[-1][j], rows[-1][j2]))
    for a, b in zip(rows[:-1], rows[1:]):
        for j in range(segs):
            j2 = (j + 1) % segs
            bm.faces.new((a[j], a[j2], b[j2], b[j]))
    return bm


def box(bm, mn, mx, matrix=Matrix.Identity(4)):
    (x0, y0, z0), (x1, y1, z1) = mn, mx
    co = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
          (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    v = [bm.verts.new(matrix @ Vector(c)) for c in co]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([v[i] for i in f])
    return bm


def extrude_profile(bm, pts_yz, x0, x1, matrix=Matrix.Identity(4)):
    """Prism from a closed 2D polygon in the (Y, Z) plane, X from x0 to x1."""
    a = [bm.verts.new(matrix @ Vector((x0, y, z))) for y, z in pts_yz]
    b = [bm.verts.new(matrix @ Vector((x1, y, z))) for y, z in pts_yz]
    n = len(pts_yz)
    fa = bm.faces.new(list(reversed(a)))
    fb = bm.faces.new(b)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.triangulate(bm, faces=[fa, fb])
    return bm


def tube(bm, path, radii, segs=16, matrix=Matrix.Identity(4), cap=True, up=Vector((0, 0, 1))):
    """Swept circle along a polyline `path` (list of Vector)."""
    rows = []
    n = len(path)
    for i, p in enumerate(path):
        p = Vector(p)
        if i == 0:
            d = Vector(path[1]) - p
        elif i == n - 1:
            d = p - Vector(path[i - 1])
        else:
            d = Vector(path[i + 1]) - Vector(path[i - 1])
        d.normalize()
        u = up - d * up.dot(d)
        if u.length < 1e-6:
            u = Vector((1, 0, 0)) - d * d.x
        u.normalize()
        w = d.cross(u)
        r = radii[i] if isinstance(radii, (list, tuple)) else radii
        rows.append([bm.verts.new(matrix @ (p + (u * math.cos(2 * math.pi * j / segs) + w * math.sin(2 * math.pi * j / segs)) * r)) for j in range(segs)])
    for a, b in zip(rows[:-1], rows[1:]):
        for j in range(segs):
            j2 = (j + 1) % segs
            bm.faces.new((a[j], a[j2], b[j2], b[j]))
    if cap:
        bm.faces.new(list(reversed(rows[0])))
        bm.faces.new(rows[-1])
    return bm


def mirror_x_object(src, new_name):
    """Copy of `src` mirrored along local X (normals fixed)."""
    me = src.data.copy()
    me.name = new_name
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.scale(bm, vec=(-1, 1, 1), verts=bm.verts)
    bmesh.ops.reverse_faces(bm, faces=bm.faces, flip_multires=True)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(new_name, me)
    for col in src.users_collection:
        col.objects.link(obj)
    for k in src.keys():
        obj[k] = src[k]
    return obj


def material(name, color, metallic=0.0, roughness=0.5):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*color, 1)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        m.diffuse_color = (*color, 1)
        m.metallic = metallic
        m.roughness = roughness
    return m


def assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
