"""
Butterfly idle loop (6.0 s, loops, priority Idle).

Everything is an offset on top of common.IDLE built from loop-periodic curves
that are exactly zero at t = 0 (so the loop starts / ends on the base pose and
the joint end -> start is seamless in value and velocity):

  * breathing: two asymmetric breaths (3.0 s each: inhale 1.1 s, exhale
    1.6 s, rest 0.3 s; the 2nd one a little shallower).  Inhale lifts the hand
    and draws it back a touch; the wrist pitch / roll follow 0.12-0.2 s later
    (overlap), the elbow sinks slightly.
  * weight shift: one slow figure-of-eight-ish drift over the whole loop
    (hand x / z, yaw, roll as a mix of the 1st-3rd loop harmonics with
    different phases, each shifted so it is 0 at t = 0).
  * wrist micro motion: tiny higher harmonics on the hand rotation
    (+-0.05-0.15 deg), loop-safe by construction.
The viewmodel moves almost rigidly (CS2 master idle f408-429: ~1.2 % of the
screen height peak to peak, rotation <= ~0.5 deg): here the hand rises
~0.045 stud (~8-9 px at 720p) per breath and drifts ~4 px sideways over the
loop.  The knife stays in the idle grip, handles together (bf open), no
fidgets, camera still.
"""

import math

from . import common

LENGTH = 6.0
STEP = 0.1                       # key spacing of the sampled curves (s)
W = 2.0 * math.pi / LENGTH       # loop fundamental

# breath: (start, inhale, exhale, rest) and depth per breath
BREATHS = ((0.0, 1.1, 1.6, 0.3, 1.0), (3.0, 1.1, 1.6, 0.3, 0.8))


def breath(t):
    """0 at rest .. depth at full inhale; C1, periodic over LENGTH."""
    t = t % LENGTH
    for t0, tin, tout, _rest, depth in BREATHS:
        u = t - t0
        if 0.0 <= u < tin:
            return depth * (0.5 - 0.5 * math.cos(math.pi * u / tin))
        if tin <= u < tin + tout:
            return depth * (0.5 + 0.5 * math.cos(math.pi * (u - tin) / tout))
    return 0.0


def harm(t, coefs):
    """sum a_k (sin(k w t + ph_k) - sin(ph_k)): zero at t = 0, periodic over
    LENGTH; coefs = (k, a) or (k, a, phase_deg)."""
    out = 0.0
    for c in coefs:
        k, amp = c[0], c[1]
        ph = math.radians(c[2]) if len(c) > 2 else 0.0
        out += amp * (math.sin(k * W * t + ph) - math.sin(ph))
    return out


def offsets(t):
    b = breath(t)
    b_rot = breath(t - 0.12)            # wrist follows the chest a beat later
    b_roll = breath(t - 0.20)
    d_pos = (
        0.004 * b + harm(t, ((1, 0.010), (2, -0.003, 60))),
        -0.008 * b + harm(t, ((1, 0.004, 40), (3, 0.0015))),
        0.042 * b + harm(t, ((1, -0.005, 30), (2, 0.006, -50))),
    )
    d_rot = (
        0.55 * b_rot + harm(t, ((2, 0.15, 35), (5, 0.07), (7, 0.05, 80))),      # pitch (tip lags)
        harm(t, ((1, 0.40, 25), (3, 0.10, -40), (8, 0.04))),                     # yaw
        -0.40 * b_roll + harm(t, ((1, -0.50, 50), (2, 0.18), (6, 0.06, 120))),   # roll
    )
    d_elbow = (harm(t, ((1, 0.02, 20),)), 0.0, -0.03 * b)
    return d_pos, d_rot, d_elbow


def build():
    a = common.new_anim("bf_idle", LENGTH, loop=True, priority="Idle",
                        description="Butterfly idle: breathing drift + wrist micro motion, seamless loop")
    common.key_idle(a, 0.0, tangent="auto")
    n = int(round(LENGTH / STEP))
    for i in range(1, n):
        t = i * STEP
        d_pos, d_rot, d_elbow = offsets(t)
        p = common.pose_from(d_pos=d_pos, d_rot=d_rot, d_elbow=d_elbow)
        a.hand("R", t, pos=p["R_pos"], rot=p["R_rot"], elbow=p["R_elbow"])
    common.key_idle(a, LENGTH, tangent="auto")
    return a
