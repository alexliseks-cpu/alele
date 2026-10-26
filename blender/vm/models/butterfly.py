"""BUTTERFLY knife (balisong) "Black Marble" - final model.

Objects (bone-local frames of spec.py, metres, identity transforms):
    BF_HandleA_Mesh   safe handle  (spine side, +Z), origin = pin A
    BF_HandleB_Mesh   bite handle  (edge side, -Z), origin = pin B, carries the latch pin
    BF_Blade_Mesh     blade + tang + kicker hook + the two pivot pins, origin = pin A
    BF_Latch_Mesh     latch, origin = spec.BF_LATCH_PIVOT, swings about local X

Everything is designed in MILLIMETRES in the knife frame (y along the knife towards
the tip, z = spine up, x = flat normal) and converted to metres / bone frames at the
very end (to3d mappers).

Curved handles that still close correctly
-----------------------------------------
Both handles meet along the curve z = F(y) of the open knife (handle A occupies
F(y)..F(y)+W, handle B F(y)-W..F(y); both pins sit in the middle of the handle
width).  Rotating a handle 180 deg about its own pin maps the band at y onto the
band at -y mirrored, so the closed handles meet along -F(-y).  With F ODD
(F(-y) = -F(y)) the closed handles therefore meet face to face along the same
curve F continued over the blade (y > 0), and the blade is designed around that
curve so it sits inside both channels when closed.  F(+-L) = 0 keeps the handle
ends (and the latch pivot) on the spec axis.

Deliberate deviation: the belly of the blade drops to EDGE_DROP = 14.1 mm below
the pin line (spec.BF_BLADE_HALF_WIDTH is 11.6) - the reference blade hangs well
below the handles.  This is still inside the closed (curved) handles with
clearance (checked: closed blade outline fully inside both handle outlines, no
triangle intersections in the open / closed / latch states); no code consumes
BF_BLADE_HALF_WIDTH.  The tang hook (kicker) sticks out of the handles in both
states, like the reference.  Pins, pivot, handle length / front, tang back, blade
length and the latch pivot are exactly as in spec.py.

Construction: every flat part (blade, handle side liners, web, latch) is a 2D
outline (+ holes) triangulated with a constrained Delaunay triangulation (the grind
lines are constraint edges so they stay crisp), extruded with per-vertex thickness
(blade grinds, distal taper) and rounded / chamfered rims.  Shading uses
face-area weighted custom normals (flats stay flat, round-overs read round).
Materials are Principled BSDF with procedural detail on GENERATED coordinates
mapped back to metric object space (invariant to the builder's KNIFE_SCALE).
"""

import math

import bmesh
import bpy
from mathutils import Vector
from mathutils import geometry as mgeo

from .. import spec
from .. import mesh_utils as mu

MM = 0.001
L_H = spec.BF_HANDLE_LEN / MM            # 130   handle length (pin -> end)
W_H = spec.BF_HANDLE_WIDTH / MM          # 12.4  handle width (Z)
T_H = spec.BF_HANDLE_THICK / MM          # 13.6  handle thickness (X)
C_W = spec.BF_CHANNEL_WIDTH / MM         # 3.8   channel width
PIN = spec.BF_PIN_Z / MM                 # 6.2
FRONT = spec.BF_HANDLE_FRONT / MM        # 7.5
TANG_BACK = spec.BF_TANG_BACK / MM       # 8.5
BLADE_LEN = spec.BF_BLADE_LEN / MM       # 110
HALF_W = spec.BF_BLADE_HALF_WIDTH / MM   # 11.6
BLADE_T = spec.BF_BLADE_THICK / MM       # 3.0
LATCH_P = Vector(spec.BF_LATCH_PIVOT) / MM

BOW = 6.5                                # handle bow (sagitta, mm) - see module doc
_BOW_K = 4.0 * BOW / (L_H * L_H)
GAP = 0.05                               # half gap between the two handles (mm)
Y_TANG = 9.0                             # tang (satin steel) / blade (marble) boundary


def F(y):
    """Meeting curve of the handles (odd, F(0)=F'(0)=0, F(+-L)=0), mm -> mm."""
    return _BOW_K * y * (abs(y) - L_H * (1.0 - math.exp(-(y / 30.0) ** 2)))


# ----------------------------------------------------------------------------
# small math helpers
# ----------------------------------------------------------------------------
def v2(a, b):
    return Vector((float(a), float(b)))


def smoothstep(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def bump(t, t0, tp, t1):
    return smoothstep(t0, tp, t) * (1.0 - smoothstep(tp, t1, t))


def inside(p, poly):
    """even-odd point in polygon (2D)."""
    x, y = p.x, p.y
    c = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i].x, poly[i].y
        xj, yj = poly[j].x, poly[j].y
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                c = not c
        j = i
    return c


def signed_area(poly):
    a = 0.0
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        a += p.x * q.y - q.x * p.y
    return 0.5 * a


# ----------------------------------------------------------------------------
# 2D curves
# ----------------------------------------------------------------------------
def catmull(pts, step=0.2):
    """Centripetal Catmull-Rom through pts (open), dense polyline incl. both ends."""
    P = [v2(*p) for p in pts]
    if len(P) == 2:
        return line(P[0], P[1], step)
    ext = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length ** 0.5, 1e-6)
        t2 = t1 + max((p2 - p1).length ** 0.5, 1e-6)
        t3 = t2 + max((p3 - p2).length ** 0.5, 1e-6)
        n = max(3, int((p2 - p1).length / step))
        for k in range(n):
            t = t1 + (t2 - t1) * k / n
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            out.append(b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1)))
    out.append(P[-1].copy())
    return out


def line(a, b, step=0.2):
    a, b = v2(*a), v2(*b)
    n = max(1, int((b - a).length / step))
    return [a.lerp(b, k / n) for k in range(n + 1)]


def arc(c, r, a0, a1, step=0.2):
    c = v2(*c)
    n = max(2, int(abs(a1 - a0) * r / step))
    return [c + v2(math.cos(a0 + (a1 - a0) * k / n), math.sin(a0 + (a1 - a0) * k / n)) * r for k in range(n + 1)]


class Path:
    """Closed dense polyline assembled from pieces, with named marks and corner fillets."""

    def __init__(self):
        self.pts = []
        self.marks = {}
        self.corners = {}

    def add(self, pts, mark=None, corner=None):
        pts = [v2(*p) for p in pts]
        if self.pts and (self.pts[-1] - pts[0]).length < 1e-6:
            pts = pts[1:]
        self.pts += pts
        if mark:
            self.marks[mark] = len(self.pts) - 1
        if corner:
            self.corners[len(self.pts) - 1] = corner
        return self

    def close(self):
        if (self.pts[-1] - self.pts[0]).length < 1e-6:
            last = len(self.pts) - 1
            self.pts.pop()
            for k, v in self.marks.items():
                if v == last:
                    self.marks[k] = 0
            if last in self.corners:
                self.corners[0] = self.corners.pop(last)
        return self

    def build(self, max_len=1.6, max_ang=7.0):
        pts, marks = round_corners(self.pts, self.corners, self.marks)
        return resample(pts, marks, max_len, max_ang)


def _walk(pts, i, dist, direction):
    """point at arc distance `dist` from pts[i] walking +-1 (closed), and index passed."""
    n = len(pts)
    acc = 0.0
    j = i
    while True:
        k = (j + direction) % n
        seg = (pts[k] - pts[j]).length
        if acc + seg >= dist:
            t = (dist - acc) / max(seg, 1e-12)
            return pts[j].lerp(pts[k], t), k
        acc += seg
        j = k
        if j == i:
            return pts[j], j


def round_corners(pts, corners, marks):
    """Replace each corner vertex by a quadratic Bezier between the points at arc
    distance d before / after it (tangent continuous)."""
    n = len(pts)
    replace = {}
    for i, d in corners.items():
        p0, k0 = _walk(pts, i, d, -1)
        p2, k2 = _walk(pts, i, d, +1)
        p1 = pts[i]
        m = max(4, int(2 * d / 0.12))
        bez = [p0 * (1 - t) ** 2 + p1 * (2 * t * (1 - t)) + p2 * t * t for t in (k / m for k in range(m + 1))]
        # indices strictly between p0 and p2 (cyclic) are removed
        rem = []
        j = (k0 + 1) % n
        while j != k2:
            rem.append(j)
            j = (j + 1) % n
        replace[i] = (set(rem), bez)
    removed = set()
    for i, (rem, _) in replace.items():
        removed |= rem
    out, new_marks = [], {}
    inv_marks = {}
    for k, v in marks.items():
        inv_marks.setdefault(v, []).append(k)
    for j in range(n):
        if j in replace:
            rem, bez = replace[j]
            mid = len(out) + len(bez) // 2
            out += bez
            for k in inv_marks.get(j, []):
                new_marks[k] = mid
            continue
        if j in removed:
            for k in inv_marks.get(j, []):
                new_marks[k] = len(out)  # nearest following point
            continue
        for k in inv_marks.get(j, []):
            new_marks[k] = len(out)
        out.append(pts[j])
    # drop near duplicates
    clean, remap = [], {}
    for j, p in enumerate(out):
        if clean and (clean[-1] - p).length < 1e-5:
            remap[j] = len(clean) - 1
            continue
        remap[j] = len(clean)
        clean.append(p)
    return clean, {k: min(remap[v], len(clean) - 1) for k, v in new_marks.items()}


def resample(pts, marks, max_len, max_ang, min_len=0.16):
    """Adaptive resampling of a closed dense polyline; marked points are kept."""
    n = len(pts)
    keep = set(marks.values())
    start = marks.get("start", 0)
    order = [(start + k) % n for k in range(n)]
    out_idx = [order[0]]
    acc_len, acc_ang = 0.0, 0.0
    lim = math.radians(max_ang)
    for a in range(1, n):
        j = order[a]
        jp = order[a - 1]
        jn = order[(a + 1) % n]
        acc_len += (pts[j] - pts[jp]).length
        d1 = pts[j] - pts[jp]
        d2 = pts[jn] - pts[j]
        if d1.length > 1e-9 and d2.length > 1e-9:
            acc_ang += abs(d1.angle_signed(d2, 0.0))
        if j in keep or ((acc_len >= max_len or acc_ang >= lim) and acc_len >= min_len):
            out_idx.append(j)
            acc_len, acc_ang = 0.0, 0.0
    pos = {j: i for i, j in enumerate(out_idx)}
    return [pts[j].copy() for j in out_idx], {k: pos[v] for k, v in marks.items()}


def loop_normals(pts):
    """Unit-ish miter normals pointing to the LEFT of the loop direction (material
    side for CCW outlines and CW holes)."""
    n = len(pts)
    out = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (b - a).normalized()
        d2 = (c - b).normalized()
        n1 = v2(-d1.y, d1.x)
        n2 = v2(-d2.y, d2.x)
        m = n1 + n2
        if m.length < 1e-9:
            m = n1.copy()
        m.normalize()
        out.append(m * (1.0 / max(0.45, m.dot(n1))))
    return out


def stadium(y0, y1, uc, hw, ccw=True, step=0.5):
    """Rounded slot (stadium) from y0 to y1 (y0 > y1), centred at u = uc, half width hw."""
    ya, yb = max(y0, y1) - hw, min(y0, y1) + hw
    pts = arc((ya, uc), hw, -math.pi / 2, math.pi / 2, step)[:-1]
    pts += line((ya, uc + hw), (yb, uc + hw), 5.0)[:-1]
    pts += arc((yb, uc), hw, math.pi / 2, 1.5 * math.pi, step)[:-1]
    pts += line((yb, uc - hw), (ya, uc - hw), 5.0)[:-1]
    return pts if ccw else list(reversed(pts))


def round_rings(c, n, x_wall, x_face):
    """Ring spec of a rounded rim: [(offset, x)] from the outline (wall) to the face."""
    out = []
    for k in range(n + 1):
        th = 0.5 * math.pi * k / n
        out.append((c * (1.0 - math.cos(th)), x_wall + (x_face - x_wall) * math.sin(th)))
    return out


# ----------------------------------------------------------------------------
# solid plate builder (outline + holes -> closed shell)
# ----------------------------------------------------------------------------
PLATE_WARN = []


def cdt(loops, lines):
    verts, edges, owner = [], [], []
    for k, L in enumerate(loops):
        base = len(verts)
        verts += L
        owner += [("loop", k, i) for i in range(len(L))]
        edges += [(base + i, base + (i + 1) % len(L)) for i in range(len(L))]
    for k, P in enumerate(lines):
        base = len(verts)
        verts += P
        owner += [("line", k, i) for i in range(len(P))]
        edges += [(base + i, base + i + 1) for i in range(len(P) - 1)]
    res = mgeo.delaunay_2d_cdt(verts, edges, [], 0, 1e-6)
    ov, of, orig = res[0], res[2], res[3]
    vowner = []
    for i in range(len(ov)):
        o = [owner[j] for j in orig[i]] if orig[i] else []
        lo = [x for x in o if x[0] == "loop"]
        vowner.append(lo[0] if lo else (o[0] if o else None))
    tris = []
    for f in of:
        if len(f) != 3:
            continue
        a, b, c = (ov[i] for i in f)
        ar = (b - a).cross(c - a)
        if abs(ar) < 1e-9:
            continue
        cen = (a + b + c) / 3.0
        if not inside(cen, loops[0]) or any(inside(cen, h) for h in loops[1:]):
            continue
        tris.append(tuple(f) if ar > 0 else (f[0], f[2], f[1]))
    return ov, tris, vowner


def plate(bm, loops, top_rings, bot_rings, to3d, lines=(), line_x_top=None, line_x_bot=None,
          face_mat=None, rim_mat=None):
    """Closed shell from 2D loops (loops[0] outer CCW, others holes CW).

    top_rings[k][i] / bot_rings[k][i]: [(offset, x), ...] from the outline (ring 0,
    the side wall) inwards to the face boundary (last ring).  to3d(x, a, b) -> Vector.
    lines: interior constraint polylines (2D) of both faces, x from line_x_top/bot(p).
    face_mat(side, centroid) / rim_mat(k, i): material indices."""
    norms = [loop_normals(L) for L in loops]
    faces = []

    def mk_rings(rings):
        rv, r2 = [], []
        for k, L in enumerate(loops):
            nr = len(rings[k][0])
            rows, rows2 = [], []
            for r in range(nr):
                row, row2 = [], []
                for i, p in enumerate(L):
                    off, x = rings[k][i][r]
                    q = p + norms[k][i] * off
                    row.append(bm.verts.new(to3d(x, q.x, q.y)))
                    row2.append(q)
                rows.append(row)
                rows2.append(row2)
            rv.append(rows)
            r2.append(rows2)
        return rv, r2

    tv, t2 = mk_rings(top_rings)
    bv, b2 = mk_rings(bot_rings)

    def add(vs, mat):
        try:
            f = bm.faces.new(vs)
        except ValueError:
            return
        f.material_index = mat
        faces.append(f)

    for k, L in enumerate(loops):
        n = len(L)
        for i in range(n):
            j = (i + 1) % n
            m = rim_mat(k, i) if rim_mat else 0
            add((bv[k][0][i], bv[k][0][j], tv[k][0][j], tv[k][0][i]), m)      # side wall
            for rows in (tv[k], bv[k]):
                for r in range(len(rows) - 1):
                    add((rows[r][i], rows[r][j], rows[r + 1][j], rows[r + 1][i]), m)
    for side, rv, r2, lx in (("top", tv, t2, line_x_top), ("bot", bv, b2, line_x_bot)):
        bl = [r2[k][-1] for k in range(len(loops))]
        ov, tris, vowner = cdt(bl, list(lines))
        vmap = {}
        rings = top_rings if side == "top" else bot_rings
        for vi, o in enumerate(vowner):
            if o is not None and o[0] == "loop":
                vmap[vi] = rv[o[1]][-1][o[2]]
            elif o is not None and lx is not None:
                p = ov[vi]
                vmap[vi] = bm.verts.new(to3d(lx(p), p.x, p.y))
            else:   # constraint intersection (should not happen): x of the nearest boundary vertex
                p = ov[vi]
                best = min(((p - q).length, k, i) for k in range(len(bl)) for i, q in enumerate(bl[k]))
                PLATE_WARN.append(("cdt_intersection", tuple(p)))
                vmap[vi] = bm.verts.new(to3d(rings[best[1]][best[2]][-1][1], p.x, p.y))
        for t in tris:
            cen = (ov[t[0]] + ov[t[1]] + ov[t[2]]) / 3.0
            m = face_mat(side, cen) if face_mat else 0
            vs = [vmap[i] for i in t]
            add(vs if side == "top" else list(reversed(vs)), m)
    bmesh.ops.remove_doubles(bm, verts=list({v for f in faces for v in f.verts}), dist=1e-9)
    faces = [f for f in faces if f.is_valid]
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def cylinder(bm, c, axis, r, h0, h1, segs, mat, cham=0.0):
    """Closed cylinder around axis (unit 3D) through point c, from h0 to h1 (mm, knife frame)."""
    axis = Vector(axis).normalized()
    u = axis.orthogonal().normalized()
    w = axis.cross(u)
    prof = [(0.0, h0), (r - cham, h0), (r, h0 + cham), (r, h1 - cham), (r - cham, h1), (0.0, h1)] if cham > 0 \
        else [(0.0, h0), (r, h0), (r, h1), (0.0, h1)]
    return revolve(bm, c, axis, u, w, prof, segs, mat)


def revolve(bm, c, axis, u, w, prof, segs, mat, radius_fn=None):
    """Surface of revolution: prof = [(radius, height)], radius 0 = pole.  Faces
    oriented with the outside on the right of the profile direction when the
    profile runs from the bottom pole outward/up to the top pole."""
    c = Vector(c)
    rows = []
    for (r, h) in prof:
        if r <= 1e-9:
            rows.append(bm.verts.new(c + axis * h))
            continue
        row = []
        for j in range(segs):
            t = 2 * math.pi * j / segs
            rr = r * (radius_fn(t) if radius_fn else 1.0)
            row.append(bm.verts.new(c + axis * h + (u * math.cos(t) + w * math.sin(t)) * rr))
        rows.append(row)
    faces = []
    for a, b in zip(rows[:-1], rows[1:]):
        for j in range(segs):
            j2 = (j + 1) % segs
            if isinstance(a, list) and isinstance(b, list):
                vs = (a[j], a[j2], b[j2], b[j])
            elif isinstance(a, list):
                vs = (a[j], a[j2], b)
            else:
                vs = (a, b[j2], b[j])
            f = bm.faces.new(vs)
            f.material_index = mat
            faces.append(f)
    return faces


def torx_head(bm, c, axis, r, h, segs, mat, recess=0.42, depth=0.4, embed=0.35):
    """Pan head screw with a Torx (6 lobe) recess, all sizes in mm (knife/bone frame).
    c = point on the surface it sits on, axis = outward normal.  Closed shell (the
    base is embedded `embed` below the surface)."""
    axis = Vector(axis).normalized()
    u = Vector((0, 1, 0)) if abs(axis.y) < 0.9 else Vector((0, 0, 1))
    u = (u - axis * u.dot(axis)).normalized()
    w = axis.cross(u)
    ch = min(0.6 * h, 0.3 * r)
    rr = r * recess
    c = Vector(c)

    def ring(rad, hh, star=False):
        out = []
        for j in range(segs):
            t = 2 * math.pi * j / segs
            k = (0.80 + 0.20 * math.cos(6 * t)) if star else 1.0
            out.append(bm.verts.new((c + axis * hh + (u * math.cos(t) + w * math.sin(t)) * rad * k) * MM))
        return out
    rows = [ring(r, -embed), ring(r, h - ch), ring(r - ch * 0.45, h - ch * 0.2), ring(r - ch * 1.2, h),
            ring(rr + 0.5 * (r - ch * 1.2 - rr), h + 0.035 * r), ring(rr, h + 0.05 * r, True),
            ring(rr * 0.9, h + 0.05 * r - depth, True)]
    centre = bm.verts.new((c + axis * (h + 0.05 * r - depth - 0.04)) * MM)
    bottom = bm.verts.new((c - axis * embed) * MM)
    faces = []
    for a, b in zip(rows[:-1], rows[1:]):
        for j in range(segs):
            j2 = (j + 1) % segs
            faces.append(bm.faces.new((a[j], a[j2], b[j2], b[j])))
    for j in range(segs):
        j2 = (j + 1) % segs
        faces.append(bm.faces.new((rows[-1][j], rows[-1][j2], centre)))
        faces.append(bm.faces.new((rows[0][j2], rows[0][j], bottom)))
    for f in faces:
        f.material_index = mat
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


# ----------------------------------------------------------------------------
# blade
# ----------------------------------------------------------------------------
TIP = (BLADE_LEN + 0.3, 1.5)
HEEL = (13.7, -10.8)         # start of the cutting edge
HOOK_TIP = (-9.4, -19.7)
EDGE_DROP = 14.1             # deepest point of the belly below the pin line (see build report)
Y_STEP = 62.5                # spine step / start of the clip


def t_flat(y):
    """Blade thickness (distal taper), mm."""
    if y < 22.0:
        return BLADE_T
    t = lerp(BLADE_T, 2.35, min(1.0, (y - 22.0) / 63.0))
    return lerp(t, 0.35, smoothstep(85.0, TIP[0], y) ** 1.3)


def spine_z(y):
    """Spine follows the closed-handle curve, 10 mm above it (the closed channel
    floor of handle A is at F + 10.95)."""
    return F(y) + 10.0


def blade_outline():
    s1 = (Y_STEP, spine_z(Y_STEP))
    s2 = (Y_STEP + 1.2, s1[1] - 0.75)
    clip = []
    for k in range(1, 9):
        t = k / 9.0
        y = lerp(s2[0], TIP[0], t)
        clip.append((y, lerp(s2[1], TIP[1], t) - 0.5 * math.sin(math.pi * t)))    # slightly concave clip
    p = Path()
    p.add(catmull([TIP] + list(reversed(clip)) + [s2]), mark="clip_end", corner=0.55)
    p.add(line(s2, s1), mark="step", corner=0.5)
    spine = [s1] + [(y, spine_z(y)) for y in (55.0, 45.0, 35.0, 25.0, 18.0)]
    p.add(catmull(spine + [(12, 9.75), (6, 9.9), (2, 10.15), (-2, 10.0), (-5.2, 8.9), (-7.6, 6.6),
                           (-8.5, 3.2), (-8.5, -2.5), (-7.9, -6.0), (-6.7, -8.9), (-5.6, -10.6)]),
          mark="hook_in", corner=0.9)
    p.add(catmull([(-5.6, -10.6), (-5.5, -12.6), (-5.9, -14.6), (-6.9, -16.5), (-8.2, -18.2), HOOK_TIP]),
          mark="hook_tip", corner=0.85)
    p.add(catmull([HOOK_TIP, (-6.6, -18.9), (-4.3, -17.1), (-2.8, -14.8), (-2.1, -12.6), (-1.8, -11.45)]),
          mark="hook_out", corner=0.8)
    p.add(catmull([(-1.8, -11.45), (2, -11.3), (6, -11.0), (9.8, -10.75)]), mark="choil0", corner=0.4)
    p.add(catmull([(9.8, -10.75), (10.3, -10.0), (11.0, -9.6), (11.75, -9.5), (12.5, -9.6),
                   (13.2, -10.05), HEEL]), mark="heel", corner=0.4)
    e = EDGE_DROP
    p.add(catmull([HEEL, (20, -11.6), (28, -12.5), (36, -13.2), (45, -13.7), (55, -e + 0.1), (66, -e),
                   (76, -e + 0.05), (84, -e + 0.35), (90, -e + 0.95), (94.5, -e + 1.9), (98.5, -e + 3.3),
                   (102, -e + 5.1), (105, -e + 7.3), (107.4, -e + 9.7), (109.1, -e + 12.2), TIP]),
          mark="tip", corner=0.55)
    p.close()
    p.marks["start"] = p.marks["tip"]
    pts, marks = p.build(max_len=1.7, max_ang=7.5)
    s = marks["tip"]
    pts = pts[s:] + pts[:s]
    marks = {k: (v - s) % len(pts) for k, v in marks.items()}
    # exact points at y = Y_TANG (material boundary) on the spine and on the tang bottom
    pts, marks = _insert_y(pts, marks, Y_TANG, marks["step"], marks["hook_in"], "tang_top")
    pts, marks = _insert_y(pts, marks, Y_TANG, marks["hook_out"], marks["choil0"], "tang_bot")
    return pts, marks


def _insert_y(pts, marks, y, i0, i1, name):
    n = len(pts)
    i = i0
    while i != i1:
        j = (i + 1) % n
        a, b = pts[i], pts[j]
        if (a.x - y) * (b.x - y) <= 0 and abs(b.x - a.x) > 1e-9:
            t = (y - a.x) / (b.x - a.x)
            q = a.lerp(b, t)
            if (q - a).length < 0.15:
                pts[i] = v2(y, q.y)
                marks[name] = i
                return pts, marks
            if (q - b).length < 0.15:
                pts[j] = v2(y, q.y)
                marks[name] = j
                return pts, marks
            pts = pts[:j] + [q] + pts[j:]
            marks = {k: (v + 1 if v >= j else v) for k, v in marks.items()}
            marks[name] = j
            return pts, marks
        i = j
    raise ValueError("no crossing for " + name)


def build_blade(mats):
    O, mk = blade_outline()
    n = len(O)
    i_tip, i_clip, i_heel = 0, mk["clip_end"], mk["heel"]
    i_tt, i_tb = mk["tang_top"], mk["tang_bot"]
    # arc length along the loop
    s = [0.0]
    for i in range(1, n):
        s.append(s[-1] + (O[i] - O[i - 1]).length)
    s_total = s[-1] + (O[0] - O[-1]).length

    def kind(i):
        if i == 0:
            return "tip"
        if i <= i_clip:
            return "clip"
        if i >= i_heel:
            return "edge"
        return "body"

    # local blade width (distance to the opposite outline) for the grind heights
    top = [O[i] for i in range(0, mk["hook_in"])]
    bot = [O[i] for i in range(mk["hook_out"], n)] + [O[0]]

    def z_on(chain, y):
        best = None
        for a, b in zip(chain[:-1], chain[1:]):
            if (a.x - y) * (b.x - y) <= 0 and abs(b.x - a.x) > 1e-9:
                z = a.y + (b.y - a.y) * (y - a.x) / (b.x - a.x)
                best = z if best is None else best
        return best

    E_TH = 0.09          # half thickness of the cutting edge
    FALSE_TH = 0.32      # half thickness of the swedge (false edge)
    CH = 0.28            # rim chamfer
    H_MAX = 4.2          # primary bevel height
    HS_MAX = 1.9         # swedge height

    s_heel = s[i_heel]
    s_tip_e = s_total    # edge runs from heel to tip (end of loop)
    rings, hgt, chs = [], {}, []
    for i, p in enumerate(O):
        k = kind(i)
        tf = t_flat(p.x) * 0.5
        # smaller rim near the two sharp points so the inset loop never folds
        dtip = min((p - v2(*TIP)).length, (p - v2(*HOOK_TIP)).length)
        ch = lerp(0.05, CH, smoothstep(0.3, 3.5, dtip))
        chs.append(ch)
        if k in ("edge", "tip"):
            d = (s[i] - s_heel) if k == "edge" else (s_tip_e - s_heel)
            zt = z_on(top, p.x)
            width = (zt - p.y) if zt is not None else 0.0
            h = H_MAX * math.sin(0.5 * math.pi * min(1.0, d / 6.5)) ** 0.8 * \
                min(1.0, max(0.0, 0.42 * width / H_MAX))            # rounded plunge line
            h = min(h, 0.42 * width)
            hgt[i] = h
            w = lerp(tf - ch, E_TH, smoothstep(0.0, 3.0, d))
            xf = tf if h <= ch else min(tf, w + (tf - w) * ch / h)
        elif k == "clip":
            d = s[i_clip] - s[i]           # distance from the step along the clip
            zb = z_on(bot, p.x)
            width = (p.y - zb) if zb is not None else 0.0
            h = HS_MAX * smoothstep(0.0, 5.0, d) * min(1.0, max(0.0, 0.33 * width / HS_MAX))
            hgt[i] = h
            w = lerp(tf - ch, FALSE_TH, smoothstep(0.0, 5.0, d))
            w = lerp(w, E_TH, smoothstep(TIP[0] - 9.0, TIP[0], p.x))
            xf = tf if h <= ch else min(tf, w + (tf - w) * ch / h)
        else:
            w, xf = tf - ch, tf
        rings.append(round_rings(ch, 2, w, xf))
    rings[0] = round_rings(chs[0], 2, E_TH, max(E_TH, t_flat(O[0].x) * 0.5))
    norms = loop_normals(O)
    inner = [O[i] + norms[i] * chs[i] for i in range(n)]
    # grind line (primary bevel) and swedge line, endpoints on the face boundary
    # interior points only where the bevel is clearly wider than the rim; the lines end
    # on the face boundary at the first edge vertex after the last interior point
    g_idx = [i for i in range(i_heel + 1, n) if hgt.get(i, 0) - chs[i] > 0.4]
    g_end = min(g_idx[-1] + 1, n - 1)
    G = [inner[i_heel]] + [O[i] + norms[i] * hgt[i] for i in g_idx] + [inner[g_end]]
    s_idx = [i for i in range(1, i_clip) if hgt.get(i, 0) - chs[i] > 0.35]
    s_end = max(s_idx[0] - 1, 1)
    Sw = [inner[s_end]] + [O[i] + norms[i] * hgt[i] for i in s_idx] + [inner[i_clip]]
    tang = [inner[i_tt], inner[i_tb]]
    bevel_poly = inner[i_heel:g_end + 1] + list(reversed(G[1:-1]))

    def line_x(p):
        return t_flat(p.x) * 0.5

    def face_mat(side, c):
        if c.x < Y_TANG:
            return mats["tang"]
        if inside(c, bevel_poly):
            return mats["bevel"]
        return mats["marble"]

    def rim_mat(k, i):
        a, b = O[i], O[(i + 1) % n]
        if (a.x + b.x) * 0.5 < Y_TANG:
            return mats["tang"]
        if i >= i_heel:
            return mats["bevel"]
        return mats["marble"]

    def to3d(x, a, b):
        return Vector((x, a, b - PIN)) * MM

    bm = bmesh.new()
    bot_rings = [[[(o, -x) for (o, x) in r] for r in rings]]
    plate(bm, [O], [rings], bot_rings, to3d, lines=[G, Sw, tang], line_x_top=line_x,
          line_x_bot=lambda p: -line_x(p), face_mat=face_mat, rim_mat=rim_mat)
    # pivot pins through the tang (between the liners)
    for zp in (PIN, -PIN):
        cylinder(bm, Vector((0, 0, zp - PIN)) * MM, (1, 0, 0), 2.05 * MM, -1.86 * MM, 1.86 * MM, 16,
                 mats["tang"], cham=0.2 * MM)
    return bm


# ----------------------------------------------------------------------------
# handles
# ----------------------------------------------------------------------------
X_IN = C_W * 0.5      # 1.9  inner face of a liner
X_OUT = T_H * 0.5     # 6.8  outer face
SCREWS = (-31.0, -39.5, -113.5, -123.5)


def inset_out(y):     # waist on the outer side of the open handle (behind the pivot knob)
    return GAP + 2.0 * bump(-y, 0.0, 9.0, 42.0)


def inset_meet(y):    # waist on the meeting side
    return GAP + 1.2 * bump(-y, 0.0, 8.0, 34.0)


def handle_outline():
    """(y, u) outline, u = distance from the meeting curve (0) to the outer face (W)."""
    p = Path()
    yb = -L_H
    # meeting side, butt -> pivot
    bot = [v2(y, inset_meet(y)) for y in [yb + 3.0 + k * (abs(yb + 3.0) / 120.0) for k in range(121)]]
    p.add(bot)
    # pivot knob: half ellipse in front of the pin
    b = PIN - GAP
    p.add([v2(FRONT * math.cos(t), PIN + b * math.sin(t)) for t in
           (-math.pi / 2 + math.pi * k / 48 for k in range(49))])
    top = [v2(y, W_H - inset_out(y)) for y in [-(k * (abs(yb + 3.0) / 120.0)) for k in range(121)]]
    p.add(top)
    # butt end
    p.add(line((yb + 3.0, W_H - GAP), (yb, W_H - GAP), 0.3), mark="c1", corner=None)
    p.add(line((yb, W_H - GAP), (yb, GAP), 0.3), mark="c2", corner=2.6)
    p.add(line((yb, GAP), (yb + 3.0, GAP), 0.3))
    p.corners[p.marks["c1"]] = 2.6
    p.close()
    pts, marks = p.build(max_len=3.6, max_ang=9.0)
    if signed_area(pts) < 0:
        pts.reverse()
    return pts


def handle_slots():
    return [stadium(-44.0, -106.0, PIN, 2.3, ccw=False), stadium(-12.5, -24.0, PIN, 1.75, ccw=False)]


def handle_z(side, y, u):
    return F(y) + side * u


def build_handle(side, mats):
    """side = +1: handle A (spine side, pivot pin A), -1: handle B (edge side, latch)."""
    pin = PIN * side
    outline = handle_outline()
    slots = handle_slots()
    loops = [outline] + slots
    bm = bmesh.new()

    def mk_to3d(xs):
        def to3d(x, y, u):
            return Vector((xs * x, y, handle_z(side, y, u) - pin)) * MM
        return to3d

    def rings_for(c_out, n_out, c_in):
        return (round_rings(c_out, n_out, X_OUT - c_out, X_OUT), round_rings(c_in, 1, X_IN + c_in, X_IN))

    ro, ri = rings_for(0.95, 2, 0.3)
    so, si = rings_for(0.55, 2, 0.2)
    top = [[ro] * len(outline)] + [[so] * len(s_) for s_ in slots]
    bot = [[ri] * len(outline)] + [[si] * len(s_) for s_ in slots]
    for xs in (1.0, -1.0):
        plate(bm, loops, top, bot, mk_to3d(xs))
    # web (bottom of the U channel) on the meeting side, between the liners
    web = Path()
    web.add(line((-29.0, -2.15), (-29.0, 2.15), 0.4), mark="a", corner=None)
    web.add(line((-29.0, 2.15), (-95.0, 2.15), 2.0), mark="b")
    web.add(line((-95.0, 2.15), (-95.0, -2.15), 0.4), mark="c")
    web.add(line((-95.0, -2.15), (-29.0, -2.15), 2.0), mark="d")
    for k in "abcd":
        web.corners[web.marks[k]] = 1.2
    web.close()
    wpts, _ = web.build(max_len=4.0, max_ang=20.0)
    if signed_area(wpts) < 0:
        wpts.reverse()
    u0, u1 = 0.12, 1.45
    wr_t = [round_rings(0.25, 1, u1 - 0.25, u1)] * len(wpts)
    wr_b = [round_rings(0.25, 1, u0 + 0.25, u0)] * len(wpts)

    def web3d(t, y, x):     # follows the liners' meeting-side waist
        return Vector((x, y, handle_z(side, y, t + inset_meet(y) - GAP) - pin)) * MM
    plate(bm, [wpts], [wr_t], [wr_b], web3d)
    # screws: pivot screw + 2 pairs of liner screws per side; on B the last one is the latch pin
    for xs in (1.0, -1.0):
        ax = Vector((xs, 0, 0))
        torx_head(bm, Vector((xs * X_OUT, 0.0, 0.0)), ax, 3.9, 0.5, 24, 1, recess=0.36, depth=0.45, embed=0.3)
        for k, ys in enumerate(SCREWS):
            if side < 0 and k == 3:
                zc = LATCH_P.z - pin
                ys = LATCH_P.y
            else:
                zc = handle_z(side, ys, PIN) - pin
            torx_head(bm, Vector((xs * X_OUT, ys, zc)), ax, 1.75, 0.32, 12, 1, recess=0.5, depth=0.28,
                      embed=0.3)
    if side < 0:   # latch pin across the channel
        cylinder(bm, Vector((0, LATCH_P.y, LATCH_P.z - pin)) * MM, (1, 0, 0), 1.0 * MM, -2.1 * MM, 2.1 * MM,
                 12, 1)
    return bm


# ----------------------------------------------------------------------------
# latch
# ----------------------------------------------------------------------------
def build_latch(mats):
    r = 2.6
    a0 = math.pi + math.asin(1.1 / r)
    p = Path()
    ring = arc((0, 0), r, a0, a0 + 2 * math.pi - 2 * math.asin(1.1 / r), 0.25)
    p.add(ring, mark="j2", corner=0.5)
    p.add(line(ring[-1], (-19.6, 1.1), 1.0), mark="i1", corner=0.45)
    p.add(line((-19.6, 1.1), (-19.6, 3.4), 0.4), mark="o1", corner=0.8)
    p.add(line((-19.6, 3.4), (-22.0, 3.4), 0.4), mark="o2", corner=0.9)
    p.add(line((-22.0, 3.4), (-22.0, -3.4), 0.4), mark="o3", corner=0.9)
    p.add(line((-22.0, -3.4), (-19.6, -3.4), 0.4), mark="o4", corner=0.8)
    p.add(line((-19.6, -3.4), (-19.6, -1.1), 0.4), mark="i2", corner=0.45)
    p.add(line((-19.6, -1.1), ring[0], 1.0), mark="j1", corner=0.5)
    p.close()
    pts, _ = p.build(max_len=2.5, max_ang=13.0)
    if signed_area(pts) < 0:
        pts.reverse()
    hole = list(reversed(arc((0, 0), 1.15, 0.0, 2 * math.pi, 0.6)[:-1]))     # pin hole (CW)
    t = 1.0
    top = [[round_rings(0.25, 2, t - 0.25, t)] * len(pts), [round_rings(0.15, 1, t - 0.15, t)] * len(hole)]
    bot = [[round_rings(0.25, 2, -t + 0.25, -t)] * len(pts), [round_rings(0.15, 1, -t + 0.15, -t)] * len(hole)]
    bm = bmesh.new()
    plate(bm, [pts, hole], top, bot, lambda x, a, b: Vector((x, a, b)) * MM)
    return bm


# ----------------------------------------------------------------------------
# materials (Principled BSDF + procedural detail, GENERATED coords -> metres)
# ----------------------------------------------------------------------------
def _sock(node, ident):
    for s in node.inputs:
        if s.identifier == ident:
            return s
    raise KeyError(ident)


def _osock(node, ident):
    for s in node.outputs:
        if s.identifier == ident:
            return s
    raise KeyError(ident)


class _NT:
    def __init__(self, mat):
        self.nt = mat.node_tree
        self.nodes = self.nt.nodes
        self.links = self.nt.links
        self.x = -1400

    def new(self, typ, **props):
        n = self.nodes.new(typ)
        n.location = (self.x, 0)
        self.x += 160
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.links.new(a, b)

    def math(self, op, a, b=None, clamp=False):
        n = self.new("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        n = self.new("ShaderNodeVectorMath", operation=op)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (tuple, list)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        if scale is not None:
            n.inputs["Scale"].default_value = scale
        return n.outputs[0]

    def noise(self, vec, scale, detail=2.0, rough=0.5, dist=0.0, dims="3D"):
        n = self.new("ShaderNodeTexNoise", noise_dimensions=dims)
        self.link(vec, n.inputs["Vector"])
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        n.inputs["Distortion"].default_value = dist
        return n

    def ramp(self, fac, stops):
        n = self.new("ShaderNodeValToRGB")
        self.link(fac, n.inputs["Fac"])
        cr = n.color_ramp
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        for i, (pos, val) in enumerate(stops):
            el = cr.elements[0] if i == 0 else cr.elements.new(pos)
            el.position = pos
            col = val if isinstance(val, (tuple, list)) else (val, val, val)
            el.color = (*col, 1.0)
        return n.outputs["Color"]

    def mix_col(self, fac, a, b):
        n = self.new("ShaderNodeMix", data_type="RGBA")
        for ident, v in (("Factor_Float", fac), ("A_Color", a), ("B_Color", b)):
            s = _sock(n, ident)
            if isinstance(v, (tuple, list)):
                s.default_value = (*v, 1.0) if len(v) == 3 else v
            elif isinstance(v, (int, float)):
                s.default_value = v
            else:
                self.link(v, s)
        return _osock(n, "Result_Color")

    def map_range(self, v, a0, a1, b0, b1, clamp=True):
        n = self.new("ShaderNodeMapRange", clamp=clamp)
        self.link(v, n.inputs["Value"])
        n.inputs["From Min"].default_value = a0
        n.inputs["From Max"].default_value = a1
        n.inputs["To Min"].default_value = b0
        n.inputs["To Max"].default_value = b1
        return n.outputs["Result"]


def _new_material(name, obj):
    """Principled material whose procedural coordinates are metric object space,
    reconstructed from GENERATED coordinates (bbox-normalised -> unaffected by
    the builder's uniform KNIFE_SCALE)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = _NT(m)
    bsdf = nt.nodes.get("Principled BSDF")
    out = nt.nodes.get("Material Output")
    bsdf.location = (600, 0)
    out.location = (900, 0)
    mn = Vector([min(v.co[i] for v in obj.data.vertices) for i in range(3)])
    mx = Vector([max(v.co[i] for v in obj.data.vertices) for i in range(3)])
    tc = nt.new("ShaderNodeTexCoord")
    mp = nt.new("ShaderNodeMapping", vector_type="POINT")
    nt.link(tc.outputs["Generated"], mp.inputs["Vector"])
    mp.inputs["Scale"].default_value = mx - mn
    mp.inputs["Location"].default_value = mn
    return m, nt, bsdf, mp.outputs["Vector"]


def mat_handle_steel(obj, name):
    """Bead-blasted satin steel, a bit darker than raw steel."""
    m, nt, bsdf, P = _new_material(name, obj)
    grain = nt.noise(P, 3200.0, 2.0, 0.55)                      # bead blast grain
    blot = nt.noise(P, 60.0, 3.0, 0.55)                         # very soft tone variation
    tone = nt.map_range(blot.outputs["Fac"], 0.3, 0.7, 0.0, 1.0)
    col = nt.mix_col(tone, (0.092, 0.094, 0.1), (0.104, 0.106, 0.113))
    nt.link(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 1.0
    rough = nt.map_range(grain.outputs["Fac"], 0.3, 0.7, 0.52, 0.6)
    nt.link(rough, bsdf.inputs["Roughness"])
    bmp = nt.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.02
    bmp.inputs["Distance"].default_value = 0.00001
    nt.link(grain.outputs["Fac"], bmp.inputs["Height"])
    nt.link(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    m.diffuse_color = (0.12, 0.123, 0.13, 1)
    return m


def mat_dark_steel(obj, name):
    m, nt, bsdf, P = _new_material(name, obj)
    n = nt.noise(P, 1500.0, 2.0, 0.5)
    nt.link(nt.mix_col(n.outputs["Fac"], (0.03, 0.031, 0.034), (0.05, 0.051, 0.055)), bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 1.0
    nt.link(nt.map_range(n.outputs["Fac"], 0.3, 0.7, 0.3, 0.42), bsdf.inputs["Roughness"])
    m.diffuse_color = (0.04, 0.04, 0.045, 1)
    return m


def mat_blade(obj, name):
    """Three full Principled materials used on the blade object: marble / bevel / tang."""
    # ---- black marble: polished black with bold white swirls + faint grey wisps --
    mm, nt, bsdf, P = _new_material(name + "_Marble", obj)
    w1 = nt.noise(P, 24.0, 2.0, 0.55)                                    # swirl warp
    warp = nt.vmath("SUBTRACT", w1.outputs["Color"], (0.5, 0.5, 0.5))
    P2 = nt.vmath("ADD", P, nt.vmath("SCALE", warp, scale=0.028))
    w2 = nt.noise(P2, 70.0, 2.0, 0.5)                                    # small turbulence
    warp2 = nt.vmath("SUBTRACT", w2.outputs["Color"], (0.5, 0.5, 0.5))
    P3 = nt.vmath("ADD", P2, nt.vmath("SCALE", warp2, scale=0.004))
    wave = nt.new("ShaderNodeTexWave", wave_type="BANDS", bands_direction="DIAGONAL", wave_profile="SAW")
    nt.link(P3, wave.inputs["Vector"])
    wave.inputs["Scale"].default_value = 13.0
    wave.inputs["Distortion"].default_value = 2.6
    wave.inputs["Detail"].default_value = 2.0
    wave.inputs["Detail Scale"].default_value = 1.2
    wave.inputs["Detail Roughness"].default_value = 0.5
    bold = nt.ramp(wave.outputs["Fac"], [(0.0, 0.0), (0.8, 0.0), (0.88, 0.12), (0.935, 0.55), (0.965, 1.0),
                                         (1.0, 1.0)])
    gate = nt.noise(P, 11.0, 2.0, 0.5)                                   # some strokes fade out
    g = nt.map_range(gate.outputs["Fac"], 0.33, 0.55, 0.0, 1.0)
    bold_f = nt.math("MULTIPLY", bold, g)
    # second family of softer grey strokes (other phase / scale / direction)
    P4 = nt.vmath("ADD", nt.vmath("MULTIPLY", P3, (1.0, -1.0, 1.0)), (0.013, 0.031, 0.007))
    wave2 = nt.new("ShaderNodeTexWave", wave_type="BANDS", bands_direction="DIAGONAL", wave_profile="SAW")
    nt.link(P4, wave2.inputs["Vector"])
    wave2.inputs["Scale"].default_value = 19.0
    wave2.inputs["Distortion"].default_value = 3.2
    wave2.inputs["Detail"].default_value = 2.0
    wave2.inputs["Detail Roughness"].default_value = 0.5
    grey = nt.ramp(wave2.outputs["Fac"], [(0.0, 0.0), (0.84, 0.0), (0.93, 0.2), (0.975, 0.42), (1.0, 0.35)])
    g2 = nt.map_range(nt.noise(P, 16.0, 2.0, 0.5).outputs["Fac"], 0.4, 0.6, 0.0, 1.0)
    vein = nt.math("MAXIMUM", bold_f, nt.math("MULTIPLY", grey, g2))
    streak = nt.vmath("MULTIPLY", P3, (1.0, 0.25, 1.0))                  # dark grey streaks
    haze = nt.map_range(nt.noise(streak, 55.0, 4.0, 0.62).outputs["Fac"], 0.5, 0.8, 0.0, 0.09)
    vein = nt.math("ADD", vein, haze, clamp=True)
    col = nt.mix_col(vein, (0.003, 0.003, 0.0036), (0.86, 0.865, 0.88))
    nt.link(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.0
    nt.link(nt.map_range(vein, 0.0, 1.0, 0.14, 0.24), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    mm.diffuse_color = (0.03, 0.03, 0.035, 1)
    # ---- polished primary bevel ---------------------------------------------
    mb, nt, bsdf, P = _new_material(name + "_Bevel", obj)
    sc = nt.vmath("MULTIPLY", P, (1.0, 1.0, 0.12))             # faint grind lines across the edge
    n = nt.noise(sc, 500.0, 2.0, 0.45)
    nt.link(nt.mix_col(n.outputs["Fac"], (0.38, 0.385, 0.4), (0.41, 0.415, 0.43)), bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 1.0
    nt.link(nt.map_range(n.outputs["Fac"], 0.3, 0.7, 0.19, 0.24), bsdf.inputs["Roughness"])
    bmp = nt.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.01
    bmp.inputs["Distance"].default_value = 0.00002
    nt.link(n.outputs["Fac"], bmp.inputs["Height"])
    nt.link(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    mb.diffuse_color = (0.58, 0.59, 0.61, 1)
    # ---- dark satin tang / pins / kicker --------------------------------------
    mt, nt, bsdf, P = _new_material(name + "_Tang", obj)
    sc = nt.vmath("MULTIPLY", P, (1.0, 0.05, 1.0))             # brushed along the knife
    n = nt.noise(sc, 1200.0, 2.0, 0.5)
    nt.link(nt.mix_col(n.outputs["Fac"], (0.07, 0.071, 0.076), (0.095, 0.096, 0.102)), bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 1.0
    nt.link(nt.map_range(n.outputs["Fac"], 0.3, 0.7, 0.26, 0.38), bsdf.inputs["Roughness"])
    mt.diffuse_color = (0.08, 0.08, 0.085, 1)
    return mm, mb, mt


# ----------------------------------------------------------------------------
# finishing: object, UVs, weighted normals
# ----------------------------------------------------------------------------
def weighted_normals(obj, sharp_deg):
    """Face-area weighted custom normals; edges sharper than sharp_deg, boundary
    edges and material boundaries split the smoothing fans."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    lim = math.radians(sharp_deg)
    sharp = set()
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2 or lf[0].material_index != lf[1].material_index or \
                lf[0].normal.angle(lf[1].normal, 0.0) > lim:
            sharp.add(e.index)
    area = [f.calc_area() for f in bm.faces]
    group, acc = {}, {}
    for v in bm.verts:
        fs = [f.index for f in v.link_faces]
        par = {f: f for f in fs}

        def find(a):
            while par[a] != a:
                par[a] = par[par[a]]
                a = par[a]
            return a
        for e in v.link_edges:
            if e.index in sharp:
                continue
            ra, rb = find(e.link_faces[0].index), find(e.link_faces[1].index)
            if ra != rb:
                par[ra] = rb
        for f in v.link_faces:
            r = find(f.index)
            group[(v.index, f.index)] = r
            acc[(v.index, r)] = acc.get((v.index, r), Vector()) + f.normal * (area[f.index] + 1e-14)
    per_face = []
    for f in bm.faces:
        row = []
        for l in f.loops:
            nv = acc[(l.vert.index, group[(l.vert.index, f.index)])]
            row.append(nv.normalized() if nv.length > 1e-14 else f.normal.copy())
        per_face.append(row)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    normals = []
    for poly in me.polygons:
        normals += per_face[poly.index]
    me.normals_split_custom_set([tuple(n) for n in normals])


def uv_unwrap(obj):
    vl = bpy.context.view_layer
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
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


def finish(name, bm, tex_group, sharp_deg):
    bm.normal_update()
    obj = mu.obj_from_bm(name, bm, smooth=True)
    obj["tex_group"] = tex_group
    return obj


def build():
    # placeholders for material index layout; actual materials need the object bbox
    blade = finish("BF_Blade_Mesh", build_blade({"marble": 0, "bevel": 1, "tang": 2}), "blade", 12.0)
    ha = finish("BF_HandleA_Mesh", build_handle(+1, None), "handle", 50.0)
    hb = finish("BF_HandleB_Mesh", build_handle(-1, None), "handle", 50.0)
    la = finish("BF_Latch_Mesh", build_latch(None), "handle", 50.0)
    mm, mb, mt = mat_blade(blade, "BF_Blade")
    for m in (mm, mb, mt):
        blade.data.materials.append(m)
    for o, tag in ((ha, "BF_HandleA"), (hb, "BF_HandleB")):
        o.data.materials.append(mat_handle_steel(o, tag + "_Steel"))
        o.data.materials.append(mat_dark_steel(o, tag + "_Screws"))
    la.data.materials.append(mat_dark_steel(la, "BF_Latch_Steel"))
    for o, deg in ((blade, 12.0), (ha, 50.0), (hb, 50.0), (la, 50.0)):
        uv_unwrap(o)
        weighted_normals(o, deg)
    return [ha, hb, blade, la]
