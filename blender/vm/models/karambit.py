"""Karambit - final model (CS2 karambit, "Carbon Fiber" finish of the Roblox showcase).

Everything is one rigid knife on bone KR_Handle (spec.py knife frame, METRES):
origin = finger-ring centre, +X = ring axis / flat normal, +Y along the handle
towards the blade, +Z = spine, the hawkbill blade curves towards -Z.

Objects (identity transforms, all detail baked into mesh data):
  KR_Handle_Mesh        two carbon-fibre scales (rounded edges, finger grooves,
                        spine jimping) + six Torx screw heads       tex_group "handle"
  KR_Handle_Mesh_Blade  full tang (black coated steel, visible as a fine stripe
                        between the scales) + hawkbill blade with the satin
                        swedge / plunge grind, primary edge bevel and apex
                        micro-bevel                                  tex_group "blade"
  KR_Handle_Mesh_Ring   faceted octagonal steel finger ring with the tail spur
                                                                     tex_group "handle"

Geometry is authored in millimetres and scaled to metres at the end.
Materials are Principled BSDF setups driven only by GENERATED coordinates
(converted back to metres per object, so they survive the builder's uniform
KNIFE_SCALE data transform) - no UVs, no images.
"""

import math

import bmesh
import bpy
from mathutils import Vector

from .. import spec
from .. import mesh_utils as mu

# ----------------------------------------------------------------------------
# dimensions (mm) - straight from the contract
# ----------------------------------------------------------------------------
RING_RO = spec.KR_RING_OUTER_R * 1000.0        # outer octagon circumradius
RING_RI = spec.KR_RING_INNER_R * 1000.0        # inner octagon apothem (min hole radius)
RING_T = spec.KR_RING_THICK * 1000.0
H_START = spec.KR_HANDLE_START * 1000.0        # scales start here on the knife axis
H_END = spec.KR_HANDLE_END * 1000.0            # guard face crosses the axis here
H_T = spec.KR_HANDLE_THICK * 1000.0
B_T = spec.KR_BLADE_THICK * 1000.0
B_ARC = spec.KR_BLADE_ARC_LEN * 1000.0
B_TURN = math.radians(spec.KR_BLADE_CURVE_DEG)

TANG_HALF = B_T / 2.0                          # tang = blade stock
SCALE_IN = TANG_HALF                           # scales sit on the tang
SCALE_OUT = H_T / 2.0

# blade spine start (top of the guard face) and its initial heading
B_ANGLE0 = math.radians(-26.0)
B_T0 = Vector((math.cos(B_ANGLE0), math.sin(B_ANGLE0)))
B_N0 = Vector((math.sin(B_ANGLE0), -math.cos(B_ANGLE0)))      # towards the edge
_GUARD_SPINE_Z = 16.0
# place the spine start so the (slanted) guard face crosses Z=0 exactly at H_END
B0 = Vector((H_END, 0.0)) - B_N0 * (_GUARD_SPINE_Z / -B_N0.y)
GUARD_TOP = B0 - B_N0 * 1.2
# blade proportions were tuned for an 82 mm spine; they follow the contract if it changes
B_SIZE = (B_ARC / 82.0) ** 0.75
QUILLON = B0 + B_N0 * min(44.0, max(38.0, 25.5 * B_SIZE + 12.5))

SCREWS = [(25.0, 11.0), (57.0, 12.4), (86.0, 7.0)]
SCREW_R = 2.5

# per-vertex analytic normals of the part being built (BMVert -> Vector)
_VN = {}


# ----------------------------------------------------------------------------
# 2D curve helpers (mm, Vector((y, z)))
# ----------------------------------------------------------------------------
def _cr_point(p0, p1, p2, p3, t, alpha=0.5):
    def tj(ti, a, b):
        return ti + max((b - a).length, 1e-6) ** alpha
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    tt = t1 + (t2 - t1) * t
    a1 = p0 * ((t1 - tt) / (t1 - t0)) + p1 * ((tt - t0) / (t1 - t0))
    a2 = p1 * ((t2 - tt) / (t2 - t1)) + p2 * ((tt - t1) / (t2 - t1))
    a3 = p2 * ((t3 - tt) / (t3 - t2)) + p3 * ((tt - t2) / (t3 - t2))
    b1 = a1 * ((t2 - tt) / (t2 - t0)) + a2 * ((tt - t0) / (t2 - t0))
    b2 = a2 * ((t3 - tt) / (t3 - t1)) + a3 * ((tt - t1) / (t3 - t1))
    return b1 * ((t2 - tt) / (t2 - t1)) + b2 * ((tt - t1) / (t2 - t1))


def spline(pts, step=0.1):
    """Centripetal Catmull-Rom through pts (open), densely sampled."""
    p = [Vector(q) for q in pts]
    if len(p) == 2:
        return line(p[0], p[1], step)
    ext = [p[0] + (p[0] - p[1])] + p + [p[-1] + (p[-1] - p[-2])]
    out = []
    for i in range(1, len(ext) - 2):
        n = max(2, int(math.ceil((ext[i + 1] - ext[i]).length / step)))
        for k in range(n):
            out.append(_cr_point(ext[i - 1], ext[i], ext[i + 1], ext[i + 2], k / n))
    out.append(p[-1].copy())
    return out


def line(a, b, step=0.1):
    a, b = Vector(a), Vector(b)
    n = max(1, int(math.ceil((b - a).length / step)))
    return [a.lerp(b, k / n) for k in range(n + 1)]


def arc(c, r, a0, a1, step=0.1):
    c = Vector(c)
    n = max(2, int(math.ceil(abs(a1 - a0) * r / step)))
    return [c + Vector((math.cos(a0 + (a1 - a0) * k / n), math.sin(a0 + (a1 - a0) * k / n))) * r
            for k in range(n + 1)]


def jimping(y0, y1, z0, z1, n, depth, step=0.05):
    """Row of rounded notches cut downwards (-Z) into a spine running y0 -> y1."""
    out = []
    m = max(8, int(abs(y1 - y0) / step))
    for k in range(m + 1):
        t = k / m
        ph = (t * n) % 1.0
        # flat-topped tooth, rounded V notch in the middle of every pitch
        if 0.18 < ph < 0.82:
            q = (ph - 0.18) / 0.64
            g = math.sin(math.pi * q) ** 0.75
        else:
            g = 0.0
        out.append(Vector((y0 + (y1 - y0) * t, z0 + (z1 - z0) * t - depth * g)))
    return out


def _trim_head(pts, dist):
    acc = 0.0
    for i in range(1, len(pts)):
        seg = (pts[i] - pts[i - 1]).length
        if acc + seg >= dist:
            f = (dist - acc) / max(seg, 1e-9)
            return [pts[i - 1].lerp(pts[i], f)] + pts[i:]
        acc += seg
    return pts[-1:]


def _rdp(pts, tags, tol, max_len):
    """Douglas-Peucker on an open polyline, also splitting segments > max_len."""
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 - i0 < 2:
            continue
        a, b = pts[i0], pts[i1]
        ab = b - a
        L = ab.length
        best, bi = -1.0, -1
        for i in range(i0 + 1, i1):
            if L < 1e-9:
                d = (pts[i] - a).length
            else:
                d = abs(ab.x * (pts[i].y - a.y) - ab.y * (pts[i].x - a.x)) / L
            if d > best:
                best, bi = d, i
        if best > tol or L > max_len:
            if best <= tol:
                bi = (i0 + i1) // 2
            keep[bi] = True
            stack.append((i0, bi))
            stack.append((bi, i1))
    return [p for p, k in zip(pts, keep) if k], [t for t, k in zip(tags, keep) if k]


class Outline:
    """Closed CCW outline built from pieces; corners between pieces are blended
    (quadratic Bezier over `corner` mm on each side).  Every point carries a
    `cap` value = max allowed edge-rounding radius at that point."""

    def __init__(self):
        self.pieces = []

    def add(self, pts, cap, corner=0.0, ccap=None):
        self.pieces.append(dict(pts=[Vector(p) for p in pts], cap=cap, corner=corner,
                                ccap=cap if ccap is None else ccap))
        return self

    def build(self, tol=0.02, max_len=2.6):
        pcs = [dict(p) for p in self.pieces]
        n = len(pcs)
        segs = [list(p["pts"]) for p in pcs]
        tags = [[p["cap"]] * len(p["pts"]) for p in pcs]
        blends = []
        for i in range(n):
            j = (i - 1) % n          # piece ending at the corner
            t = pcs[i]["corner"]
            if t <= 0:
                blends.append(None)
                continue
            c = segs[i][0].copy()
            head = _trim_head(segs[i], t)
            tail = list(reversed(_trim_head(list(reversed(segs[j])), t)))
            p1, p2 = tail[-1], head[0]
            bz = []
            for k in range(1, 12):
                u = k / 12
                bz.append(p1 * (1 - u) ** 2 + c * (2 * u * (1 - u)) + p2 * u * u)
            segs[i] = head
            tags[i] = tags[i][len(tags[i]) - len(head):]
            segs[j] = tail
            tags[j] = tags[j][:len(tail)]
            blends.append(bz)
        pts, tg = [], []
        for i in range(n):
            if blends[i]:
                pts += blends[i]
                tg += [pcs[i]["ccap"]] * len(blends[i])
            pts += segs[i]
            tg += tags[i]
        # drop duplicates
        cp, ct = [pts[0]], [tg[0]]
        for p, t in zip(pts[1:], tg[1:]):
            if (p - cp[-1]).length > 0.02:
                cp.append(p)
                ct.append(t)
            else:
                ct[-1] = min(ct[-1], t)
        if (cp[-1] - cp[0]).length < 0.02:
            cp.pop()
            ct.pop()
        # simplify (open the loop at index 0, close it again afterwards)
        cp.append(cp[0])
        ct.append(ct[0])
        sp, st = _rdp(cp, ct, tol, max_len)
        sp.pop()
        st.pop()
        # caps of removed points are folded into the neighbours by the smoothing below
        return sp, _smooth_caps(sp, st, cp, ct)


def _smooth_caps(sp, st, dense, dtags, grow=0.55):
    """Per-vertex rounding radius: min over the dense outline of cap + grow*distance."""
    out = []
    for p in sp:
        best = 1e9
        for q, t in zip(dense, dtags):
            d = (p - q).length
            if d < 8.0:
                v = t + grow * d
                if v < best:
                    best = v
        out.append(best)
    return out


def inset_dirs(pts):
    """Miter directions (inward, scaled for constant offset) of a CCW loop."""
    n = len(pts)
    out = []
    for i in range(n):
        a, p, b = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (p - a).normalized()
        d2 = (b - p).normalized()
        n1 = Vector((-d1.y, d1.x))
        n2 = Vector((-d2.y, d2.x))
        m = n1 + n2
        if m.length < 1e-6:
            m = n1
        m.normalize()
        s = 1.0 / max(0.55, m.dot(n1))
        out.append(m * s)
    return out


def _seg_x(a1, a2, b1, b2):
    d = (a2.x - a1.x) * (b2.y - b1.y) - (a2.y - a1.y) * (b2.x - b1.x)
    if abs(d) < 1e-12:
        return False
    t = ((b1.x - a1.x) * (b2.y - b1.y) - (b1.y - a1.y) * (b2.x - b1.x)) / d
    u = ((b1.x - a1.x) * (a2.y - a1.y) - (b1.y - a1.y) * (a2.x - a1.x)) / d
    return 0.0 < t < 1.0 and 0.0 < u < 1.0


def safe_radii(loop, radii, window=30, iters=40):
    """Shrink per-vertex inset radii until the inset loop has no local self-intersections."""
    radii = list(radii)
    dirs = inset_dirs(loop)
    n = len(loop)
    for _ in range(iters):
        cap = [p + d * r for p, d, r in zip(loop, dirs, radii)]
        bad = set()
        for i in range(n):
            a1, a2 = cap[i], cap[(i + 1) % n]
            for k in range(2, window):
                j = (i + k) % n
                if (j + 1) % n == i:
                    break
                if _seg_x(a1, a2, cap[j], cap[(j + 1) % n]):
                    for m in range(i - 1, i + k + 3):
                        bad.add(m % n)
        if not bad:
            break
        for m in bad:
            radii[m] *= 0.75
    return radii


def signed_area(pts):
    return 0.5 * sum(pts[i - 1].x * pts[i].y - pts[i].x * pts[i - 1].y for i in range(len(pts)))


# ----------------------------------------------------------------------------
# bmesh builders (mm)
# ----------------------------------------------------------------------------
def fill_between(bm, loops, mat=0):
    """Planar cap bounded by one or more closed vertex loops (holes allowed)."""
    edges = []
    for lp in loops:
        n = len(lp)
        for i in range(n):
            e = bm.edges.get((lp[i], lp[(i + 1) % n]))
            if e is None:
                e = bm.edges.new((lp[i], lp[(i + 1) % n]))
            edges.append(e)
    res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges, normal=(1.0, 0.0, 0.0))
    faces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
    for f in faces:
        f.material_index = mat
    return faces


def _out3(d2, fx=0.0, fo=1.0):
    """3D normal from an inward 2D miter dir: fx * X + fo * outward."""
    o = -d2.normalized()
    v = Vector((fx, o.x * fo, o.y * fo))
    return v.normalized()


# ----------------------------------------------------------------------------
# outlines
# ----------------------------------------------------------------------------
def handle_outline(rear_r):
    """Scale / tang outline (mm, CCW).  rear_r: radius of the concave cut that
    hugs the ring at the butt (scales: H_START, tang: hidden inside the ring).
    Banana profile of the reference: the spine arches up over the middle of the
    grip, the belly carries three finger grooves and ends in a hooked quillon."""
    o = Outline()
    R = 1.8
    gt, q = GUARD_TOP, QUILLON
    # spine: guard top -> hump -> front jimping (thumb ramp) -> dip -> arch
    o.add(spline([gt, (106.9, 18.0), (105.3, 18.35), (104.0, 18.3)]), R, corner=1.1, ccap=0.85)
    o.add(jimping(104.0, 91.0, 18.3, 17.5, 7, 0.8), 0.32)
    o.add(spline([(91.0, 17.5), (88.5, 17.35), (84.0, 17.9), (76.0, 21.0), (66.0, 24.4),
                  (55.0, 26.4), (44.0, 27.2), (34.0, 26.9), (28.0, 26.0), (24.0, 25.0)]), R)
    # rear jimping where the spine starts to roll down towards the ring
    o.add(jimping(24.0, 12.6, 25.0, 22.1, 4, 1.15), 0.4)
    # rear: spine rolls over the ring top into a straight line parallel to the
    # ring's 135 deg flat (continued by the ring tail spur)
    c45 = RING_RO * math.cos(math.radians(22.5)) * math.sqrt(2) + 1.25
    zj = 19.4
    yj = zj - c45
    o.add(spline([(12.6, 22.1), (9.0, 21.2), (4.5, 20.1), (yj, zj)]), R)
    rc = Vector((-9.9, -9.9 + c45))
    o.add(line((yj, zj), rc), R, corner=3.2, ccap=R)
    a_s = math.atan2(rc.y, rc.x)
    a_e = math.radians(-34.0)
    pa = Vector((math.cos(a_s), math.sin(a_s))) * rear_r
    o.add(line(rc, pa), 0.6, corner=0.7, ccap=0.55)
    o.add(arc((0, 0), rear_r, a_s, a_e), 0.9, corner=0.5, ccap=0.6)
    pe = Vector((math.cos(a_e), math.sin(a_e))) * rear_r
    j = Vector((14.9, -8.2))
    o.add(line(pe, j), 0.6, corner=0.9, ccap=0.4)
    # belly: three finger grooves (middle / ring / little finger), ridges, quillon
    o.add(spline([j, (18.5, -5.6), (23.5, -2.6), (29.5, -3.4), (34.2, -5.15), (35.8, -5.4),
                  (37.6, -5.05), (43.0, -1.8), (51.0, 0.6), (57.5, -1.0), (61.8, -4.3),
                  (63.4, -4.6), (65.2, -4.2), (70.0, -1.8), (76.5, 0.4), (81.5, -0.6),
                  (84.6, -3.8), (86.4, -8.9), (87.9, -14.2), q]), R, corner=0.8, ccap=1.1)
    # guard face: straight, perpendicular to the blade's initial heading
    o.add(line(q, gt), R, corner=2.8, ccap=1.4)
    return o.build(tol=0.025, max_len=3.0)


def ring_outlines():
    """Outer (octagon + tail spur, CCW) and inner (octagon, CW) loops of the ring."""
    o = Outline()
    verts = [Vector((math.cos(math.radians(22.5 + 45 * k)), math.sin(math.radians(22.5 + 45 * k)))) * RING_RO
             for k in range(8)]
    d = (verts[3] - verts[2]).normalized()
    spur = verts[3] + d * 7.5
    poly = [verts[0], verts[1], verts[2], spur, verts[4], verts[5], verts[6], verts[7]]
    cor = [0.75, 0.75, 0.75, 0.6, 0.75, 0.75, 0.75, 0.75]
    for k in range(8):
        a, b = poly[k], poly[(k + 1) % 8]
        o.add(line(a, b), 0.9, corner=cor[k], ccap=0.9)
    outer, ocaps = o.build(tol=0.01, max_len=6.0)
    ap = RING_RI / math.cos(math.radians(22.5))
    iv = [Vector((math.cos(math.radians(22.5 + 45 * k)), math.sin(math.radians(22.5 + 45 * k)))) * ap
          for k in range(8)]
    oi = Outline()
    iv = list(reversed(iv))                  # CW
    for k in range(8):
        oi.add(line(iv[k], iv[(k + 1) % 8]), 0.9, corner=0.55, ccap=0.9)
    inner, icaps = oi.build(tol=0.01, max_len=6.0)
    return outer, ocaps, inner, icaps


# ----------------------------------------------------------------------------
# blade sweep
# ----------------------------------------------------------------------------
def _pchip(xs, ys):
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    dl = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = dl[0], dl[-1]
    for i in range(1, n - 1):
        if dl[i - 1] * dl[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / dl[i - 1] + w2 / dl[i])

    def f(x):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = max(k for k in range(n - 1) if xs[k] <= x)
        t = (x - xs[i]) / h[i]
        h00 = 2 * t ** 3 - 3 * t ** 2 + 1
        h10 = t ** 3 - 2 * t ** 2 + t
        h01 = -2 * t ** 3 + 3 * t ** 2
        h11 = t ** 3 - t ** 2
        return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]
    return f


# blade width (spine -> edge, mm) along the normalised spine length
BLADE_W = _pchip([0.0, 0.11, 0.22, 0.44, 0.66, 0.80, 0.92, 1.0],
                 [25.5, 23.8, 21.4, 16.4, 10.4, 5.9, 2.1, 0.0])
CURV_RATIO = 2.8          # curvature at the tip / at the guard (hawkbill hooks harder at the tip)


class Spine:
    def __init__(self):
        L = B_ARC
        self.k0 = B_TURN / (L * (1 + (CURV_RATIO - 1) / 2))
        self.n = 2000
        self.ds = L / self.n
        self.pts = [B0.copy()]
        p = B0.copy()
        for i in range(self.n):
            s = (i + 0.5) * self.ds
            a = self.angle(s)
            p = p + Vector((math.cos(a), math.sin(a))) * self.ds
            self.pts.append(p.copy())

    def angle(self, s):
        L = B_ARC
        s = max(0.0, s)
        return B_ANGLE0 - self.k0 * (s + (CURV_RATIO - 1) * s * s / (2 * L))

    def at(self, s):
        a = self.angle(s)
        t = Vector((math.cos(a), math.sin(a)))
        nrm = Vector((math.sin(a), -math.cos(a)))
        if s <= 0:
            return B0 + B_T0 * s, t, nrm
        f = min(s / self.ds, self.n - 1e-6)
        i = int(f)
        return self.pts[i].lerp(self.pts[i + 1], f - i), t, nrm


PLUNGE = 2.6


def blade_section(s):
    """Half cross-section (d from spine along N, half thickness h) at spine length s."""
    t = min(max(s / B_ARC, 0.0), 1.0)
    w = BLADE_W(t) * B_SIZE
    hb = TANG_HALF * (1.0 - 0.5 * t ** 1.25)
    flare = 1.0 if s <= 0 else max(0.0, 1.0 - s / PLUNGE)
    hm = hb * (0.88 + 0.12 * flare)
    hm = min(hm, 0.30 * w + 0.06)
    tf = min(max((t - 0.55) / 0.3, 0.0), 1.0)
    hsp = min((0.52 * (1 - tf) + 0.07 * tf), 0.5 * hm)
    dsp = min(1.0, 0.055 * w)
    dsw = min(max(0.34 * w, dsp + 0.05), 7.0)
    e = min(5.0, 0.24 * w)
    m = min(0.42, 0.035 * w + 0.03)
    hsl = hsp + 0.38 * (hm - hsp)
    hap = min(0.22, 0.5 * hm)
    # spine flat | rounded corner | black sliver | satin swedge | flat | edge bevel | apex micro-bevel
    cols = [(0.0, hsp), (0.3 * dsp, hsp + 0.62 * (hsl - hsp)), (dsp, hsl), (dsw, hm), (w - e, hm), (w - m, hap)]
    return w, cols


# material slots on the blade object
M_PRINT, M_STEEL, M_COAT = 0, 1, 2
_BAND_MAT = [M_COAT, M_COAT, M_STEEL, M_PRINT, M_PRINT, M_STEEL]


def build_blade(bm):
    sp = Spine()
    L = B_ARC
    ss = [-1.5, 0.0, PLUNGE]
    s = PLUNGE
    while s < L - 1.2:
        tt = s / L
        step = 1.35 if tt < 0.7 else (0.9 if tt < 0.9 else 0.5)
        s += step
        ss.append(min(s, L - 1.0))
    for extra in (L - 0.6, L - 0.3, L - 0.12):
        if extra > ss[-1] + 0.05:
            ss.append(extra)
    rows = []
    for s in ss:
        p, t, nrm = sp.at(s)
        w, cols = blade_section(s)
        half = [(d, h) for d, h in cols]
        loop = half + [(w, 0.0)] + [(d, -h) for d, h in reversed(half)]
        ring = []
        for d, h in loop:
            q = p + nrm * d
            ring.append(bm.verts.new((h, q.x, q.y)))
        rows.append((s, ring))
    tip_p, _, _ = sp.at(L)
    tip = bm.verts.new((0.0, tip_p.x, tip_p.y))
    nc = len(rows[0][1])          # 13
    sharp_cols = {2, 3, 4, 5, 6, 7, 8, 9, 10}          # facet lines (+apex)
    faces = []
    for (s0, ra), (s1, rb) in zip(rows[:-1], rows[1:]):
        plunge_band = s0 >= -1e-6 and s1 <= PLUNGE + 1e-6
        for j in range(nc):
            j2 = (j + 1) % nc
            f = bm.faces.new((ra[j], ra[j2], rb[j2], rb[j]))
            band = j if j < 6 else (11 - j if j < 12 else -1)
            if j == 12:
                mat = M_COAT
            else:
                mat = _BAND_MAT[band]
            if plunge_band and 2 <= j <= 9:
                mat = M_STEEL
            f.material_index = mat
            faces.append(f)
    last = rows[-1][1]
    for j in range(nc):
        j2 = (j + 1) % nc
        f = bm.faces.new((last[j], last[j2], tip))
        band = j if j < 6 else (11 - j if j < 12 else -1)
        f.material_index = M_COAT if j == 12 else _BAND_MAT[band]
    root = bm.faces.new(list(reversed(rows[0][1])))
    root.material_index = M_COAT
    bmesh.ops.triangulate(bm, faces=[root])
    # sharp facet lines
    bm.edges.ensure_lookup_table()
    for _, ring in rows:
        for j in sharp_cols:
            v = ring[j]
            for e in v.link_edges:
                o = e.other_vert(v)
                # longitudinal edges only (same column in neighbour rows)
                if o in _col_set(rows, j) or o is tip:
                    e.smooth = False
    for s, ring in rows:
        if abs(s - PLUNGE) < 1e-6 or abs(s) < 1e-6:
            for j in range(nc):
                if 1 <= j <= 11:
                    e = bm.edges.get((ring[j], ring[(j + 1) % nc]))
                    if e:
                        e.smooth = False
    return sp


_col_cache = {}


def _col_set(rows, j):
    key = (id(rows), j)
    if key not in _col_cache:
        _col_cache[key] = {r[j] for _, r in rows}
    return _col_cache[key]


# ----------------------------------------------------------------------------
# parts
# ----------------------------------------------------------------------------
def _loft(bm, loop, rows, vn=True):
    """Loft a closed (y, z) loop through cross-section rows.
    rows: [(inset_mm_per_vertex(list) | float, x_per_vertex(list) | float, (fx, fo) normal mix)].
    The analytic vertex normal is fx * X + fo * outward-outline-normal."""
    dirs = inset_dirs(loop)
    rings = []
    for ins, xs, nmix in rows:
        ring = []
        for i, p in enumerate(loop):
            d = ins[i] if isinstance(ins, (list, tuple)) else ins
            x = xs[i] if isinstance(xs, (list, tuple)) else xs
            q = p + dirs[i] * d
            v = bm.verts.new((x, q.x, q.y))
            if vn and nmix is not None:
                _VN[v] = _out3(dirs[i], nmix[0], nmix[1])
            ring.append(v)
        rings.append(ring)
    n = len(loop)
    faces = []
    for ra, rb in zip(rings[:-1], rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((ra[i], ra[j], rb[j], rb[i])))
    return rings, faces


def _round_rows(radii, x_face, x_dir, segs=2):
    """Rows of a quarter-round edge: from the face (x_face, inset = r) to the wall
    (x_face - x_dir * r, inset 0).  x_dir = +1 for a face looking along +X."""
    rows = []
    for k in range(segs + 1):
        ph = (math.pi / 2) * k / segs
        rows.append(([r * (1 - math.sin(ph)) for r in radii],
                     [x_face - x_dir * r * (1 - math.cos(ph)) for r in radii],
                     (x_dir * math.cos(ph), math.sin(ph))))
    return rows


def build_scale(bm, loop, radii, side):
    """One carbon-fibre scale on the +X (side=1) or -X (side=-1) face of the tang:
    quarter-round outer edge, small chamfer against the tang (fine V-groove)."""
    xi, xo = side * SCALE_IN, side * SCALE_OUT
    c = 0.25
    rows = _round_rows(radii, xo, side, segs=2)
    cc = [min(c, 0.7 * r) for r in radii]
    rows += [(0.0, [xi + side * q for q in cc], (0.0, 1.0)), (cc, xi, (-side * 0.7071, 0.7071))]
    rings, _ = _loft(bm, loop, rows)
    fill_between(bm, [rings[0]])
    fill_between(bm, [rings[-1]])


def build_screw(bm, y, z, side, segs=18):
    """Torx button-head screw sitting on the scale face (axis = X)."""
    x0 = side * SCALE_OUT

    def P(r, x, a):
        return (x0 + side * x, y + r * math.cos(a), z + r * math.sin(a))

    def star(a):
        return 1.18 + 0.24 * math.cos(6 * a)

    prof = [("c", SCREW_R, -0.25), ("c", SCREW_R, 0.16), ("c", SCREW_R - 0.28, 0.42),
            ("c", 1.85, 0.52), ("s", 1.0, 0.53), ("s", 0.86, -0.22)]
    rings = []
    for kind, r, x in prof:
        ring = []
        for k in range(segs):
            a = 2 * math.pi * k / segs
            rr = r if kind == "c" else r * star(a)
            ring.append(bm.verts.new(P(rr, x, a)))
        rings.append(ring)
    for ra, rb in zip(rings[:-1], rings[1:]):
        for k in range(segs):
            k2 = (k + 1) % segs
            bm.faces.new((ra[k], ra[k2], rb[k2], rb[k]))
    cb = bm.verts.new(P(0, -0.25, 0))
    cf = bm.verts.new(P(0, -0.34, 0))
    for k in range(segs):
        k2 = (k + 1) % segs
        bm.faces.new((rings[0][k2], rings[0][k], cb))
        bm.faces.new((rings[-1][k], rings[-1][k2], cf))
    faces = set()
    for r in rings:
        for v in r:
            faces.update(v.link_faces)
    for f in faces:
        f.material_index = 1
    # crisp recess rim / chamfer lines
    for ring in (rings[1], rings[3], rings[4]):
        for v in ring:
            for e in v.link_edges:
                e.smooth = False


def build_tang(bm, loop):
    """Full tang plate between the scales; only its chamfered edge shows."""
    h = TANG_HALF
    c = safe_radii(loop, [0.2] * len(loop))
    rows = [(c, h, (0.7071, 0.7071)), (0.0, [h - q for q in c], (0.0, 1.0)), (0.0, [-h + q for q in c], (0.0, 1.0)),
            (c, -h, (-0.7071, 0.7071))]
    rings, faces = _loft(bm, loop, rows)
    faces += fill_between(bm, [rings[0]]) + fill_between(bm, [rings[-1]])
    for f in faces:
        f.material_index = M_COAT


def build_ring(bm):
    """Faceted octagonal finger ring with the tail spur, rounded edges both faces."""
    outer, ocaps, inner, icaps = ring_outlines()
    R = 0.9
    half = RING_T / 2

    def rows_for(loop, caps):
        rr = safe_radii(loop, [min(R, c) for c in caps])
        top = _round_rows(rr, half, 1.0, segs=2)
        bot = list(reversed(_round_rows(rr, -half, -1.0, segs=2)))
        return top + bot

    ro, _ = _loft(bm, outer, rows_for(outer, ocaps))
    ri, _ = _loft(bm, inner, rows_for(inner, icaps))
    fill_between(bm, [ro[0], ri[0]])
    fill_between(bm, [ro[-1], ri[-1]])
    for lp in (ro[0], ri[0]):
        for v in lp:
            _VN[v] = Vector((1.0, 0.0, 0.0))
    for lp in (ro[-1], ri[-1]):
        for v in lp:
            _VN[v] = Vector((-1.0, 0.0, 0.0))


# ----------------------------------------------------------------------------
# materials (Principled BSDF, GENERATED coordinates converted to metres)
# ----------------------------------------------------------------------------
class NB:
    def __init__(self, name):
        old = bpy.data.materials.get(name)
        if old is not None:
            bpy.data.materials.remove(old)
        self.mat = bpy.data.materials.new(name)
        self.nt = self.mat.node_tree
        self.nt.nodes.clear()
        self.out = self.new("ShaderNodeOutputMaterial")
        self.bsdf = self.new("ShaderNodeBsdfPrincipled")
        self.link(self.bsdf.outputs[0], self.out.inputs["Surface"])
        self.tc = self.new("ShaderNodeTexCoord")

    def new(self, t, **kw):
        n = self.nt.nodes.new(t)
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def put(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.link(v, sock)
        elif v is not None:
            sock.default_value = v

    def m(self, op, a, b=None, c=None, clamp=False):
        n = self.new("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.put(n.inputs[0], a)
        if b is not None:
            self.put(n.inputs[1], b)
        if c is not None:
            self.put(n.inputs[2], c)
        return n.outputs[0]

    def v(self, op, a, b=None, c=None, out=0):
        n = self.new("ShaderNodeVectorMath", operation=op)
        self.put(n.inputs[0], a)
        if b is not None:
            self.put(n.inputs[1], b)
        if c is not None:
            self.put(n.inputs[2], c)
        return n.outputs[out]

    def sep(self, vec):
        n = self.new("ShaderNodeSeparateXYZ")
        self.link(vec, n.inputs[0])
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def comb(self, x, y, z):
        n = self.new("ShaderNodeCombineXYZ")
        for s, val in zip(n.inputs, (x, y, z)):
            self.put(s, val)
        return n.outputs[0]

    def noise(self, vec, scale, detail=2.0, rough=0.5, dist=0.0, lac=2.0):
        n = self.new("ShaderNodeTexNoise")
        n.noise_dimensions = "3D"
        self.put(n.inputs["Vector"], vec)
        self.put(n.inputs["Scale"], scale)
        self.put(n.inputs["Detail"], detail)
        self.put(n.inputs["Roughness"], rough)
        self.put(n.inputs["Lacunarity"], lac)
        self.put(n.inputs["Distortion"], dist)
        return n.outputs[0]

    def voronoi(self, vec, scale, feature="F1", rand=1.0):
        n = self.new("ShaderNodeTexVoronoi")
        n.voronoi_dimensions = "3D"
        n.feature = feature
        self.put(n.inputs["Vector"], vec)
        self.put(n.inputs["Scale"], scale)
        self.put(n.inputs["Randomness"], rand)
        return n.outputs["Distance"]

    def lerp(self, a, b, t):
        """a + (b - a) * t for constant floats a, b."""
        return self.m("MULTIPLY_ADD", t, b - a, a)

    def coords(self, bb_min, bb_size):
        """Knife-frame position in metres + scale factor of the mesh data now vs at build."""
        P = self.v("MULTIPLY_ADD", self.tc.outputs["Generated"], tuple(bb_size), tuple(bb_min))
        k = self.m("DIVIDE", self.v("LENGTH", self.tc.outputs["Object"], out=1),
                   self.m("MAXIMUM", self.v("LENGTH", P, out=1), 1e-6))
        return P, k

    def bump(self, height, dist, k, strength=1.0, normal=None):
        """Bump of `height` * `dist` metres.  The scale factor k multiplies the
        height (a linked Distance socket is not honoured by Cycles' bump)."""
        n = self.new("ShaderNodeBump")
        self.put(n.inputs["Strength"], strength)
        n.inputs["Distance"].default_value = dist
        self.put(n.inputs["Height"], self.m("MULTIPLY", height, k))
        if normal is not None:
            self.put(n.inputs["Normal"], normal)
        return n.outputs[0]

    def principled(self, base, metallic, rough, normal=None, tint=(1, 1, 1), spec_lvl=0.5):
        b = self.bsdf
        if isinstance(base, bpy.types.NodeSocket):
            self.link(self.v("MULTIPLY", self.comb(base, base, base), tuple(tint)), b.inputs["Base Color"])
        else:
            b.inputs["Base Color"].default_value = (base * tint[0], base * tint[1], base * tint[2], 1)
        self.put(b.inputs["Metallic"], metallic)
        self.put(b.inputs["Roughness"], rough)
        self.put(b.inputs["Specular IOR Level"], spec_lvl)
        if normal is not None:
            self.link(normal, b.inputs["Normal"])
        return self.mat


def twill(nb, u, v, fibre_scale=26.0):
    """2/2 twill weave in cell units.  Returns (warp 0/1, tow height 0..1, fibre streak 0..1)."""
    iu = nb.m("FLOOR", u)
    iv = nb.m("FLOOR", v)
    fu = nb.m("SUBTRACT", u, iu)
    fv = nb.m("SUBTRACT", v, iv)
    kk = nb.m("ADD", iu, iv)
    m4 = nb.m("SUBTRACT", kk, nb.m("MULTIPLY", nb.m("FLOOR", nb.m("MULTIPLY", kk, 0.25)), 4.0))
    warp = nb.m("LESS_THAN", m4, 1.5)
    across = nb.m("MULTIPLY_ADD", nb.m("SUBTRACT", fu, fv), warp, fv)
    along = nb.m("MULTIPLY_ADD", nb.m("SUBTRACT", fv, fu), warp, fu)
    # pillow across the tow, dip at the ends of each 2-cell float
    a2 = nb.m("SUBTRACT", nb.m("MULTIPLY", across, 2.0), 1.0)
    h_ac = nb.m("SUBTRACT", 1.0, nb.m("MULTIPLY", a2, a2), clamp=True)
    phase = nb.m("MULTIPLY", nb.m("ADD", nb.m("SUBTRACT", m4, nb.m("MULTIPLY", nb.m("SUBTRACT", 1.0, warp), 2.0)),
                                  along), 0.5)
    h_al = nb.m("SINE", nb.m("MULTIPLY", phase, math.pi), clamp=True)
    # smooth tow pillow (bounded slopes: no sparkle at the tow edges)
    h = nb.m("MULTIPLY", nb.m("MULTIPLY", h_ac, nb.m("SUBTRACT", 3.0, nb.m("MULTIPLY", h_ac, 2.0))),
             nb.lerp(0.7, 1.0, h_al))
    # fibre streaks running along the tow
    gu = nb.m("MULTIPLY_ADD", nb.m("SUBTRACT", u, v), warp, v)      # across coordinate (global)
    gv = nb.m("MULTIPLY_ADD", nb.m("SUBTRACT", v, u), warp, u)      # along coordinate
    fib = nb.noise(nb.comb(nb.m("MULTIPLY", gu, fibre_scale), nb.m("MULTIPLY", gv, 0.9),
                           nb.m("MULTIPLY", warp, 7.0)), 1.0, detail=3.0, rough=0.55)
    return warp, h, h_ac, fib


def mat_carbon(name, bb_min, bb_size, cell=0.0026, relief=0.00004, triplanar=True,
               vals=(0.009, 0.030), roughs=(0.56, 0.44)):
    """Black 2/2 twill carbon fibre.  relief: tow bump height (m, 0 = printed film)."""
    nb = NB(name)
    P, k = nb.coords(bb_min, bb_size)
    x, y, z = nb.sep(P)
    inv = 1.0 / cell
    # side faces (normal ~X): weave in the Y/Z plane
    wa, ha, haca, fa = twill(nb, nb.m("MULTIPLY", y, inv), nb.m("MULTIPLY", z, inv))
    if triplanar:
        nx, ny, nz = nb.sep(nb.tc.outputs["Normal"])
        # edge faces: weave in the plane of X and the outline tangent
        l = nb.m("MAXIMUM", nb.m("SQRT", nb.m("ADD", nb.m("MULTIPLY", ny, ny), nb.m("MULTIPLY", nz, nz))), 1e-4)
        tcoord = nb.m("DIVIDE", nb.m("SUBTRACT", nb.m("MULTIPLY", y, nz), nb.m("MULTIPLY", z, ny)), l)
        wb, hb, hacb, fb = twill(nb, nb.m("MULTIPLY", tcoord, inv), nb.m("MULTIPLY", x, inv))
        mr = nb.new("ShaderNodeMapRange", clamp=True)
        nb.put(mr.inputs["Value"], nb.m("ABSOLUTE", nx))
        mr.inputs["From Min"].default_value = 0.45
        mr.inputs["From Max"].default_value = 0.8
        wx = mr.outputs[0]

        def mix(a, b):
            return nb.m("MULTIPLY_ADD", nb.m("SUBTRACT", a, b), wx, b)
        warp, h, hac, fib = mix(wa, wb), mix(ha, hb), mix(haca, hacb), mix(fa, fb)
    else:
        warp, h, hac, fib = wa, ha, haca, fa
    # colour: warp tows catch more light than weft tows (baked anisotropy look)
    val = nb.lerp(vals[0], vals[1], warp)
    val = nb.m("MULTIPLY", val, nb.lerp(0.55, 1.0, hac))
    val = nb.m("MULTIPLY", val, nb.lerp(0.75, 1.25, fib))
    # resin: large soft variation
    big = nb.noise(P, 60.0, detail=2.0)
    val = nb.m("MULTIPLY", val, nb.lerp(0.9, 1.1, big))
    rough = nb.lerp(roughs[0], roughs[1], warp)
    rough = nb.m("ADD", rough, nb.m("MULTIPLY", nb.m("SUBTRACT", 1.0, hac), 0.10))
    rough = nb.m("ADD", rough, nb.m("MULTIPLY", nb.m("SUBTRACT", fib, 0.5), 0.06))
    if relief > 0:
        hh = nb.m("ADD", h, nb.m("MULTIPLY", fib, 0.15))
        normal = nb.bump(hh, relief, k, strength=1.0)
    else:
        normal = nb.bump(nb.m("MULTIPLY", fib, 0.3), 0.000004, k, strength=1.0)
    return nb.principled(val, 0.0, rough, normal, tint=(1.0, 1.0, 1.03), spec_lvl=0.5)


def mat_satin_steel(name, bb_min, bb_size, center_yz, base=0.50, rough0=0.34, tint=(0.98, 0.99, 1.02)):
    """Satin / brushed steel; brushing marks run concentric around center_yz (the
    blade arc) so they follow the hawkbill curve."""
    nb = NB(name)
    P, k = nb.coords(bb_min, bb_size)
    x, y, z = nb.sep(P)
    dy = nb.m("SUBTRACT", y, center_yz[0])
    dz = nb.m("SUBTRACT", z, center_yz[1])
    r = nb.m("SQRT", nb.m("ADD", nb.m("MULTIPLY", dy, dy), nb.m("MULTIPLY", dz, dz)))
    th = nb.m("ARCTAN2", dz, dy)
    br = nb.noise(nb.comb(nb.m("MULTIPLY", r, 5200.0), nb.m("MULTIPLY", th, 7.0), nb.m("MULTIPLY", x, 900.0)),
                  1.0, detail=4.0, rough=0.6)
    br2 = nb.noise(nb.comb(nb.m("MULTIPLY", r, 900.0), nb.m("MULTIPLY", th, 2.0), 0.0), 1.0, detail=2.0)
    val = nb.m("MULTIPLY", base, nb.lerp(0.9, 1.08, br))
    val = nb.m("MULTIPLY", val, nb.lerp(0.96, 1.04, br2))
    rough = nb.lerp(rough0 - 0.05, rough0 + 0.08, br)
    normal = nb.bump(nb.m("MULTIPLY", br, 1.0), 0.000006, k, strength=1.0)
    return nb.principled(val, 1.0, rough, normal, tint=tint)


def mat_bead_steel(name, bb_min, bb_size, base=0.56, rough0=0.36):
    """Bead-blasted / satin stainless (finger ring)."""
    nb = NB(name)
    P, k = nb.coords(bb_min, bb_size)
    grain = nb.noise(P, 9000.0, detail=2.0, rough=0.6)
    vor = nb.voronoi(P, 2500.0)
    big = nb.noise(P, 120.0, detail=3.0)
    val = nb.m("MULTIPLY", base, nb.lerp(0.92, 1.06, grain))
    val = nb.m("MULTIPLY", val, nb.lerp(0.94, 1.05, big))
    rough = nb.lerp(rough0 - 0.04, rough0 + 0.07, grain)
    rough = nb.m("ADD", rough, nb.m("MULTIPLY", nb.m("SUBTRACT", big, 0.5), 0.08))
    h = nb.m("ADD", nb.m("MULTIPLY", vor, 0.6), nb.m("MULTIPLY", grain, 0.4))
    normal = nb.bump(h, 0.000008, k, strength=1.0)
    return nb.principled(val, 1.0, rough, normal, tint=(0.985, 0.99, 1.01))


def mat_coat(name, bb_min, bb_size, base=0.028, rough0=0.5, metallic=0.0):
    """Black ceramic coating (tang, blade spine) / black oxide."""
    nb = NB(name)
    P, k = nb.coords(bb_min, bb_size)
    g = nb.noise(P, 6000.0, detail=2.0, rough=0.6)
    big = nb.noise(P, 90.0, detail=2.0)
    val = nb.m("MULTIPLY", base, nb.lerp(0.85, 1.15, big))
    rough = nb.lerp(rough0 - 0.06, rough0 + 0.06, g)
    normal = nb.bump(g, 0.000005, k, strength=1.0)
    return nb.principled(val, metallic, rough, normal)


# ----------------------------------------------------------------------------
# object assembly
# ----------------------------------------------------------------------------
def _finish(name, bm, mats, tex_group, sharp_deg=None):
    """bmesh (mm) -> linked object (metres) with materials, UVMap and custom normals:
    analytic normals where the builders recorded them (_VN), Blender's smooth /
    sharp-edge corner normals everywhere else."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.scale(bm, vec=(0.001, 0.001, 0.001), verts=bm.verts)
    for f in bm.faces:
        f.smooth = True
    if sharp_deg is not None:
        lim = math.radians(sharp_deg)
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) > lim:
                if not (e.verts[0] in _VN and e.verts[1] in _VN):
                    e.smooth = False
    bm.verts.index_update()
    vnorm = [_VN.get(v) for v in bm.verts]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    _VN.clear()
    me.update()
    cn = [tuple(c.vector) for c in me.corner_normals]
    loops = []
    for lp in me.loops:
        n = vnorm[lp.vertex_index]
        loops.append(tuple(n) if n is not None else cn[lp.index])
    me.normals_split_custom_set(loops)
    obj = bpy.data.objects.new(name, me)
    mu.link(obj)
    obj["tex_group"] = tex_group
    # bounding box (metres) for the material coordinate conversion
    xs = [v.co for v in me.vertices]
    mn = Vector([min(c[i] for c in xs) for i in range(3)])
    mx = Vector([max(c[i] for c in xs) for i in range(3)])
    for mk in mats:
        me.materials.append(mk(mn, mx - mn))
    _uv_unwrap(obj)
    return obj


def _uv_unwrap(obj):
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


def build():
    _col_cache.clear()
    _VN.clear()
    # --- handle scales + screws -------------------------------------------------
    loop, radii = handle_outline(H_START)
    if signed_area(loop) < 0:
        raise RuntimeError("handle outline must be CCW")
    sradii = safe_radii(loop, [min(r, 1.8) for r in radii])
    bm = bmesh.new()
    for side in (1, -1):
        build_scale(bm, loop, sradii, side)
        for (y, z) in SCREWS:
            build_screw(bm, y, z, side)
    handle = _finish("KR_Handle_Mesh", bm, [
        lambda mn, sz: mat_carbon("KR_Handle_CarbonFibre", mn, sz),
        lambda mn, sz: mat_coat("KR_Handle_ScrewSteel", mn, sz, base=0.09, rough0=0.38, metallic=1.0),
    ], "handle", sharp_deg=50.0)

    # --- tang + blade -----------------------------------------------------------
    tloop, _ = handle_outline(12.8)
    bm = bmesh.new()
    build_tang(bm, tloop)
    sp = build_blade(bm)
    # centre of the blade arc for concentric satin marks (metres)
    mid = B_ARC * 0.5
    p, t, nrm = sp.at(mid)
    kap = sp.k0 * (1 + (CURV_RATIO - 1) * mid / B_ARC)
    cen = (p + nrm * (1.0 / kap)) * 0.001
    blade = _finish("KR_Handle_Mesh_Blade", bm, [
        lambda mn, sz: mat_carbon("KR_Blade_CarbonPrint", mn, sz, relief=0.0, triplanar=False,
                                  vals=(0.007, 0.026), roughs=(0.58, 0.48)),
        lambda mn, sz: mat_satin_steel("KR_Blade_SatinSteel", mn, sz, (cen.x, cen.y)),
        lambda mn, sz: mat_coat("KR_Blade_BlackCoat", mn, sz),
    ], "blade", sharp_deg=60.0)

    # --- ring ---------------------------------------------------------------------
    bm = bmesh.new()
    build_ring(bm)
    ring = _finish("KR_Handle_Mesh_Ring", bm, [
        lambda mn, sz: mat_bead_steel("KR_Ring_Steel", mn, sz),
    ], "handle")
    return [handle, blade, ring]
