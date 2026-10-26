"""
kr_draw - CS2-style karambit deploy (R15 blocky arm, no fingers).

No fingers exist, so the finger spin is sold with knife + wrist motion: while
the karambit spins, the hand is turned thumb-up with the palm towards the
camera (CS2's finger-spin pose) and the finger ring rides just off the palm
face at its thumb edge, ring axis ~ palmar.  The knife whirls in a plane
parallel to the palm face, on the camera side of the hand/forearm blocks, so
the chunky arm never hides or cuts it.  The spin runs counter-clockwise on
screen (like CS2's closing inspect spin) so the catch can roll on with it:
at 6 o'clock the hand pronates ~75 deg (also counter-clockwise on screen)
while the knife keeps turning a little, the ring rolls round the hand's
long axis onto the thumb side and the handle settles into the fist
(hand-local slerp into common.GRIP).

Beats (seconds, 60 fps grid):
  0.00        off screen (common.OFFSCREEN), knife loose on the "finger".
  0.00-0.22   RISE: the hand swings up out of the bottom-right corner, hooks
              up-right at the top and twists thumb-up; the knife trails.
  0.12-0.67   SPIN: the hand brakes, the karambit whips round: 2 turns about
              the ring axis (~1560 deg/s peak, 1375 average, constant through the middle,
              easing ~35 % into the catch).  The hand "stirs" a small circle
              90 deg ahead of the knife (what keeps a real finger spin going)
              and drifts down-left.
  0.67-0.77   CATCH at 6 o'clock: pronate + squeeze, handle into the fist,
              0.35 deg camera kick.
  0.77-1.18   GLIDE + SETTLE: diagonal ease-out down-left into the idle spot,
              tiny overshoot, exactly common.IDLE at the end.
Markers: Sound deploy (0.00) / spin (whip) / catch.
"""

import math

from mathutils import Euler, Matrix, Vector

from ..core import Anim
from ... import skeleton as sk
from . import common as C

FR = 1.0 / 60.0
LENGTH = 71 * FR                      # 1.183 s

# --- knife on the implied finger (hand semantic frame) ----------------------
SPIN_PIVOT = (0.30, 0.05, 0.64)       # ring centre: just off the palm face, thumb edge
SPIN_YZ = (-75.0, 0.0)                # knife X (ring axis) = palmar tilted 15 deg radial
# theta = knife rot X while spinning.  Handle direction in the hand frame is
# (-.966 sin th, cos th, .259 sin th): 0 = distal (screen left), 90 = hanging
# along the pinky side (down), 180 = proximal (right), 270 = up.  Increasing
# theta = counter-clockwise on screen.
TH_START = 90.0 - 720.0 - 22.0        # off screen: trailing a little
TH_TRAIL = 90.0 - 720.0 - 36.0        # max lag while the hand hooks up-right
TH_CATCH = 90.0                       # hanging again after 2 turns

F_TRAIL = 7                           # frames (60 fps)
F_APEX = 13
F_CATCH = 40
F_GRIPPED = 46

# --- hand path (viewmodel space, studs / deg) -------------------------------
P_LOW = (2.05, 3.05, -1.55)           # coming up the right side
R_LOW = (4.0, 20.0, 42.0)
P_APEX = (2.25, 3.45, -0.60)          # top of the rise, right edge of the view (like CS2)
R_APEX = (14.0, 24.0, 6.0)            # thumb up, palm to the camera, fingers forward-left
P_SPIN_END = (2.14, 3.40, -0.70)      # drifted down-left while spinning
R_SPIN_END = (16.0, 25.0, 11.0)
STIR = 0.035                          # stud radius of the stirring circle
WOBBLE = (2.0, 1.5)                   # deg pitch / yaw wrist rock at the spin rate
SH_SPIN = (1.00, 0.80, 0.10)          # shoulder reaches forward/right: straight wrist, arm clear of the knife
EL_SPIN = (1.00, 0.0, 0.20)

R_CAUGHT = (33.0, 31.0, 87.0)         # pronated into the grip, knuckles up
F_OVER = 61                           # glide ends a hair past idle (overshoot) ...
SETTLE_DPOS = (-0.014, 0.0, -0.018)   # ... continuing the down-left glide
SETTLE_DROT = (-1.2, 0.4, 0.8)


# ---------------------------------------------------------------------------
def _speed(t):
    """relative knife angular speed after the whip."""
    t0, t1 = F_TRAIL * FR, F_CATCH * FR
    if t <= t0:
        return 0.0
    if t < t0 + 0.09:
        u = (t - t0) / 0.09
        return u * u * (3 - 2 * u)
    if t < t1 - 0.12:
        return 1.0
    u = (t - (t1 - 0.12)) / 0.12
    return 1.0 - 0.35 * u * u * (3 - 2 * u)


def _theta_table():
    t0, t1 = F_TRAIL * FR, F_CATCH * FR
    sub = 20
    acc, tab = 0.0, {}
    for f in range(F_TRAIL, F_CATCH + 1):
        tab[f] = acc
        for k in range(sub):
            acc += _speed(f * FR + (k + 0.5) * FR / sub) * FR / sub
    scale = (TH_CATCH - TH_TRAIL) / tab[F_CATCH]
    return {f: TH_TRAIL + v * scale for f, v in tab.items()}, scale   # scale = peak deg/s


THETA, OMEGA = _theta_table()


def theta_f(f):
    if f <= F_TRAIL:
        u = f / F_TRAIL
        return TH_START + (TH_TRAIL - TH_START) * (1 - (1 - u) ** 2)   # ease out into max lag
    return THETA[f]


def _m3(rot):
    return Euler([math.radians(x) for x in rot], "XYZ").to_matrix()


def _lerp(p0, p1, w):
    return tuple(x + (y - x) * w for x, y in zip(p0, p1))


def _smooth(u):
    return u * u * (3 - 2 * u)


def _handle_dir(th):
    th = math.radians(th)
    return Vector((-0.966 * math.sin(th), math.cos(th), 0.259 * math.sin(th)))


def _spin_hand(f):
    """hand pos/rot during the spin: base drift + stir circle."""
    w = _smooth((f - F_APEX) / (F_CATCH - F_APEX))
    p, r = _lerp(P_APEX, P_SPIN_END, w), _lerp(R_APEX, R_SPIN_END, w)
    t = f * FR
    fade = max(0.0, min(1.0, (t - F_APEX * FR) / 0.08, (F_CATCH - f) * FR / 0.06))
    lead = theta_f(f) + 90.0                   # 90 deg ahead of the knife along its travel
    off = sk.hand_rotation("R", r) @ _handle_dir(lead) * (STIR * fade)
    # the wrist rocks with the stir (small pitch / yaw wobble at the spin rate)
    ph = math.radians(lead)
    r = (r[0] + WOBBLE[0] * fade * math.sin(ph), r[1] + WOBBLE[1] * fade * math.cos(ph), r[2])
    return tuple(pc + oc for pc, oc in zip(p, off)), r


def _cyl(p):
    """hand-local point -> (angle about distal from +palmar towards +radial, radius, y)."""
    x, y, z = p
    return math.atan2(x, z), math.hypot(x, z), y


def build():
    a = Anim("kr_draw", "karambit", length=LENGTH, priority="Action",
             description="Karambit draw: rises from the bottom-right, 2 finger spins, rolling catch, glide to idle")
    I = C.IDLE

    # ---- start: off screen --------------------------------------------------
    C.key_pose(a, 0.0, C.OFFSCREEN, knife=False, tangent="auto")
    a.knife(0.0, anchor=I["anchor"])
    C.key_left_hidden(a, 0.0)
    C.key_left_hidden(a, LENGTH)
    C.key_cam_zero(a, 0.0)
    a.marker(0.0, "Sound", "deploy")

    # ---- rise: up the right side, hook up-right, twist thumb-up --------------
    a.hand("R", 6 * FR, pos=P_LOW, rot=R_LOW, shoulder=_lerp(C.OFFSCREEN["R_shoulder"], SH_SPIN, 0.6),
           elbow=_lerp(C.OFFSCREEN["R_elbow"], EL_SPIN, 0.6))
    a.hand("R", F_APEX * FR, pos=P_APEX, rot=R_APEX, shoulder=SH_SPIN, elbow=EL_SPIN)

    # ---- spin (dense keys on the bake grid) ---------------------------------
    for f in range(F_APEX + 1, F_CATCH + 1):
        p, r = _spin_hand(f)
        a.hand("R", f * FR, pos=p, rot=r)
    a.hand("R", F_CATCH * FR, shoulder=SH_SPIN, elbow=EL_SPIN)
    for f in range(0, F_CATCH + 1):
        a.knife(f * FR, pos=SPIN_PIVOT, rot=(theta_f(f),) + SPIN_YZ)
    a.marker((F_TRAIL + 2) * FR, "Sound", "spin")
    a.cam(F_TRAIL * FR, rot=(0.0, 0.0, 0.0))
    a.cam((F_TRAIL + 4) * FR, rot=(0.25, 0.0, -0.15))
    a.cam((F_TRAIL + 16) * FR, rot=(0.0, 0.0, 0.0), tangent="flat")

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
        ks = _smooth(u)                             # knife: keeps spinning first, then seats
        a.hand("R", f * FR, rot=_lerp(r0, R_CAUGHT, hr))
        if i == n:
            a.knife(f * FR, pos=C.GRIP["pos"], rot=C.GRIP["rot"])
            break
        th = TH_CATCH + w_c * (tau - tau * tau / (2 * T))
        q_spin = _m3((th,) + SPIN_YZ).to_quaternion()
        e = q_spin.slerp(q_grip, ks).to_matrix().to_euler("XYZ", prev)
        prev = e
        # the ring rolls round the hand's long axis as fast as the hand pronates
        # (the two cancel: the ring hardly turns in view space)
        ang = a0 + (a1 - a0) * hr
        rad = rad0 + (rad1 - rad0) * hr
        pos = (rad * math.sin(ang), y0 + (y1 - y0) * hr, rad * math.cos(ang))
        a.knife(f * FR, pos=pos, rot=tuple(math.degrees(x) for x in e))
    a.marker((F_CATCH + 3) * FR, "Sound", "catch")      # handle seats in the palm
    a.cam(F_CATCH * FR, rot=(0.0, 0.0, 0.0))
    a.cam((F_CATCH + 3) * FR, rot=(-0.35, 0.0, 0.15))
    a.cam((F_CATCH + 14) * FR, rot=(0.0, 0.0, 0.0), tangent="flat")

    # ---- glide: one ease-out stroke from the catch spot down-left into idle ----
    # (CS2: fastest right after the catch, then decelerating), a hair past idle
    # at F_OVER, then key_settle's flat landing on IDLE.
    over = C.pose_offset(R_pos=SETTLE_DPOS, R_rot=SETTLE_DROT)
    for f in range(F_CATCH + 1, F_OVER + 1):
        v = (f - F_CATCH) / (F_OVER - F_CATCH)
        g = 1 - (1 - v) ** 2.4
        a.hand("R", f * FR, pos=_lerp(p0, over["R_pos"], g),
               shoulder=_lerp(SH_SPIN, I["R_shoulder"], g), elbow=_lerp(EL_SPIN, I["R_elbow"], g))
        if f > F_GRIPPED:
            g1 = 1 - (1 - (F_GRIPPED - F_CATCH) / (F_OVER - F_CATCH)) ** 2.4
            w = (g - g1) / (1 - g1)
            a.hand("R", f * FR, rot=_lerp(R_CAUGHT, over["R_rot"], w))
    C.key_settle(a, F_OVER * FR, LENGTH, dpos=SETTLE_DPOS, drot=SETTLE_DROT)
    return a
