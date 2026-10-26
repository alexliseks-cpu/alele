"""ICE limited pack: Ice_Sniper, Ice_Revolver, Ice_Butterfly (knife skin), Ice_Stand.

Follows blender/packs/CONTRACT.md (studs, +Y forward, +Z up, weapon origin = grip
point, one ITEM_<Name> collection per item, rbx_* / bake / pulse custom props,
VFX_<Preset>[_n] empties).

Style: white / pale-blue frosted bodies, pale-gold filigree trim, deep-blue
crystal inlay panels, translucent ice crystals (Glass) and glowing cyan Neon
veins / runes - the ornate "premium skin" look of the references.

    build()                  -> builds the 4 items into the current scene
    render_showcase(out_dir) -> EEVEE turntables <out_dir>/<Item>.mp4

Every mesh is built with bmesh in item space and has identity transform, except
the butterfly parts (posed open in knife model space, mesh data in studs, object
origin at the bone pivot) and Ice_Stand_SignPlate (origin at the plate centre,
title face = -Y).
"""

import math
import os
import random
import shutil
import subprocess

import bmesh
import bpy
from mathutils import Matrix, Vector

from vm import mesh_utils as mu

NEON = (0.3, 0.8, 1.0)
ICE = (0.6, 0.85, 1.0)
PULSE = 0.5
IDENT = Matrix.Identity(4)
RX90 = Matrix.Rotation(math.pi / 2, 4, "X")          # lathe axis +Y -> +Z
ITEMS = ("Ice_Sniper", "Ice_Revolver", "Ice_Butterfly", "Ice_Stand")


def T(x, y=0.0, z=0.0):
    if not isinstance(x, (int, float)):
        return Matrix.Translation(Vector(x))
    return Matrix.Translation(Vector((x, y, z)))


def V(*a):
    return Vector(a)


def _set(obj, attr, val):
    try:
        setattr(obj, attr, val)
        return True
    except Exception:
        return False


# =============================================================================
# materials
# =============================================================================

class _NT:
    def __init__(self, nt):
        self.nt = nt

    def n(self, t, **kw):
        node = self.nt.nodes.new(t)
        for k, v in kw.items():
            setattr(node, k, v)
        return node

    def put(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        elif isinstance(v, (tuple, list)) and len(v) == 3:
            sock.default_value = (*v, 1.0)
        else:
            sock.default_value = v

    def math(self, op, a, b=0.0, clamp=False):
        node = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.put(node.inputs[0], a)
        self.put(node.inputs[1], b)
        return node.outputs[0]

    def mrange(self, v, a, b, c, d):
        node = self.n("ShaderNodeMapRange", clamp=True)
        self.put(node.inputs["Value"], v)
        node.inputs["From Min"].default_value = a
        node.inputs["From Max"].default_value = b
        node.inputs["To Min"].default_value = c
        node.inputs["To Max"].default_value = d
        return node.outputs["Result"]

    def noise(self, P, scale, detail=4.0, rough=0.5):
        node = self.n("ShaderNodeTexNoise")
        self.put(node.inputs["Vector"], P)
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        node.inputs["Roughness"].default_value = rough
        return node

    def voronoi(self, P, scale, feature="F1", rnd=1.0):
        node = self.n("ShaderNodeTexVoronoi", feature=feature)
        self.put(node.inputs["Vector"], P)
        node.inputs["Scale"].default_value = scale
        node.inputs["Randomness"].default_value = rnd
        return node

    def ramp(self, fac, stops):
        node = self.n("ShaderNodeValToRGB")
        self.put(node.inputs["Fac"], fac)
        els = node.color_ramp.elements

        def c4(c):
            return (c, c, c, 1.0) if isinstance(c, (int, float)) else (*c, 1.0)
        els[0].position, els[0].color = stops[0][0], c4(stops[0][1])
        els[1].position, els[1].color = stops[-1][0], c4(stops[-1][1])
        for p, c in stops[1:-1]:
            e = els.new(p)
            e.color = c4(c)
        return node.outputs["Color"]

    def coords(self):
        return self.n("ShaderNodeTexCoord").outputs["Object"]

    def bsdf(self):
        b = self.n("ShaderNodeBsdfPrincipled")
        o = self.n("ShaderNodeOutputMaterial")
        self.nt.links.new(b.outputs[0], o.inputs["Surface"])
        return b

    def bump(self, bsdf, height, strength, dist=0.02):
        bp = self.n("ShaderNodeBump")
        bp.inputs["Strength"].default_value = strength
        bp.inputs["Distance"].default_value = dist
        self.put(bp.inputs["Height"], height)
        self.nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])


def _mat(name, viewport=(0.8, 0.8, 0.8)):
    m = bpy.data.materials.get(name)
    if m is not None:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    _set(m, "use_nodes", True)
    m.node_tree.nodes.clear()
    m.diffuse_color = (*viewport[:3], 1.0)
    return m, _NT(m.node_tree)


def _pin(bsdf, name, v):
    s = bsdf.inputs.get(name)
    if s is not None:
        s.default_value = (*v, 1.0) if isinstance(v, tuple) and len(v) == 3 else v


def mat_frost(name, hi, lo, line, scale=3.0, cell=5.0, rough=(0.22, 0.42), metal=0.0, coat=0.5,
              bump=0.15, facet=0.14):
    """Frosted ice: cloudy white-blue noise, crystalline voronoi facets + crack lines.
    Single Principled BSDF, Object coordinates -> bakeable."""
    m, t = _mat(name, hi)
    P = t.coords()
    n1 = t.noise(P, scale, 6.0, 0.55).outputs["Fac"]
    edge = t.voronoi(P, cell, "DISTANCE_TO_EDGE").outputs["Distance"]
    line_f = t.mrange(edge, 0.0, 0.03, 1.0, 0.0)
    cellc = t.voronoi(P, cell, "F1").outputs["Color"]
    fine = t.noise(P, scale * 14.0, 2.0, 0.6).outputs["Fac"]
    tt = t.math("ADD", n1, t.math("MULTIPLY", t.math("SUBTRACT", cellc, 0.5), facet))
    tt = t.math("SUBTRACT", tt, t.math("MULTIPLY", line_f, 0.35))
    b = t.bsdf()
    t.put(b.inputs["Base Color"], t.ramp(tt, [(0.08, line), (0.38, lo), (0.64, hi)]))
    r = t.math("ADD", rough[0], t.math("MULTIPLY", fine, rough[1] - rough[0]))
    t.put(b.inputs["Roughness"], t.math("SUBTRACT", r, t.math("MULTIPLY", line_f, 0.08), clamp=True))
    b.inputs["Metallic"].default_value = metal
    _pin(b, "Coat Weight", coat)
    _pin(b, "Coat Roughness", 0.08)
    t.bump(b, t.math("ADD", t.math("MULTIPLY", line_f, 0.6), t.math("MULTIPLY", fine, 0.4)), bump)
    return m


def mat_crystal_panel(name, scale=9.0):
    """Deep-blue shattered crystal inlay (per-cell blues + bright facet edges). Bakeable."""
    m, t = _mat(name, (0.1, 0.3, 0.85))
    P = t.coords()
    w = t.noise(P, 3.0, 2.0, 0.5).outputs["Fac"]
    cellc = t.voronoi(P, scale, "F1").outputs["Color"]
    edge = t.voronoi(P, scale, "DISTANCE_TO_EDGE").outputs["Distance"]
    e = t.mrange(edge, 0.0, 0.025, 1.0, 0.0)
    tt = t.math("ADD", t.math("MULTIPLY", cellc, 0.65), t.math("MULTIPLY", w, 0.25))
    tt = t.math("ADD", tt, t.math("MULTIPLY", e, 0.45))
    b = t.bsdf()
    t.put(b.inputs["Base Color"], t.ramp(tt, [(0.05, (0.015, 0.06, 0.32)), (0.42, (0.06, 0.25, 0.8)),
                                              (0.72, (0.3, 0.65, 1.0)), (0.95, (0.85, 0.95, 1.0))]))
    t.put(b.inputs["Roughness"], t.math("ADD", 0.1, t.math("MULTIPLY", e, 0.25)))
    b.inputs["Metallic"].default_value = 0.35
    _pin(b, "Coat Weight", 0.8)
    _pin(b, "Coat Roughness", 0.05)
    t.bump(b, e, 0.25)
    return m


def mat_metal(name, c0, c1, rough=(0.16, 0.3), scale=6.0):
    m, t = _mat(name, c1)
    P = t.coords()
    n1 = t.noise(P, scale, 4.0, 0.5).outputs["Fac"]
    fine = t.noise(P, scale * 18.0, 2.0, 0.5).outputs["Fac"]
    b = t.bsdf()
    t.put(b.inputs["Base Color"], t.ramp(n1, [(0.3, c0), (0.7, c1)]))
    t.put(b.inputs["Roughness"], t.math("ADD", rough[0], t.math("MULTIPLY", fine, rough[1] - rough[0])))
    b.inputs["Metallic"].default_value = 1.0
    t.bump(b, fine, 0.05)
    return m


def mat_rough(name, c0, c1, rough=0.5, metal=0.0, scale=40.0, bump=0.3):
    """Grippy / snowy dielectric with noise colour + bump. Bakeable."""
    m, t = _mat(name, c1)
    P = t.coords()
    n1 = t.noise(P, scale * 0.1, 5.0, 0.55).outputs["Fac"]
    fine = t.noise(P, scale, 3.0, 0.6).outputs["Fac"]
    b = t.bsdf()
    t.put(b.inputs["Base Color"], t.ramp(t.math("ADD", t.math("MULTIPLY", n1, 0.7), t.math("MULTIPLY", fine, 0.3)),
                                         [(0.3, c0), (0.7, c1)]))
    t.put(b.inputs["Roughness"], t.math("ADD", rough - 0.1, t.math("MULTIPLY", fine, 0.2)))
    b.inputs["Metallic"].default_value = metal
    t.bump(b, fine, bump)
    return m


def mat_glacier(name):
    m, t = _mat(name, (0.2, 0.38, 0.55))
    P = t.coords()
    cellc = t.voronoi(P, 1.4, "F1").outputs["Color"]
    edge = t.voronoi(P, 1.4, "DISTANCE_TO_EDGE").outputs["Distance"]
    e = t.mrange(edge, 0.0, 0.06, 1.0, 0.0)
    n1 = t.noise(P, 2.5, 6.0, 0.6).outputs["Fac"]
    tt = t.math("ADD", t.math("MULTIPLY", cellc, 0.5), t.math("MULTIPLY", n1, 0.5))
    tt = t.math("ADD", tt, t.math("MULTIPLY", e, 0.35))
    b = t.bsdf()
    t.put(b.inputs["Base Color"], t.ramp(tt, [(0.2, (0.03, 0.08, 0.17)), (0.5, (0.12, 0.28, 0.45)),
                                              (0.8, (0.45, 0.68, 0.85)), (1.0, (0.85, 0.94, 1.0))]))
    t.put(b.inputs["Roughness"], t.math("ADD", 0.22, t.math("MULTIPLY", n1, 0.3)))
    _pin(b, "Coat Weight", 0.4)
    t.bump(b, t.math("ADD", e, t.math("MULTIPLY", n1, 0.5)), 0.35, 0.05)
    return m


def mat_neon(name, color=NEON, strength=9.0):
    m, t = _mat(name, color)
    e = t.n("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1.0)
    e.inputs["Strength"].default_value = strength
    o = t.n("ShaderNodeOutputMaterial")
    t.nt.links.new(e.outputs[0], o.inputs["Surface"])
    m["ice_strength"] = strength
    return m


def mat_glass(name, alpha=0.32):
    """Translucent glowing ice (preview only - Roblox uses Glass material)."""
    m, t = _mat(name, ICE)
    b = t.bsdf()
    b.inputs["Base Color"].default_value = (0.3, 0.62, 1.0, 1.0)
    b.inputs["Roughness"].default_value = 0.05
    _pin(b, "IOR", 1.31)
    _pin(b, "Coat Weight", 1.0)
    _pin(b, "Coat Roughness", 0.02)
    _pin(b, "Transmission Weight", 0.35)
    lw = t.n("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.4
    _pin(b, "Emission Color", (0.3, 0.7, 1.0))
    t.put(b.inputs["Emission Strength"], t.math("ADD", t.math("MULTIPLY", lw.outputs["Fresnel"], 1.1), 0.06))
    t.put(b.inputs["Alpha"], t.math("ADD", alpha, t.math("MULTIPLY", lw.outputs["Facing"], 0.4), clamp=True))
    _set(m, "surface_render_method", "BLENDED")
    _set(m, "blend_method", "BLEND")
    _set(m, "use_backface_culling", False)
    _set(m, "use_transparency_overlap", True)
    return m


_MATS = {}


def _materials():
    if _MATS and all(m.name in bpy.data.materials for m in _MATS.values()):
        return _MATS
    _MATS.clear()
    _MATS.update(
        frost=mat_frost("Ice_Frost", (0.93, 0.97, 1.0), (0.66, 0.82, 0.96), (0.42, 0.66, 0.95)),
        blue=mat_crystal_panel("Ice_CrystalPanel"),
        gold=mat_metal("Ice_PaleGold", (0.93, 0.74, 0.42), (1.0, 0.87, 0.6)),
        silver=mat_metal("Ice_Silver", (0.74, 0.8, 0.88), (0.9, 0.94, 0.98)),
        navy=mat_rough("Ice_Navy", (0.015, 0.04, 0.13), (0.05, 0.11, 0.3), 0.45, 0.2, 60.0, 0.25),
        snow=mat_rough("Ice_Snow", (0.78, 0.86, 0.95), (0.98, 0.99, 1.0), 0.75, 0.0, 9.0, 0.45),
        glacier=mat_glacier("Ice_Glacier"),
        glass=mat_glass("Ice_Glass"),
    )
    return _MATS


# =============================================================================
# geometry helpers (bmesh)
# =============================================================================

def _setmat(bm, n0, mat):
    bm.faces.ensure_lookup_table()
    for i in range(n0, len(bm.faces)):
        bm.faces[i].material_index = mat


def _area(p):
    return 0.5 * sum(p[i].x * p[(i + 1) % len(p)].y - p[(i + 1) % len(p)].x * p[i].y for i in range(len(p)))


def ccw(pts):
    p = [Vector((float(a), float(b))) for a, b in pts]
    return p if _area(p) > 0 else p[::-1]


def offset(pts, d):
    """Offset a CCW polygon (d > 0 outward)."""
    n = len(pts)
    out = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        e1, e2 = (b - a).normalized(), (c - b).normalized()
        n1, n2 = Vector((e1.y, -e1.x)), Vector((e2.y, -e2.x))
        nv = n1 + n2
        nv = n1 if nv.length < 1e-6 else nv.normalized()
        out.append(b + nv * (d / max(nv.dot(n1), 0.35)))
    return out


def slab(bm, pts, xa, xb, bev=0.0, mat=0, M=IDENT):
    """Prism of a closed (Y, Z) outline between X = xa..xb with chamfered rims."""
    n0 = len(bm.faces)
    x0, x1 = min(xa, xb), max(xa, xb)
    pts = ccw(pts)
    bev = min(bev, (x1 - x0) * 0.45)
    if bev > 0:
        inner = offset(pts, -bev)
        rows = [(inner, x0), (pts, x0 + bev), (pts, x1 - bev), (inner, x1)]
    else:
        rows = [(pts, x0), (pts, x1)]
    vr = [[bm.verts.new(M @ Vector((x, p.x, p.y))) for p in poly] for poly, x in rows]
    n = len(pts)
    for a, b in zip(vr[:-1], vr[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    caps = [bm.faces.new(list(reversed(vr[0]))), bm.faces.new(vr[-1])]
    bmesh.ops.triangulate(bm, faces=caps)
    _setmat(bm, n0, mat)


def _resample(loop, n, c):
    k = min(range(len(loop)), key=lambda i: abs(math.atan2((loop[i] - c).y, (loop[i] - c).x)))
    p = loop[k:] + loop[:k] + [loop[k]]
    seg = [(p[i + 1] - p[i]).length for i in range(len(p) - 1)]
    tot = sum(seg)
    out, acc, i = [], 0.0, 0
    for s in range(n):
        target = tot * s / n
        while i < len(seg) - 1 and acc + seg[i] < target:
            acc += seg[i]
            i += 1
        f = (target - acc) / max(seg[i], 1e-9)
        out.append(p[i].lerp(p[i + 1], min(max(f, 0.0), 1.0)))
    return out


def ring_slab(bm, outer, inner, xa, xb, bev=0.0, mat=0, M=IDENT, n=56):
    """Prism of an outline WITH one hole (e.g. a skeleton stock)."""
    n0 = len(bm.faces)
    x0, x1 = min(xa, xb), max(xa, xb)
    o, h = ccw(outer), ccw(inner)
    c = sum(h, Vector((0, 0))) / len(h)
    O, H = _resample(o, n, c), _resample(h, n, c)
    Oi, Ho = offset(O, -bev), offset(H, bev)
    ro = [(Oi, x0), (O, x0 + bev), (O, x1 - bev), (Oi, x1)]
    rh = [(Ho, x0), (H, x0 + bev), (H, x1 - bev), (Ho, x1)]
    vo = [[bm.verts.new(M @ Vector((x, p.x, p.y))) for p in poly] for poly, x in ro]
    vh = [[bm.verts.new(M @ Vector((x, p.x, p.y))) for p in poly] for poly, x in rh]
    for rows in (vo, vh):
        for a, b in zip(rows[:-1], rows[1:]):
            for i in range(n):
                j = (i + 1) % n
                bm.faces.new((a[i], a[j], b[j], b[i]))
    for a, b in ((vo[0], vh[0]), (vo[-1], vh[-1])):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    _setmat(bm, n0, mat)


def lathe(bm, prof, segs=24, M=IDENT, mat=0, phase=0.0, fn=None, closed=False):
    """Revolve a (y, r) profile about +Y. r == 0 -> pole vertex. closed -> ring (no caps).
    fn(j, theta, y, r, row) -> (y, r) deforms individual vertices."""
    n0 = len(bm.faces)
    rows = []
    for i, (y, r) in enumerate(prof):
        if r <= 1e-7 and not closed:
            rows.append([bm.verts.new(M @ Vector((0.0, y, 0.0)))])
            continue
        row = []
        for j in range(segs):
            t = phase + 2.0 * math.pi * j / segs
            yy, rr = fn(j, t, y, r, i) if fn else (y, r)
            row.append(bm.verts.new(M @ Vector((math.cos(t) * rr, yy, math.sin(t) * rr))))
        rows.append(row)
    pairs = list(zip(rows[:-1], rows[1:])) + ([(rows[-1], rows[0])] if closed else [])
    for a, b in pairs:
        if len(a) == 1 and len(b) == 1:
            continue
        for j in range(segs):
            j2 = (j + 1) % segs
            if len(a) == 1:
                bm.faces.new((a[0], b[j], b[j2]))
            elif len(b) == 1:
                bm.faces.new((a[j], b[0], a[j2]))
            else:
                bm.faces.new((a[j], b[j], b[j2], a[j2]))
    if not closed:
        if len(rows[0]) > 1:
            bm.faces.new(rows[0])
        if len(rows[-1]) > 1:
            bm.faces.new(list(reversed(rows[-1])))
    _setmat(bm, n0, mat)


def band(bm, y0, y1, r, h, segs=24, M=IDENT, mat=0, phase=0.0):
    """Ring (trim band) around +Y: inner radius r, outer r + h."""
    lathe(bm, [(y0, r), (y0, r + h * 0.7), (y0 + (y1 - y0) * 0.2, r + h), (y1 - (y1 - y0) * 0.2, r + h),
               (y1, r + h * 0.7), (y1, r)], segs, M, mat, phase, closed=True)


def tube(bm, path, radius, segs=6, mat=0):
    n0 = len(bm.faces)
    mu.tube(bm, [Vector(p) for p in path], radius, segs=segs)
    _setmat(bm, n0, mat)


def ribbon(bm, path, widths, thick, nrm, mat=0):
    """Flat strip (rectangular section) along a path; nrm = surface normal (vector or fn(i, p))."""
    n0 = len(bm.faces)
    P = [Vector(p) for p in path]
    N = len(P)
    rows = []
    for i, p in enumerate(P):
        d = (P[min(i + 1, N - 1)] - P[max(i - 1, 0)]).normalized()
        nv = Vector(nrm(i, p) if callable(nrm) else nrm)
        nv = (nv - d * nv.dot(d)).normalized()
        b = d.cross(nv).normalized()
        w = (widths[i] if isinstance(widths, (list, tuple)) else widths) * 0.5
        rows.append([bm.verts.new(p + nv * sx * thick + b * sy * w) for sx, sy in ((-1, -1), (-1, 1), (1, 1), (1, -1))])
    for a, b in zip(rows[:-1], rows[1:]):
        for j in range(4):
            j2 = (j + 1) % 4
            bm.faces.new((a[j], a[j2], b[j2], b[j]))
    bm.faces.new(rows[0])
    bm.faces.new(list(reversed(rows[-1])))
    _setmat(bm, n0, mat)


def crystal(bm, base, direction, L, R, rng, sides=6, mat=0, tipf=None):
    """Hexagonal ice crystal with pointed tip, base slightly buried at `base`."""
    d = Vector(direction).normalized()
    M = T(base) @ d.to_track_quat("Y", "Z").to_matrix().to_4x4()
    fac = [rng.uniform(0.78, 1.2) for _ in range(sides)]
    tf = tipf if tipf is not None else rng.uniform(0.55, 0.72)
    lathe(bm, [(-0.15 * L, 0.0), (0.0, R * 0.92), (L * tf, R), (L, 0.0)], sides, M, mat,
          rng.random() * 6.28, lambda j, t, y, r, i: (y, r * fac[j]))


def gem(bm, c, axis, R, H, sides=8, mat=0):
    d = Vector(axis).normalized()
    M = T(c) @ d.to_track_quat("Y", "Z").to_matrix().to_4x4()
    lathe(bm, [(-H * 0.55, 0.0), (0.0, R), (H * 0.2, R * 0.72), (H * 0.3, 0.0)], sides, M, mat, math.pi / sides)


def pnoise(t, seed, k=(1, 2, 3, 5)):
    rng = random.Random(seed)
    return sum(math.sin(t * h + rng.random() * 6.28) / h for h in k) / 1.6


def jag(p0, p1, n, amp, rng, perp):
    """Jagged (lightning-like) polyline from p0 to p1 offset along `perp`."""
    p0, p1, perp = Vector(p0), Vector(p1), Vector(perp)
    out = []
    for i in range(n + 1):
        f = i / n
        a = 0.0 if i in (0, n) else rng.uniform(-amp, amp)
        out.append(p0.lerp(p1, f) + perp * a)
    return out


def taper(n, w, ends=0.25):
    return [w * max(ends, min(1.0, 4.0 * (i / (n - 1)) * (1 - i / (n - 1)) + 0.15)) for i in range(n)]


# =============================================================================
# objects / collections
# =============================================================================

def _collection(name):
    col = bpy.data.collections.get(name)
    if col is not None:
        for o in list(col.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(col)
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def P_BAKE(rbx="SmoothPlastic", color=(0.9, 0.95, 1.0)):
    return {"rbx_material": rbx, "rbx_color": color, "bake": True}


P_NEON = {"rbx_material": "Neon", "rbx_color": NEON, "bake": False, "pulse": PULSE}
P_GLASS = {"rbx_material": "Glass", "rbx_color": ICE, "rbx_transparency": 0.25, "bake": False}


class Part:
    def __init__(self, name, mats, props, smooth=40.0, flat=False):
        self.name, self.mats, self.props, self.smooth, self.flat = name, mats, props, smooth, flat
        self.bm = bmesh.new()

    def done(self, col, off=None, to_local=None):
        bm = self.bm
        if off is not None:
            bmesh.ops.translate(bm, vec=Vector(off), verts=bm.verts)
        if to_local is not None:
            bmesh.ops.transform(bm, matrix=to_local, verts=bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        obj = bpy.data.objects.new(self.name, me)
        col.objects.link(obj)
        for m in self.mats:
            me.materials.append(m)
        if self.flat:
            me.shade_flat()
        else:
            mu.set_auto_smooth(obj, self.smooth)
        for k, v in self.props.items():
            obj[k] = v
        return obj


def vfx(col, preset, loc, **props):
    n = 1
    while bpy.data.objects.get(f"VFX_{preset}_{n}") is not None:
        n += 1
    e = bpy.data.objects.new(f"VFX_{preset}_{n}", None)
    e.empty_display_type = "SPHERE"
    e.empty_display_size = 0.12
    e.location = Vector(loc)
    col.objects.link(e)
    for k, v in props.items():
        e[k] = v
    return e


def mount(col, name, loc, rot_deg):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = 0.6
    e.location = Vector(loc)
    e.rotation_euler = [math.radians(a) for a in rot_deg]
    col.objects.link(e)
    return e


def _fin(lead, tip, back, teeth=4, depth=0.03):
    """Swept fin outline: leading edge points, tip, serrated trailing edge to `back`."""
    pts = [Vector(p) for p in lead] + [Vector(tip)]
    a, b = Vector(tip), Vector(back)
    d = b - a
    nrm = Vector((d.y, -d.x)).normalized()
    for k in range(1, teeth * 2):
        p = a + d * (k / (teeth * 2))
        if k % 2:
            p += nrm * depth
        pts.append(p)
    pts.append(b)
    return [(p.x, p.y) for p in pts]


# =============================================================================
# Ice_Sniper
# =============================================================================

def build_sniper(M):
    N = "Ice_Sniper"
    col = _collection("ITEM_" + N)
    rng = random.Random(11)
    OFF = V(0, 0.08, 0.27)      # design coords -> grip point at origin
    BZ = 0.20                   # bore axis height (design)
    SZ = 0.66                   # scope axis height
    neon = mat_neon(N + "_Neon")
    lens_m = mat_neon(N + "_LensGlow", NEON, 7.0)

    rec = Part(N + "_Receiver", [M["frost"], M["blue"]], P_BAKE())
    trim = Part(N + "_Trim", [M["gold"]], P_BAKE("Metal", (1.0, 0.86, 0.58)))
    glow = Part(N + "_Glow", [neon], dict(P_NEON))
    ice = Part(N + "_Crystals", [M["glass"]], dict(P_GLASS), flat=True)

    # ---- receiver + blue side panels + gold outline + rail -------------------
    R = [(-0.14, 0.04), (0.2, 0.0), (0.9, 0.0), (1.25, 0.03), (1.34, 0.11), (1.34, 0.30), (1.22, 0.37),
         (0.4, 0.38), (-0.06, 0.37), (-0.14, 0.30)]
    slab(rec.bm, R, -0.15, 0.15, 0.03, 0)
    panel = offset(ccw(R), -0.075)
    loop = offset(ccw(R), -0.036)
    for s in (1, -1):
        slab(rec.bm, [(p.x, p.y) for p in panel], s * 0.138, s * 0.162, 0.008, 1)
        tube(trim.bm, [V(s * 0.152, p.x, p.y) for p in loop + [loop[0]]], 0.013)
        vein = jag(V(s * 0.165, -0.02, 0.2), V(s * 0.165, 1.2, 0.19), 14, 0.035, rng, V(0, 0, 1))
        ribbon(glow.bm, vein, taper(len(vein), 0.022), 0.006, V(s, 0, 0))
        for yb in (0.35, 0.8):   # branches
            br = jag(V(s * 0.165, yb, 0.19), V(s * 0.165, yb + 0.2, 0.29), 4, 0.015, rng, V(0, 1, 0))
            ribbon(glow.bm, br, taper(len(br), 0.016), 0.006, V(s, 0, 0))
    slab(rec.bm, [(0.0, 0.36), (1.15, 0.36), (1.15, 0.43), (0.0, 0.43)], -0.065, 0.065, 0.012, 0)

    # ---- scope ----------------------------------------------------------------
    scope = Part(N + "_Scope", [M["frost"]], P_BAKE())
    MS = T(0, 0, SZ)
    lathe(scope.bm, [(0.0, 0.0), (0.0, 0.085), (-0.06, 0.085), (-0.06, 0.115), (0.02, 0.122), (0.24, 0.118),
                     (0.32, 0.078), (0.88, 0.078), (1.02, 0.105), (1.14, 0.138), (1.26, 0.138), (1.26, 0.118),
                     (1.21, 0.118), (1.21, 0.0)], 28, MS)
    for y0, y1, r, h in ((-0.065, -0.02, 0.112, 0.014), (0.40, 0.47, 0.076, 0.02), (0.74, 0.81, 0.076, 0.02),
                         (1.15, 1.19, 0.136, 0.012), (1.225, 1.265, 0.134, 0.013)):
        band(trim.bm, y0, y1, r, h, 28, MS)
    for y0 in (0.40, 0.74):          # mount legs
        slab(trim.bm, [(y0, 0.42), (y0 + 0.07, 0.42), (y0 + 0.07, SZ - 0.07), (y0, SZ - 0.07)], -0.05, 0.05, 0.012)
    tur = [(0.05, 0.0), (0.05, 0.05), (0.12, 0.05), (0.125, 0.056), (0.15, 0.05), (0.155, 0.0)]
    lathe(trim.bm, tur, 16, T(0, 0.6, SZ) @ RX90)
    lathe(trim.bm, tur, 16, T(0, 0.6, SZ) @ Matrix.Rotation(-math.pi / 2, 4, "Z"))
    lens = Part(N + "_ScopeLens", [lens_m], dict(P_NEON))
    lathe(lens.bm, [(1.205, 0.0), (1.205, 0.117), (1.222, 0.09), (1.23, 0.0)], 28, MS)
    lathe(lens.bm, [(0.004, 0.0), (0.004, 0.084), (-0.012, 0.06), (-0.018, 0.0)], 20, MS)
    band(glow.bm, 0.03, 0.05, 0.12, 0.006, 28, MS)
    band(glow.bm, 1.085, 1.105, 0.125, 0.007, 28, MS)

    # ---- barrel, handguard, muzzle -------------------------------------------
    bar = Part(N + "_Barrel", [M["silver"], M["frost"], M["blue"]], P_BAKE())
    MB = T(0, 0, BZ)
    lathe(bar.bm, [(1.30, 0.0), (1.30, 0.075), (2.6, 0.068), (3.48, 0.058), (3.48, 0.0)], 20, MB, 0)
    lathe(bar.bm, [(1.28, 0.0), (1.28, 0.15), (1.36, 0.168), (2.30, 0.155), (2.46, 0.125), (2.52, 0.085),
                   (2.52, 0.0)], 8, MB, 1, math.pi / 8)
    hp = [(1.44, BZ), (1.52, BZ - 0.045), (2.22, BZ - 0.04), (2.30, BZ), (2.22, BZ + 0.04), (1.52, BZ + 0.045)]
    for s in (1, -1):
        slab(bar.bm, hp, s * 0.128, s * 0.158, 0.008, 2)
        v = jag(V(s * 0.16, 1.5, BZ), V(s * 0.16, 2.25, BZ), 9, 0.022, rng, V(0, 0, 1))
        ribbon(glow.bm, v, taper(len(v), 0.02), 0.006, V(s, 0, 0))
    band(trim.bm, 1.25, 1.33, 0.15, 0.03, 8, MB, phase=math.pi / 8)
    band(trim.bm, 2.20, 2.27, 0.143, 0.025, 8, MB, phase=math.pi / 8)
    band(trim.bm, 3.00, 3.05, 0.062, 0.012, 20, MB)
    lathe(trim.bm, [(3.42, 0.0), (3.42, 0.075), (3.47, 0.095), (3.58, 0.095), (3.58, 0.08), (3.63, 0.08),
                    (3.63, 0.097), (3.72, 0.097), (3.72, 0.08), (3.77, 0.08), (3.77, 0.095), (3.84, 0.09),
                    (3.87, 0.06), (3.87, 0.035), (3.84, 0.035), (3.84, 0.0)], 16, MB)
    # helix vein around the bare barrel
    hel = []
    for i in range(57):
        f = i / 56
        y = 2.6 + 0.78 * f
        th = f * 2 * math.pi * 1.75
        r = 0.068 - (y - 2.6) / 0.88 * 0.01 + 0.002
        hel.append(V(math.cos(th) * r, y, BZ + math.sin(th) * r))
    ribbon(glow.bm, hel, taper(len(hel), 0.02), 0.005,
           lambda i, p: V(p.x, 0, p.z - BZ))
    # muzzle crown + icicles under the handguard
    for k in range(4):
        th = math.pi / 4 + k * math.pi / 2
        crystal(ice.bm, V(math.cos(th) * 0.08, 3.6, BZ + math.sin(th) * 0.08),
                V(math.cos(th) * 0.6, 1.0, math.sin(th) * 0.6), 0.3, 0.03, rng)
    for y, L in ((1.45, 0.12), (1.7, 0.22), (1.95, 0.32), (2.15, 0.21), (2.35, 0.12)):
        crystal(ice.bm, V(rng.uniform(-0.03, 0.03), y, BZ - 0.13), V(0, -0.25, -1), L, 0.035, rng, tipf=0.35)

    # ---- wing fins (gold) sweeping back from the handguard -------------------
    fin = _fin([(2.46, 0.10), (2.36, 0.20), (2.18, 0.30), (1.95, 0.40), (1.72, 0.48)], (1.50, 0.54),
               (2.10, 0.10), 4, 0.035)
    for s in (1, -1):
        Mf = T(0, 0, BZ) @ Matrix.Rotation(s * math.radians(-40), 4, "Y")
        slab(trim.bm, fin, -0.018, 0.018, 0.008, 0, Mf)

    # ---- stock (skeleton frame + ice window) ---------------------------------
    stock = Part(N + "_Stock", [M["frost"], M["navy"]], P_BAKE())
    O = [(-0.12, -0.05), (-0.5, -0.12), (-1.1, -0.22), (-1.62, -0.33), (-1.76, -0.34), (-1.80, -0.20),
         (-1.80, 0.22), (-1.74, 0.34), (-1.2, 0.34), (-0.6, 0.28), (-0.12, 0.30)]
    H = [(-0.62, 0.03), (-1.2, -0.06), (-1.52, -0.12), (-1.58, 0.06), (-1.48, 0.20), (-0.78, 0.16)]
    ring_slab(stock.bm, O, H, -0.12, 0.12, 0.025, 0)
    slab(stock.bm, [(-1.79, -0.33), (-1.88, -0.35), (-1.89, 0.32), (-1.79, 0.33)], -0.125, 0.125, 0.02, 1)
    win = offset(ccw(H), 0.03)
    slab(ice.bm, [(p.x, p.y) for p in win], -0.035, 0.035, 0.012)
    for s in (1, -1):
        for a, b, amp in (((-0.25, 0.25), (-1.62, 0.26), 0.02), ((-0.45, -0.075), (-1.58, -0.255), 0.015)):
            v = jag(V(s * 0.121, *a), V(s * 0.121, *b), 12, amp, rng, V(0, 0, 1))
            ribbon(glow.bm, v, taper(len(v), 0.02), 0.006, V(s, 0, 0))
        spike = [(-0.05, 0.17), (-0.30, 0.25), (-0.70, 0.31), (-1.12, 0.36), (-0.78, 0.25), (-0.42, 0.15),
                 (-0.15, 0.10)]
        slab(trim.bm, spike, s * 0.118, s * 0.138, 0.007)
        tube(trim.bm, [V(s * 0.122, p.x, p.y) for p in offset(ccw(H), 0.012) + [offset(ccw(H), 0.012)[0]]], 0.011)
    for y, z, L in ((-0.75, -0.15, 0.16), (-1.0, -0.19, 0.26), (-1.25, -0.24, 0.2), (-1.5, -0.3, 0.13)):
        crystal(ice.bm, V(0, y, z), V(0, -0.35, -1), L, 0.04, rng, tipf=0.35)
    for dx, dy, L in ((0.0, 0.0, 0.32), (0.06, 0.08, 0.2), (-0.06, 0.06, 0.18)):
        crystal(ice.bm, V(dx, -1.68 + dy, 0.31), V(dx * 4, -0.7, 1), L, 0.04, rng)

    # ---- grip, trigger, magazine, guard --------------------------------------
    grip = Part(N + "_Grip", [M["navy"], M["silver"], M["frost"], M["blue"]], P_BAKE())
    G = [(-0.12, 0.02), (0.12, 0.02), (0.06, -0.20), (-0.02, -0.48), (-0.10, -0.58), (-0.26, -0.56), (-0.24, -0.44),
         (-0.16, -0.18)]
    slab(grip.bm, G, -0.10, 0.10, 0.025, 0)
    gp = offset(ccw(G), -0.055)
    for s in (1, -1):
        slab(grip.bm, [(p.x, p.y) for p in gp], s * 0.092, s * 0.108, 0.006, 3)
        v = jag(V(s * 0.11, -0.04, -0.06), V(s * 0.11, -0.16, -0.5), 6, 0.012, rng, V(0, 1, 0))
        ribbon(glow.bm, v, taper(len(v), 0.016), 0.005, V(s, 0, 0))
    slab(grip.bm, [(0.22, 0.01), (0.27, 0.01), (0.25, -0.05), (0.21, -0.11), (0.18, -0.12), (0.17, -0.10),
                   (0.21, -0.05)], -0.018, 0.018, 0.006, 1)
    slab(grip.bm, [(0.55, 0.02), (0.88, 0.02), (0.86, -0.26), (0.57, -0.26)], -0.11, 0.11, 0.02, 2)
    slab(trim.bm, [(0.54, -0.23), (0.89, -0.23), (0.88, -0.31), (0.55, -0.31)], -0.125, 0.125, 0.015)
    for s in (1, -1):
        ribbon(glow.bm, [V(s * 0.112, 0.715, -0.04), V(s * 0.112, 0.715, -0.12), V(s * 0.112, 0.715, -0.2)],
               [0.01, 0.07, 0.01], 0.005, V(s, 0, 0))
    tube(trim.bm, [V(0, 0.48, 0.01), V(0, 0.47, -0.08), V(0, 0.40, -0.15), V(0, 0.28, -0.18), V(0, 0.14, -0.17),
                   V(0, 0.06, -0.12), V(0, 0.03, -0.05)], 0.022, 8)

    # ---- bolt + rail ridges ---------------------------------------------------
    bolt = Part(N + "_Bolt", [M["silver"]], P_BAKE("Metal", (0.88, 0.92, 0.97)))
    lathe(bolt.bm, [(-0.26, 0.0), (-0.26, 0.055), (-0.22, 0.072), (-0.12, 0.072), (-0.12, 0.0)], 16, T(0, 0, 0.30))
    tube(bolt.bm, [V(0.10, 0.10, 0.30), V(0.20, 0.10, 0.30), V(0.27, 0.07, 0.25), V(0.31, 0.05, 0.18)], 0.024, 8)
    for i in range(9):
        y = 0.04 + i * 0.125
        mu.box(bolt.bm, (-0.068, y, 0.425), (0.068, y + 0.05, 0.455))
    gem(ice.bm, V(0.325, 0.045, 0.16), V(0.35, -0.2, -1), 0.06, 0.13)

    objs = [p.done(col, OFF) for p in (rec, scope, lens, bar, stock, grip, bolt, trim, ice, glow)]
    O3 = OFF
    for preset, loc, kw in (("Frost", (0, 3.95, BZ), {}), ("Frost", (0, 2.9, BZ), {"size": 0.7}),
                            ("Snow", (0, 1.9, BZ + 0.45), {}), ("Snow", (0, 3.2, BZ + 0.35), {"rate": 0.7}),
                            ("Sparkle", (0, 3.65, BZ), {}), ("Sparkle", (0, 1.9, BZ - 0.3), {}),
                            ("Sparkle", (0, -1.65, 0.45), {}), ("Sparkle", (0, -1.1, 0.05), {"rate": 0.6}),
                            ("IceGlow", (0.0, 0.6, 0.45), {}), ("IceGlow", (0, 2.0, BZ), {"size": 0.8})):
        vfx(col, preset, V(*loc) + O3, **kw)
    return objs


# =============================================================================
# Ice_Revolver
# =============================================================================

def build_revolver(M):
    N = "Ice_Revolver"
    col = _collection("ITEM_" + N)
    rng = random.Random(23)
    OFF = V(0, 0.19, 0.18)
    BZ, CZ = 0.21, 0.145
    neon = mat_neon(N + "_Neon")
    frame = Part(N + "_Frame", [M["frost"], M["blue"]], P_BAKE())
    cyl = Part(N + "_Cylinder", [M["frost"]], P_BAKE())
    bar = Part(N + "_Barrel", [M["silver"], M["frost"], M["blue"]], P_BAKE())
    grip = Part(N + "_Grip", [M["navy"], M["blue"], M["silver"]], P_BAKE())
    trim = Part(N + "_Trim", [M["gold"]], P_BAKE("Metal", (1.0, 0.86, 0.58)))
    glow = Part(N + "_Glow", [neon], dict(P_NEON))
    ice = Part(N + "_Crystals", [M["glass"]], dict(P_GLASS), flat=True)

    F = [(-0.18, 0.20), (-0.12, 0.06), (0.02, 0.03), (0.42, 0.06), (0.46, 0.12), (0.46, 0.31), (0.38, 0.35),
         (0.0, 0.35), (-0.12, 0.33), (-0.18, 0.28)]
    slab(frame.bm, F, -0.075, 0.075, 0.02, 0)
    fl = offset(ccw(F), -0.024)
    for s in (1, -1):
        tube(trim.bm, [V(s * 0.077, p.x, p.y) for p in fl + [fl[0]]], 0.009)

    # cylinder with 6 flutes (neon strips inside the flutes)
    ph = math.pi / 2

    def flute(j, t, y, r, i):
        if 0.13 < y < 0.30 and r > 0.13:
            return y, r - 0.026 * max(0.0, math.cos(6 * (t - ph))) ** 6
        return y, r
    MC = T(0, 0, CZ)
    lathe(cyl.bm, [(0.06, 0.0), (0.06, 0.11), (0.075, 0.135), (0.11, 0.135), (0.14, 0.135), (0.29, 0.135),
                   (0.32, 0.135), (0.355, 0.135), (0.37, 0.11), (0.37, 0.0)], 48, MC, 0, 0.0, flute)
    band(trim.bm, 0.08, 0.10, 0.134, 0.008, 48, MC)
    band(trim.bm, 0.33, 0.35, 0.134, 0.008, 48, MC)
    for k in range(6):
        th = ph + k * math.pi / 3
        dr = V(math.cos(th), 0, math.sin(th))
        path = [MC @ (dr * 0.112 + V(0, y, 0)) for y in (0.15, 0.185, 0.215, 0.245, 0.28)]
        ribbon(glow.bm, path, [0.006, 0.016, 0.02, 0.016, 0.006], 0.004, dr)
    lathe(cyl.bm, [(0.04, 0.0), (0.04, 0.03), (0.39, 0.03), (0.39, 0.0)], 12, MC, 0)   # axle

    # barrel + full-lug shroud
    MB = T(0, 0, BZ)
    lathe(bar.bm, [(0.44, 0.0), (0.44, 0.05), (1.24, 0.045), (1.24, 0.024), (1.21, 0.024), (1.21, 0.0)], 16, MB, 0)
    S = [(0.44, 0.10), (1.12, 0.12), (1.20, 0.15), (1.20, 0.27), (1.14, 0.29), (0.44, 0.30)]
    slab(bar.bm, S, -0.062, 0.062, 0.018, 1)
    slab(bar.bm, [(0.46, 0.285), (1.16, 0.285), (1.16, 0.318), (0.46, 0.318)], -0.024, 0.024, 0.006, 0)
    sp = offset(ccw(S), -0.035)
    for s in (1, -1):
        slab(bar.bm, [(p.x, p.y) for p in sp], s * 0.054, s * 0.071, 0.006, 2)
        v = jag(V(s * 0.073, 0.5, 0.2), V(s * 0.073, 1.12, 0.2), 9, 0.03, rng, V(0, 0, 1))
        ribbon(glow.bm, v, taper(len(v), 0.018), 0.005, V(s, 0, 0))
        fin = _fin([(1.19, 0.12), (1.08, 0.09)], (0.80, 0.04), (1.05, 0.125), 3, 0.02)
        slab(trim.bm, fin, s * 0.058, s * 0.074, 0.005)
        wing = _fin([(-0.04, 0.30), (-0.15, 0.36)], (-0.32, 0.43), (-0.10, 0.27), 2, 0.02)
        slab(trim.bm, wing, s * 0.072, s * 0.09, 0.005)
    band(trim.bm, 1.20, 1.245, 0.046, 0.012, 16, MB)

    # grip, hammer, trigger, guard, pommel
    G = [(-0.02, 0.06), (-0.08, -0.18), (-0.14, -0.38), (-0.20, -0.46), (-0.34, -0.46), (-0.36, -0.38),
         (-0.30, -0.16), (-0.24, 0.08), (-0.19, 0.22), (-0.12, 0.26)]
    slab(grip.bm, G, -0.085, 0.085, 0.025, 0)
    gp = offset(ccw(G), -0.05)
    gl = offset(ccw(G), -0.03)
    for s in (1, -1):
        slab(grip.bm, [(p.x, p.y) for p in gp], s * 0.078, s * 0.096, 0.006, 1)
        tube(trim.bm, [V(s * 0.088, p.x, p.y) for p in gl + [gl[0]]], 0.01)
        v = jag(V(s * 0.098, -0.14, 0.12), V(s * 0.098, -0.27, -0.36), 7, 0.015, rng, V(0, 1, 0))
        ribbon(glow.bm, v, taper(len(v), 0.017), 0.005, V(s, 0, 0))
    slab(grip.bm, [(-0.12, 0.30), (-0.08, 0.33), (-0.15, 0.43), (-0.25, 0.45), (-0.25, 0.41), (-0.17, 0.37)],
         -0.022, 0.022, 0.006, 2)
    slab(grip.bm, [(0.12, 0.04), (0.16, 0.04), (0.14, -0.02), (0.10, -0.08), (0.07, -0.08), (0.07, -0.06),
                   (0.11, -0.02)], -0.018, 0.018, 0.005, 2)
    tube(trim.bm, [V(0, 0.24, 0.05), V(0, 0.23, -0.04), V(0, 0.17, -0.10), V(0, 0.07, -0.12), V(0, -0.02, -0.10),
                   V(0, -0.06, -0.04)], 0.016, 8)
    slab(trim.bm, [(-0.20, -0.44), (-0.35, -0.44), (-0.37, -0.49), (-0.19, -0.49)], -0.09, 0.09, 0.012)

    # crystals: crest on the rib, pommel spike, frame spikes
    for y, L in ((0.62, 0.12), (0.84, 0.17), (1.06, 0.22)):
        crystal(ice.bm, V(0, y, 0.30), V(0, -0.55, 1), L, 0.028, rng)
    crystal(ice.bm, V(0, 1.16, 0.30), V(0, 0.2, 1), 0.08, 0.018, rng)
    crystal(ice.bm, V(0, -0.28, -0.48), V(0, -0.6, -1), 0.22, 0.04, rng)
    for s in (1, -1):
        crystal(ice.bm, V(s * 0.05, -0.24, -0.47), V(s * 0.7, -0.4, -1), 0.12, 0.028, rng)
        crystal(ice.bm, V(s * 0.06, 0.40, 0.08), V(s * 0.6, 0.7, -0.5), 0.13, 0.025, rng)
    gem(ice.bm, V(0.0, -0.105, 0.33), V(0, -0.5, 1), 0.03, 0.06)

    objs = [p.done(col, OFF) for p in (frame, cyl, bar, grip, trim, ice, glow)]
    for preset, loc, kw in (("Frost", (0, 1.30, BZ), {}), ("Frost", (0, 0.22, CZ), {"size": 0.6}),
                            ("Sparkle", (0, 0.85, 0.42), {}), ("Sparkle", (0, -0.32, -0.6), {}),
                            ("Snow", (0, 0.7, 0.55), {"rate": 0.5}), ("IceGlow", (0.2, 0.3, 0.2), {})):
        vfx(col, preset, V(*loc) + OFF, **kw)
    return objs


# =============================================================================
# Ice_Butterfly (skin of vm.models.butterfly, knife model space, OPEN, studs)
# =============================================================================

def build_butterfly(M):
    from vm import skeleton, spec
    from vm.models import butterfly
    col = _collection("ITEM_Ice_Butterfly")
    for nm in ("BF_HandleA_Mesh", "BF_HandleB_Mesh", "BF_Blade_Mesh", "BF_Latch_Mesh"):
        o = bpy.data.objects.get(nm)
        if o is not None and any(c.name == "ITEM_Ice_Butterfly" for c in o.users_collection):
            bpy.data.objects.remove(o, do_unlink=True)
    had_meshes = bpy.data.collections.get("Meshes") is not None
    objs = butterfly.build()
    meshes = bpy.data.collections.get("Meshes")
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    if meshes is not None and not had_meshes and not meshes.all_objects:
        bpy.data.collections.remove(meshes)
    rng = random.Random(31)

    # pose open in knife model space (tools/model_preview.pose_butterfly logic, studs)
    A, blade_f, B = skeleton.bf_link_frames(Matrix.Identity(4), "A", 0, 0)
    frames = {"BF_HandleA": A @ skeleton.T(skeleton.PIN_A), "BF_Blade": blade_f @ skeleton.T(skeleton.PIN_A),
              "BF_HandleB": B @ skeleton.T(skeleton.PIN_B), "BF_Latch": B @ skeleton.T(skeleton.LATCH_PIVOT)}
    by = {}
    for o in objs:
        bone = spec.mesh_bone(o.name)
        o.data.transform(Matrix.Scale(spec.KNIFE_SCALE, 4))
        o.matrix_world = frames[bone]
        by[bone] = o

    old = {m for o in objs for m in o.data.materials if m}
    blade_frost = mat_frost("Ice_BF_BladeFrost", (0.94, 0.98, 1.0), (0.62, 0.8, 0.97), (0.3, 0.58, 0.95),
                            scale=7.0, cell=16.0, rough=(0.12, 0.3), metal=0.15, coat=0.7, bump=0.12, facet=0.22)
    edge = mat_metal("Ice_BF_EdgeSteel", (0.78, 0.88, 0.98), (0.92, 0.97, 1.0), (0.08, 0.16), 12.0)
    silver = mat_metal("Ice_BF_HandleSilver", (0.78, 0.82, 0.88), (0.93, 0.95, 0.98), (0.18, 0.32), 9.0)
    screws = mat_metal("Ice_BF_ScrewSteel", (0.25, 0.45, 0.75), (0.45, 0.65, 0.9), (0.15, 0.25), 20.0)

    def setm(o, lst):
        for i in range(len(o.data.materials)):
            o.data.materials[i] = lst[min(i, len(lst) - 1)]
    setm(by["BF_Blade"], [blade_frost, edge, silver])
    setm(by["BF_HandleA"], [silver, screws])
    setm(by["BF_HandleB"], [silver, screws])
    setm(by["BF_Latch"], [silver])
    for m in old:
        if m.users == 0:
            bpy.data.materials.remove(m)
    for b, o in by.items():
        o["rbx_material"] = "Metal"
        o["bake"] = True
        o["rbx_color"] = (0.85, 0.93, 1.0) if b == "BF_Blade" else (0.88, 0.91, 0.95)
        if o.data.uv_layers and "UVMap" not in o.data.uv_layers:
            o.data.uv_layers[0].name = "UVMap"

    def wv(o):
        return [o.matrix_world @ v.co for v in o.data.vertices]

    # ---- crystals along the spine (rides on BF_Blade) -------------------------
    bv = wv(by["BF_Blade"])
    y_tip = max(v.y for v in bv)
    ice = Part("BF_Blade_Skin_Crystals", [M["glass"]], dict(P_GLASS), flat=True)
    nC = 7
    for k in range(nC):
        f = 0.2 + 0.6 * k / (nC - 1)
        y = f * y_tip
        sl = [v for v in bv if abs(v.y - y) < 0.025]
        if not sl:
            continue
        top = max(sl, key=lambda v: v.z)
        L = 0.07 + 0.09 * math.sin(math.pi * (f - 0.1) / 0.8)
        side = (-1) ** k * 0.25
        crystal(ice.bm, V(top.x, y, top.z - 0.012), V(side, -0.55, 1.0), L, 0.022, rng)
        if k % 2 == 0 and k < nC - 1:
            crystal(ice.bm, V(top.x, y + 0.04, top.z - 0.01), V(-side * 1.6, -0.3, 1.0), L * 0.55, 0.015, rng)
    MBL = frames["BF_Blade"]
    o_ice = ice.done(col, to_local=MBL.inverted())
    o_ice.matrix_world = MBL

    # ---- neon inlays on both outer faces of each handle -----------------------
    extra = [o_ice]
    neon_bf = mat_neon("Ice_BF_Neon")
    for bone in ("BF_HandleA", "BF_HandleB"):
        hv = wv(by[bone])
        y0, y1 = min(v.y for v in hv), max(v.y for v in hv)
        L = y1 - y0
        glow = Part(bone + "_Skin_Glow", [neon_bf], dict(P_NEON))
        n = 25
        for s in (1, -1):
            path = []
            for i in range(n):
                y = y0 + L * (0.2 + 0.42 * i / (n - 1))
                sl = [v for v in hv if abs(v.y - y) < 0.02] or hv
                zc = 0.5 * (max(v.z for v in sl) + min(v.z for v in sl))
                xs = max(v.x for v in sl) if s > 0 else min(v.x for v in sl)
                path.append(V(xs + s * 0.001, y, zc))
            w = [0.026] * n
            for c in (4, 12, 20):
                w[c - 1], w[c], w[c + 1] = 0.045, 0.07, 0.045
            w[0] = w[-1] = 0.006
            ribbon(glow.bm, path, w, 0.0045, V(s, 0, 0))
        Mh = frames[bone]
        og = glow.done(col, to_local=Mh.inverted())
        og.matrix_world = Mh
        extra.append(og)

    zt = max(v.z for v in bv)
    for preset, loc, kw in (("Frost", (0, 0.65 * y_tip, zt * 0.4), {}), ("Frost", (0, y_tip, 0.0), {"size": 0.6}),
                            ("Sparkle", (0, 0.5 * y_tip, zt + 0.06), {}), ("Sparkle", (0, -0.7, 0.0), {"rate": 0.5}),
                            ("IceGlow", (0, 0.35 * y_tip, 0.0), {})):
        vfx(col, preset, loc, **kw)
    return objs + extra


# =============================================================================
# Ice_Stand
# =============================================================================

def build_stand(M):
    N = "Ice_Stand"
    col = _collection("ITEM_" + N)
    rng = random.Random(5)
    neon = mat_neon(N + "_Neon", NEON, 8.0)
    sign_m = mat_frost("Ice_SignNavy", (0.12, 0.25, 0.55), (0.04, 0.1, 0.3), (0.3, 0.6, 1.0), scale=2.0, cell=3.0,
                       rough=(0.2, 0.35), coat=0.6, bump=0.1)
    base = Part(N + "_Base", [M["glacier"]], P_BAKE("SmoothPlastic", (0.35, 0.55, 0.75)))
    ped = Part(N + "_Pedestals", [M["frost"]], P_BAKE())
    snow = Part(N + "_Snow", [M["snow"]], P_BAKE("SmoothPlastic", (0.95, 0.97, 1.0)), smooth=60)
    trim = Part(N + "_Trim", [M["gold"]], P_BAKE("Metal", (1.0, 0.86, 0.58)))
    glow = Part(N + "_Glow", [neon], dict(P_NEON))
    ice = Part(N + "_Crystals", [M["glass"]], dict(P_GLASS), flat=True)

    def tier1(j, t, y, r, i):
        return y, r * (1 + 0.035 * pnoise(t, 1))
    lathe(base.bm, [(0.0, 0.0), (0.0, 4.75), (0.18, 4.95), (0.5, 4.8), (0.62, 4.5), (0.62, 0.0)], 14, RX90, 0, 0.0, tier1)
    lathe(base.bm, [(0.55, 0.0), (0.55, 3.55), (0.65, 3.7), (1.10, 3.62), (1.22, 3.45), (1.22, 0.0)], 6, RX90, 0)
    band(trim.bm, 1.16, 1.25, 3.38, 0.12, 6, RX90)

    # snow ring on the lower ledge (follows the irregular rock edge) + drifts
    def snowfn(j, t, y, r, i):
        rr = r * (1 + 0.035 * pnoise(t, 1)) if i >= 3 else r
        yy = y + (0.06 * pnoise(t * 3, 7) if 1 <= i <= 4 else 0.0)
        return yy, rr
    lathe(snow.bm, [(0.56, 3.55), (0.74, 3.62), (0.82, 3.95), (0.78, 4.35), (0.68, 4.6), (0.56, 4.62)], 64, RX90,
          0, 0.0, snowfn, closed=True)
    for k in range(11):
        a = math.radians(-60 + k * 30 + rng.uniform(-8, 8))
        if abs(math.degrees(a) + 90) < 30:
            continue
        r = rng.uniform(3.9, 4.3)
        R, h = rng.uniform(0.3, 0.55), rng.uniform(0.15, 0.3)
        lathe(snow.bm, [(0.0, 0.0), (0.0, R), (h * 0.45, R * 0.82), (h * 0.8, R * 0.45), (h, 0.0)], 12,
              T(math.cos(a) * r, math.sin(a) * r, 0.68) @ RX90)

    # central + side pedestals with gold bands and glowing rings
    def pedestal(x, y, z0, z1, r, ringr):
        Mp = T(x, y, 0) @ RX90
        lathe(ped.bm, [(z0, 0.0), (z0, r * 1.1), (z0 + 0.15, r * 0.95), (z1 - 0.3, r * 0.8), (z1 - 0.15, r * 1.0),
                       (z1, r * 1.15), (z1, 0.0)], 6, Mp)
        band(trim.bm, z0 + 0.05, z0 + 0.16, r * 0.93, 0.07, 6, Mp)
        band(trim.bm, z1 - 0.1, z1 + 0.02, r * 1.1, 0.08, 6, Mp)
        band(glow.bm, z1 + 0.0, z1 + 0.04, ringr * 0.86, ringr * 0.14, 40, Mp)
        for k in range(6):
            a = k * math.pi / 3 + math.pi / 6
            c = V(x + math.cos(a) * r * 0.745, y - math.sin(a) * r * 0.745, (z0 + z1) * 0.5)
            ribbon(glow.bm, [c + V(0, 0, -0.25), c, c + V(0, 0, 0.25)], [0.02, 0.09, 0.02], 0.02,
                   V(math.cos(a), -math.sin(a), 0))
    pedestal(0.0, 0.3, 1.2, 2.7, 0.85, 0.75)
    pedestal(-2.35, -1.55, 1.2, 2.3, 0.55, 0.45)
    pedestal(2.35, -1.55, 1.2, 2.3, 0.55, 0.45)

    # magic circle on the platform top + runes on the 6 platform faces
    band(glow.bm, 1.22, 1.25, 2.92, 0.1, 64, RX90)
    band(glow.bm, 1.22, 1.25, 1.95, 0.06, 64, RX90)
    for k in range(18):
        a = 2 * math.pi * k / 18
        c = V(math.cos(a) * 2.45, math.sin(a) * 2.45, 1.235)
        d = V(-math.sin(a), math.cos(a), 0)
        ribbon(glow.bm, [c - d * 0.16, c, c + d * 0.16], [0.02, 0.12, 0.02], 0.015, V(0, 0, 1))
    glyphs = (
        [[(0, -0.17), (0.11, 0), (0, 0.17), (-0.11, 0)]],
        [[(-0.13, -0.12), (0, 0.0), (0.13, -0.12), (0.13, 0.0), (0, 0.15), (-0.13, 0.0)]],
        [[(-0.025, -0.17), (0.025, -0.17), (0.025, 0.17), (-0.025, 0.17)],
         [(-0.15, 0.06), (-0.11, 0.09), (0.0, -0.01), (0.0, 0.05)], [(0.15, 0.06), (0.11, 0.09), (0.0, -0.01), (0.0, 0.05)]],
    )
    for f in range(6):
        a = -math.pi / 2 + f * math.pi / 3
        ap = 3.66 * math.cos(math.pi / 6) - 0.01
        Mr = Matrix.Rotation(a, 4, "Z")
        for g, u in enumerate((-1.0, 0.0, 1.0)):
            for poly in glyphs[(g + f) % 3]:
                slab(glow.bm, [(u + p[0], 0.88 + p[1]) for p in poly], ap - 0.02, ap + 0.035, 0.0, 0, Mr)

    # big ice crystals behind + small clusters on the ledge
    for x, y, L, R, lx, ly in ((0.0, 2.6, 5.6, 0.55, 0.0, 0.15), (-1.0, 2.4, 4.4, 0.45, -0.35, 0.15),
                               (1.1, 2.3, 4.6, 0.45, 0.35, 0.12), (-1.9, 1.9, 3.2, 0.38, -0.55, 0.1),
                               (2.0, 1.8, 3.4, 0.38, 0.55, 0.1), (-0.5, 2.9, 3.0, 0.3, -0.15, 0.3),
                               (0.6, 3.0, 2.6, 0.3, 0.2, 0.35), (-2.7, 1.0, 2.0, 0.3, -0.6, 0.0),
                               (2.8, 0.9, 2.2, 0.3, 0.6, 0.0)):
        crystal(ice.bm, V(x, y, 1.0), V(lx, ly, 1.0), L, R, rng, 6)
    for deg in (30, 150, 205, 335, 245, 295):
        a = math.radians(deg)
        c = V(math.cos(a) * 4.15, math.sin(a) * 4.15, 0.55)
        out = V(math.cos(a), math.sin(a), 0)
        for k in range(3):
            j = V(rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), 0)
            crystal(ice.bm, c + j, out * rng.uniform(0.3, 0.7) + j + V(0, 0, 1), rng.uniform(0.5, 1.4),
                    rng.uniform(0.12, 0.22), rng, 6)

    # sign plate (faces -Y) with gold frame and posts
    SC = V(0.0, -4.15, 1.2)
    sign = Part(N + "_SignPlate", [sign_m], P_BAKE("SmoothPlastic", (0.06, 0.14, 0.34)), smooth=30)
    mu.box(sign.bm, (-1.75, -0.07, -0.42), (1.75, 0.07, 0.42))
    bmesh.ops.bevel(sign.bm, geom=list(sign.bm.edges), offset=0.025, segments=1, affect="EDGES")
    fy = SC.y - 0.075
    rect = [V(-1.7, fy, SC.z - 0.37), V(1.7, fy, SC.z - 0.37), V(1.7, fy, SC.z + 0.37), V(-1.7, fy, SC.z + 0.37)]
    tube(trim.bm, rect + [rect[0]], 0.032, 8)
    for s in (1, -1):
        tube(trim.bm, [V(s * 1.3, SC.y + 0.05, 0.6), V(s * 1.3, SC.y + 0.05, SC.z)], 0.05, 8)
        crystal(ice.bm, V(s * 1.72, SC.y, SC.z + 0.3), V(s * 0.8, 0, 1), 0.55, 0.1, rng)
        crystal(ice.bm, V(s * 1.85, SC.y + 0.1, 0.62), V(s * 0.5, -0.2, 1), 0.8, 0.14, rng)

    objs = [p.done(col) for p in (base, ped, snow, trim, glow, ice)]
    so = sign.done(col)
    so.location = SC
    objs.append(so)

    # mounts (empty +Y = weapon forward)
    mount(col, "MOUNT_Ice_Sniper", (-1.09, 0.3, 3.75), (0, 0, -90))
    a = math.radians(-110)
    fwd = V(-math.sin(a), math.cos(a), 0)
    mount(col, "MOUNT_Ice_Revolver", V(-2.35, -1.55, 2.95) - fwd * 0.6, (0, 0, -110))
    mount(col, "MOUNT_Ice_Butterfly", (2.35, -1.55, 4.05), (90, 0, -90))

    for preset, loc, kw in (("Snow", (0, 0, 7.5), {"size": 3.0}), ("Snow", (0, 2.5, 6.2), {"size": 2.0, "rate": 0.6}),
                            ("Frost", (3.1, 3.1, 0.9), {"size": 2.0}), ("Frost", (-3.1, 3.1, 0.9), {"size": 2.0}),
                            ("Frost", (-3.1, -3.1, 0.9), {"size": 2.0}), ("Frost", (3.1, -3.1, 0.9), {"size": 2.0}),
                            ("Sparkle", (0, 2.6, 4.0), {"size": 2.0}), ("Sparkle", (-1.9, 1.9, 2.8), {"size": 1.5}),
                            ("Sparkle", (2.0, 1.8, 2.8), {"size": 1.5}), ("IceGlow", (0, 0.3, 3.0), {"size": 2.0}),
                            ("IceGlow", (0, 2.4, 3.5), {"size": 2.0})):
        vfx(col, preset, loc, **kw)
    return objs


# =============================================================================
# build
# =============================================================================

def _unwrap(objs):
    vl = bpy.context.view_layer
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        me = o.data
        if "UVMap" in me.uv_layers:
            continue
        me.uv_layers.new(name="UVMap")
        for ob in vl.objects:
            ob.select_set(False)
        vl.objects.active = o
        o.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")


def tri_count(o):
    o.data.calc_loop_triangles()
    return len(o.data.loop_triangles)


def build():
    _MATS.clear()
    M = _materials()
    build_sniper(M)
    build_revolver(M)
    build_butterfly(M)
    build_stand(M)
    for item in ITEMS:
        col = bpy.data.collections["ITEM_" + item]
        meshes = [o for o in col.objects if o.type == "MESH"]
        _unwrap([o for o in meshes if o.get("bake")])
        counts = {o.name: tri_count(o) for o in meshes}
        print(f"[ice] {item}: {sum(counts.values())} tris  " + ", ".join(f"{k}={v}" for k, v in counts.items()))


# =============================================================================
# showcase (EEVEE turntables + particle VFX)
# =============================================================================

def _emit_mat(name, color, strength):
    m = mat_neon(name, color, strength)
    return m


def _show_assets():
    col = bpy.data.collections.get("ICE_SHOW_ASSETS") or bpy.data.collections.new("ICE_SHOW_ASSETS")
    out = {}

    def mk(name, bm, mat, smooth=True):
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        if smooth:
            me.shade_smooth()
        o = bpy.data.objects.new(name, me)
        o.location = (0, 0, -500)
        me.materials.append(mat)
        col.objects.link(o)
        return o
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    out["Snow"] = mk("ICE_FX_Flake", bm, _emit_mat("ICE_FX_FlakeMat", (0.85, 0.93, 1.0), 3.0), False)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    m, t = _mat("ICE_FX_MistMat", (0.7, 0.85, 1.0))
    lw = t.n("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    a = t.math("MULTIPLY", t.math("POWER", t.math("SUBTRACT", 1.0, lw.outputs["Facing"], clamp=True), 3.0), 0.09)
    tr, em, mix = t.n("ShaderNodeBsdfTransparent"), t.n("ShaderNodeEmission"), t.n("ShaderNodeMixShader")
    em.inputs["Color"].default_value = (0.62, 0.84, 1.0, 1)
    em.inputs["Strength"].default_value = 0.7
    t.put(mix.inputs[0], a)
    t.nt.links.new(tr.outputs[0], mix.inputs[1])
    t.nt.links.new(em.outputs[0], mix.inputs[2])
    o = t.n("ShaderNodeOutputMaterial")
    t.nt.links.new(mix.outputs[0], o.inputs["Surface"])
    _set(m, "surface_render_method", "BLENDED")
    _set(m, "blend_method", "BLEND")
    out["Frost"] = mk("ICE_FX_Mist", bm, m)
    bm = bmesh.new()
    d = [(0, -1), (0.1, 0), (0, 1), (-0.1, 0)]
    slab(bm, d, -0.02, 0.02)
    slab(bm, [(p[1], p[0]) for p in d], -0.02, 0.02)
    slab(bm, d, -0.02, 0.02, M=Matrix.Rotation(math.pi / 2, 4, "Z"))
    out["Sparkle"] = mk("ICE_FX_Star", bm, _emit_mat("ICE_FX_StarMat", (0.75, 0.92, 1.0), 40.0), False)
    return col, out


def _particles(em, kind, S, rate, frames, seed):
    ps_set = bpy.data.particles.new(em.name + "_PS")
    st = ps_set
    st.frame_start, st.frame_end = -90, frames
    st.emit_from = "VOLUME"
    st.render_type = "OBJECT"
    st.physics_type = "NEWTON"
    st.use_rotations = True
    st.rotation_mode = "NONE"
    st.rotation_factor_random = 1.0
    st.angular_velocity_mode = "RAND"
    st.normal_factor = 0.0
    if kind == "Snow":
        st.count = int(300 * rate)
        st.lifetime, st.lifetime_random = 150, 0.3
        st.factor_random = 0.12 * S
        st.effector_weights.gravity = 0.012
        st.brownian_factor = 0.12 * S
        st.drag_factor = 0.3
        st.particle_size, st.size_random = 0.018 * S ** 0.7, 0.6
        st.angular_velocity_factor = 2.0
    elif kind == "Frost":
        st.count = int(110 * rate)
        st.lifetime, st.lifetime_random = 70, 0.4
        st.factor_random = 0.1 * S
        st.object_align_factor = (0, 0, 0.06 * S)
        st.effector_weights.gravity = 0.0
        st.brownian_factor = 0.04 * S
        st.particle_size, st.size_random = 0.15 * S ** 0.8, 0.6
        st.angular_velocity_factor = 0.3
    else:  # Sparkle
        st.count = int(240 * rate)
        st.lifetime, st.lifetime_random = 10, 0.5
        st.factor_random = 0.0
        st.effector_weights.gravity = 0.0
        st.particle_size, st.size_random = 0.045 * S ** 0.8, 0.7
        st.angular_velocity_factor = 3.0
    em.modifiers.new("PS", "PARTICLE_SYSTEM")
    psys = em.particle_systems[0]
    psys.settings = st
    psys.seed = seed
    return st


def _neon_sockets():
    """(emission strength socket, base strength, pulse Hz) of every pulsing Neon material of the pack."""
    out, done = [], set()
    for item in ITEMS:
        col = bpy.data.collections.get("ITEM_" + item)
        for o in (col.all_objects if col else []):
            if o.type != "MESH" or o.get("rbx_material") != "Neon":
                continue
            hz = float(o.get("pulse", 0.0) or 0.0)
            for m in o.data.materials:
                if m is None or m.name in done or hz <= 0:
                    continue
                done.add(m.name)
                em = next((n for n in m.node_tree.nodes if n.type == "EMISSION"), None)
                if em is not None:
                    out.append((em.inputs["Strength"], float(m.get("ice_strength", 8.0)), hz))
    return out


def _look(cam, target):
    d = Vector(target) - cam.matrix_world.translation
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def _bbox(objs):
    pts = []
    for o in objs:
        if o.type == "MESH":
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def _setup_scene(sc, res, samples, frames):
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        if _set(sc.render, "engine", eng):
            break
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = 30
    sc.frame_start, sc.frame_end = 1, frames
    ee = sc.eevee
    _set(ee, "taa_render_samples", samples)
    _set(ee, "use_raytracing", True)
    _set(ee, "use_shadows", True)
    _set(ee, "use_bloom", True)
    sc.render.image_settings.file_format = "PNG"
    _set(sc.view_settings, "view_transform", "AgX")
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        if _set(sc.view_settings, "look", look):
            break
    w = bpy.data.worlds.get("ICE_SHOW_World")
    if w is None:
        w = bpy.data.worlds.new("ICE_SHOW_World")
        _set(w, "use_nodes", True)
        bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg is None:
            bg = w.node_tree.nodes.new("ShaderNodeBackground")
            out = w.node_tree.nodes.new("ShaderNodeOutputWorld")
            w.node_tree.links.new(bg.outputs[0], out.inputs[0])
        bg.inputs["Strength"].default_value = 1.0
        # dark backdrop for camera rays, soft cold studio environment for reflections
        nt = w.node_tree
        lp, mix = nt.nodes.new("ShaderNodeLightPath"), nt.nodes.new("ShaderNodeMixRGB")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        cr = nt.nodes.new("ShaderNodeValToRGB")
        nt.links.new(sep.outputs["Z"], cr.inputs[0])
        cr.color_ramp.elements[0].position, cr.color_ramp.elements[0].color = 0.0, (0.06, 0.08, 0.11, 1)
        cr.color_ramp.elements[1].position, cr.color_ramp.elements[1].color = 1.0, (0.14, 0.19, 0.26, 1)
        cr.color_ramp.elements.new(0.45).color = (0.26, 0.34, 0.46, 1)
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(cr.outputs["Color"], mix.inputs[1])
        mix.inputs[2].default_value = (0.002, 0.004, 0.009, 1)
        nt.links.new(mix.outputs[0], bg.inputs["Color"])
    sc.world = w
    _bloom(sc)


def _bloom(sc):
    try:
        if hasattr(sc, "compositing_node_group"):
            ng = bpy.data.node_groups.new("ICE_Bloom", "CompositorNodeTree")
            ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            out = ng.nodes.new("NodeGroupOutput")
            sc.compositing_node_group = ng
        else:
            sc.use_nodes = True
            ng = sc.node_tree
            ng.nodes.clear()
            out = ng.nodes.new("CompositorNodeComposite")
        rl = ng.nodes.new("CompositorNodeRLayers")
        rl.scene = sc
        gl = ng.nodes.new("CompositorNodeGlare")
        if not _set(gl, "glare_type", "BLOOM"):
            _set(gl, "glare_type", "FOG_GLOW")
        for k, v in (("Type", "Bloom"), ("Threshold", 1.4), ("Strength", 0.3), ("Size", 0.45), ("Quality", "Medium")):
            s = gl.inputs.get(k)
            if s is not None:
                try:
                    s.default_value = v
                except Exception:
                    pass
        _set(gl, "threshold", 1.4)
        _set(gl, "size", 6)
        _set(gl, "mix", -0.6)
        _set(gl, "quality", "MEDIUM")
        ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
        ng.links.new(gl.outputs["Image"], out.inputs[0])
        sc.render.use_compositing = True
    except Exception as e:  # bloom is a nicety
        print("[ice] bloom disabled:", e)


def _floor_mats():
    fm = bpy.data.materials.get("ICE_SHOW_Floor")
    if fm is None:
        fm, t = _mat("ICE_SHOW_Floor", (0.02, 0.03, 0.05))
        b = t.bsdf()
        P = t.coords()
        n1 = t.noise(P, 0.4, 3.0, 0.5).outputs["Fac"]
        t.put(b.inputs["Base Color"], t.ramp(n1, [(0.3, (0.002, 0.004, 0.009)), (0.7, (0.006, 0.012, 0.024))]))
        t.put(b.inputs["Roughness"], t.math("ADD", 0.3, t.math("MULTIPLY", n1, 0.3)))
    bdm = bpy.data.materials.get("ICE_SHOW_Backdrop")
    if bdm is None:
        bdm, t = _mat("ICE_SHOW_Backdrop", (0.02, 0.04, 0.1))
        sep = t.n("ShaderNodeSeparateXYZ")
        t.nt.links.new(t.coords(), sep.inputs[0])
        c = t.ramp(t.mrange(sep.outputs["Z"], -1.0, 1.0, 0.0, 1.0),
                   [(0.0, (0.0, 0.0, 0.0)), (0.42, (0.006, 0.018, 0.045)), (0.6, (0.003, 0.01, 0.026)), (1.0, (0.0, 0.0, 0.0))])
        e = t.n("ShaderNodeEmission")
        t.put(e.inputs["Color"], c)
        e.inputs["Strength"].default_value = 1.0
        o = t.n("ShaderNodeOutputMaterial")
        t.nt.links.new(e.outputs[0], o.inputs["Surface"])
    return fm, bdm


def _make_show_scene(item, assets, frames, res, samples):
    acol, inst = assets
    sc = bpy.data.scenes.new("ICE_SHOW_" + item)
    _setup_scene(sc, res, samples, frames)
    stu = bpy.data.collections.new("ICE_STUDIO_" + item)
    sc.collection.children.link(stu)
    sc.collection.children.link(acol)
    icol = bpy.data.collections["ITEM_" + item]
    sc.collection.children.link(icol)
    made = []

    def link(o):
        stu.objects.link(o)
        made.append(o)
        return o
    is_stand = item == "Ice_Stand"
    mn, mx = _bbox([o for o in icol.all_objects if o.type == "MESH"])
    size = mx - mn
    center = (mn + mx) * 0.5
    if is_stand:   # weapons on their mounts (collection instances) + title text
        for w in ITEMS[:3]:
            mt = bpy.data.objects.get("MOUNT_" + w)
            e = link(bpy.data.objects.new("ICE_INST_" + w, None))
            e.instance_type = "COLLECTION"
            e.instance_collection = bpy.data.collections["ITEM_" + w]
            e.matrix_world = mt.matrix_world.copy()
        cu = bpy.data.curves.new("ICE_TITLE", "FONT")
        cu.body = "ICE PACK"
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        cu.size = 0.56
        cu.extrude = 0.015
        _set(cu, "bevel_depth", 0.004)
        tx = link(bpy.data.objects.new("ICE_TITLE", cu))
        sp = bpy.data.objects["Ice_Stand_SignPlate"]
        tx.location = sp.matrix_world.translation + Vector((0, -0.09, -0.02))
        tx.rotation_euler = (math.pi / 2, 0, 0)
        cu.materials.append(_emit_mat("ICE_SHOW_TitleMat", (0.45, 0.85, 1.0), 7.0))
        center = Vector((0, 0.0, 2.45))
        dist, elev, lens = 16.5, math.radians(15), 40
        floor_z = 0.0
    else:
        L = max(size.x, size.y, size.z)
        dist, elev, lens = L * 2.3 + 0.8, math.radians(13), 50
        floor_z = mn.z - 0.12 * L - 0.15
    S = 3.0 if is_stand else 1.0

    # floor + rig (camera, lights, backdrop rotate together)
    fm, bdm = _floor_mats()
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=64, radius=dist * 4)
    me = bpy.data.meshes.new("ICE_SHOW_FloorMesh")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(fm)
    fl = link(bpy.data.objects.new("ICE_SHOW_Floor", me))
    fl.location = (center.x, center.y, floor_z - 0.002)
    rig = link(bpy.data.objects.new("ICE_SHOW_Rig", None))
    rig.location = center
    cd = bpy.data.cameras.new("ICE_SHOW_Cam")
    cd.lens = lens
    cd.clip_start, cd.clip_end = 0.05, dist * 20
    cam = link(bpy.data.objects.new("ICE_SHOW_Cam", cd))
    cam.parent = rig
    cam_off = Vector((0, -math.cos(elev), math.sin(elev))) * dist
    cam.location = cam_off
    cam.rotation_euler = (-cam_off).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    bdme = bpy.data.meshes.new("ICE_SHOW_BackdropMesh")
    bm = bmesh.new()
    mu.box(bm, (-1, -0.01, -1), (1, 0.01, 1))
    bm.to_mesh(bdme)
    bm.free()
    bdme.materials.append(bdm)
    bd = link(bpy.data.objects.new("ICE_SHOW_Backdrop", bdme))
    bd.parent = rig
    bd.location = (0, dist * 2.2, dist * 0.3)
    bd.scale = (dist * 3.0, 1, dist * 1.4)
    for name, loc, energy, color, size_ in (("Key", (-0.7, -0.8, 0.9), 11, (0.85, 0.92, 1.0), 0.5),
                                            ("RimL", (-1.0, 0.9, 0.35), 22, (0.3, 0.7, 1.0), 0.25),
                                            ("RimR", (1.0, 0.8, 0.6), 20, (0.6, 0.85, 1.0), 0.25),
                                            ("Top", (0.2, -0.2, 1.4), 3, (0.8, 0.9, 1.0), 1.0)):
        ld = bpy.data.lights.new("ICE_SHOW_" + name, "AREA")
        ld.energy = energy * dist * dist
        ld.color = color
        ld.size = size_ * dist
        ld.use_shadow = False      # shadows cost ~3x render time on software GL; glow look doesn't need them
        lo = link(bpy.data.objects.new("ICE_SHOW_" + name, ld))
        lo.parent = rig
        lo.location = Vector(loc) * dist
        lo.rotation_euler = (-Vector(loc)).to_track_quat("-Z", "Y").to_euler()

    # animation (applied explicitly per frame, see render_showcase): rig orbit + camera push-in
    neon = _neon_sockets()

    def apply(f):
        t = (f - 1) / max(frames - 1, 1)
        if is_stand:
            e = t * t * (3 - 2 * t)
            rig.rotation_euler = (0, 0, math.radians(-38 + 76 * e))
            cam.location = cam_off * (1.08 - 0.16 * e)
        else:
            rig.rotation_euler = (0, 0, math.radians(90 + 360 * (f - 1) / frames))
            cam.location = cam_off * (1.0 - 0.38 * math.sin(math.pi * t) ** 2)
        for sock, s0, hz in neon:
            sock.default_value = s0 * (0.975 + 0.475 * math.cos(2 * math.pi * hz * f / 30.0))
        sc.frame_set(f)

    # VFX: particle emitters + IceGlow lights at the VFX_ empties
    seed = 1
    for e in [o for o in icol.all_objects if o.type == "EMPTY" and o.name.startswith("VFX_")]:
        kind = e.name.split("_")[1]
        pos = e.matrix_world.translation
        sz = float(e.get("size", 1.0))
        rate = float(e.get("rate", 1.0))
        if kind == "IceGlow":
            ld = bpy.data.lights.new("ICE_SHOW_Glow", "POINT")
            ld.energy = 35.0 * S * S * sz
            ld.color = (0.35, 0.75, 1.0)
            _set(ld, "shadow_soft_size", 0.15 * S)
            ld.use_shadow = False
            lo = link(bpy.data.objects.new("ICE_SHOW_Glow", ld))
            lo.location = pos
            continue
        if kind not in inst:
            continue
        r = {"Snow": 0.4, "Frost": 0.16, "Sparkle": 0.22}[kind] * S * sz
        bm = bmesh.new()
        if kind == "Snow" and is_stand:
            mu.box(bm, (-r, -r, -0.3), (r, r, 0.3))
        else:
            bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r)
        me = bpy.data.meshes.new("ICE_EM_" + e.name)
        bm.to_mesh(me)
        bm.free()
        em = link(bpy.data.objects.new("ICE_EM_" + e.name, me))
        em.location = pos
        em.show_instancer_for_render = False
        em.show_instancer_for_viewport = False
        st = _particles(em, kind, S * sz ** 0.5, rate, frames, seed)
        st.instance_object = inst[kind]
        seed += 7
    return sc, made, apply


def _bake_particles(sc, frames):
    try:
        with bpy.context.temp_override(scene=sc, view_layer=sc.view_layers[0]):
            bpy.ops.ptcache.bake_all(bake=True)
    except Exception as e:
        print("[ice] ptcache bake failed, stepping frames:", e)
        for f in range(-90, frames + 1):
            sc.frame_set(f)


def render_showcase(out_dir, items=None, frames=150, res=(960, 540), samples=8, stills=None):
    """Render <out_dir>/<Item>.mp4 turntables (or PNG stills at frames `stills`)."""
    os.makedirs(out_dir, exist_ok=True)
    if bpy.data.collections.get("ITEM_Ice_Sniper") is None:
        build()
    items = list(items or ITEMS)
    assets = _show_assets()
    written = []
    for item in items:
        sc, made, apply = _make_show_scene(item, assets, frames, res, samples)
        _bake_particles(sc, frames)
        if stills:
            for f in stills:
                apply(f)
                sc.render.filepath = os.path.join(out_dir, f"{item}_f{f:03d}.png")
                bpy.ops.render.render(write_still=True, scene=sc.name)
                written.append(sc.render.filepath)
        else:
            fdir = os.path.join(out_dir, "_frames_" + item)
            shutil.rmtree(fdir, ignore_errors=True)
            os.makedirs(fdir)
            for f in range(1, frames + 1):
                apply(f)
                sc.render.filepath = os.path.join(fdir, f"f_{f:04d}.png")
                bpy.ops.render.render(write_still=True, scene=sc.name)
            mp4 = os.path.join(out_dir, item + ".mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", os.path.join(fdir, "f_%04d.png"),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", mp4], check=True)
            shutil.rmtree(fdir, ignore_errors=True)
            written.append(mp4)
            print("[ice] wrote", mp4)
        _cleanup(made)
        bpy.data.scenes.remove(sc)
    acol, inst = assets
    _cleanup(list(inst.values()))
    bpy.data.collections.remove(acol)
    return written


def _cleanup(objs):
    for o in objs:
        data = o.data
        psets = [ps.settings for ps in getattr(o, "particle_systems", [])]
        bpy.data.objects.remove(o, do_unlink=True)
        for st in psets:
            if st.users == 0:
                bpy.data.particles.remove(st)
        if data is None or data.users:
            continue
        for typ, coll in ((bpy.types.Mesh, bpy.data.meshes), (bpy.types.Camera, bpy.data.cameras),
                          (bpy.types.Light, bpy.data.lights), (bpy.types.Curve, bpy.data.curves)):
            if isinstance(data, typ):
                coll.remove(data)
                break
