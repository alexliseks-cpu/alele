"""
Butterfly ATTACK 1 - light primary slash (draft v1).
"""

import math

from mathutils import Euler

from ... import skeleton
from ..core import Channel
from . import common

LENGTH = 0.60
FPS = 60.0
I = common.IDLE

_TAN = math.tan(math.radians(35.0))
_ASP = 16.0 / 9.0
_NINV = skeleton.R_NEUTRAL["R"].inverted()


def scr(x, y, d):
    """screen point (0..1, 0 = top left, 16:9, 70 deg FOV) at depth d -> viewmodel pos."""
    return ((x - 0.5) * 2.0 * d * _TAN * _ASP, d, (0.5 - y) * 2.0 * d * _TAN)


def to_scr(p):
    x, d, z = p
    return (0.5 + 0.5 * x / (d * _TAN * _ASP), 0.5 - 0.5 * z / (d * _TAN), d)


def spun(rot, spin=0.0, tilt=0.0, turn=0.0):
    """Hand (pitch, yaw, roll) rotated in screen axes about the hand centre:
    spin + = counter-clockwise on screen, tilt + = top towards the camera,
    turn + = right side away from the camera."""
    R = skeleton.hand_rotation("R", rot)
    Q = skeleton.R3("Z", turn) @ skeleton.R3("X", tilt) @ skeleton.R3("Y", -spin)
    M = Q @ R @ _NINV
    base = Euler((math.radians(rot[0]), math.radians(-rot[2]), math.radians(rot[1])), "YXZ")
    e = M.to_euler("YXZ", base)
    return (math.degrees(e.x), math.degrees(e.z), -math.degrees(e.y))


def _add(*vs):
    return tuple(sum(x) for x in zip(*vs))


IDLE_SCR = to_scr(I["R_pos"])
Z3 = (0.0, 0.0, 0.0)

# t, screen (x, y, depth), spin, tilt, turn, d_rot (pitch, yaw, roll), d_elbow, shoulder
KEYS = [
    (0.000, IDLE_SCR, 0.0, 0.0, 0.0, Z3, Z3, Z3),
    # anticipation: tiny pull up-right, knife cocks up (supinate + CW)
    (0.075, (0.745, 0.735, 2.90), -24.0, 3.0, 0.0, (0.0, 4.0, -16.0), (-0.10, 0.0, -0.10), (0.05, -0.03, 0.06)),
    # slash starts: wrist leads left, knife lags (tip still trailing)
    (0.105, (0.715, 0.700, 2.82), -30.0, 3.0, 0.0, (0.0, 3.0, -14.0), (-0.15, -0.10, -0.10), (0.0, 0.0, 0.06)),
    # crossing the screen centre (Hit)
    (0.140, (0.615, 0.715, 2.64), -14.0, 2.0, 0.0, (0.0, 0.0, -4.0), (0.0, 0.0, -0.10), (-0.10, 0.05, 0.04)),
    # whip through
    (0.175, (0.515, 0.790, 2.50), 14.0, 0.0, 0.0, (0.0, 0.0, 6.0), (0.0, 0.0, -0.10), (-0.18, 0.08, 0.0)),
    (0.210, (0.450, 0.860, 2.45), 30.0, -2.0, 0.0, (0.0, 0.0, 10.0), (0.0, 0.0, -0.05), (-0.24, 0.10, 0.0)),
    # follow-through end
    (0.250, (0.425, 0.885, 2.48), 34.0, -3.0, 0.0, (0.0, 0.0, 12.0), (0.0, 0.0, -0.05), (-0.24, 0.08, 0.0)),
    # recovery: dip and glide back up-right
    (0.300, (0.460, 0.910, 2.58), 28.0, -2.0, 0.0, (0.0, 0.0, 9.0), (0.0, 0.0, -0.10), (-0.18, 0.04, 0.0)),
    (0.390, (0.600, 0.870, 2.82), 9.0, 0.0, 0.0, (0.0, 0.0, 3.0), (0.0, 0.0, -0.05), (-0.04, 0.0, 0.0)),
    # tiny overshoot up-right, then settle
    (0.470, (0.697, 0.788, 2.965), -2.5, 0.5, 0.0, (0.0, 0.0, -1.0), Z3, Z3),
    (LENGTH, IDLE_SCR, 0.0, 0.0, 0.0, Z3, Z3, Z3),
]

T_SWING = 0.085
T_HIT = 0.14


def build():
    a = common.new_anim("bf_attack1", LENGTH, description="Butterfly light slash: upper right to lower left")
    common.key_idle(a, 0.0)
    common.key_idle(a, LENGTH)

    ch = {k: Channel(k, 3) for k in ("pos", "srot", "drot", "delbow", "sh")}
    for t, sp, spin, tilt, turn, dr, de, sh in KEYS:
        tg = "flat" if t in (0.0, LENGTH) else "auto"
        ch["pos"].add(t, sp, "smooth", tg)
        ch["srot"].add(t, (spin, tilt, turn), "smooth", tg)
        ch["drot"].add(t, dr, "smooth", tg)
        ch["delbow"].add(t, de, "smooth", tg)
        ch["sh"].add(t, sh, "smooth", tg)
    n = int(round(LENGTH * FPS))
    for i in range(1, n):
        t = i / FPS
        sx, sy, sd = ch["pos"].eval(t)
        spin, tilt, turn = ch["srot"].eval(t)
        rot = spun(_add(I["R_rot"], ch["drot"].eval(t)), spin, tilt, turn)
        a.hand("R", t, pos=scr(sx, sy, sd), rot=rot, elbow=_add(I["R_elbow"], ch["delbow"].eval(t)),
               shoulder=ch["sh"].eval(t), interp="linear")

    # camera kick in the slash direction (pitch, roll, yaw deg)
    a.cam(0.12, rot=Z3, interp="out")
    a.cam(0.17, rot=(-0.9, -0.4, 0.6))
    a.cam(0.31, rot=(0.15, 0.08, -0.10))
    a.cam(0.46, rot=Z3)

    a.marker(T_SWING, "Sound", "swing")
    a.marker(T_HIT, "Hit", "light")
    return a
