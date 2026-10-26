"""
Animation authoring core (R15 avatar arms + knife).

An Anim is a set of control channels with keys.  Sampling it at 60 fps and
running the skeleton solver (two-bone arm IK, knife links) gives per-frame
joint transforms which are written to Blender actions and Roblox
KeyframeSequences.  The arms are the player's R15 avatar arms: there are no
fingers - the knife handle sits in / passes through the blocky hand.

Units: STUDS (Roblox), seconds, degrees.

    a = Anim("bf_draw", knife="butterfly", length=1.25)
    a.hand("R", 0.00, pos=(0.9, 1.0, -1.9), rot=(-20, 10, 40), interp="out")
    a.hand("R", 0.35, pos=(0.75, 1.45, -0.95), rot=(5, 15, 0))
    a.knife(0.00, pos=(...), rot=(...), anchor="B")   # knife link in the hand frame
    a.bf(0.00, a=1, b=1)                              # butterfly closed
    a.bf(0.30, a=0, b=0, interp="out_back")
    a.cam(0.30, rot=(1.5, 0, -0.5))
    a.marker(0.30, "Sound", "flip")

  hand pos  : centre of the R15 hand block in viewmodel space (camera at the
              origin, +Y forward, +Z up, +X right), studs.  A typical
              right-hand idle spot is around (0.75, 1.45, -0.95).
  hand rot  : (pitch, yaw, roll) on top of the neutral "handshake" pose
              (bottom of the hand block = "fingers" pointing forward, thumb
              side up, palm facing the centre line).  pitch + fingers up,
              yaw + fingers towards the centre, roll + pronation (palm down).
              Mirrored for the left hand.  (-90, 0, 0) = arm hanging down.
  elbow     : offset of the automatic elbow pole (move the elbow out/down).
  shoulder  : small shoulder pivot offset (lunges / reach), studs.
  knife     : pos/rot of the anchored knife link in the hand semantic frame
              (origin = hand block centre, +X radial (thumb side), +Y distal,
              +Z palmar), rot = euler in `knife_rot_order` (default XYZ: the
              X angle is a spin about the knife's OWN X axis = pin / ring axis).
              anchor (butterfly): which link pos/rot describe: "A" (safe
              handle), "B" (bite handle), "BLADE".  switch_anchor(t, new)
              changes the held link without a jump.
  bf        : a, b = 0 open .. 1 closed for handle A / B, latch 0..1.
  interp    : the curve LEAVING that key: "smooth" (default, monotone cubic),
              "linear", "step", or an easing: in, out, inout, in_back,
              out_back, inout_back, in_expo, out_expo, snap, in_quint,
              out_quint, out_soft, or a (x1, y1, x2, y2) cubic-bezier tuple.
  tangent   : "auto" (default) or "flat" (velocity 0 at that key: a hold).
"""

import math
from bisect import bisect_right

from mathutils import Matrix, Vector, Quaternion, Euler

from .. import spec, skeleton

# ----------------------------------------------------------------------------
# easing
# ----------------------------------------------------------------------------
EASINGS = {
    "in": (0.42, 0.0, 1.0, 1.0),
    "out": (0.0, 0.0, 0.58, 1.0),
    "inout": (0.42, 0.0, 0.58, 1.0),
    "in_quint": (0.64, 0.0, 0.78, 0.0),
    "out_quint": (0.22, 1.0, 0.36, 1.0),
    "in_expo": (0.7, 0.0, 0.84, 0.0),
    "out_expo": (0.16, 1.0, 0.3, 1.0),
    "in_back": (0.36, 0.0, 0.66, -0.56),
    "out_back": (0.34, 1.56, 0.64, 1.0),
    "inout_back": (0.68, -0.6, 0.32, 1.6),
    "snap": (0.08, 0.9, 0.2, 1.0),
    "out_soft": (0.25, 0.6, 0.4, 1.0),
}


def cubic_bezier(x1, y1, x2, y2):
    def bez(t, p1, p2):
        return 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3

    def f(x):
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) * 0.5
            if bez(mid, x1, x2) < x:
                lo = mid
            else:
                hi = mid
        return bez((lo + hi) * 0.5, y1, y2)
    return f


_EASE_CACHE = {}


def easing_fn(spec_):
    key = spec_ if isinstance(spec_, str) else tuple(spec_)
    if key not in _EASE_CACHE:
        params = EASINGS[spec_] if isinstance(spec_, str) else tuple(spec_)
        _EASE_CACHE[key] = cubic_bezier(*params)
    return _EASE_CACHE[key]


# ----------------------------------------------------------------------------
# channels
# ----------------------------------------------------------------------------
class Key:
    __slots__ = ("t", "v", "interp", "tangent")

    def __init__(self, t, v, interp, tangent):
        self.t, self.v, self.interp, self.tangent = t, v, interp, tangent


class Channel:
    def __init__(self, name, dim, discrete=False):
        self.name, self.dim, self.discrete = name, dim, discrete
        self.keys = []
        self._tangents = None

    def add(self, t, v, interp="smooth", tangent="auto"):
        if self.discrete:
            v = (v,)
        else:
            v = tuple(float(x) for x in (v if isinstance(v, (tuple, list)) else (v,)))
            if len(v) != self.dim:
                raise ValueError(f"{self.name}: expected {self.dim} values, got {v}")
        # replace a key at the same time
        self.keys = [k for k in self.keys if abs(k.t - t) > 1e-6]
        self.keys.append(Key(float(t), v, interp, tangent))
        self.keys.sort(key=lambda k: k.t)
        self._tangents = None

    def _compute_tangents(self, loop_len=None):
        ks = self.keys
        n = len(ks)
        tans = []
        for i in range(n):
            if ks[i].tangent == "flat" or n < 2:
                tans.append((0.0,) * self.dim)
                continue
            if 0 < i < n - 1:
                p, c, nx = ks[i - 1], ks[i], ks[i + 1]
            elif loop_len is not None and n > 2:
                # wrap: last key == first key (same pose) for loops
                if i == 0:
                    p, c, nx = ks[n - 2], ks[0], ks[1]
                    p = Key(p.t - loop_len, p.v, p.interp, p.tangent)
                else:
                    p, c, nx = ks[n - 2], ks[n - 1], ks[1]
                    nx = Key(nx.t + loop_len, nx.v, nx.interp, nx.tangent)
            else:
                tans.append((0.0,) * self.dim)
                continue
            h0, h1 = c.t - p.t, nx.t - c.t
            m = []
            for j in range(self.dim):
                s0 = (c.v[j] - p.v[j]) / h0 if h0 > 1e-9 else 0.0
                s1 = (nx.v[j] - c.v[j]) / h1 if h1 > 1e-9 else 0.0
                if s0 * s1 <= 0:
                    m.append(0.0)
                    continue
                mm = (s0 * h1 + s1 * h0) / (h0 + h1)
                lim = 3.0 * min(abs(s0), abs(s1))
                m.append(max(-lim, min(lim, mm)))
            tans.append(tuple(m))
        self._tangents = tans

    def eval(self, t, loop_len=None):
        ks = self.keys
        if not ks:
            return None
        if self.discrete:
            i = bisect_right([k.t for k in ks], t + 1e-9) - 1
            return ks[max(i, 0)].v[0]
        if self._tangents is None:
            self._compute_tangents(loop_len)
        if t <= ks[0].t:
            return ks[0].v
        if t >= ks[-1].t:
            return ks[-1].v
        times = [k.t for k in ks]
        i = bisect_right(times, t) - 1
        k0, k1 = ks[i], ks[i + 1]
        h = k1.t - k0.t
        u = (t - k0.t) / h
        mode = k0.interp
        if mode == "step":
            return k0.v
        if mode == "linear":
            return tuple(a + (b - a) * u for a, b in zip(k0.v, k1.v))
        if mode != "smooth":
            e = easing_fn(mode)(u)
            return tuple(a + (b - a) * e for a, b in zip(k0.v, k1.v))
        m0, m1 = self._tangents[i], self._tangents[i + 1]
        if k1.interp == "step":
            pass
        u2, u3 = u * u, u * u * u
        h00 = 2 * u3 - 3 * u2 + 1
        h10 = u3 - 2 * u2 + u
        h01 = -2 * u3 + 3 * u2
        h11 = u3 - u2
        return tuple(h00 * a + h10 * h * ma + h01 * b + h11 * h * mb
                     for a, b, ma, mb in zip(k0.v, k1.v, m0, m1))


def _noise1(x, seed):
    """cheap smooth 1D value noise in [-1, 1]."""
    def h(i):
        n = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
        n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 0xFFFF) / 32767.5 - 1.0
    i = math.floor(x)
    f = x - i
    f = f * f * (3 - 2 * f)
    return h(i) * (1 - f) + h(i + 1) * f


# ----------------------------------------------------------------------------
# Anim
# ----------------------------------------------------------------------------
CHANNEL_DIMS = {"pos": 3, "rot": 3, "elbow": 3, "shoulder": 3}

HAND_CHANNELS = ("pos", "rot", "elbow", "shoulder")


class Anim:
    def __init__(self, name, knife, length, loop=False, priority="Action",
                 knife_rot_order="XYZ", fps=spec.FPS, roblox_name=None, description=""):
        assert knife in ("butterfly", "karambit")
        self.name, self.kind, self.length, self.loop = name, knife, float(length), loop
        self.priority, self.knife_rot_order, self.fps = priority, knife_rot_order, fps
        self.roblox_name = roblox_name or name
        self.description = description
        self.ch = {}
        self.markers = []          # (t, name, value)
        self.noise = []            # (channel, amp tuple, freq, seed, t0, t1)
        self.anchor_switches = []  # (t, new_anchor)
        self.warnings = []

    # -- channel helpers ---------------------------------------------------------
    def _chan(self, name):
        if name not in self.ch:
            if name == "knife.anchor":
                self.ch[name] = Channel(name, 1, discrete=True)
            else:
                dim = len(skeleton.DEFAULT_CTRL[name]) if isinstance(skeleton.DEFAULT_CTRL[name], tuple) else 1
                self.ch[name] = Channel(name, dim)
        return self.ch[name]

    def set(self, name, t, value, interp="smooth", tangent="auto"):
        if name.startswith("knife."):
            self.__dict__.pop("_segs", None)
        self._chan(name).add(t, value, interp, tangent)
        return self

    def hand(self, side, t, pos=None, rot=None, elbow=None, shoulder=None, interp="smooth", tangent="auto"):
        for nm, v in (("pos", pos), ("rot", rot), ("elbow", elbow), ("shoulder", shoulder)):
            if v is not None:
                self.set(f"{side}.{nm}", t, v, interp, tangent)
        return self

    def knife(self, t, pos=None, rot=None, anchor=None, interp="smooth", tangent="auto"):
        if pos is not None:
            self.set("knife.pos", t, pos, interp, tangent)
        if rot is not None:
            self.set("knife.rot", t, rot, interp, tangent)
        if anchor is not None:
            if self.ch.get("knife.anchor") and self.ch["knife.anchor"].keys:
                raise ValueError("use switch_anchor() to change the anchor after the first key")
            self.__dict__.pop("_segs", None)
            self._chan("knife.anchor").add(t, anchor)
        return self

    def switch_anchor(self, t, anchor):
        """From time t on, knife.pos/rot describe `anchor`.  The knife does not
        jump: keys you give for t' >= t are relative to the new link; a key at
        exactly t is generated automatically from the old link's pose."""
        self.__dict__.pop("_segs", None)
        self.anchor_switches.append((float(t), anchor))
        self.anchor_switches.sort()
        return self

    def bf(self, t, a=None, b=None, latch=None, interp="smooth", tangent="auto"):
        cur = self._chan("bf")
        prev = cur.eval(t) if cur.keys else (0.0, 0.0, 0.0)
        v = (prev[0] if a is None else a, prev[1] if b is None else b, prev[2] if latch is None else latch)
        cur.add(t, v, interp, tangent)
        return self

    def cam(self, t, rot=None, pos=None, interp="smooth", tangent="auto"):
        if rot is not None:
            self.set("cam.rot", t, rot, interp, tangent)
        if pos is not None:
            self.set("cam.pos", t, pos, interp, tangent)
        return self

    def marker(self, t, name, value=""):
        self.markers.append((float(t), name, str(value)))
        return self

    def add_noise(self, channel, amp, freq=0.6, seed=1, t0=0.0, t1=None):
        """Additive smooth noise (amp per component) on a channel."""
        self.noise.append((channel, tuple(amp), freq, seed, t0, self.length if t1 is None else t1))
        return self

    def pose(self, t, side=None):
        """Evaluated control dict at time t (for building relative keys)."""
        return self.controls(t)

    # -- evaluation --------------------------------------------------------------
    def _segment_channels(self):
        """Split knife.pos/rot keys into anchor segments.  Returns list of
        (t_start, t_end, anchor, pos_channel, rot_channel)."""
        if hasattr(self, "_segs"):
            return self._segs
        anchor0 = "A"
        if "knife.anchor" in self.ch and self.ch["knife.anchor"].keys:
            anchor0 = self.ch["knife.anchor"].keys[0].v[0]
        cuts = [(0.0, anchor0)] + [s for s in self.anchor_switches if s[0] > 0]
        pos_all = self.ch.get("knife.pos")
        rot_all = self.ch.get("knife.rot")
        segs = []
        for i, (ts, anc) in enumerate(cuts):
            te = cuts[i + 1][0] if i + 1 < len(cuts) else float("inf")
            pc, rc = Channel("knife.pos", 3), Channel("knife.rot", 3)
            for src, dst in ((pos_all, pc), (rot_all, rc)):
                if src is None:
                    continue
                for k in src.keys:
                    # a key exactly at a switch time belongs to the OLD anchor
                    if (i == 0 and k.t <= te + 1e-9) or (i > 0 and ts + 1e-9 < k.t <= te + 1e-9):
                        dst.keys.append(Key(k.t, k.v, k.interp, k.tangent))
            segs.append([ts, te, anc, pc, rc])
        # seed each later segment with a continuity key at its start
        self._segs = segs
        for i in range(1, len(segs)):
            ts, te, anc, pc, rc = segs[i]
            prev = segs[i - 1]
            c = self._raw_controls(ts, seg_override=i - 1)
            hand = skeleton.hand_semantic_frame(skeleton.evaluate(c, self.knife_rot_order, self.kind))
            # world pose of the new anchor link at ts
            kp = skeleton.T(c["knife.pos"]) @ skeleton.euler_matrix(c["knife.rot"], self.knife_rot_order).to_4x4()
            aw = hand @ kp
            a_, b_, _ = c["bf"]
            A, blade, B = skeleton.bf_link_frames(aw, prev[2], a_, b_)
            new_world = {"A": A, "KNIFE": A, "BLADE": blade, "B": B}[anc]
            local = hand.inverted() @ new_world
            nxt = rc.keys[0].v if rc.keys else c["knife.rot"]
            compat = Euler([math.radians(x) for x in nxt], self.knife_rot_order)
            e = local.to_3x3().to_euler(self.knife_rot_order, compat)
            pc.keys.insert(0, Key(ts, tuple(local.translation), "smooth", "auto"))
            rc.keys.insert(0, Key(ts, tuple(math.degrees(x) for x in e), "smooth", "auto"))
            pc._tangents = rc._tangents = None
        return segs

    def _raw_controls(self, t, seg_override=None):
        loop_len = self.length if self.loop else None
        c = {}
        for name, ch in self.ch.items():
            if name in ("knife.pos", "knife.rot", "knife.anchor"):
                continue
            v = ch.eval(t, loop_len)
            if v is not None:
                c[name] = v
        segs = self._segs if hasattr(self, "_segs") else None
        if segs is None:
            segs = self._segment_channels()
        si = seg_override
        if si is None:
            si = 0
            for i, s in enumerate(segs):
                if t >= s[0] - 1e-9:
                    si = i
        ts, te, anc, pc, rc = segs[si]
        c["knife.anchor"] = anc
        pv, rv = pc.eval(t, loop_len), rc.eval(t, loop_len)
        if pv is not None:
            c["knife.pos"] = pv
        if rv is not None:
            c["knife.rot"] = rv
        return c

    def controls(self, t):
        c = self._raw_controls(t)
        for chn, amp, freq, seed, t0, t1 in self.noise:
            if not (t0 <= t <= t1):
                continue
            base = c.get(chn, skeleton.DEFAULT_CTRL[chn])
            # fade noise in/out over 0.3 s at the window borders (except loops)
            w = 1.0
            if not self.loop:
                w = min(1.0, (t - t0) / 0.3 if t0 > 0 else 1.0, (t1 - t) / 0.3 if t1 < self.length else 1.0)
            vals = []
            for j, (b, a) in enumerate(zip(base, amp)):
                x = t * freq
                if self.loop:   # loop-safe noise: blend two phases
                    L = self.length * freq
                    n = (_noise1(x, seed + 31 * j) * (L - x) + _noise1(x - L, seed + 31 * j) * x) / max(L, 1e-6)
                else:
                    n = _noise1(x, seed + 31 * j)
                vals.append(b + a * n * w)
            c[chn] = tuple(vals)
        return c

    def nframes(self):
        return int(round(self.length * self.fps)) + 1

    def sample(self):
        """-> list of dicts {bone: world 4x4} for every frame, plus warnings."""
        frames = []
        self.warnings = []
        flagged = set()
        for f in range(self.nframes()):
            t = min(f / self.fps, self.length)
            info = {}
            W = skeleton.evaluate(self.controls(t), self.knife_rot_order, self.kind, info)
            for side in ("R", "L"):
                i = info[side]
                if abs(i["wrist_flex"]) > spec.WRIST_FLEX_LIMIT or abs(i["wrist_dev"]) > spec.WRIST_DEV_LIMIT:
                    tag = (side, round(t, 1))
                    if tag not in flagged:
                        flagged.add(tag)
                        self.warnings.append(f"t={t:.2f}s {side} wrist flex={i['wrist_flex']:.0f} dev={i['wrist_dev']:.0f}")
            frames.append(W)
        return frames

    def bake(self):
        """-> list (per frame) of {bone: (loc Vector, rot Quaternion)} local
        bases, quaternion-continuous over time."""
        frames = self.sample()
        out = []
        prevq = {}
        for W in frames:
            B = skeleton.local_basis(W)
            fr = {}
            for name, m in B.items():
                loc, q, _ = m.decompose()
                pq = prevq.get(name)
                if pq is not None and pq.dot(q) < 0:
                    q.negate()
                prevq[name] = q
                fr[name] = (loc, q)
            out.append(fr)
        return frames, out


# registry --------------------------------------------------------------------
REGISTRY = {}


def register(fn):
    """Decorator for animation builder functions returning an Anim."""
    REGISTRY[fn.__module__ + "." + fn.__name__] = fn
    return fn
