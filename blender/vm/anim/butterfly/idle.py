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
    (hand x / z, yaw, roll as a mix of the 1st-3rd loop harmonics).
  * wrist micro motion: tiny higher harmonics on the hand rotation
    (+-0.1-0.2 deg), loop-safe by construction.
The knife stays in the idle grip, handles closed together (bf open), camera
still.
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
    """sum a_k sin(k w t): zero at t = 0, periodic over LENGTH."""
    return sum(a * math.sin(k * W * t) for k, a in coefs)


def offsets(t):
    b = breath(t)
    b_rot = breath(t - 0.12)            # wrist follows the chest a beat later
    b_roll = breath(t - 0.20)
    d_pos = (
        0.004 * b + harm(t, ((1, 0.012), (2, -0.003))),
        -0.010 * b + harm(t, ((1, 0.004), (3, 0.002))),
        0.028 * b + harm(t, ((1, -0.004), (2, 0.006))),
    )
    d_rot = (
        0.9 * b_rot + harm(t, ((2, 0.20), (5, 0.10), (7, 0.07))),     # pitch
        harm(t, ((1, 0.50), (3, 0.12), (8, 0.06))),                    # yaw
        -0.55 * b_roll + harm(t, ((1, -0.70), (2, 0.25), (6, 0.09))),  # roll
    )
    d_elbow = (harm(t, ((1, 0.015),)), 0.0, -0.02 * b)
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
