"""
kr_heavy - CS2-style karambit heavy attack: rising uppercut hook (R15 blocky arm).

Reference: CS2 karambit heavy, ref frames f_0125-f_0136 (ref_specs/
karambit_segmentation.md section 4): the hand sinks below the bottom edge,
rips up fast with the fist turned vertical (ring on top, the claw's concave
edge facing the travel), sweeps past the camera off the top of the screen and
comes back in from the right edge with the karambit hanging from the "finger"
for a spin.  CS2's recording cuts off there; the spin + catch + settle reuse
kr_draw's finger-spin rig (knife on an implied finger just off the palm face,
hand thumb-up / palm to the camera, the knife whirls on the camera side).

Beats (seconds, 60 fps grid):
  0.00        common.IDLE (flat hold).
  0.00-0.18   WIND-UP: the fist drops low/right below the bottom edge (only the
              ring and the claw show), rolls towards vertical, knife pivots
              blade-down on the ring; tiny camera dip.
  0.18-0.37   STRIKE: powerful rising hook up through the screen centre: the
              fist turns vertical (ring on top) and the knife pivots ~30 deg on
              the ring so the claw leads, hooked edge first, crossing the
              centre at the Hit (0.30), then the arm sweeps past the camera off
              the top (shoulder offset for reach); camera kick up ~3 deg.
  0.37-0.55   FOLLOW-THROUGH + RETURN: off the top-right; the grip opens (knife
              slides onto the implied finger, hidden) and the hand drops back in
              from the right edge, thumb up, the karambit hanging.
  0.55-0.80   SPIN: one turn about the ring axis (knife rot X +360, ~1700
              deg/s peak); the hand stirs a small circle ahead of the knife.
  0.80-0.90   CATCH at 6 o'clock: pronate + squeeze, handle into the fist
              (hand-local slerp into common.GRIP), small camera kick.
  0.80-1.15   GLIDE + SETTLE: ease-out down-left into the idle spot, tiny
              overshoot, exactly common.IDLE at the end (flat).
Markers: Sound swing_heavy (strike start), Hit heavy (impact), Sound spin,
Sound catch.  Left arm hidden throughout.
"""

import math

from mathutils import Euler, Vector

from ..core import Anim
from ... import skeleton as sk
from . import common as C

FR = 1.0 / 60.0

F_WIND = 11                           # bottom of the wind-up = strike start
F_HIT = 18                            # claw crosses the screen centre
F_PEAK = 22                           # fist leaves the top edge
F_TOP = 26                            # follow-through end (off the top-right)
F_RET = 33                            # back in at the right edge, knife hanging
F_CATCH = 48                          # one turn later, 6 o'clock
F_GRIPPED = 54
F_OVER = 61
LENGTH = 69 * FR                      # 1.15 s

# --- strike path (viewmodel studs / deg; shoulder = offset on the rig) -------
# solved for a straight-ish wrist (|flex|, |dev| <= ~20 deg); kdx = knife pivot on the
# ring (added to GRIP rot X, negative = blade end up / forward)
WIND = dict(pos=(1.45, 2.45, -1.95), rot=(15.0, 42.0, 38.0), elbow=(0.50, 0.0, -0.50),
            shoulder=(0.10, -0.40, 0.00), kdx=10.0)
HIT = dict(pos=(0.58, 2.90, -0.50), rot=(55.0, 85.0, 15.0), elbow=(0.60, 0.0, -0.60),
           shoulder=(0.10, -0.20, 0.80), kdx=-45.0)
PEAK = dict(pos=(0.62, 1.95, 1.32), rot=(65.0, 80.0, 10.0), elbow=(0.60, 0.0, -0.60),
            shoulder=(0.12, -0.35, 1.45), kdx=-48.0)
TOP = dict(pos=(1.30, 1.70, 1.90), rot=(60.0, 40.0, 0.0), elbow=(0.60, 0.0, -0.40),
           shoulder=(0.60, -0.40, 1.75))

# --- finger-spin rig (same as kr_draw) ---------------------------------------
SPIN_PIVOT = (0.30, 0.05, 0.64)       # ring centre: just off the palm face, thumb edge
SPIN_YZ = (-75.0, 0.0)                # knife X (ring axis) = palmar tilted 15 deg radial
TH_HANG = 90.0 - 360.0                # hanging along the pinky side
TH_CATCH = 90.0                       # hanging again after one turn
P_SPIN0 = (2.20, 3.40, -0.55)         # right edge, thumb up, palm to the camera
R_SPIN0 = (14.0, 24.0, 6.0)
P_SPIN1 = (2.12, 3.38, -0.68)         # drifted down-left while spinning
R_SPIN1 = (16.0, 25.0, 11.0)
SH_SPIN = (1.00, 0.80, 0.10)
EL_SPIN = (1.00, 0.0, 0.20)
STIR = 0.035
WOBBLE = (2.0, 1.5)
R_CAUGHT = (33.0, 31.0, 87.0)         # pronated into the grip, knuckles up
SETTLE_DPOS = (-0.014, 0.0, -0.018)   # overshoot continuing the down-left glide
SETTLE_DROT = (-1.2, 0.4, 0.8)


# ---------------------------------------------------------------------------
def _lerp(p0, p1, w):
    return tuple(x + (y - x) * w for x, y in zip(p0, p1))


def _smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _m3(rot):
    return Euler([math.radians(x) for x in rot], "XYZ").to_matrix()


def _kgrip(dx):
    g = C.GRIP["rot"]
    return (g[0] + dx, g[1], g[2])


def _speed(t):
    """relative knife angular speed: whip, constant, ease ~35 % into the catch."""
    t0, t1 = F_RET * FR, F_CATCH * FR
    if t <= t0:
        return 0.0
    if t < t0 + 0.06:
        return _smooth((t - t0) / 0.06)
    if t < t1 - 0.09:
        return 1.0
    return 1.0 - 0.35 * _smooth((t - (t1 - 0.09)) / 0.09)


def _theta_table():
    sub = 20
    acc, tab = 0.0, {}
    for f in range(F_RET, F_CATCH + 1):
        tab[f] = acc
        for k in range(sub):
            acc += _speed(f * FR + (k + 0.5) * FR / sub) * FR / sub
    scale = (TH_CATCH - TH_HANG) / tab[F_CATCH]
    return {f: TH_HANG + v * scale for f, v in tab.items()}, scale   # scale = peak deg/s


THETA, OMEGA = _theta_table()


def _handle_dir(th):
    th = math.radians(th)
    return Vector((-0.966 * math.sin(th), math.cos(th), 0.259 * math.sin(th)))


def _spin_hand(f):
    """hand pos/rot during the spin: base drift + stir circle (kr_draw technique)."""
    w = _smooth((f - F_RET) / (F_CATCH - F_RET))
    p, r = _lerp(P_SPIN0, P_SPIN1, w), _lerp(R_SPIN0, R_SPIN1, w)
    t = f * FR
    fade = max(0.0, min(1.0, (t - F_RET * FR) / 0.08, (F_CATCH - f) * FR / 0.06))
    lead = THETA[f] + 90.0                     # 90 deg ahead of the knife along its travel
    off = sk.hand_rotation("R", r) @ _handle_dir(lead) * (STIR * fade)
    ph = math.radians(lead)
    r = (r[0] + WOBBLE[0] * fade * math.sin(ph), r[1] + WOBBLE[1] * fade * math.cos(ph), r[2])
    return tuple(pc + oc for pc, oc in zip(p, off)), r


def _cyl(p):
    """hand-local point -> (angle about distal from +palmar towards +radial, radius, y)."""
    x, y, z = p
    return math.atan2(x, z), math.hypot(x, z), y


def _key_hand(a, f, d, interp="smooth"):
    a.hand("R", f * FR, pos=d["pos"], rot=d["rot"], elbow=d["elbow"], shoulder=d["shoulder"], interp=interp)


def build():
    a = Anim("kr_heavy", "karambit", length=LENGTH, priority="Action",
             description="Karambit heavy: low wind-up, rising uppercut hook off the top, "
                         "return with a ring spin, catch, settle to idle")
    I = C.IDLE

    # ---- start / end on the base pose (left arm stays hidden) ---------------
    C.key_idle(a, 0.0)

    # ---- wind-up: drop low/right ------------------------------------------
    _key_hand(a, F_WIND, WIND)
    a.knife(F_WIND * FR, pos=C.GRIP["pos"], rot=_kgrip(WIND["kdx"]))
    a.cam((F_WIND - 2) * FR, rot=(-0.6, 0.1, 0.3))

    # ---- strike: rising hook through the centre, off the top ------------------
    a.marker(F_WIND * FR, "Sound", "swing_heavy")
    _key_hand(a, F_HIT, HIT)
    a.knife(F_HIT * FR, pos=C.GRIP["pos"], rot=_kgrip(HIT["kdx"]))
    a.marker(F_HIT * FR, "Hit", "heavy")
    _key_hand(a, F_PEAK, PEAK, interp="out")
    a.knife(F_PEAK * FR, pos=C.GRIP["pos"], rot=_kgrip(PEAK["kdx"]))
    _key_hand(a, F_TOP, TOP)
    a.cam(F_HIT * FR, rot=(-0.2, 0.05, 0.1), interp="out_quint")
    a.cam((F_HIT + 3) * FR, rot=(3.0, -0.4, -1.0))
    a.cam((F_HIT + 20) * FR, rot=(0.0, 0.0, 0.0), tangent="flat")

    # ---- release (off screen): the knife slides onto the implied finger -----
    q0 = _m3(_kgrip(PEAK["kdx"])).to_quaternion()
    q1 = _m3((TH_HANG,) + SPIN_YZ).to_quaternion()
    prev = Euler([math.radians(x) for x in _kgrip(PEAK["kdx"])], "XYZ")
    for f in range(F_PEAK + 1, F_RET):
        w = _smooth((f - F_PEAK) / (F_RET - 2 - F_PEAK))
        e = q0.slerp(q1, w).to_matrix().to_euler("XYZ", prev)
        prev = e
        a.knife(f * FR, pos=_lerp(C.GRIP["pos"], SPIN_PIVOT, w), rot=tuple(math.degrees(x) for x in e))

    # ---- return in from the right edge, then the spin (dense keys) -----------
    a.hand("R", F_RET * FR, pos=P_SPIN0, rot=R_SPIN0, shoulder=SH_SPIN, elbow=EL_SPIN)
    for f in range(F_RET + 1, F_CATCH + 1):
        p, r = _spin_hand(f)
        a.hand("R", f * FR, pos=p, rot=r)
    a.hand("R", F_CATCH * FR, shoulder=SH_SPIN, elbow=EL_SPIN)
    for f in range(F_RET, F_CATCH + 1):
        a.knife(f * FR, pos=SPIN_PIVOT, rot=(THETA[f],) + SPIN_YZ)
    a.marker((F_RET + 2) * FR, "Sound", "spin")
    a.cam((F_RET + 1) * FR, rot=(0.0, 0.0, 0.0))
    a.cam((F_RET + 5) * FR, rot=(0.25, 0.0, -0.15))
    a.cam((F_RET + 13) * FR, rot=(0.0, 0.0, 0.0), tangent="flat")

    # ---- catch: the hand rolls under the still-turning knife -----------------
    p0, r0 = _spin_hand(F_CATCH)
    n = F_GRIPPED - F_CATCH
    T = n * FR
    w_c = OMEGA * (1.0 - 0.35)                     # deg/s arriving at the catch
    q_grip = _m3(C.GRIP["rot"]).to_quaternion()
    a0, rad0, y0 = _cyl(SPIN_PIVOT)
    a1, rad1, y1 = _cyl(C.GRIP["pos"])
    prev = Euler([math.radians(x) for x in (TH_CATCH,) + SPIN_YZ], "XYZ")
    for i in range(1, n + 1):
        f = F_CATCH + i
        u = i / n
        tau = i * FR
        hr = 1 - (1 - u) ** 2                       # pronation: snaps on at once, stops soft
        a.hand("R", f * FR, rot=_lerp(r0, R_CAUGHT, hr))
        if i == n:
            a.knife(f * FR, pos=C.GRIP["pos"], rot=C.GRIP["rot"])
            break
        th = TH_CATCH + w_c * (tau - tau * tau / (2 * T))
        q_spin = _m3((th,) + SPIN_YZ).to_quaternion()
        e = q_spin.slerp(q_grip, _smooth(u)).to_matrix().to_euler("XYZ", prev)
        prev = e
        ang = a0 + (a1 - a0) * hr                   # ring rolls round the hand's long axis
        rad = rad0 + (rad1 - rad0) * hr
        pos = (rad * math.sin(ang), y0 + (y1 - y0) * hr, rad * math.cos(ang))
        a.knife(f * FR, pos=pos, rot=tuple(math.degrees(x) for x in e))
    a.marker((F_CATCH + 3) * FR, "Sound", "catch")
    a.cam(F_CATCH * FR, rot=(0.0, 0.0, 0.0))
    a.cam((F_CATCH + 3) * FR, rot=(-0.35, 0.0, 0.15))
    a.cam((F_CATCH + 13) * FR, rot=(0.0, 0.0, 0.0), tangent="flat")

    # ---- glide: one ease-out stroke from the catch spot into idle ------------
    over = C.pose_offset(R_pos=SETTLE_DPOS, R_rot=SETTLE_DROT)
    g1 = 1 - (1 - (F_GRIPPED - F_CATCH) / (F_OVER - F_CATCH)) ** 2.4
    for f in range(F_CATCH + 1, F_OVER + 1):
        v = (f - F_CATCH) / (F_OVER - F_CATCH)
        g = 1 - (1 - v) ** 2.4
        a.hand("R", f * FR, pos=_lerp(p0, over["R_pos"], g),
               shoulder=_lerp(SH_SPIN, I["R_shoulder"], g), elbow=_lerp(EL_SPIN, I["R_elbow"], g))
        if f > F_GRIPPED:
            a.hand("R", f * FR, rot=_lerp(R_CAUGHT, over["R_rot"], (g - g1) / (1 - g1)))
    C.key_settle(a, F_OVER * FR, LENGTH, dpos=SETTLE_DPOS, drot=SETTLE_DROT)
    return a
