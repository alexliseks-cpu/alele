"""
kr_attack1 - CS2 karambit light attack 1: horizontal right-to-left slash.

CS2 (ref f_0094-f_0124): the fist snaps out to the right in one frame, the
arm sweeps back across the view at full speed (back of the glove to the
camera, the hawkbill standing up out of the top of the fist with its concave
edge leading), leaves the lower-left edge, loops UNDER the frame and the fist
rises back in from the bottom-centre, overshoots ~3 cm right of rest, glides
back left and settles with a small nose-up tilt (knife swinging up on the
ring).  The grip never changes.  CS2's ~2 s are compressed to 0.65 s here
and the hidden arcs are pushed further out for the wider 16:9 / 70 deg view.

R15 adaptation: no fingers, so the "blade stands up" read comes purely from
the forearm rolling a further ~70 deg (roll 90 -> 160: pinky side up, back
of the hand to the camera) and yawing the fingers to the left; the knife
stays in common.GRIP and only pivots a few degrees on the ring (trailing on
the wind-up, swinging up in the tail).  The long reach to the left edge is
a shoulder lunge (torso turn) - the shoulder itself stays off screen.

Beats (seconds, 60 fps grid):
  0.00        IDLE (flat).
  0.00-0.05   COCK: snap up-right towards the right shoulder, roll begins,
              blade trailing.  Sound swing at 0.05 (start of the fast part).
  0.05-0.18   SLASH: constant top speed right -> left, path dropping ~10 deg,
              hawkbill up, concave edge leading.  Hit at the centre crossing
              (0.117).  0.5 deg camera yaw/roll kick with the cut.
  0.18-0.23   EXIT: off the lower-left edge, hard ease-out off screen.
  0.23-0.33   LOOP: drop below the bottom-left (still rolled, so the blade
              stays out of view), then under the frame back to the right,
              un-rolling to the grip.
  0.33-0.45   RISE from the bottom-centre, wrist low, ease-out into a small
              overshoot right of rest (~0.1 stud) at 0.45.
  0.45-0.65   GLIDE back left, nose-up tilt (common.TILT) with the knife
              swinging up on the ring, one-sided decay into IDLE (flat).
Markers: Sound swing (0.05), Hit light (0.117).
"""

import math

from mathutils import Matrix, Vector

from ..core import Anim, Channel
from ... import skeleton as sk
from . import common as C

FR = 1.0 / 60.0
LENGTH = 39 * FR                       # 0.65 s
I = C.IDLE
Z3 = (0.0, 0.0, 0.0)

_TAN = math.tan(math.radians(35.0))
_ASP = 16.0 / 9.0


def scr(x, y, d):
    """screen point (0..1, x right / y down, 16:9, 70 deg FOV) at depth d -> viewmodel pos."""
    return ((x - 0.5) * 2.0 * d * _TAN * _ASP, d, (0.5 - y) * 2.0 * d * _TAN)


def to_scr(p):
    x, d, z = p
    return (0.5 + 0.5 * x / (d * _TAN * _ASP), 0.5 - 0.5 * z / (d * _TAN), d)


def axes_rot(distal, palmar, near=(0.0, 0.0, 0.0)):
    """hand (pitch, yaw, roll) whose fingers point along `distal` and whose
    palm faces `palmar` (orthogonalised); of the two euler solutions (and
    their 360 deg wraps) the one closest to `near` (keeps keys continuous)."""
    d = Vector(distal).normalized()
    p = Vector(palmar)
    p = (p - d * p.dot(d)).normalized()
    M = Matrix((d.cross(p), d, p)).transposed() @ sk.R_NEUTRAL["R"].inverted()
    e = M.to_euler("YXZ")
    a = (math.degrees(e.x), math.degrees(e.z), -math.degrees(e.y))
    best = None
    for c in (a, (180.0 - a[0], a[1] + 180.0, a[2] + 180.0)):
        c = [x - 360.0 * round((x - n) / 360.0) for x, n in zip(c, near)]
        cost = sum(abs(x - n) for x, n in zip(c, near))
        if best is None or cost < best[0]:
            best = (cost, tuple(c))
    return best[1]


def _add(*vs):
    return tuple(sum(x) for x in zip(*vs))


_HANG = Vector((0.35, 0.45, 0.82)).normalized()      # = skeleton.solve_arm's elbow hang
_S0 = sk.ARM_REST["R"]["shoulder"] + Vector(I["R_shoulder"])
EL_FREE = tuple(-x for x in I["R_elbow"])            # d_elbow that cancels IDLE's elbow bias


def auto_shoulder(sp, rot, toward=(0.0, 0.0, 0.0)):
    """d_shoulder (on top of IDLE's) that lets the arm reach screen point `sp`
    with hand rot `rot` and a straight wrist: the forearm lies along the
    solver's preferred direction and the upper arm points from that elbow
    back towards the idle shoulder + `toward` (use with d_elbow = EL_FREE).
    Big values = torso turn / lunge; check the shoulder stays off screen."""
    sem = sk.hand_rotation("R", rot)
    wrist = Vector(scr(*sp)) - (sem @ sk.PART_IN_SEM["R"]) @ sk.V_HAND
    elbow = wrist - (sem.col[1] * 0.8 + _HANG * 0.2).normalized() * sk.L_LOWER
    s = elbow + (_S0 + Vector(toward) - elbow).normalized() * sk.L_UPPER
    return tuple(s - _S0)


IDLE_SCR = to_scr(I["R_pos"])
TILT_D = tuple(b - a for a, b in zip(I["R_rot"], C.TILT["R_rot"]))           # tilt rot offset
TILT_K = tuple(b - a for a, b in zip(I["knife_rot"], C.TILT["knife_rot"]))   # knife up on the ring

# frame, screen (x, y, depth), hand rot (pitch, yaw, roll), d_shoulder (on top of
# IDLE's), d_elbow, knife d_rot (on top of GRIP; [0] - = blade end up)
KEYS = [
    (0, IDLE_SCR, I["R_rot"], Z3, Z3, Z3),
    # cock: up-right towards the right shoulder, forearm yawed right, roll starting, blade trails
    (3, (0.88, 0.64, 2.05), (22.0, 12.0, 127.0), (0.30, -0.10, 0.40), (0.10, 0.0, -0.10), (8.0, 0.0, 0.0)),
    # slash: constant speed, the forearm swings across, hawkbill up, concave edge leading
    (5, (0.72, 0.645, 2.40), (12.0, 50.0, 150.0), (0.00, 0.15, 0.25), (0.0, 0.0, -0.10), (3.0, 0.0, 0.0)),
    (7, (0.50, 0.69, 2.60), (5.0, 73.0, 161.0), (-0.55, 0.30, 0.10), (-0.10, 0.0, -0.10), (-3.0, 0.0, 0.0)),
    (9, (0.27, 0.76, 2.42), (0.0, 82.0, 164.0), (-1.00, 0.30, 0.10), (-0.20, 0.0, 0.0), (-4.0, 0.0, 0.0)),
    (11, (0.06, 0.85, 2.10), (-4.0, 91.0, 165.0), (-1.55, 0.20, 0.00), (-0.30, 0.0, 0.10), (-4.0, 0.0, 0.0)),
    # exit: hard ease-out beyond the lower-left edge
    (14, (-0.08, 0.99, 1.88), (-6.0, 97.0, 160.0), (-2.00, 0.10, -0.10), (-0.30, 0.0, 0.10), (-2.0, 0.0, 0.0)),
    # loop under the frame (blade below the bottom edge), un-rolling into the grip
    (17, (-0.04, 1.50, 1.90), (2.0, 84.0, 148.0), (-1.90, 0.10, -1.00), (-0.10, 0.0, 0.0), (2.0, 0.0, 0.0)),
    (20, (0.32, 1.48, 2.20), (35.0, 45.0, 98.0), (-1.00, 0.00, -1.20), Z3, (3.0, 0.0, 0.0)),
    # rise from the bottom-centre, wrist low
    (23, (0.50, 1.08, 2.50), (48.0, 33.0, 96.0), (-0.30, -0.05, -0.10), (0.05, 0.0, -0.05), (3.0, 0.0, 0.0)),
    # overshoot right of rest, slightly high and closer
    (27, (0.695, 0.800, 2.66), (40.5, 30.0, 92.0), (0.03, 0.00, 0.01), (0.02, 0.0, 0.0), (1.0, 0.0, 0.0)),
    # glide back left + nose-up tilt, knife swinging up on the ring
    (32, (0.658, 0.812, 2.73), _add(I["R_rot"], TILT_D), Z3, Z3, TILT_K),
    (35, (IDLE_SCR[0] + 0.002, IDLE_SCR[1] - 0.003, IDLE_SCR[2]), _add(I["R_rot"], (-0.3, -1.5, -0.4)),
     Z3, Z3, (-1.5, 0.0, 0.0)),
    (39, IDLE_SCR, I["R_rot"], Z3, Z3, Z3),
]

T_SWING = 3 * FR
T_HIT = 7 * FR
CAM = [  # t, rot (pitch, roll, yaw) deg
    (T_SWING, Z3),
    (T_HIT + 3 * FR, (-0.35, -0.45, 0.55)),
    (0.30, (0.10, 0.08, -0.10)),
    (0.42, Z3),
]


def key_path(a, keys, length):
    """Interpolate the key table in screen space and key the right hand
    densely (every frame) - the shared engine of kr_attack1 / kr_attack2."""
    names = ("pos", "rot", "sh", "el", "kn")
    ch = {k: Channel(k, 3) for k in names}
    last = keys[-1][0]
    for row in keys:
        f = row[0]
        tg = "flat" if f in (0, last) else "auto"
        for k, v in zip(names, row[1:]):
            ch[k].add(f * FR, v, "smooth", tg)
    n = int(round(length / FR))
    for i in range(1, n):
        t = i * FR
        a.hand("R", t, pos=scr(*ch["pos"].eval(t)), rot=ch["rot"].eval(t),
               shoulder=_add(I["R_shoulder"], ch["sh"].eval(t)), elbow=_add(I["R_elbow"], ch["el"].eval(t)),
               interp="linear")
        a.knife(t, rot=_add(I["knife_rot"], ch["kn"].eval(t)), interp="linear")


def key_cam(a, cam):
    for t, r in cam:
        a.cam(t, rot=r, tangent="flat" if r == Z3 else "auto")


def build():
    a = Anim("kr_attack1", "karambit", length=LENGTH, priority="Action",
             description="Karambit light slash: right to left, hawkbill leading, loops under, rises into idle")
    C.key_idle(a, 0.0)
    C.key_idle(a, LENGTH)
    key_path(a, KEYS, LENGTH)
    key_cam(a, CAM)
    a.marker(T_SWING, "Sound", "swing")
    a.marker(T_HIT, "Hit", "light")
    return a
