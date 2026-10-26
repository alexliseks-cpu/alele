"""
Butterfly ATTACK 2 - alternate light slash (backhand, draft v1).

Mirror of attack1's timing envelope in the opposite direction: a short
backhand cock up-left (hand comes in towards the centre, tip dips back),
a fast slash from upper left to lower right with the tip whipping up as the
hand decelerates, follow-through low right, then an ease-out glide back up
into IDLE.  Alternating attack1 / attack2 draws an X across the view.
"""

from ..core import Channel
from . import common
from .attack1 import scr, to_scr, spun, _add

LENGTH = 0.62
FPS = 60.0
I = common.IDLE

IDLE_SCR = to_scr(I["R_pos"])
Z3 = (0.0, 0.0, 0.0)

# t, screen (x, y, depth), spin, tilt, turn, d_rot (pitch, yaw, roll), d_elbow, shoulder
#   spin + = counter-clockwise on screen (tip dips), - = tip rises
KEYS = [
    (0.000, IDLE_SCR, 0.0, 0.0, 0.0, Z3, Z3, Z3),
    # anticipation: backhand cock - hand in towards the centre and up, tip dips back
    (0.100, (0.585, 0.740, 2.74), 20.0, 3.0, 0.0, (0.0, -3.0, 10.0), (0.05, 0.0, 0.05), (-0.10, 0.0, 0.06)),
    # slash starts: hand leads right, the knife lags (tip still dipped)
    (0.125, (0.605, 0.745, 2.70), 24.0, 2.0, 0.0, (0.0, -3.0, 10.0), (0.05, -0.05, 0.0), (-0.08, 0.04, 0.06)),
    # blade crossing the screen centre (Hit)
    (0.160, (0.680, 0.775, 2.66), 6.0, 0.0, 0.0, (0.0, 0.0, 3.0), (0.0, 0.0, -0.05), (0.0, 0.08, 0.04)),
    # whip through: tip catches up and rises
    (0.195, (0.770, 0.830, 2.60), -18.0, -2.0, 0.0, (0.0, 0.0, -6.0), (0.05, 0.0, -0.10), (0.06, 0.08, 0.0)),
    (0.230, (0.830, 0.870, 2.56), -32.0, -3.0, 0.0, (0.0, 0.0, -10.0), (0.08, 0.0, -0.10), (0.08, 0.06, 0.0)),
    # follow-through end
    (0.270, (0.848, 0.885, 2.57), -36.0, -3.0, 0.0, (0.0, 0.0, -11.0), (0.08, 0.0, -0.10), (0.08, 0.04, 0.0)),
    # recovery: settle down and glide back up-left
    (0.320, (0.830, 0.900, 2.66), -29.0, -2.0, 0.0, (0.0, 0.0, -8.0), (0.06, 0.0, -0.08), (0.06, 0.02, 0.0)),
    (0.410, (0.740, 0.865, 2.86), -9.0, 0.0, 0.0, (0.0, 0.0, -3.0), (0.02, 0.0, -0.03), (0.02, 0.0, 0.0)),
    # tiny overshoot up-left, then settle
    (0.490, (0.676, 0.790, 2.965), 2.5, 0.5, 0.0, (0.0, 0.0, 1.0), Z3, Z3),
    (LENGTH, IDLE_SCR, 0.0, 0.0, 0.0, Z3, Z3, Z3),
]

T_SWING = 0.11
T_HIT = 0.16


def build():
    a = common.new_anim("bf_attack2", LENGTH, description="Butterfly light slash (backhand): upper left to lower right")
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

    # camera kick in the slash direction (pitch, roll, yaw deg): down / right
    a.cam(0.14, rot=Z3, interp="out")
    a.cam(0.19, rot=(-0.9, 0.4, -0.6))
    a.cam(0.33, rot=(0.15, -0.08, 0.10))
    a.cam(0.48, rot=Z3)

    a.marker(T_SWING, "Sound", "swing")
    a.marker(T_HIT, "Hit", "light")
    return a
