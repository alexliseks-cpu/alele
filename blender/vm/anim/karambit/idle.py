"""
kr_idle - CS2 karambit idle loop (5.0 s, loops seamlessly).

CS2's karambit idle is a still pose; all the life here is deliberately tiny:
  * breathing: two breaths per loop (2.5 s each, inhale 40 % / exhale 60 %,
    the second one ~20 % shallower so the loop does not read as a metronome).
    On the inhale the fist rises ~0.02 stud and drifts 0.01 towards the
    camera, the knuckles lift ~0.65 deg and the forearm rolls out a hair.
  * overlap: the knife pivots on the finger ring ~0.5 deg, 0.18 s behind the
    hand (a loose ring "settling" after each breath).
  * wrist micro-motion: three slow sine layers (periods 5/3, 5/4 and 5/7 s,
    all whole cycles of the loop) of +-0.15..0.25 deg and +-0.003 stud.
All layers are periodic in the loop length and exactly zero at t = 0, so the
first frame == the last frame == common.IDLE (other clips end there and the
runtime blends straight into this loop).  Camera stays perfectly still.
"""

import math

from ..core import Anim
from . import common as C

LENGTH = 5.0
BREATHS = ((0.0, 2.5, 1.0), (2.5, 5.0, 0.8))   # (start, end, amplitude)
INHALE = 0.40                                  # fraction of a breath spent inhaling
STEP = 1.0 / 12.0                              # key spacing for the sampled layers

# offsets at the top of a full breath
BREATH_POS = (0.005, -0.010, 0.020)
BREATH_ROT = (0.65, 0.2, -0.45)                # pitch (knuckles up), yaw, roll (supinate a hair)
BREATH_ELBOW = (0.0, 0.0, 0.015)
KNIFE_LAG = 0.18                               # s
KNIFE_PIVOT = 0.6                              # deg about the ring axis (peak trailing angle)

# wrist micro-motion: (cycles per loop, amplitude, phase) per component
MICRO_ROT = (
    ((3, 0.18, 0.4), (7, 0.07, 1.9)),          # pitch
    ((4, 0.15, 2.3), (7, 0.05, 0.7)),          # yaw
    ((3, 0.12, 4.1), (4, 0.10, 5.2)),          # roll
)
MICRO_POS = (
    ((4, 0.0025, 1.1),),
    ((3, 0.0015, 2.9),),
    ((3, 0.0030, 5.6), (7, 0.0010, 0.3)),
)


def breath(t):
    """0 at rest, 1 at the top of a full breath; periodic in LENGTH."""
    t %= LENGTH
    for t0, t1, amp in BREATHS:
        if t0 <= t < t1 or (t1 == LENGTH and t >= t0):
            ph = (t - t0) / (t1 - t0)
            # warp so the inhale takes INHALE of the breath; the kink sits at
            # the extremes where the cosine's slope is zero -> C1 smooth
            w = ph / INHALE * 0.5 if ph < INHALE else 0.5 + (ph - INHALE) / (1.0 - INHALE) * 0.5
            return amp * (0.5 - 0.5 * math.cos(2.0 * math.pi * w))
    return 0.0


def micro(layers, t):
    v = 0.0
    for k, amp, phase in layers:
        w = 2.0 * math.pi * k / LENGTH
        v += amp * (math.sin(w * t + phase) - math.sin(phase))
    return v


def build():
    a = Anim("kr_idle", "karambit", length=LENGTH, loop=True, priority="Idle",
             description="Karambit idle: CS2 still pose with subtle breathing and wrist micro-motion")
    C.key_idle(a, 0.0, tangent="auto")
    n = int(round(LENGTH / STEP))
    I = C.IDLE
    for i in range(n + 1):
        t = min(i * STEP, LENGTH)
        if i == n:      # exact loop closure
            C.key_idle(a, LENGTH, tangent="auto")
            break
        b = breath(t)
        bk = breath(t - KNIFE_LAG)
        pos = tuple(I["R_pos"][j] + BREATH_POS[j] * b + micro(MICRO_POS[j], t) for j in range(3))
        rot = tuple(I["R_rot"][j] + BREATH_ROT[j] * b + micro(MICRO_ROT[j], t) for j in range(3))
        elb = tuple(I["R_elbow"][j] + BREATH_ELBOW[j] * b for j in range(3))
        # knife_rot[0] > 0 = blade end down: on the inhale (hand rising) the far end
        # trails a little, then catches up on the exhale
        kr = (I["knife_rot"][0] + KNIFE_PIVOT * (b - bk) / 0.25, I["knife_rot"][1], I["knife_rot"][2])
        if i > 0:
            a.hand("R", t, pos=pos, rot=rot, elbow=elb)
            a.knife(t, rot=kr)
    return a
