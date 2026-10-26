"""LAVA limited pack: Lava_AR, Lava_Deagle, Lava_Karambit (skin) and Lava_Stand.

Follows blender/packs/CONTRACT.md.  Run headless:
    python -c "import sys; sys.path.insert(0,'blender'); import bpy; from packs import lava; lava.build()"
Preview videos (EEVEE needs a display -> xvfb-run):
    lava.build(); lava.render_showcase('previews/packs')

Style: obsidian / black-basalt bodies, sculpted molten-gold flame fins with dark
obsidian inlays, glowing Neon lava cracks, veins, runes, gems and a magma core.
"""

import math
import os
import random
import shutil
import subprocess

import bmesh
import bpy
from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree

from vm import mesh_utils as mu

I4 = Matrix.Identity(4)
LAVA = (1.0, 0.35, 0.05)
LAVA_HOT = (1.0, 0.6, 0.1)
LAVA_GEM = (1.0, 0.22, 0.04)
ITEMS = ("Lava_AR", "Lava_Deagle", "Lava_Karambit", "Lava_Stand")


# =============================================================================
# small helpers
# =============================================================================
def _collection(item):
    name = "ITEM_" + item
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    return col


def _rot_about(pivot, axis, ang):
    p = Vector(pivot)
    return Matrix.Translation(p) @ Matrix.Rotation(ang, 4, axis) @ Matrix.Translation(-p)


def _sock(node, ident, out=False):
    for s in (node.outputs if out else node.inputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)


def _apply_mods(obj):
    if not obj.modifiers:
        return
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)
    me.name = obj.name


def _uv(obj):
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    vl.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(55.0), island_margin=0.004, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)
    if obj.data.uv_layers:
        obj.data.uv_layers[0].name = "UVMap"


def make_obj(name, bm, col, mat, rbx="SmoothPlastic", color=(0.05, 0.05, 0.05), bake=None,
             pulse=None, bevel=0.0, bevel_segs=2, smooth_deg=40.0):
    """bmesh -> object at identity in `col` with material + contract custom props."""
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    if bevel > 0:
        md = obj.modifiers.new("Bevel", "BEVEL")
        md.width = bevel
        md.segments = bevel_segs
        md.limit_method = "ANGLE"
        md.angle_limit = math.radians(30)
        md.use_clamp_overlap = True
        _apply_mods(obj)
    mu.set_auto_smooth(obj, smooth_deg)
    obj.data.materials.append(mat)
    if bake is None:
        bake = rbx not in ("Neon", "Glass", "ForceField")
    obj["rbx_material"] = rbx
    obj["rbx_color"] = tuple(color)
    obj["bake"] = bool(bake)
    if pulse:
        obj["pulse"] = float(pulse)
    if bake:
        _uv(obj)
    return obj


def make_empty(name, loc, col, size=0.12, rot=None, **props):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "SPHERE" if name.startswith("VFX_") else "ARROWS"
    e.empty_display_size = size
    e.matrix_world = Matrix.Translation(Vector(loc)) @ (rot if rot is not None else I4)
    col.objects.link(e)
    for k, v in props.items():
        e[k] = v
    return e


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


# =============================================================================
# materials (Principled + OBJECT-coordinate procedurals -> bakeable)
# =============================================================================
class _NT:
    def __init__(self, mat):
        self.nt = mat.node_tree
        self.n = self.nt.nodes
        self.l = self.nt.links

    def new(self, kind, **kw):
        nd = self.n.new(kind)
        for k, v in kw.items():
            setattr(nd, k, v)
        return nd

    def link(self, a, b):
        self.l.new(a, b)

    def mix(self, fac, a, b):
        m = self.new("ShaderNodeMix", data_type="RGBA")
        self._in(_sock(m, "Factor_Float"), fac)
        self._in(_sock(m, "A_Color"), a)
        self._in(_sock(m, "B_Color"), b)
        return _sock(m, "Result_Color", out=True)

    def math(self, op, a, b=None, clamp=False):
        m = self.new("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(m.inputs[0], a)
        if b is not None:
            self._in(m.inputs[1], b)
        return m.outputs[0]

    def maprange(self, v, a0, a1, b0, b1):
        m = self.new("ShaderNodeMapRange", clamp=True)
        self._in(m.inputs["Value"], v)
        m.inputs["From Min"].default_value = a0
        m.inputs["From Max"].default_value = a1
        m.inputs["To Min"].default_value = b0
        m.inputs["To Max"].default_value = b1
        return m.outputs["Result"]

    def _in(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.link(v, sock)
        elif isinstance(v, (tuple, list)) and len(v) == 3 and sock.type == "RGBA":
            sock.default_value = (*v, 1.0)
        else:
            sock.default_value = v


def _coords(t, distort=0.0, dscale=2.0):
    tc = t.new("ShaderNodeTexCoord")
    co = tc.outputs["Object"]
    if distort > 0:
        nz = t.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = dscale
        t.link(co, nz.inputs["Vector"])
        sc = t.new("ShaderNodeVectorMath", operation="SCALE")
        t.link(nz.outputs["Color"], sc.inputs[0])
        sc.inputs["Scale"].default_value = distort
        add = t.new("ShaderNodeVectorMath", operation="ADD")
        t.link(co, add.inputs[0])
        t.link(sc.outputs[0], add.inputs[1])
        co = add.outputs[0]
    return co


def mat_surface(name, dark, light, rough=(0.2, 0.4), metallic=0.0, scale=4.0, bump=0.15,
                facets=0.0, crack=None, crack_scale=3.0, crack_w=0.03, crack_emit=0.0,
                heat_z=None):
    """Stone / glass / metal surface.  crack=(r,g,b) adds a voronoi crack network
    baked into the colour (+ emission for the EEVEE preview)."""
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = _NT(m)
    b = t.n["Principled BSDF"]
    co = _coords(t)
    nz = t.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 6.0
    nz.inputs["Roughness"].default_value = 0.6
    t.link(co, nz.inputs["Vector"])
    f = t.maprange(nz.outputs["Fac"], 0.3, 0.7, 0.0, 1.0)
    col = t.mix(f, dark, light)
    t.link(t.maprange(nz.outputs["Fac"], 0.3, 0.7, rough[0], rough[1]), b.inputs["Roughness"])
    b.inputs["Metallic"].default_value = metallic
    height = nz.outputs["Fac"]
    if facets > 0:
        vo = t.new("ShaderNodeTexVoronoi", feature="F1")
        vo.inputs["Scale"].default_value = scale * 1.6
        t.link(co, vo.inputs["Vector"])
        height = t.math("ADD", t.math("MULTIPLY", vo.outputs["Distance"], facets), nz.outputs["Fac"])
    if heat_z is not None:      # warm glow tint near the lava (low z)
        z = t.new("ShaderNodeSeparateXYZ")
        t.link(co, z.inputs[0])
        hf = t.maprange(z.outputs["Z"], heat_z[0], heat_z[1], 1.0, 0.0)
        col = t.mix(t.math("MULTIPLY", hf, 0.35), col, (0.30, 0.05, 0.01))
    if crack is not None:
        cco = _coords(t, distort=0.35 / crack_scale * 3.0, dscale=crack_scale * 1.3)
        vo = t.new("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
        vo.inputs["Scale"].default_value = crack_scale
        t.link(cco, vo.inputs["Vector"])
        mask = t.maprange(vo.outputs["Distance"], crack_w * 0.35, crack_w, 1.0, 0.0)
        # break the network up so not every cell edge glows
        nz2 = t.new("ShaderNodeTexNoise")
        nz2.inputs["Scale"].default_value = crack_scale * 0.6
        t.link(co, nz2.inputs["Vector"])
        mask = t.math("MULTIPLY", mask, t.maprange(nz2.outputs["Fac"], 0.42, 0.55, 0.0, 1.0))
        col = t.mix(mask, col, crack)
        height = t.math("SUBTRACT", height, t.math("MULTIPLY", mask, 0.6))
        if crack_emit > 0:
            t.link(t.mix(mask, (0, 0, 0), crack), b.inputs["Emission Color"])
            b.inputs["Emission Strength"].default_value = crack_emit
    t.link(col, b.inputs["Base Color"])
    if bump > 0:
        bp = t.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.02
        t.link(height, bp.inputs["Height"])
        t.link(bp.outputs["Normal"], b.inputs["Normal"])
    m.diffuse_color = (*[(a + c) * 0.5 for a, c in zip(dark, light)], 1.0)
    m.metallic = metallic
    m.roughness = sum(rough) / 2
    return m


def mat_neon(name, color, strength=7.0, pulse=None, scale=6.0, flow=False):
    """Emission (Roblox Neon) with molten variation; pulse -> driver on strength."""
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = _NT(m)
    out = t.n["Material Output"]
    t.n.remove(t.n["Principled BSDF"])
    em = t.new("ShaderNodeEmission")
    co = _coords(t)
    nz = t.new("ShaderNodeTexNoise", noise_dimensions="4D" if flow else "3D")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 4.0
    t.link(co, nz.inputs["Vector"])
    if flow:
        d = nz.inputs["W"].driver_add("default_value").driver
        d.type = "SCRIPTED"
        d.expression = "frame*0.012"
    ramp = t.new("ShaderNodeValToRGB")
    t.link(nz.outputs["Fac"], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.3, (color[0] * 0.55, color[1] * 0.25, color[2] * 0.2, 1)
    els[1].position, els[1].color = 0.75, (1.0, 0.62, 0.22, 1)
    e = els.new(0.5)
    e.color = (*color, 1)
    t.link(ramp.outputs["Color"], em.inputs["Color"])
    em.inputs["Strength"].default_value = strength
    if pulse:
        d = em.inputs["Strength"].driver_add("default_value").driver
        d.type = "SCRIPTED"
        d.expression = f"{strength:.2f}*(0.78+0.22*sin(frame*{2 * math.pi * pulse / 30.0:.5f}))"
    t.link(em.outputs[0], out.inputs["Surface"])
    m.diffuse_color = (*color, 1.0)
    return m


def lava_materials():
    return {
        "obsidian": mat_surface("Lava_Obsidian", (0.010, 0.008, 0.010), (0.045, 0.030, 0.034),
                                rough=(0.10, 0.30), scale=3.0, bump=0.12, facets=0.6,
                                crack=(0.20, 0.035, 0.008), crack_scale=2.2, crack_w=0.035),
        "basalt": mat_surface("Lava_Basalt", (0.018, 0.016, 0.016), (0.07, 0.06, 0.058),
                              rough=(0.55, 0.85), scale=9.0, bump=0.35,
                              crack=(0.55, 0.12, 0.02), crack_scale=4.0, crack_w=0.04, crack_emit=0.6),
        "gold": mat_surface("Lava_Gold", (0.62, 0.30, 0.08), (1.0, 0.68, 0.26), rough=(0.18, 0.36),
                            metallic=1.0, scale=7.0, bump=0.05),
        "darkmetal": mat_surface("Lava_DarkMetal", (0.035, 0.03, 0.03), (0.09, 0.07, 0.06),
                                 rough=(0.25, 0.45), metallic=1.0, scale=10.0, bump=0.04),
        "rock": mat_surface("Lava_Rock", (0.016, 0.013, 0.012), (0.055, 0.045, 0.041),
                            rough=(0.6, 0.95), scale=1.2, bump=0.6, facets=1.0,
                            crack=(0.6, 0.13, 0.02), crack_scale=0.9, crack_w=0.035, crack_emit=0.8,
                            heat_z=(0.4, 1.6)),
        "neon": mat_neon("Lava_Neon", LAVA, 3.6, pulse=0.8),
        "neon_hot": mat_neon("Lava_NeonHot", LAVA_HOT, 3.6, pulse=0.6),
        "neon_core": mat_neon("Lava_NeonCore", LAVA_HOT, 4.5, pulse=1.0, flow=True),
        "gem": mat_neon("Lava_Gem", LAVA_GEM, 5.0, pulse=0.7, scale=14.0),
        "pool": mat_neon("Lava_Pool", LAVA, 2.2, pulse=0.6, scale=0.9, flow=True),
        "fall": mat_neon("Lava_Fall", LAVA_HOT, 3.2, pulse=1.0, scale=1.5, flow=True),
    }


# =============================================================================
# geometry builders
# =============================================================================
def prism(bm, pts, x0, x1, matrix=I4):
    mu.extrude_profile(bm, [tuple(p) for p in pts], x0, x1, matrix)


def torus(bm, center, axis, R, r, n=24, m=6, matrix=I4):
    axis = Vector(axis).normalized()
    c = Vector(center)
    u = axis.orthogonal().normalized()
    w = axis.cross(u)
    rings = []
    for i in range(n):
        a = 2 * math.pi * i / n
        d = u * math.cos(a) + w * math.sin(a)
        rings.append([bm.verts.new(matrix @ (c + d * R + (d * math.cos(2 * math.pi * j / m) + axis * math.sin(2 * math.pi * j / m)) * r))
                      for j in range(m)])
    for i in range(n):
        a, b = rings[i], rings[(i + 1) % n]
        for j in range(m):
            j2 = (j + 1) % m
            bm.faces.new((a[j], a[j2], b[j2], b[j]))


def gem(bm, center, normal, r, h, sides=8, matrix=I4):
    """Faceted gem: girdle at center, crown along +normal, pavilion embedded."""
    nrm = Vector(normal).normalized()
    c = Vector(center)
    u = nrm.orthogonal().normalized()
    w = nrm.cross(u)

    def ring(rad, off, rot=0.0):
        return [bm.verts.new(matrix @ (c + nrm * off + (u * math.cos(2 * math.pi * (i + rot) / sides) + w * math.sin(2 * math.pi * (i + rot) / sides)) * rad))
                for i in range(sides)]
    g = ring(r, 0.0)
    tb = ring(r * 0.55, h * 0.45, 0.5)
    top = bm.verts.new(matrix @ (c + nrm * h * 0.5))
    bot = bm.verts.new(matrix @ (c - nrm * h * 0.6))
    for i in range(sides):
        i2 = (i + 1) % sides
        bm.faces.new((g[i], g[i2], tb[i]))
        bm.faces.new((tb[i], g[i2], tb[i2]))
        bm.faces.new((tb[i], tb[i2], top))
        bm.faces.new((g[i2], g[i], bot))


def bezier2(P0, P1, P2, t):
    return P0 * (1 - t) ** 2 + P1 * (2 * t * (1 - t)) + P2 * (t * t)


def flame_outline(p0, p1, p2, w0, t_end=1.0, barbs=0, barb=0.55, n=12, barbs_up=0):
    """Swept flame / wing blade outline in 2D (y, z): curved centre line (quadratic
    bezier), tapering width, saw-tooth barbs pointing towards the tip."""
    P0, P1, P2 = Vector(p0), Vector(p1), Vector(p2)

    def frame(t):
        c = bezier2(P0, P1, P2, t)
        d = ((P1 - P0) * (2 * (1 - t)) + (P2 - P1) * (2 * t)).normalized()
        return c, d, Vector((-d.y, d.x))

    def width(t):
        return w0 * max(0.0, 1 - t) ** 0.85 * (1 + 0.25 * math.sin(t * math.pi))

    def edge(sign, nb):
        pts = []
        btab = {int(n * (k + 0.8) / (nb + 1.2)) for k in range(nb)} if nb else set()
        for i in range(n):
            t = t_end * i / n
            c, d, nn = frame(t)
            w = width(t)
            pts.append(c + nn * (sign * w * 0.5))
            if i in btab and 0 < i < n - 1:
                tb = t_end * (i + 0.6) / n
                c2, d2, n2 = frame(tb)
                w2 = width(tb)
                pts.append(c2 + n2 * (sign * w2 * (0.5 + barb)) + d2 * (w2 * 0.9))
                pts.append(c2 + n2 * (sign * w2 * 0.12))
        return pts
    up = edge(1, barbs_up)
    lo = edge(-1, barbs)
    tip_c, tip_d, _ = frame(t_end)
    tip = tip_c + tip_d * (width(t_end) * 0.8)
    return up + [tip] + list(reversed(lo))


def fin(bms, p0, p1, p2, w0, x_off=0.0, splay=0.0, roll=0.0, roll_axis_pt=None, thick=0.03,
        barbs=2, barbs_up=0, mirror=False, inlay=True):
    """Ornate fin = gold blade + dark obsidian inlay + Neon vein (added to bms dict)."""
    p0v = Vector((0.0, p0[0], p0[1]))
    xs = -1.0 if mirror else 1.0
    M = Matrix.Translation((x_off * xs, 0, 0)) @ _rot_about(p0v, "Z", splay * xs) @ _rot_about(p0v, "Y", roll * xs)
    if roll_axis_pt is not None:   # rotation around the bore axis (muzzle crowns)
        M = _rot_about(Vector(roll_axis_pt), "Y", roll) @ Matrix.Translation((x_off, 0, 0))
    prism(bms["gold"], flame_outline(p0, p1, p2, w0, barbs=barbs, barbs_up=barbs_up), -thick / 2, thick / 2, M)
    if inlay:
        prism(bms["dark"], flame_outline(p0, p1, p2, w0 * 0.58, t_end=0.8), -thick * 0.8, thick * 0.8, M)
        prism(bms["vein"], flame_outline(p0, p1, p2, w0 * 0.13, t_end=0.72), -thick * 0.8 - 0.006, thick * 0.8 + 0.006, M)


def rock_lathe(bm, prof, segs=40, seed=0, amp=0.08, nscale=0.9, center=(0, 0, 0), sx=1.0, sy=1.0,
               rows_per=2, disp=0.0, cap=True):
    """Lathed rock: profile [(r, z)...] bottom -> top, noisy radius; r=0 -> pole."""
    c = Vector(center)
    off = Vector((seed * 7.31, seed * 3.17, seed * 1.73))
    pts = []
    for (r0, z0), (r1, z1) in zip(prof[:-1], prof[1:]):
        for k in range(rows_per):
            f = k / rows_per
            pts.append((r0 + (r1 - r0) * f, z0 + (z1 - z0) * f))
    pts.append(prof[-1])
    rings = []
    for r, z in pts:
        if r < 1e-4:
            rings.append([bm.verts.new(c + Vector((0, 0, z)))])
            continue
        ring = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            q = Vector((math.cos(a), math.sin(a), z / max(r, 0.5)))
            nv = noise.noise(q * nscale * 2.0 + off) * 0.7 + noise.noise(q * nscale * 5.0 + off) * 0.3
            rr = r * (1 + amp * nv)
            p = c + Vector((math.cos(a) * rr * sx, math.sin(a) * rr * sy, z))
            if disp > 0:
                p += noise.noise_vector(p * 1.7 + off) * disp
            ring.append(bm.verts.new(p))
        rings.append(ring)
    for a, b in zip(rings[:-1], rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for j in range(segs):
                bm.faces.new((a[0], b[j], b[(j + 1) % segs]))
        elif len(b) == 1:
            for j in range(segs):
                bm.faces.new((a[j], a[(j + 1) % segs], b[0]))
        else:
            for j in range(segs):
                j2 = (j + 1) % segs
                bm.faces.new((a[j], a[j2], b[j2], b[j]))
    if cap and len(rings[0]) > 1:
        f = bm.faces.new(list(reversed(rings[0])))
        bmesh.ops.triangulate(bm, faces=[f])


def spike(bm, base, direction, length, radius, rng, sides=6):
    """Obsidian crystal / spike: faceted prism tapering to an apex."""
    d = Vector(direction).normalized()
    u = d.orthogonal().normalized()
    w = d.cross(u)
    b = Vector(base)
    tw = rng.uniform(0, math.pi)
    rings = []
    for f, rf in ((-0.25, 1.05), (0.0, 1.0), (0.62, 0.78)):
        rings.append([bm.verts.new(b + d * (length * f) + (u * math.cos(tw + 2 * math.pi * i / sides) + w * math.sin(tw + 2 * math.pi * i / sides))
                                   * radius * rf * rng.uniform(0.85, 1.1)) for i in range(sides)])
    apex = bm.verts.new(b + d * length + u * radius * rng.uniform(-0.2, 0.2))
    for a, c in zip(rings[:-1], rings[1:]):
        for i in range(sides):
            i2 = (i + 1) % sides
            bm.faces.new((a[i], a[i2], c[i2], c[i]))
    for i in range(sides):
        bm.faces.new((rings[-1][i], rings[-1][(i + 1) % sides], apex))
    bm.faces.new(list(reversed(rings[0])))


def displace(bm, amp, scale, seed=0):
    off = Vector((seed * 5.1, seed * 2.3, seed * 9.7))
    for v in bm.verts:
        v.co += noise.noise_vector(v.co * scale + off) * amp


# ---- cracks / runes projected onto surfaces ---------------------------------
def bvh_of(objs, keep_first=None):
    vs, ps = [], []
    for o in objs:
        base = len(vs)
        mw = o.matrix_world
        vs += [mw @ v.co for v in o.data.vertices]
        ps += [[base + i for i in p.vertices] for p in o.data.polygons]
    return BVHTree.FromPolygons(vs, ps)


def crack_paths(rng, start, ang, length, step, jit=0.45, branch=0.22, depth=2, w=0.03):
    """Random branching zig-zag polylines in 2D -> [(pts, w)]."""
    out = []

    def walk(p, a, L, w, d, a0):
        pts = [Vector(p)]
        n = max(2, int(L / step))
        for i in range(n):
            a += rng.uniform(-jit, jit)
            a = a0 + max(-0.9, min(0.9, a - a0))
            p = p + Vector((math.cos(a), math.sin(a))) * step * rng.uniform(0.7, 1.3)
            pts.append(Vector(p))
            if d > 0 and 1 < i < n - 1 and rng.random() < branch:
                ab = a + rng.choice((-1, 1)) * rng.uniform(0.5, 1.1)
                walk(p, ab, L * rng.uniform(0.25, 0.5), w * 0.65, d - 1, ab)
        out.append((pts, w))
    walk(Vector(start), ang, length, w, depth, ang)
    return out


GLYPHS = [
    [[(0, -.5), (0, .5)], [(0, .25), (.32, .5)], [(0, 0), (.32, .25)]],
    [[(-.3, -.5), (0, .5), (.3, -.5)], [(-.16, -.05), (.16, -.05)]],
    [[(0, .5), (0, -.5)], [(0, .35), (.3, .1), (0, -.15)]],
    [[(0, -.5), (0, .5)], [(-.3, .5), (0, .18), (.3, .5)]],
    [[(-.28, -.5), (-.28, .5), (.28, -.5), (.28, .5)]],
    [[(0, .5), (.3, 0), (0, -.5), (-.3, 0), (0, .5)], [(0, .2), (0, -.2)]],
    [[(-.3, .5), (.3, -.5)], [(.3, .5), (-.3, -.5)], [(-.3, 0), (.3, 0)]],
]


def glyph_paths(idx, center, size, w, rot=0.0):
    c = Vector(center)
    R = Matrix.Rotation(rot, 2)
    out = []
    for line in GLYPHS[idx % len(GLYPHS)]:
        pts = []
        for a, b in zip(line[:-1], line[1:]):
            a, b = Vector(a), Vector(b)
            n = max(2, int((b - a).length * size / (w * 1.2)))
            pts += [c + (R @ a.lerp(b, k / n)) * size for k in range(n + 1) if not (pts and k == 0)]
        out.append((pts, w))
    return out


def ribbons(bm, paths, probe, bvh, h=0.006, hd=0.012, max_jump=3.0, accept=None, taper=True):
    """Project 2D polylines onto a surface (bvh) and build raised glowing ribbons.
    probe(p2d) -> (ray origin, ray dir).  accept(face_index) filters hit faces."""
    n_seg = 0
    for pts, w in paths:
        run = []
        step = max((pts[1] - pts[0]).length if len(pts) > 1 else 0.05, 1e-4)
        hits = []
        for q in pts:
            o, d = probe(q)
            loc, nrm, idx, _ = bvh.ray_cast(o, d)
            ok = loc is not None and (accept is None or accept(idx))
            if ok and run and (loc - run[-1][0]).length > step * max_jump:
                ok = False
            if ok:
                if nrm.dot(d) > 0:
                    nrm = -nrm
                run.append((loc, nrm))
            else:
                if len(run) >= 2:
                    hits.append(run)
                run = []
        if len(run) >= 2:
            hits.append(run)
        for run in hits:
            n = len(run)
            rows = []
            for i, (p, nv) in enumerate(run):
                a = run[max(0, i - 1)][0]
                b = run[min(n - 1, i + 1)][0]
                tv = (b - a).normalized()
                s = tv.cross(nv).normalized()
                f = i / (n - 1)
                ww = w * ((1.0 - 0.6 * f) if taper else 1.0) * (0.35 if i in (0, n - 1) else 1.0)
                rows.append([bm.verts.new(p + nv * h + s * ww * 0.5), bm.verts.new(p + nv * h - s * ww * 0.5),
                             bm.verts.new(p - nv * hd - s * ww * 0.5), bm.verts.new(p - nv * hd + s * ww * 0.5)])
            for ra, rb in zip(rows[:-1], rows[1:]):
                for j in range(4):
                    j2 = (j + 1) % 4
                    bm.faces.new((ra[j], ra[j2], rb[j2], rb[j]))
            bm.faces.new(list(reversed(rows[0])))
            bm.faces.new(rows[-1])
            n_seg += n
    return n_seg


def side_probe(sign, far=3.0):
    """Probe for a YZ-plane 2D path projected onto the +X (sign=1) / -X side."""
    return lambda q: (Vector((far * sign, q.x, q.y)), Vector((-sign, 0, 0)))


def _bms(*keys):
    return {k: bmesh.new() for k in keys}


def _fins_to_objs(prefix, bms, col, M, pulse=0.8):
    out = []
    if len(bms["gold"].verts):
        out.append(make_obj(prefix + "FinsGold", bms["gold"], col, M["gold"], "Metal", (1.0, 0.66, 0.25), bevel=0.007, bevel_segs=1))
    if len(bms["dark"].verts):
        out.append(make_obj(prefix + "FinsDark", bms["dark"], col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), bevel=0.01, bevel_segs=1))
    if len(bms["vein"].verts):
        out.append(make_obj(prefix + "FinVeins", bms["vein"], col, M["neon_hot"], "Neon", LAVA_HOT, pulse=pulse))
    return out


# =============================================================================
# Lava_AR
# =============================================================================
ZB = 0.62     # bore height above the grip point


def build_ar():
    M = lava_materials()
    col = _collection("Lava_AR")
    P = "Lava_AR_"
    rng = random.Random(11)

    # --- body: receivers, stock, handguard, buffer tube --------------------------
    bm = bmesh.new()
    prism(bm, [(-0.40, 0.50), (0.80, 0.50), (0.80, 0.36), (0.66, 0.30), (0.66, 0.14), (0.30, 0.14),
               (0.28, 0.30), (-0.30, 0.30), (-0.40, 0.37)], -0.125, 0.125)                   # lower receiver
    prism(bm, [(-0.42, 0.49), (0.88, 0.49), (0.88, 0.75), (0.80, 0.79), (-0.34, 0.79), (-0.42, 0.72)], -0.115, 0.115)
    prism(bm, [(-0.86, 0.70), (-1.50, 0.80), (-1.56, 0.74), (-1.56, 0.18), (-1.48, 0.12), (-1.30, 0.20),
               (-1.00, 0.44), (-0.86, 0.48)], -0.10, 0.10)                                    # stock
    up8 = Vector((math.sin(math.pi / 8), 0, math.cos(math.pi / 8)))
    mu.tube(bm, [Vector((0, 0.86, ZB)), Vector((0, 1.40, ZB)), Vector((0, 1.95, ZB))], [0.165, 0.16, 0.15], segs=8, up=up8)
    mu.tube(bm, [Vector((0, -0.40, ZB)), Vector((0, -0.90, ZB))], 0.075, segs=12)            # buffer tube
    body = make_obj(P + "Body", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), bevel=0.02)

    bm = bmesh.new()   # pistol grip
    prism(bm, [(0.22, 0.32), (0.10, -0.06), (0.07, -0.30), (0.02, -0.36), (-0.16, -0.36), (-0.21, -0.29),
               (-0.06, 0.30)], -0.1, 0.1)
    grip = make_obj(P + "Grip", bm, col, M["basalt"], "SmoothPlastic", (0.05, 0.045, 0.045), bevel=0.03)

    bm = bmesh.new()   # magazine (curved)
    mag_pts = [(0.64, 0.16), (0.67, -0.10), (0.75, -0.36), (0.86, -0.60), (0.60, -0.66), (0.50, -0.40), (0.42, -0.12), (0.34, 0.16)]
    prism(bm, mag_pts, -0.085, 0.085)
    mag = make_obj(P + "Mag", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), bevel=0.018)

    bm = bmesh.new()   # sight: base + hood
    prism(bm, [(0.02, 0.77), (0.52, 0.77), (0.52, 0.86), (0.44, 0.90), (0.10, 0.90), (0.02, 0.85)], -0.065, 0.065)
    mu.tube(bm, [Vector((0, 0.14, 0.99)), Vector((0, 0.44, 0.99))], [0.085, 0.09], segs=16)
    prism(bm, [(0.16, 0.86), (0.40, 0.86), (0.40, 0.95), (0.16, 0.95)], -0.04, 0.04)
    sight = make_obj(P + "Sight", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), bevel=0.012)

    bm = bmesh.new()   # barrel
    mu.tube(bm, [Vector((0, 1.9, ZB)), Vector((0, 2.36, ZB))], 0.045, segs=12)
    make_obj(P + "Barrel", bm, col, M["darkmetal"], "Metal", (0.08, 0.06, 0.05))

    # --- gold trim -----------------------------------------------------------------
    bm = bmesh.new()
    for y in (0.90, 1.40, 1.92):
        torus(bm, (0, y, ZB), (0, 1, 0), 0.168, 0.022, n=8, m=6)
    mu.tube(bm, [Vector((0, 2.34, ZB)), Vector((0, 2.42, ZB)), Vector((0, 2.58, ZB)), Vector((0, 2.62, ZB))],
            [0.07, 0.078, 0.078, 0.065], segs=8, up=up8)                                       # muzzle brake
    mu.box(bm, (-0.06, 2.0, 0.54), (0.06, 2.1, 0.71))                                       # gas block
    torus(bm, (0, 0.445, 0.99), (0, 1, 0), 0.092, 0.016, n=16, m=6)                          # sight rings
    torus(bm, (0, 0.14, 0.99), (0, 1, 0), 0.087, 0.014, n=16, m=6)
    mu.tube(bm, [Vector((0, 0.30, 0.30)), Vector((0, 0.30, 0.18)), Vector((0, 0.22, 0.13)),
                 Vector((0, 0.10, 0.14)), Vector((0, 0.05, 0.22))], 0.022, segs=8)            # trigger guard
    prism(bm, [(0.17, 0.30), (0.19, 0.22), (0.16, 0.17), (0.14, 0.18), (0.15, 0.24), (0.14, 0.30)], -0.018, 0.018)
    prism(bm, [(0.58, -0.64), (0.88, -0.58), (0.90, -0.66), (0.60, -0.73)], -0.095, 0.095)    # mag base plate
    prism(bm, [(-1.56, 0.80), (-1.62, 0.80), (-1.62, 0.16), (-1.56, 0.12)], -0.105, 0.105)    # butt pad
    for s in (1, -1):        # mag core frames + gem bezels
        win = [(0.50, -0.04), (0.585, -0.05), (0.655, -0.30), (0.73, -0.50), (0.64, -0.53), (0.56, -0.33)]
        loop = [Vector((0.09 * s, y, z)) for y, z in win]
        mu.tube(bm, loop + [loop[0]], 0.013, segs=6, cap=False)
        torus(bm, (0.125 * s, 0.12, 0.40), (s, 0, 0), 0.05, 0.012, n=12, m=6)
        torus(bm, (0.10 * s, -1.22, 0.48), (s, 0, 0), 0.06, 0.012, n=12, m=6)
    gold = make_obj(P + "Gold", bm, col, M["gold"], "Metal", (1.0, 0.66, 0.25), bevel=0.006)

    # --- ornate fins ---------------------------------------------------------------
    fb = _bms("gold", "dark", "vein")
    for mir in (False, True):
        fin(fb, (1.86, 0.68), (1.45, 1.00), (0.92, 1.03), 0.22, x_off=0.155, splay=0.14, roll=0.12, barbs=3, mirror=mir)
        fin(fb, (1.72, 0.52), (1.38, 0.28), (0.98, 0.24), 0.15, x_off=0.15, splay=0.12, roll=-0.1, barbs=2, mirror=mir)
        fin(fb, (0.74, 0.66), (0.40, 0.84), (-0.06, 0.86), 0.12, x_off=0.11, splay=0.08, barbs=2, mirror=mir)
        fin(fb, (-0.88, 0.64), (-1.20, 0.98), (-1.74, 1.02), 0.24, x_off=0.095, splay=0.1, roll=0.08, barbs=3, mirror=mir)
        fin(fb, (-1.02, 0.36), (-1.30, 0.12), (-1.70, 0.00), 0.15, x_off=0.095, splay=0.1, barbs=2, mirror=mir)
        fin(fb, (0.70, -0.60), (0.86, -0.74), (1.04, -0.72), 0.08, x_off=0.07, splay=0.15, barbs=1, mirror=mir, inlay=False)
    for k in range(4):        # muzzle crown
        fin(fb, (2.60, ZB + 0.07), (2.48, ZB + 0.20), (2.28, ZB + 0.24), 0.07, roll=math.pi / 4 + k * math.pi / 2,
            roll_axis_pt=(0, 0, ZB), barbs=1, thick=0.022, inlay=False)
    _fins_to_objs(P, fb, col, M)

    # --- glowing parts ---------------------------------------------------------------
    bvh = bvh_of([body])
    bm = bmesh.new()
    for s in (1, -1):
        r2 = random.Random(5 + s)
        paths = []
        for (st, a, L) in (((0.84, 0.64), math.pi + 0.15, 1.1), ((0.78, 0.40), math.pi - 0.1, 0.9),
                           ((1.95, ZB + 0.02), math.pi, 1.0), ((1.6, ZB - 0.08), math.pi + 0.3, 0.5),
                           ((-0.88, 0.58), math.pi - 0.1, 0.65), ((-1.0, 0.32), math.pi + 0.5, 0.55)):
            paths += crack_paths(r2, st, a, L, 0.035, w=0.032)
        ribbons(bm, paths, side_probe(s), bvh)
    cracks = make_obj(P + "Cracks", bm, col, M["neon"], "Neon", LAVA, pulse=0.8)
    bm = bmesh.new()
    gb = bvh_of([grip])
    for s in (1, -1):
        r2 = random.Random(9 + s)
        paths = crack_paths(r2, (0.12, 0.26), -math.pi / 2 - 0.35, 0.55, 0.03, w=0.026)
        ribbons(bm, paths, side_probe(s), gb)
    for s in (1, -1):   # runes on the stock + lower receiver
        paths = []
        for i, (y, z) in enumerate(((-1.0, 0.56), (-1.42, 0.50), (-1.42, 0.30))):
            paths += glyph_paths(i + (0 if s > 0 else 3), (y, z), 0.1, 0.018)
        for i, y in enumerate((-0.25, -0.1)):
            paths += glyph_paths(i + 4, (y, 0.40), 0.08, 0.016)
        ribbons(bm, paths, side_probe(s), bvh, taper=False)
    make_obj(P + "Runes", bm, col, M["neon_hot"], "Neon", LAVA_HOT, pulse=0.6)

    bm = bmesh.new()   # magma core: magazine windows, muzzle ports, sight lens
    for s in (1, -1):
        win = [(0.50, -0.04), (0.585, -0.05), (0.655, -0.30), (0.73, -0.50), (0.64, -0.53), (0.56, -0.33)]
        prism(bm, win, 0.07 * s, 0.093 * s)
        for y in (2.44, 2.52):
            mu.box(bm, (-0.083, y - 0.02, ZB - 0.03), (0.083, y + 0.02, ZB + 0.03))
    mu.tube(bm, [Vector((0, 0.135, 0.99)), Vector((0, 0.15, 0.99))], 0.07, segs=16)
    mu.tube(bm, [Vector((0, 2.6, ZB)), Vector((0, 2.625, ZB))], 0.03, segs=10)
    make_obj(P + "Core", bm, col, M["neon_core"], "Neon", LAVA_HOT, pulse=1.0)

    bm = bmesh.new()
    for s in (1, -1):
        gem(bm, (0.125 * s, 0.12, 0.40), (s, 0, 0), 0.042, 0.05)
        gem(bm, (0.10 * s, -1.22, 0.48), (s, 0, 0), 0.05, 0.06)
    make_obj(P + "Gems", bm, col, M["gem"], "Neon", LAVA_GEM, pulse=0.7)

    # --- VFX ---------------------------------------------------------------------------
    make_empty("VFX_Embers_1", (0, 2.64, ZB), col, rate=1.0, size=1.0)
    make_empty("VFX_Embers_2", (0, 1.4, ZB + 0.25), col, rate=0.8, size=0.9)
    make_empty("VFX_Embers_3", (0, -1.25, 0.85), col, rate=0.6, size=0.8)
    make_empty("VFX_Embers_4", (0, 0.62, -0.4), col, rate=0.5, size=0.7)
    make_empty("VFX_Smoke_1", (0, 2.66, ZB + 0.04), col, rate=1.0, size=0.8)
    make_empty("VFX_Smoke_2", (0, 0.45, 0.82), col, rate=0.5, size=0.6)
    make_empty("VFX_Fire_1", (0, 2.50, ZB + 0.06), col, rate=1.0, size=0.7)
    make_empty("VFX_HeatGlow_1", (0, 0.62, -0.25), col, rate=1.0, size=1.0, color=LAVA)
    make_empty("VFX_HeatGlow_2", (0, 1.6, ZB + 0.2), col, rate=1.0, size=0.8, color=LAVA_HOT)
    return col


# =============================================================================
# Lava_Deagle
# =============================================================================
def build_deagle():
    M = lava_materials()
    col = _collection("Lava_Deagle")
    P = "Lava_Deagle_"
    ZS = 0.475   # bore height

    bm = bmesh.new()   # slide
    prism(bm, [(-0.28, 0.37), (1.22, 0.37), (1.22, 0.52), (1.15, 0.585), (-0.20, 0.585), (-0.28, 0.54)], -0.085, 0.085)
    slide = make_obj(P + "Slide", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), bevel=0.016)
    bm = bmesh.new()   # frame
    prism(bm, [(-0.22, 0.375), (0.98, 0.375), (0.98, 0.27), (0.42, 0.25), (0.14, 0.22), (-0.12, 0.22), (-0.22, 0.29)], -0.07, 0.07)
    frame = make_obj(P + "Frame", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), bevel=0.014)
    bm = bmesh.new()   # grip
    prism(bm, [(0.14, 0.26), (0.03, -0.29), (-0.01, -0.34), (-0.19, -0.34), (-0.235, -0.28), (-0.12, 0.26)], -0.078, 0.078)
    grip = make_obj(P + "Grip", bm, col, M["basalt"], "SmoothPlastic", (0.05, 0.045, 0.045), bevel=0.022)

    bm = bmesh.new()   # gold trim
    mu.tube(bm, [Vector((0, 0.14, 0.24)), Vector((0, 0.15, 0.09)), Vector((0, 0.20, 0.05)), Vector((0, 0.40, 0.05)),
                 Vector((0, 0.45, 0.10)), Vector((0, 0.44, 0.255))], 0.022, segs=8)             # trigger guard
    prism(bm, [(0.23, 0.24), (0.25, 0.16), (0.22, 0.10), (0.20, 0.11), (0.21, 0.17), (0.20, 0.24)], -0.016, 0.016)
    prism(bm, [(-0.27, 0.50), (-0.36, 0.56), (-0.38, 0.62), (-0.33, 0.62), (-0.24, 0.56)], -0.025, 0.025)   # hammer
    prism(bm, [(-0.18, 0.58), (-0.06, 0.58), (-0.07, 0.64), (-0.17, 0.64)], -0.05, 0.05)    # rear sight
    prism(bm, [(1.06, 0.58), (1.14, 0.58), (1.12, 0.65), (1.08, 0.65)], -0.015, 0.015)      # front sight
    mu.box(bm, (-0.03, -0.18, 0.585), (0.03, 1.12, 0.605))                                  # top rib
    torus(bm, (0, 1.222, ZS), (0, 1, 0), 0.05, 0.012, n=16, m=6)                            # muzzle crown ring
    prism(bm, [(0.04, -0.34), (-0.21, -0.34), (-0.20, -0.38), (0.03, -0.38)], -0.085, 0.085)   # grip base
    for s in (1, -1):
        torus(bm, (0.082 * s, -0.07, 0.0), (s, 0, 0), 0.045, 0.011, n=12, m=6)              # gem bezel
        for k in range(5):                                                                  # slide serrations
            y = -0.22 + k * 0.045
            mu.box(bm, (min(0.078 * s, 0.094 * s), y, 0.40), (max(0.078 * s, 0.094 * s), y + 0.018, 0.56))
    make_obj(P + "Gold", bm, col, M["gold"], "Metal", (1.0, 0.66, 0.25), bevel=0.004)

    fb = _bms("gold", "dark", "vein")
    for mir in (False, True):
        fin(fb, (1.06, 0.49), (0.70, 0.74), (0.18, 0.72), 0.14, x_off=0.085, splay=0.12, roll=0.1, barbs=2, mirror=mir, thick=0.024)
        fin(fb, (0.92, 0.31), (0.72, 0.13), (0.50, 0.09), 0.08, x_off=0.068, splay=0.12, barbs=1, mirror=mir, thick=0.02)
        fin(fb, (-0.14, 0.40), (-0.34, 0.47), (-0.52, 0.62), 0.10, x_off=0.05, splay=0.12, barbs=1, mirror=mir, thick=0.022)
        fin(fb, (-0.06, -0.33), (-0.20, -0.46), (-0.36, -0.47), 0.07, x_off=0.05, splay=0.1, barbs=1, mirror=mir, thick=0.02, inlay=False)
    for k in range(4):
        fin(fb, (1.21, ZS + 0.05), (1.13, ZS + 0.13), (1.0, ZS + 0.15), 0.05, roll=math.pi / 4 + k * math.pi / 2,
            roll_axis_pt=(0, 0, ZS), barbs=1, thick=0.016, inlay=False)
    _fins_to_objs(P, fb, col, M)

    bvh = bvh_of([slide, frame])
    bm = bmesh.new()
    for s in (1, -1):
        r2 = random.Random(21 + s)
        paths = []
        for (st, a, L) in (((1.2, 0.48), math.pi + 0.05, 1.3), ((1.0, 0.41), math.pi - 0.1, 0.8),
                           ((0.96, 0.31), math.pi + 0.05, 0.7)):
            paths += crack_paths(r2, st, a, L, 0.028, w=0.024)
        ribbons(bm, paths, side_probe(s), bvh, h=0.005, hd=0.01)
        gb = bvh_of([grip])
        ribbons(bm, crack_paths(r2, (0.08, 0.22), -math.pi / 2 - 0.35, 0.5, 0.025, w=0.02), side_probe(s), gb, h=0.005, hd=0.01)
    make_obj(P + "Cracks", bm, col, M["neon"], "Neon", LAVA, pulse=0.8)

    bm = bmesh.new()
    for s in (1, -1):
        paths = []
        for i, y in enumerate((0.62, 0.74, 0.86)):
            paths += glyph_paths(i + (0 if s > 0 else 2), (y, 0.30), 0.065, 0.013)
        ribbons(bm, paths, side_probe(s), bvh, h=0.005, hd=0.01, taper=False)
    mu.tube(bm, [Vector((0, 1.215, ZS)), Vector((0, 1.228, ZS))], 0.034, segs=12)   # hot bore
    make_obj(P + "Runes", bm, col, M["neon_hot"], "Neon", LAVA_HOT, pulse=0.6)

    bm = bmesh.new()
    for s in (1, -1):
        gem(bm, (0.082 * s, -0.07, 0.0), (s, 0, 0), 0.036, 0.045)
    make_obj(P + "Gems", bm, col, M["gem"], "Neon", LAVA_GEM, pulse=0.7)

    make_empty("VFX_Embers_1", (0, 1.24, ZS), col, rate=1.0, size=0.7)
    make_empty("VFX_Embers_2", (0, 0.3, 0.66), col, rate=0.6, size=0.6)
    make_empty("VFX_Smoke_1", (0, 1.26, ZS + 0.03), col, rate=0.5, size=0.45)
    make_empty("VFX_HeatGlow_1", (0, 0.5, 0.5), col, rate=1.0, size=0.6, color=LAVA)
    return col


# =============================================================================
# Lava_Karambit (skin of vm.models.karambit)
# =============================================================================
def build_karambit():
    from vm import spec
    from vm.models import karambit
    M = lava_materials()
    col = _collection("Lava_Karambit")
    S = spec.KNIFE_SCALE
    objs = karambit.build()
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
        o.data.transform(o.matrix_basis)
        o.matrix_basis = I4
        o.data.transform(Matrix.Scale(S, 4))
    mc = bpy.data.collections.get("Meshes")
    if mc is not None and not mc.objects and not mc.children:
        bpy.data.collections.remove(mc)
    handle, blade, ring = objs

    kb = mat_surface("Lava_KR_Blade", (0.008, 0.007, 0.009), (0.04, 0.026, 0.03), rough=(0.12, 0.3),
                     scale=9.0, bump=0.08, facets=0.5, crack=LAVA, crack_scale=9.0, crack_w=0.03, crack_emit=1.5)
    ke = mat_surface("Lava_KR_Edge", (0.45, 0.10, 0.02), (1.0, 0.45, 0.08), rough=(0.25, 0.4), metallic=0.6,
                     scale=14.0, bump=0.02)
    kh = mat_surface("Lava_KR_Handle", (0.012, 0.011, 0.011), (0.06, 0.05, 0.048), rough=(0.6, 0.85),
                     scale=22.0, bump=0.3, crack=LAVA, crack_scale=11.0, crack_w=0.022, crack_emit=0.8)
    for o, mats in ((handle, [kh, M["gold"]]), (blade, [kb, ke, M["obsidian"]]), (ring, [M["gold"]])):
        for i, mt in enumerate(mats[:len(o.data.materials)]):
            o.data.materials[i] = mt
        o["bake"] = True
    handle["rbx_material"], handle["rbx_color"] = "SmoothPlastic", (0.05, 0.04, 0.04)
    blade["rbx_material"], blade["rbx_color"] = "SmoothPlastic", (0.06, 0.03, 0.02)
    ring["rbx_material"], ring["rbx_color"] = "Metal", (1.0, 0.66, 0.25)

    # bounding info (studs)
    bv = [v.co for v in blade.data.vertices]
    bmin = Vector([min(c[i] for c in bv) for i in range(3)])
    bmax = Vector([max(c[i] for c in bv) for i in range(3)])
    tip = max(bv, key=lambda c: c.length)
    nb = len(blade.data.polygons)
    bvh = bvh_of([blade, handle])

    # crack lines on the blade (only accept hits on blade faces beyond the guard)
    hy = spec.KR_HANDLE_END * S
    bfaces = blade.data.polygons
    hz0 = min(v.co.z for v in handle.data.vertices)

    def on_blade(idx):
        return idx < nb and (bfaces[idx].center.y > hy or bfaces[idx].center.z < hz0)
    bm = bmesh.new()
    rng = random.Random(4)
    for s in (1, -1):
        paths = []
        for k in range(7):
            st = (rng.uniform(bmin.y + 0.1, bmax.y), rng.uniform(bmin.z, bmax.z))
            paths += crack_paths(rng, st, rng.uniform(0, 2 * math.pi), 0.45, 0.022, jit=0.6, w=0.014)
        ribbons(bm, paths, side_probe(s, 1.0), bvh, h=0.0025, hd=0.006, accept=on_blade)
    make_obj("KR_Handle_Skin_Cracks", bm, col, M["neon"], "Neon", LAVA, pulse=0.9)

    # veins on the handle scales
    bm = bmesh.new()
    hv = [v.co for v in handle.data.vertices]
    hmin = Vector([min(c[i] for c in hv) for i in range(3)])
    hmax = Vector([max(c[i] for c in hv) for i in range(3)])
    for s in (1, -1):
        paths = []
        r2 = random.Random(7 + s)
        for k in range(4):
            st = (hmin.y + 0.05 + k * (hmax.y - hmin.y) / 4.5, (hmin.z + hmax.z) / 2 + r2.uniform(-0.05, 0.05))
            paths += crack_paths(r2, st, r2.uniform(0.3, 1.2) * r2.choice((1, -1)), 0.3, 0.02, jit=0.7, w=0.013)
        ribbons(bm, paths, side_probe(s, 1.0), bvh, h=0.0025, hd=0.006, accept=lambda i: i >= nb)
    make_obj("KR_Handle_Skin_Veins", bm, col, M["neon_hot"], "Neon", LAVA_HOT, pulse=0.6)

    # glowing ring inlay (projected circle on both ring faces)
    rb = bvh_of([ring])
    R = 0.5 * (spec.KR_RING_INNER_R / math.cos(math.pi / 8) + spec.KR_RING_OUTER_R * math.cos(math.pi / 8)) * S
    circ = [Vector((math.cos(2 * math.pi * i / 48) * R, math.sin(2 * math.pi * i / 48) * R)) for i in range(49)]
    bm = bmesh.new()
    for s in (1, -1):
        ribbons(bm, [(circ, 0.014)], side_probe(s, 1.0), rb, h=0.002, hd=0.006, taper=False)
    make_obj("KR_Handle_Skin_RingInlay", bm, col, M["neon_core"], "Neon", LAVA_HOT, pulse=1.0)

    mid = (bmin + bmax) / 2
    make_empty("VFX_Embers_1", mid, col, rate=0.8, size=0.6, bone="KR_Handle")
    make_empty("VFX_Drip_1", tip, col, rate=1.0, size=0.6, bone="KR_Handle")
    make_empty("VFX_HeatGlow_1", mid, col, rate=1.0, size=0.6, color=LAVA, bone="KR_Handle")
    make_empty("VFX_Embers_2", (0, 0, 0), col, rate=0.4, size=0.5, bone="KR_Handle")
    print(f"[lava] karambit blade bbox {tuple(round(c, 3) for c in bmin)} .. {tuple(round(c, 3) for c in bmax)} tip {tuple(round(c, 3) for c in tip)}")
    return col


# =============================================================================
# Lava_Stand
# =============================================================================
POOL_Z = 0.46


def build_stand():
    M = lava_materials()
    col = _collection("Lava_Stand")
    P = "Lava_Stand_"
    rng = random.Random(3)

    # basin rim
    bm = bmesh.new()
    rock_lathe(bm, [(4.92, 0.0), (5.0, 0.25), (4.88, 0.55), (4.55, 0.74), (4.2, 0.70), (3.95, 0.56), (3.85, 0.40), (0.0, 0.36)],
               segs=56, seed=1, amp=0.035, nscale=1.6, rows_per=2, disp=0.05)
    base = make_obj(P + "Base", bm, col, M["rock"], "SmoothPlastic", (0.06, 0.05, 0.05), smooth_deg=50)
    # central altar
    bm = bmesh.new()
    rock_lathe(bm, [(2.1, 0.3), (1.95, 0.8), (1.62, 1.4), (1.35, 2.0), (1.45, 2.35), (1.78, 2.58), (1.82, 2.72), (1.6, 2.82), (0.0, 2.84)],
               segs=40, seed=2, amp=0.07, nscale=1.3, rows_per=2, disp=0.05)
    altar = make_obj(P + "Altar", bm, col, M["rock"], "SmoothPlastic", (0.06, 0.05, 0.05), smooth_deg=50)
    # side pillars
    bm = bmesh.new()
    pillar_xy = [(-3.0, -0.9), (3.0, -0.9)]
    for k, (x, y) in enumerate(pillar_xy):
        rock_lathe(bm, [(0.85, 0.3), (0.7, 0.9), (0.5, 1.6), (0.48, 2.0), (0.62, 2.22), (0.5, 2.3), (0.0, 2.31)],
                   segs=24, seed=5 + k, amp=0.09, nscale=1.4, center=(x, y, 0), rows_per=2, disp=0.03)
    pillars = make_obj(P + "Pillars", bm, col, M["rock"], "SmoothPlastic", (0.06, 0.05, 0.05), smooth_deg=50)
    # back spires + arch
    bm = bmesh.new()
    for s in (-1, 1):
        rock_lathe(bm, [(1.2, 0.3), (1.0, 1.2), (0.75, 2.6), (0.62, 3.8), (0.4, 4.9), (0.08, 5.9), (0.0, 6.0)],
                   segs=20, seed=8 + s, amp=0.12, nscale=1.2, center=(3.0 * s, 2.7, 0), rows_per=2, disp=0.06)
    path = [Vector((3.0 * math.sin(a), 2.85, 4.0 + 0.5 * math.cos(a))) for a in [(-1 + 2 * k / 14) * math.pi / 2 for k in range(15)]]
    mu.tube(bm, path, [0.52 - 0.12 * math.sin(k / 14 * math.pi) for k in range(15)], segs=10)
    spires = make_obj(P + "Spires", bm, col, M["rock"], "SmoothPlastic", (0.06, 0.05, 0.05), smooth_deg=50)
    # obsidian crystal spikes around the rim
    bm = bmesh.new()
    for a in [math.radians(d) for d in (-60, -35, 20, 45, 70, 110, 135, 160, 215, 240)]:
        r = 4.55
        b = Vector((math.cos(a) * r, math.sin(a) * r, 0.5))
        out = Vector((math.cos(a), math.sin(a), 0))
        for k in range(rng.randint(2, 3)):
            d = (Vector((0, 0, 1)) + out * rng.uniform(0.25, 0.7) + Vector((rng.uniform(-.3, .3), rng.uniform(-.3, .3), 0))).normalized()
            spike(bm, b + Vector((rng.uniform(-.25, .25), rng.uniform(-.25, .25), 0)), d, rng.uniform(0.8, 1.9), rng.uniform(0.12, 0.22), rng)
    for s in (-1, 1):   # big crystals hugging the spires
        for k in range(3):
            d = Vector((0.45 * s + rng.uniform(-.2, .2), rng.uniform(-0.4, 0.1), 1)).normalized()
            spike(bm, Vector((3.0 * s + rng.uniform(-.6, .6), 2.4 + rng.uniform(-.4, .3), 0.4)), d, rng.uniform(1.6, 2.8), rng.uniform(0.2, 0.32), rng)
    make_obj(P + "Crystals", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), smooth_deg=20)

    # altar top slab + gold trim + side cups
    bm = bmesh.new()
    mu.tube(bm, [Vector((0, 0, 2.78)), Vector((0, 0, 2.96))], [1.72, 1.66], segs=8, up=Vector((1, 0, 0)))
    for x, y in pillar_xy:
        mu.tube(bm, [Vector((x, y, 2.25)), Vector((x, y, 2.42))], [0.42, 0.5], segs=8, up=Vector((1, 0, 0)))
    make_obj(P + "AltarTop", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), bevel=0.03)
    bm = bmesh.new()
    torus(bm, (0, 0, 2.96), (0, 0, 1), 1.66, 0.045, n=8, m=6)
    torus(bm, (0, 0, 2.8), (0, 0, 1), 1.74, 0.05, n=8, m=6)
    for x, y in pillar_xy:
        torus(bm, (x, y, 2.42), (0, 0, 1), 0.5, 0.035, n=8, m=6)
    # fire bowls at the front corners
    bowls = [(-3.3, -3.3), (3.3, -3.3)]
    for x, y in bowls:
        rock_lathe(bm, [(0.12, 1.0), (0.2, 1.06), (0.38, 1.25), (0.46, 1.42), (0.40, 1.45), (0.30, 1.30), (0.0, 1.28)],
                   segs=16, seed=0, amp=0.0, center=(x, y, 0), rows_per=1)
    gold = make_obj(P + "Gold", bm, col, M["gold"], "Metal", (1.0, 0.66, 0.25), bevel=0.01)
    bm = bmesh.new()
    for k, (x, y) in enumerate(bowls):
        rock_lathe(bm, [(0.32, 0.5), (0.22, 0.75), (0.14, 1.02), (0.0, 1.03)], segs=12, seed=20 + k, amp=0.1,
                   center=(x, y, 0), rows_per=1, disp=0.02)
    make_obj(P + "BowlPosts", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03))

    # sign plate (+ gold frame + gem), front face looks to -Y (viewer)
    bm = bmesh.new()
    mu.box(bm, (-1.9, -4.86, 0.62), (1.9, -4.66, 1.48))
    sign = make_obj(P + "SignPlate", bm, col, M["obsidian"], "SmoothPlastic", (0.03, 0.025, 0.03), smooth_deg=10)
    bm = bmesh.new()
    rect = [Vector((x, -4.87, z)) for x, z in ((-1.93, 0.59), (1.93, 0.59), (1.93, 1.51), (-1.93, 1.51), (-1.93, 0.59))]
    mu.tube(bm, rect, 0.045, segs=6, cap=False)
    for s in (-1, 1):   # flame finials on the upper corners (fins rotated into the XZ plane)
        M_xz = Matrix.Translation((0, -4.79, 0)) @ Matrix.Rotation(-math.pi / 2, 4, "Z")
        prism(bm, flame_outline((1.75 * s, 1.40), (2.25 * s, 1.85), (2.0 * s, 2.35), 0.32, barbs=2),
              -0.04, 0.04, M_xz)
        prism(bm, flame_outline((1.8 * s, 0.7), (2.25 * s, 0.6), (2.45 * s, 0.25), 0.2, barbs=1),
              -0.04, 0.04, M_xz)
    prism(bm, flame_outline((0.0, 1.42), (0.05, 1.75), (0.0, 2.05), 0.34, barbs=0), -0.04, 0.04,
          Matrix.Translation((0, -4.79, 0)) @ Matrix.Rotation(-math.pi / 2, 4, "Z"))
    torus(bm, (0, -4.86, 1.63), (0, -1, 0), 0.13, 0.03, n=12, m=6)
    make_obj(P + "SignFrame", bm, col, M["gold"], "Metal", (1.0, 0.66, 0.25), bevel=0.008)
    bm = bmesh.new()
    gem(bm, (0, -4.86, 1.63), (0, -1, 0), 0.11, 0.12)
    make_obj(P + "Gem", bm, col, M["gem"], "Neon", LAVA_GEM, pulse=0.7)
    bm = bmesh.new()   # rock plinth the sign sits on
    rock_lathe(bm, [(1.0, 0.0), (1.0, 0.45), (0.85, 0.66), (0.0, 0.68)], segs=20, seed=31, amp=0.06,
               center=(0, -4.6, 0), sx=2.3, sy=0.45, rows_per=1, disp=0.03)
    make_obj(P + "SignRock", bm, col, M["rock"], "SmoothPlastic", (0.06, 0.05, 0.05), smooth_deg=50)

    # lava: pool, fall, splash, coals, crust, streams, runes ---------------------------
    bm = bmesh.new()
    rock_lathe(bm, [(4.05, POOL_Z), (3.0, POOL_Z + 0.01), (2.0, POOL_Z), (0.0, POOL_Z)], segs=48, seed=0, amp=0.0, rows_per=1, cap=False)
    make_obj(P + "LavaPool", bm, col, M["pool"], "Neon", LAVA, pulse=0.6, smooth_deg=80)

    bm = bmesh.new()
    P0, P1, P2 = Vector((0, 2.9, 4.2)), Vector((0, 2.25, 2.9)), Vector((0, 2.35, POOL_Z - 0.05))
    rows = []
    for i in range(17):
        t = i / 16
        c = bezier2(P0, P1, P2, t)
        d = ((P1 - P0) * (2 * (1 - t)) + (P2 - P1) * (2 * t)).normalized()
        nrm = d.cross(Vector((1, 0, 0))).normalized()
        w = 0.75 - 0.2 * t + 0.25 * t * t
        row = []
        for j in range(7):
            u = -1 + 2 * j / 6
            x = u * w + 0.06 * math.sin(t * 9 + u * 2)
            ripple = 0.04 * math.sin(t * 23 + u * 5)
            row.append(c + Vector((x, 0, 0)) + nrm * ripple)
        rows.append(row)
    fr = []
    for row in rows:
        c0 = sum(row, Vector()) / len(row)
        nrm = Vector((0, -1, 0.2)).normalized()
        fr.append(([bm.verts.new(p + nrm * 0.05) for p in row], [bm.verts.new(p - nrm * 0.05) for p in row]))
    for (fa, ba), (fb_, bb) in zip(fr[:-1], fr[1:]):
        for j in range(6):
            bm.faces.new((fa[j], fa[j + 1], fb_[j + 1], fb_[j]))
            bm.faces.new((ba[j + 1], ba[j], bb[j], bb[j + 1]))
        bm.faces.new((fa[0], fb_[0], bb[0], ba[0]))
        bm.faces.new((ba[6], bb[6], fb_[6], fa[6]))
    bm.faces.new(fr[0][0] + list(reversed(fr[0][1])))
    bm.faces.new(list(reversed(fr[-1][0])) + fr[-1][1])
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    rock_lathe(bm, [(0.0, POOL_Z - 0.05), (0.9, POOL_Z), (0.6, POOL_Z + 0.18), (0.0, POOL_Z + 0.22)], segs=16,
               seed=40, amp=0.25, center=(0, 2.3, 0), sx=1.1, sy=0.8, rows_per=1)
    make_obj(P + "LavaFall", bm, col, M["fall"], "Neon", LAVA_HOT, pulse=1.0, smooth_deg=70)

    bm = bmesh.new()   # coals in the fire bowls
    for x, y in bowls:
        rock_lathe(bm, [(0.0, 1.3), (0.36, 1.36), (0.2, 1.47), (0.0, 1.5)], segs=12, seed=50, amp=0.2,
                   center=(x, y, 0), rows_per=1)
    make_obj(P + "Coals", bm, col, M["neon_core"], "Neon", LAVA_HOT, pulse=1.0)

    bm = bmesh.new()   # floating basalt crust plates
    plates = 0
    while plates < 11:
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(2.5, 3.7)
        c = Vector((math.cos(a) * r, math.sin(a) * r))
        if any((c - Vector(p)).length < 1.05 for p in pillar_xy) or (c - Vector((0, 2.4))).length < 1.3 or \
           (c - Vector((0, -4.0))).length < 0.9:
            continue
        rad = rng.uniform(0.22, 0.45)
        pts = [c + Vector((math.cos(2 * math.pi * k / 7), math.sin(2 * math.pi * k / 7))) * rad * rng.uniform(0.6, 1.1) for k in range(7)]
        verts_a = [bm.verts.new((p.x, p.y, POOL_Z - 0.03)) for p in pts]
        verts_b = [bm.verts.new((p.x * 0.95 + c.x * 0.05, p.y * 0.95 + c.y * 0.05, POOL_Z + rng.uniform(0.04, 0.08))) for p in pts]
        bm.faces.new(list(reversed(verts_a)))
        bm.faces.new(verts_b)
        for k in range(7):
            k2 = (k + 1) % 7
            bm.faces.new((verts_a[k], verts_a[k2], verts_b[k2], verts_b[k]))
        plates += 1
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    make_obj(P + "Crust", bm, col, M["basalt"], "SmoothPlastic", (0.05, 0.045, 0.045), smooth_deg=30)

    # lava streams down the altar, pillars and spires (radial projection)
    bm = bmesh.new()
    abvh = bvh_of([altar])

    def radial(cx, cy, R=4.0, r_ref=1.6):
        return lambda q: (Vector((cx + math.cos(q.x / r_ref) * R, cy + math.sin(q.x / r_ref) * R, q.y)),
                          Vector((-math.cos(q.x / r_ref), -math.sin(q.x / r_ref), 0)))
    for k in range(9):
        a = (k / 9) * 2 * math.pi + rng.uniform(-0.2, 0.2)
        ribbons(bm, crack_paths(rng, (a * 1.6, 2.7), -math.pi / 2 + rng.uniform(-0.2, 0.2), 2.3, 0.15, jit=0.35,
                                branch=0.25, depth=1, w=0.11), radial(0, 0), abvh, h=0.02, hd=0.05)
    pb = bvh_of([pillars])
    for x, y in pillar_xy:
        for k in range(4):
            a = (k / 4) * 2 * math.pi + rng.uniform(-0.3, 0.3)
            ribbons(bm, crack_paths(rng, (a * 0.6, 2.15), -math.pi / 2, 1.8, 0.12, jit=0.35, depth=1, w=0.07),
                    radial(x, y, 2.0, 0.6), pb, h=0.015, hd=0.04)
    make_obj(P + "LavaStreams", bm, col, M["neon"], "Neon", LAVA, pulse=0.8)
    bm = bmesh.new()
    sb = bvh_of([spires])
    for s in (-1, 1):
        for k in range(4):
            a = (k / 4) * 2 * math.pi + rng.uniform(-0.3, 0.3) + 0.4
            ribbons(bm, crack_paths(rng, (a * 0.8, 4.6), -math.pi / 2, 4.0, 0.2, jit=0.3, depth=1, w=0.08),
                    radial(3.0 * s, 2.7, 3.0, 0.8), sb, h=0.02, hd=0.05)
    bb = bvh_of([base])
    for k in range(14):
        a = rng.uniform(0, 2 * math.pi)
        ribbons(bm, crack_paths(rng, (a * 4.6, 0.72), -math.pi / 2 + rng.uniform(-0.4, 0.4), 0.8, 0.12, depth=1, w=0.07),
                radial(0, 0, 7.0, 4.6), bb, h=0.015, hd=0.04)
    make_obj(P + "LavaStreams2", bm, col, M["neon"], "Neon", LAVA, pulse=0.8)

    bm = bmesh.new()   # rune circle on the altar top
    tb = bvh_of([o for o in col.objects if o.name.startswith(P + "AltarTop")])
    down = lambda q: (Vector((q.x, q.y, 5.0)), Vector((0, 0, -1)))
    circ = [Vector((math.cos(2 * math.pi * i / 64) * 1.38, math.sin(2 * math.pi * i / 64) * 1.38)) for i in range(65)]
    circ2 = [p * 0.82 for p in circ]
    paths = [(circ, 0.04), (circ2, 0.03)]
    for i in range(10):
        a = 2 * math.pi * i / 10
        paths += glyph_paths(i, (math.cos(a) * 1.13, math.sin(a) * 1.13), 0.2, 0.028, rot=a - math.pi / 2)
    ribbons(bm, paths, down, tb, h=0.008, hd=0.02, taper=False)
    make_obj(P + "Runes", bm, col, M["neon_hot"], "Neon", LAVA_HOT, pulse=0.6)

    # mounts (weapon local +Y -> world +X, right side faces the viewer at -Y)
    rz = Matrix.Rotation(-math.pi / 2, 4, "Z")
    make_empty("MOUNT_Lava_AR", (-0.5, 0.0, 3.78), col, size=0.5, rot=rz)
    make_empty("MOUNT_Lava_Deagle", (-3.45, -0.9, 3.0), col, size=0.4, rot=rz @ Matrix.Rotation(math.radians(8), 4, "X"))
    make_empty("MOUNT_Lava_Karambit", (2.28, -0.9, 3.15), col, size=0.4, rot=rz)

    # VFX
    for i, (x, y) in enumerate(((-2.2, -2.2), (2.3, -2.0), (-1.6, 2.6), (1.8, 2.4), (0, -3.2))):
        make_empty(f"VFX_Embers_{i + 1}", (x, y, POOL_Z + 0.1), col, rate=1.0, size=1.5)
    make_empty("VFX_Embers_6", (0, 2.5, 3.9), col, rate=0.8, size=1.2)
    make_empty("VFX_Smoke_1", (-1.8, 2.0, POOL_Z + 0.2), col, rate=0.7, size=1.6)
    make_empty("VFX_Smoke_2", (1.9, 1.8, POOL_Z + 0.2), col, rate=0.7, size=1.6)
    make_empty("VFX_Smoke_3", (0, 2.4, 0.8), col, rate=0.7, size=1.4)
    for i, (x, y) in enumerate(bowls):
        make_empty(f"VFX_Fire_{i + 1}", (x, y, 1.48), col, rate=1.0, size=2.2)
        make_empty(f"VFX_HeatGlow_{i + 1}", (x, y, 1.9), col, size=1.0, color=LAVA_HOT)
    make_empty("VFX_Fire_3", (0, 2.92, 4.05), col, rate=1.0, size=2.5)
    make_empty("VFX_HeatGlow_3", (0, 0, 1.4), col, size=2.0, color=LAVA)
    make_empty("VFX_HeatGlow_4", (0, 2.2, 2.2), col, size=2.0, color=LAVA_HOT)
    return col


def _tmp_mesh(bm):
    me = bpy.data.meshes.new("_tmp")
    bm.to_mesh(me)
    bm.free()
    return me


# =============================================================================
# build
# =============================================================================
def build():
    build_ar()
    build_deagle()
    build_karambit()
    build_stand()
    for m in [m for m in bpy.data.meshes if m.name.startswith("_tmp") and m.users == 0]:
        bpy.data.meshes.remove(m)
    for item in ITEMS:
        col = bpy.data.collections["ITEM_" + item]
        ms = [o for o in col.objects if o.type == "MESH"]
        tt = sum(tris(o) for o in ms)
        big = max(ms, key=tris)
        print(f"[lava] {item}: {len(ms)} meshes, {tt} tris (max {big.name} {tris(big)}), "
              f"{len([o for o in col.objects if o.type == 'EMPTY'])} empties")
        print("   ", ", ".join(f"{o.name[len(item) + 1:] if o.name.startswith(item) else o.name}={tris(o)}" for o in ms))
        if tt > 40000 or tris(big) > 8000:
            print(f"[lava] WARNING {item} exceeds triangle budget")


# =============================================================================
# showcase (EEVEE)
# =============================================================================
PRE = 30          # particle pre-roll frames
NF = 150          # turntable frames


def _show_col(name, exclude=False):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    bpy.context.view_layer.layer_collection.children[col.name].exclude = exclude
    return col


def _proto(name, kind, col):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2 if kind == "smoke" else 1, radius=1.0)
    if kind in ("fire", "drip"):
        for v in bm.verts:
            z = v.co.z
            f = 0.55 + 0.45 * (1 - z) / 2 if kind == "fire" else 1.0
            v.co.x *= f * (0.6 if z > 0 else 1.0)
            v.co.y *= f * (0.6 if z > 0 else 1.0)
            v.co.z *= 2.2 if kind == "fire" else (1.6 if z > 0 else 1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    o = bpy.data.objects.new(name, me)
    col.objects.link(o)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    if kind == "smoke":
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.012, 0.011, 0.011, 1)
        b.inputs["Roughness"].default_value = 1.0
        b.inputs["Alpha"].default_value = 0.3
        b.inputs["Emission Color"].default_value = (1.0, 0.3, 0.05, 1)
        b.inputs["Emission Strength"].default_value = 0.04
    else:
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = {"ember": (1.0, 0.45, 0.1, 1), "fire": (1.0, 0.42, 0.07, 1),
                                            "fire2": (1.0, 0.75, 0.3, 1), "drip": (1.0, 0.5, 0.08, 1)}[kind]
        em.inputs["Strength"].default_value = {"ember": 14.0, "fire": 7.0, "fire2": 9.0, "drip": 8.0}[kind]
        nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    me.materials.append(m)
    return o


def _emitter(name, preset, loc, col, protos, scale=1.0, rate=1.0, size=1.0, seed=0, light_col=None):
    loc = Vector(loc)
    if preset == "HeatGlow":
        ld = bpy.data.lights.new(name, "POINT")
        ld.energy = (14.0 if scale <= 1 else 7.0) * (scale ** 2) * size
        ld.color = light_col or LAVA
        ld.shadow_soft_size = 0.15 * scale
        ld.use_shadow = False
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        col.objects.link(lo)
        return lo
    cfg = {  # rate/s, life frames, life rand, vz, rand vel, brownian, gravity, size, size rand, radius
        "Embers": (22, 55, 0.5, 0.55, 0.25, 0.35, 0.0, 0.012, 0.6, 0.06, "ember"),
        "Smoke": (7, 75, 0.4, 0.32, 0.08, 0.15, 0.0, 0.07, 0.6, 0.04, "smoke"),
        "Fire": (70, 11, 0.5, 0.75, 0.12, 0.6, 0.0, 0.035, 0.55, 0.035, "fire"),
        "Drip": (5, 30, 0.2, 0.0, 0.02, 0.0, 0.15, 0.012, 0.3, 0.01, "drip"),
    }.get(preset)
    if cfg is None:
        return None
    r_s, life, life_r, vz, rv, brown, grav, psize, srand, rad, pk = cfg
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=rad * scale * max(size, 0.5))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    col.objects.link(ob)
    ob.show_instancer_for_render = False
    ob.show_instancer_for_viewport = False
    ob.modifiers.new("ps", "PARTICLE_SYSTEM")
    psys = ob.particle_systems[0]
    psys.seed = seed
    s = psys.settings
    fend = PRE + NF + 2
    s.count = max(4, int(r_s * rate * (fend / 30.0)))
    s.frame_start, s.frame_end = 1, fend
    s.lifetime, s.lifetime_random = life, life_r
    s.emit_from = "VOLUME"
    s.normal_factor = 0.0
    s.object_align_factor = (0, 0, vz * scale)
    s.factor_random = rv * scale
    s.brownian_factor = brown * scale
    s.effector_weights.gravity = grav * scale
    s.drag_factor = 0.0
    s.render_type = "OBJECT"
    s.instance_object = protos[pk]
    s.particle_size = psize * scale * size
    s.size_random = srand
    psys.point_cache.frame_start = 1
    psys.point_cache.frame_end = fend
    if preset == "Fire":     # second, hotter core layer
        ob.modifiers.new("ps2", "PARTICLE_SYSTEM")
        p2 = ob.particle_systems[1]
        p2.settings = s.copy()
        p2.settings.instance_object = protos["fire2"]
        p2.settings.particle_size = psize * scale * size * 0.55
        p2.settings.lifetime = int(life * 0.7)
        p2.seed = seed + 7
        p2.point_cache.frame_start = 1
        p2.point_cache.frame_end = fend
    return ob


def _vfx_for(col_src, dst, protos, M=I4, scale=1.0, only=None, rate_mul=1.0, seed=0):
    for i, e in enumerate(o for o in col_src.objects if o.type == "EMPTY" and o.name.startswith("VFX_")):
        preset = e.name.split("_")[1]
        if only and preset not in only:
            continue
        c = tuple(e["color"]) if "color" in e else None
        _emitter(f"SH_{col_src.name}_{e.name}_{seed}", preset, M @ e.matrix_world.translation, dst, protos, scale,
                 float(e.get("rate", 1.0)) * rate_mul, float(e.get("size", 1.0)), seed=seed + i * 13, light_col=c)


def _bbox(col):
    pts = [o.matrix_world @ Vector(c) for o in col.all_objects if o.type == "MESH" for c in o.bound_box]
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    return mn, mx


def _track(obj, target_local):
    d = Vector(target_local) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def _setup_studio(res=(960, 540), samples=16):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = 30
    sc.eevee.taa_render_samples = samples
    sc.eevee.use_shadows = False      # virtual shadow maps are far too slow on software GL
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    w = bpy.data.worlds.get("LavaStudio") or bpy.data.worlds.new("LavaStudio")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.004, 0.0035, 0.004, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sc.world = w
    # bloom for the neon
    ng = bpy.data.node_groups.get("LavaComp")
    if ng is None:
        ng = bpy.data.node_groups.new("LavaComp", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        out = ng.nodes.new("NodeGroupOutput")
        for v in ("Bloom", "BLOOM", "Fog Glow", "FOG_GLOW"):
            try:
                gl.inputs["Type"].default_value = v
                break
            except Exception:
                continue
        gl.inputs["Threshold"].default_value = 1.0
        gl.inputs["Strength"].default_value = 0.4
        gl.inputs["Size"].default_value = 0.55
        ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
        ng.links.new(gl.outputs[0], out.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True

    col = _show_col("SHOW_Studio")
    rig = bpy.data.objects.get("SH_Rig")
    if rig is None:
        rig = bpy.data.objects.new("SH_Rig", None)
        col.objects.link(rig)
        cam = bpy.data.objects.new("SH_Cam", bpy.data.cameras.new("SH_Cam"))
        cam.parent = rig
        col.objects.link(cam)
        sc.camera = cam
        for nm, colr, size in (("Key", (1.0, 0.9, 0.82), 3.0), ("RimL", (1.0, 0.42, 0.12), 2.0),
                               ("RimR", (0.62, 0.72, 1.0), 2.0), ("Back", (1.0, 0.35, 0.08), 6.0)):
            ld = bpy.data.lights.new("SH_" + nm, "AREA" if nm != "Back" else "SPOT")
            ld.color = colr
            if nm == "Back":
                ld.spot_size = math.radians(70)
                ld.spot_blend = 1.0
                ld.shadow_soft_size = 1.0
            else:
                ld.size = size
            lo = bpy.data.objects.new("SH_" + nm, ld)
            lo.parent = rig
            col.objects.link(lo)
        bm = bmesh.new()   # backdrop (rides with the rig, behind the subject)
        mu.box(bm, (-30, 0, -10), (30, 0.1, 30))
        bd = bpy.data.objects.new("SH_Backdrop", bpy.data.meshes.new("SH_Backdrop"))
        bm.to_mesh(bd.data)
        bm.free()
        bd.parent = rig
        col.objects.link(bd)
        bd.data.materials.append(mat_surface("SH_BackdropMat", (0.012, 0.011, 0.012), (0.02, 0.018, 0.02), rough=(0.7, 0.8), bump=0.0))
        bm = bmesh.new()
        mu.box(bm, (-40, -40, -0.2), (40, 40, 0.0))
        fl = bpy.data.objects.new("SH_Floor", bpy.data.meshes.new("SH_Floor"))
        bm.to_mesh(fl.data)
        bm.free()
        col.objects.link(fl)
        fl.data.materials.append(mat_surface("SH_FloorMat", (0.004, 0.0035, 0.0035), (0.012, 0.01, 0.01), rough=(0.45, 0.7), scale=0.6, bump=0.0))
    return rig


def _set_pass(rig, center, dist, elev=0.28, lens=50, floor_z=0.0, orbit=None, frame0=PRE + 1, nf=NF):
    """Place rig + camera + lights for a pass; orbit=(a0, a1) radians or full turn."""
    sc = bpy.context.scene
    rig.location = center
    cam = bpy.data.objects["SH_Cam"]
    cam.data.lens = lens
    cam.data.clip_end = 500
    cam.location = (0, -dist * math.cos(elev), dist * math.sin(elev))
    _track(cam, (0, 0, 0))
    d = dist
    for nm, pos, en in (("Key", (-0.55 * d, -0.75 * d, 0.65 * d), 420), ("RimL", (-0.85 * d, 0.55 * d, 0.35 * d), 700),
                        ("RimR", (0.85 * d, 0.5 * d, 0.55 * d), 520), ("Back", (0, 0.2 * d, 0.5 * d), 1500)):
        lo = bpy.data.objects["SH_" + nm]
        lo.location = pos
        if nm == "Back":
            _track(lo, (0, 1.1 * d, 0.0))
        else:
            _track(lo, (0, 0, 0))
        lo.data.energy = en * (d / 6.0) ** 2
    bd = bpy.data.objects["SH_Backdrop"]
    bd.location = (0, 1.1 * d, 0)
    bpy.data.objects["SH_Floor"].location.z = floor_z
    if rig.animation_data:
        rig.driver_remove("rotation_euler", 2)
    drv = rig.driver_add("rotation_euler", 2).driver
    drv.type = "SCRIPTED"
    if orbit is None:
        drv.expression = f"(frame-{frame0})*{2 * math.pi / nf:.6f}+1.97"
    else:
        a0, a1 = orbit
        drv.expression = f"{a0:.4f}+({a1 - a0:.4f})*(0.5-0.5*cos(pi*(frame-{frame0})/{nf}))"


def _render_frames(out_dir, tag, f0, f1):
    """Render frames f0..f1 (animation render keeps EEVEE alive between frames)."""
    sc = bpy.context.scene
    tmp = os.path.join(out_dir, "_frames_" + tag)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    sc.frame_start, sc.frame_end = f0, f1
    sc.render.filepath = os.path.join(tmp, "f_")
    bpy.ops.render.render(animation=True)
    return tmp


def _encode(dirs, start, out_path):
    args = []
    for d in dirs:
        args += ["-framerate", "30", "-start_number", str(start), "-i", os.path.join(d, "f_%04d.png")]
    flt = "".join(f"[{i}:v]" for i in range(len(dirs))) + f"concat=n={len(dirs)}:v=1:a=0[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", flt, "-map", "[v]",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out_path], check=True)
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)


def prepare_showcase(res=(960, 540), samples=16):
    """Studio, VFX particle emitters, stand copies of the weapons; returns rig."""
    sc = bpy.context.scene
    rig = _setup_studio(res, samples)
    pc = _show_col("SHOW_Proto")
    protos = {k: _proto("SH_P_" + k, k, pc) for k in ("ember", "smoke", "fire", "fire2", "drip")}
    bpy.context.view_layer.layer_collection.children[pc.name].exclude = True
    for item in ITEMS:
        dst = _show_col("SHOW_" + item)
        src = bpy.data.collections["ITEM_" + item]
        _vfx_for(src, dst, protos, scale=3.0 if item == "Lava_Stand" else 1.0, seed=len(item))
    stand = bpy.data.collections["ITEM_Lava_Stand"]
    dst = bpy.data.collections["SHOW_Lava_Stand"]
    for w in ("Lava_AR", "Lava_Deagle", "Lava_Karambit"):
        mount = stand.objects["MOUNT_" + w].matrix_world
        for o in bpy.data.collections["ITEM_" + w].objects:
            if o.type != "MESH":
                continue
            c = o.copy()
            c.matrix_world = mount @ o.matrix_world
            dst.objects.link(c)
        _vfx_for(bpy.data.collections["ITEM_" + w], dst, protos, M=mount, only=("Embers", "HeatGlow"),
                 rate_mul=0.6, seed=99)
    sc.frame_start, sc.frame_end = 1, PRE + NF + 2
    sc.frame_set(1)
    try:
        with bpy.context.temp_override(scene=sc):
            bpy.ops.ptcache.bake_all(bake=True)
    except Exception as e:
        print("[lava] particle bake failed, simulating on the fly:", e)
    return rig


def _solo(item):
    for it in ITEMS:
        bpy.data.collections["ITEM_" + it].hide_render = it != item
        bpy.data.collections["SHOW_" + it].hide_render = it != item


def setup_item_pass(rig, item):
    _solo(item)
    mn, mx = _bbox(bpy.data.collections["ITEM_" + item])
    c = (mn + mx) / 2
    if item == "Lava_Stand":
        _set_pass(rig, Vector((0, 0, 2.6)), 15.0, elev=0.26, lens=38, floor_z=0.0, orbit=(-0.55, 0.55))
    else:
        ext = max((mx - mn).x, (mx - mn).y, (mx - mn).z * 1.6)
        dist = ext * 1.22 / (2 * math.tan(math.atan(18 / 50)))
        _set_pass(rig, c, dist, elev=0.22, lens=50, floor_z=mn.z - 0.35 * ext)


def render_showcase(out_dir, res=(960, 540), samples=16, items=ITEMS):
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    rig = prepare_showcase(res, samples)
    for item in items:
        setup_item_pass(rig, item)
        dirs = [_render_frames(out_dir, item, PRE + 1, PRE + NF)]
        if item == "Lava_AR":     # close-up of the muzzle effects
            mz = bpy.data.objects["VFX_Fire_1"].matrix_world.translation
            _set_pass(rig, mz + Vector((0, -0.35, 0.05)), 1.6, elev=0.18, lens=50,
                      floor_z=bpy.data.objects["SH_Floor"].location.z, orbit=(1.2, 1.9), nf=60)
            dirs.append(_render_frames(out_dir, item + "_close", PRE + 1, PRE + 60))
        _encode(dirs, PRE + 1, os.path.join(out_dir, item + ".mp4"))
        print("[lava] wrote", os.path.join(out_dir, item + ".mp4"))
    for it in ITEMS:
        bpy.data.collections["ITEM_" + it].hide_render = False
