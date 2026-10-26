"""
Butterfly HEAVY - forward stab (draft v1).

Wind-up (0 - 0.30 s): the hand pulls back / up towards the camera and the
wrist turns the tip forward so it aims at the screen centre, with a short
coil at the end.  Thrust (0.30 - 0.40 s): the arm drives forward and in
towards the centre, the shoulder pivot lunging (R_shoulder) for extra reach;
Hit at full extension.  Short hold with a small recoil, then the hand pulls
back, the tip turns back across the view and the pose settles into IDLE.
"""

from ..core import Channel
from . import common
from .attack1 import scr, to_scr, spun, _add

LENGTH = 1.00
FPS = 60.0
I = common.IDLE

IDLE_SCR = to_scr(I["R_pos"])
Z3 = (0.0, 0.0, 0.0)

# t, screen (x, y, depth), spin, tilt, turn, d_rot (pitch, yaw, roll), d_elbow, shoulder
#   turn - = tip away from the camera (forward), tilt + = top towards the camera
KEYS = [
    (0.000, IDLE_SCR, 0.0, 0.0, 0.0, Z3, Z3, Z3),
    # wind-up: pull back / up, tip turning forward
    (0.120, (0.715, 0.775, 2.76), 2.0, 6.0, -22.0, Z3, (0.05, -0.05, -0.05), (0.02, -0.03, 0.02)),
    (0.250, (0.750, 0.730, 2.47), 5.0, 15.0, -50.0, Z3, (0.10, -0.10, -0.10), (0.05, -0.08, 0.05)),
    # coil (tension before the thrust)
    (0.300, (0.758, 0.722, 2.42), 6.0, 16.0, -52.0, Z3, (0.10, -0.12, -0.10), (0.06, -0.10, 0.06)),
    # thrust towards the screen centre, arm extended, shoulder lunging
    (0.365, (0.665, 0.748, 3.12), -6.0, 10.0, -47.0, Z3, (0.0, 0.0, -0.05), (-0.03, 0.24, 0.08)),
    # full extension (Hit)
    (0.400, (0.645, 0.755, 3.30), -10.0, 10.0, -45.0, Z3, (-0.05, 0.0, 0.0), (-0.05, 0.30, 0.10)),
    # short hold with a small recoil
    (0.480, (0.652, 0.760, 3.25), -9.0, 10.0, -44.0, Z3, (-0.05, 0.0, 0.0), (-0.04, 0.26, 0.09)),
    # pull back, tip turning back across the view
    (0.580, (0.675, 0.780, 3.12), -5.0, 6.0, -34.0, Z3, (0.0, 0.0, -0.03), (-0.02, 0.15, 0.05)),
    (0.740, (0.700, 0.812, 2.90), 1.0, 1.0, -8.0, Z3, (0.02, 0.0, -0.02), (0.0, 0.0, 0.0)),
    # tiny overshoot, then settle
    (0.860, (0.690, 0.806, 2.935), -0.5, -0.5, 2.0, Z3, Z3, Z3),
    (LENGTH, IDLE_SCR, 0.0, 0.0, 0.0, Z3, Z3, Z3),
]

T_SWING = 0.31
T_HIT = 0.40


def build():
    a = common.new_anim("bf_heavy", LENGTH, description="Butterfly heavy: wind-up and forward stab to the screen centre")
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

    # camera: slight lift on the wind-up, kick with the impact, recover
    a.cam(0.25, rot=(0.5, 0.2, -0.2))
    a.cam(0.34, rot=(0.3, 0.1, -0.1), interp="out")
    a.cam(0.42, rot=(-2.4, -0.9, 0.9))
    a.cam(0.60, rot=(0.3, 0.1, -0.1))
    a.cam(0.80, rot=Z3)

    a.marker(T_SWING, "Sound", "swing_heavy")
    a.marker(T_HIT, "Hit", "heavy")
    return a
