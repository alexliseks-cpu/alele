"""
Butterfly DRAW (deploy), 1.25 s.

Starts off-screen (hand low right, knife CLOSED and latched, held by the
safe handle A near its butt), ends exactly on common.IDLE.

Beats (all knife rotations counter-clockwise on screen = negative knife X):
  0.00-0.22  rise into view, elbow leading; the wrist cocks clockwise so the
             closed knife stands up out of the thumb side of the fist; the
             latch pops open at the top of the rise
  0.22-0.28  flick: hard counter-clockwise wrist snap + stop; the bite handle
             B is released and whips out over the top (b 1 -> 0)
  ~0.33      B hits its stop and yanks the blade out of A: blade + B swing on
             over the top / round under the fist (a 1 -> 0) while the fist
             slides up the handle to the pins
  ~0.46      B slaps into A; the impact carries the open knife into one
             twirl about the pins (knife rot X -360); the hand lifts and
             stirs a small circle that leads the spin
  ~0.73      catch: the handles slap into the fist with a small rebound, the
             latch flips shut (camera kick)
  0.73-0.90  the spinning knife's momentum carries the fist down below idle,
             rolling the blade towards edge-on (like the CS2 inspect outro
             "bottom out", ref f128-130)
  0.90-1.25  the fist glides up-right into idle with an ease-out, a hair of
             overshoot, and settles (flat at 1.25)
Markers: Sound deploy 0.00, flip at the release (0.24), latch at the slap /
catch (~0.73), catch when the fist bottoms out with the knife (0.90).
B / blade / A angles come from one integrated angular-velocity profile (the
speed drops at every impact as momentum is shared with a heavier link), so
the spins keep consistent momentum; small rebounds follow each impact.
Hand / knife / handle channels are baked at 60 fps (linear keys).
"""

import math

from mathutils import Euler

from ... import skeleton
from ..core import Channel
from . import common

LENGTH = 1.25
FPS = 60.0
I = common.IDLE

# ---------------------------------------------------------------------------
# hand orientation helper: IDLE-style (pitch, yaw, roll) turned in SCREEN axes
# ---------------------------------------------------------------------------
_NINV = skeleton.R_NEUTRAL["R"].inverted()


def spun(rot, spin=0.0, tilt=0.0, turn=0.0):
    """Hand (pitch, yaw, roll) rotated in world/screen axes about the hand
    centre: spin + = counter-clockwise on screen (about the view axis),
    tilt + = top towards the camera, turn + = right side away from camera."""
    R = skeleton.hand_rotation("R", rot)
    Q = skeleton.R3("Z", turn) @ skeleton.R3("X", tilt) @ skeleton.R3("Y", -spin)
    M = Q @ R @ _NINV
    base = Euler((math.radians(rot[0]), math.radians(-rot[2]), math.radians(rot[1])), "YXZ")
    e = M.to_euler("YXZ", base)
    return (math.degrees(e.x), math.degrees(e.z), -math.degrees(e.y))


def _add(*vs):
    return tuple(sum(x) for x in zip(*vs))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _bump(t, t0, dur, amp):
    """impact rebound: fast rise (peak at 1/3 of dur), smooth return."""
    u = (t - t0) / dur
    if u <= 0.0 or u >= 1.0:
        return 0.0
    return amp * 6.75 * u * (1.0 - u) ** 2


def _smooth(t, t0, t1):
    if t <= t0:
        return 0.0
    if t >= t1:
        return 1.0
    u = (t - t0) / (t1 - t0)
    return u * u * (3.0 - 2.0 * u)


# ---------------------------------------------------------------------------
# momentum chain (relative to the hand), CCW degrees
# ---------------------------------------------------------------------------
T_LATCH0, T_LATCH1 = 0.17, 0.215      # latch pops open at the top of the rise
T_REL = 0.24                           # bite handle released (mid-snap)
RAMP = 0.03                            # whip ramp-up as the wrist stops
W1 = 2000.0                            # B alone (light)
W2 = 1400.0                            # B + blade after the 1st impact
W3 = 1550.0                            # whole knife twirl (hand stirs it up)
W3_END = 1350.0
CATCH_DEG = 40.0                       # decelerate over the last degrees
W_CATCH = 420.0                        # speed when the fist closes on it


def _omega(t, phi):
    if t < T_REL:
        return 0.0
    if phi < 180.0:
        return W1 * _smooth(t, T_REL, T_REL + RAMP) ** 0.6
    if phi < 360.0:
        return W2
    w = W3 + (W3_END - W3) * (phi - 360.0) / 360.0
    rem = 720.0 - phi
    if rem < CATCH_DEG:
        w = W_CATCH + (w - W_CATCH) * (rem / CATCH_DEG) ** 0.7
    return w


def _integrate():
    dt = 1.0 / 2400.0
    t, phi = 0.0, 0.0
    hits = {}
    out = [(0.0, 0.0)]
    while t < LENGTH and phi < 720.0:
        phi_n = min(720.0, phi + _omega(t, phi) * dt)
        for mark in (180.0, 360.0, 720.0):
            if phi < mark <= phi_n:
                hits[mark] = t + dt * (mark - phi) / max(phi_n - phi, 1e-9)
        phi = phi_n
        t += dt
        out.append((t, phi))
    return out, hits


_PROFILE, _HITS = _integrate()
T_HIT1, T_HIT2, T_CATCH = _HITS[180.0], _HITS[360.0], _HITS[720.0]


def _phi(t):
    if t <= 0.0:
        return 0.0
    if t >= _PROFILE[-1][0]:
        return _PROFILE[-1][1]
    i = min(len(_PROFILE) - 2, int(t * 2400.0))
    while i > 0 and _PROFILE[i][0] > t:
        i -= 1
    while i < len(_PROFILE) - 2 and _PROFILE[i + 1][0] < t:
        i += 1
    (t0, p0), (t1, p1) = _PROFILE[i], _PROFILE[i + 1]
    u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
    return p0 + (p1 - p0) * u


def chain(t):
    """-> (a, b, latch, twirl_deg) at time t."""
    phi = _phi(t)
    if phi < 180.0:
        a, b, tw = 1.0, 1.0 - phi / 180.0, 0.0
    elif phi < 360.0:
        a, b, tw = 1.0 - (phi - 180.0) / 180.0, 0.0, 0.0
    else:
        a, b, tw = 0.0, 0.0, phi - 360.0
    # rebounds after each impact (kept inside [0, 1])
    b += _bump(t, T_HIT1, 0.10, 0.06)
    a += _bump(t, T_HIT2, 0.09, 0.05)
    b += _bump(t, T_HIT2, 0.12, 0.09)
    a += _bump(t, T_CATCH, 0.10, 0.035)
    b += _bump(t, T_CATCH, 0.13, 0.10)
    a, b = min(1.0, max(0.0, a)), min(1.0, max(0.0, b))
    # latch: pops open, jiggles at the impacts, flicks shut after the catch
    if t < T_LATCH0:
        latch = 0.0
    elif t < T_LATCH1:
        u = (t - T_LATCH0) / (T_LATCH1 - T_LATCH0)
        latch = 1.0 - (1.0 - u) ** 3
    else:
        latch = 1.0
    latch -= _bump(t, T_HIT1, 0.08, 0.15) + _bump(t, T_HIT2, 0.08, 0.18)
    t_shut = T_CATCH + 0.02
    if t >= t_shut:
        u = min(1.0, (t - t_shut) / 0.04)
        latch = 1.0 - u * u
        latch += _bump(t, t_shut + 0.04, 0.08, 0.08)
    return a, b, min(1.0, max(0.0, latch)), tw


# ---------------------------------------------------------------------------
# knife slide in the fist: held near the butt of A for the opening, the fist
# chokes up to the pins (common.GRIP) while the blade swings out
# ---------------------------------------------------------------------------
SLIDE = 0.30                           # studs along the knife +Y (pins out)
_KY = (0.94, 0.342, 0.0)               # knife +Y in the hand frame at GRIP


def knife_pos(t):
    s = SLIDE * (1.0 - _smooth(t, T_HIT1 - 0.02, T_HIT2 + 0.01))
    return _add(common.GRIP["pos"], tuple(s * k for k in _KY))


# ---------------------------------------------------------------------------
# hand: sparse parameter keys + procedural layers
# ---------------------------------------------------------------------------
_OFF = common.OFFSCREEN
T_DIP = 0.90                           # the fist bottoms out after the catch
_TAN = math.tan(math.radians(35.0))


def scr(x, y, d):
    """screen point (0..1, 0 = top left, 16:9, 70 deg FOV) at depth d -> viewmodel pos."""
    return ((x - 0.5) * 2.0 * d * _TAN * 16.0 / 9.0, d, (0.5 - y) * 2.0 * d * _TAN)


def _hand_keys():
    """(t, hand pos, spin, tilt, d_rot, d_elbow) - pos absolute (viewmodel),
    spin / tilt in screen axes on top of IDLE R_rot + d_rot."""
    tc = T_CATCH
    z3 = (0.0, 0.0, 0.0)
    return [
        (0.0, _OFF["R_pos"], 0.0, 0.0, _sub(_OFF["R_rot"], I["R_rot"]), _sub(_OFF["R_elbow"], I["R_elbow"])),
        # rise, elbow leading, wrist still dropped
        (0.10, scr(0.735, 0.92, 2.77), -14.0, 0.0, (-24.0, 0.0, -4.0), (0.05, 0.0, 0.10)),
        # top of the rise: cocked clockwise, closed knife standing up
        (0.215, scr(0.705, 0.765, 2.88), -32.0, 0.0, z3, (-0.20, 0.0, -0.05)),
        # snap counter-clockwise and stop (hand jerks a touch left / down)
        (0.275, scr(0.680, 0.800, 2.93), 14.0, 0.0, z3, (-0.12, 0.0, -0.10)),
        # recoil, then lift to drive the blade over the top
        (0.34, scr(0.675, 0.785, 2.92), 3.0, 0.0, z3, (-0.12, 0.0, -0.05)),
        (0.46, scr(0.656, 0.705, 2.84), 5.0, 0.0, z3, (-0.06, 0.0, 0.0)),
        # twirl: hand held up (the stir circle is layered on top)
        (0.60, scr(0.650, 0.685, 2.80), 0.0, 10.0, z3, (-0.04, 0.0, 0.02)),
        (tc, scr(0.655, 0.700, 2.82), 2.0, 4.0, z3, (-0.04, 0.0, 0.0)),
        # catch: the spinning knife carries the fist down, rolling the blade
        # towards edge-on, then the fist glides up-right into idle
        (tc + 0.07, scr(0.662, 0.785, 2.88), 8.0, 10.0, z3, (-0.03, 0.0, -0.03)),
        (T_DIP, scr(0.666, 0.852, 2.94), 10.0, 20.0, z3, (-0.04, 0.0, -0.04)),
        (1.12, scr(0.6865, 0.796, 2.95), -0.8, -1.0, z3, (0.0, 0.0, 0.0)),
        (LENGTH, I["R_pos"], 0.0, 0.0, z3, z3),
    ]


def _stir(t):
    """small circle of the hand leading the twirl by ~90 deg (drives the
    spin like a pen spun round a finger), faded in / out; -> (d_pos, spin)."""
    if not (T_HIT2 - 0.03 < t < T_CATCH + 0.02):
        return (0.0, 0.0, 0.0), 0.0
    w = _smooth(t, T_HIT2 - 0.03, T_HIT2 + 0.06) * (1.0 - _smooth(t, T_CATCH - 0.08, T_CATCH + 0.02))
    tw = math.radians(_phi(t) - 360.0 + 90.0)
    r = 0.06 * w
    # CCW on screen: x = cos, z = sin
    return (r * math.cos(tw), 0.0, r * math.sin(tw)), 4.0 * w * math.sin(tw)


def build():
    a = common.new_anim("bf_draw", LENGTH, description="Butterfly draw: rise, flick open, twirl, catch, settle")

    # -- exact start / end poses ---------------------------------------------
    common.key_offscreen(a, 0.0)
    a.knife(0.0, pos=knife_pos(0.0))
    common.key_idle(a, LENGTH, knife_turns=(-360.0, 0.0, 0.0))

    # -- hand: bake the parameter splines + layers at 60 fps -------------------
    ch = {k: Channel(k, 3) for k in ("pos", "rot", "drot", "delbow")}
    for t, pos, sp, tl, dr, de in _hand_keys():
        tg = "flat" if t in (0.0, LENGTH) else "auto"
        ch["pos"].add(t, pos, "smooth", tg)
        ch["rot"].add(t, (sp, tl, 0.0), "smooth", tg)
        ch["drot"].add(t, dr, "smooth", tg)
        ch["delbow"].add(t, de, "smooth", tg)
    n = int(round(LENGTH * FPS))
    for i in range(1, n):
        t = i / FPS
        sp, tl, _ = ch["rot"].eval(t)
        sdp, ssp = _stir(t)
        rot = spun(_add(I["R_rot"], ch["drot"].eval(t)), sp + ssp, tl)
        a.hand("R", t, pos=_add(ch["pos"].eval(t), sdp), rot=rot, elbow=_add(I["R_elbow"], ch["delbow"].eval(t)),
               shoulder=(0.0, 0.0, 0.0), interp="linear")

    # -- knife + handles: momentum chain at 60 fps -----------------------------
    gx, gy, gz = common.GRIP["rot"]
    for i in range(1, n):
        t = i / FPS
        av, bv, lv, tw = chain(t)
        a.bf(t, av, bv, lv, interp="linear")
        a.knife(t, pos=knife_pos(t), rot=(gx - tw, gy, gz), interp="linear")

    # -- camera: tiny kicks on the flick and the catch (deg: pitch, roll, yaw)
    tc = T_CATCH
    a.cam(0.22, rot=(0.0, 0.0, 0.0))
    a.cam(0.27, rot=(0.20, 0.25, -0.10))
    a.cam(0.40, rot=(-0.04, -0.04, 0.02))
    a.cam(0.50, rot=(0.0, 0.0, 0.0))
    a.cam(tc - 0.01, rot=(0.0, 0.0, 0.0))
    a.cam(tc + 0.04, rot=(-0.28, -0.20, 0.08))
    a.cam(tc + 0.20, rot=(0.04, 0.03, -0.01))
    a.cam(tc + 0.34, rot=(0.0, 0.0, 0.0))

    # -- markers ---------------------------------------------------------------
    a.marker(0.0, "Sound", "deploy")
    a.marker(T_REL, "Sound", "flip")
    a.marker(tc, "Sound", "latch")
    a.marker(T_DIP, "Sound", "catch")
    return a
