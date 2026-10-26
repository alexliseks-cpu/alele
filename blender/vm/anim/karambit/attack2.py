"""
kr_attack2 - karambit light attack 2: rising backhand hook, left -> right.

The complement of kr_attack1 (same timing envelope, opposite direction): the
fist snaps down-left across the body, the hawkbill standing up out of the
fist (kr_attack1's strike silhouette), then the forearm whips clockwise
round the elbow and the fist rips up and out to the right.  The back of the
fist stays to the camera the whole way (fingers left-up -> up -> right, a
back-fist), so the claw on the pinky side always points along the cut: it
sweeps through the centre tip-first, out in front of the fist, its concave
edge facing up / outwards - the hook leads.  The arm leaves the right edge
(upper third), drops outside it and the fist comes back in from the
bottom-right (wrist low), overshoots a hair up-left of rest and settles with
the same nose-up tilt / knife swing as kr_attack1.

Shoulder offsets of the fast keys come from attack1.auto_shoulder (straight
wrist at every key, torso turn / lunge); the high exit keys aim the upper arm
out to the right so the shoulder stays off screen.  The grip never changes.

Beats (seconds, 60 fps grid):
  0.00        IDLE (flat).
  0.00-0.05   COCK: down-left across the body, claw up.  Sound swing at 0.05.
  0.05-0.18   RIP: lower-left -> right, rising ~20 deg, accelerating, claw
              leading.  Hit at the centre crossing (0.117).  Camera kicks
              up-right (<= 0.55 deg).
  0.18-0.23   EXIT: off the right edge, hard ease-out.
  0.23-0.38   DROP outside the right edge, under the frame, back into the grip.
  0.38-0.45   RISE in from the bottom-right, ease-out into a small overshoot
              up-left of rest.
  0.45-0.65   SETTLE: tilt + knife swing, one-sided decay into IDLE (flat).
Markers: Sound swing (0.05), Hit light (0.117).
"""

from ..core import Anim
from . import common as C
from .attack1 import (FR, LENGTH, I, Z3, IDLE_SCR, TILT_D, TILT_K, EL_FREE, auto_shoulder, axes_rot,
                      key_path, key_cam, _add)

AUTO = None


def _rip_rots(rows, near):
    """(distal, palmar) view-space axes -> euler-continuous hand rots."""
    out = []
    for distal, palmar in rows:
        near = axes_rot(distal, palmar, near)
        out.append(near)
    return out


# the rip, as hand axes: the back of the fist faces the camera while the
# forearm sweeps clockwise round the elbow (fingers left-up -> up -> right),
# so the claw (pinky side) always points along the cut
R_COCK, R_UP, R_HIT, R_OUT, R_HIGH, R_EXIT = _rip_rots([
    ((-0.75, 0.35, 0.55), (0.10, 1.0, 0.20)),
    ((-0.45, 0.35, 0.80), (0.05, 1.0, -0.10)),
    ((0.00, 0.35, 1.00), (0.0, 1.0, -0.30)),
    ((0.45, 0.35, 0.85), (0.0, 1.0, -0.30)),
    ((0.75, 0.35, 0.60), (0.0, 1.0, -0.30)),
    ((0.90, 0.30, 0.35), (0.0, 1.0, -0.20)),
], I["R_rot"])

# frame, screen (x, y, depth), hand rot (pitch, yaw, roll), d_shoulder (AUTO =
# straight-wrist reach), d_elbow (AUTO = EL_FREE), knife d_rot
_KEYS = [
    (0, IDLE_SCR, I["R_rot"], Z3, Z3, Z3),
    # cock: down-left across the body, hawkbill standing up out of the fist
    (3, (0.30, 0.94, 2.25), R_COCK, AUTO, AUTO, (6.0, 0.0, 0.0)),
    # rip: lower-left -> upper-right, accelerating, claw leading
    (5, (0.38, 0.85, 2.40), R_UP, AUTO, AUTO, (3.0, 0.0, 0.0)),
    (7, (0.52, 0.72, 2.50), R_HIT, AUTO, AUTO, (-2.0, 0.0, 0.0)),
    (9, (0.68, 0.60, 2.45), R_OUT, AUTO, AUTO, (-5.0, 0.0, 0.0)),
    (11, (0.86, 0.52, 2.42), R_HIGH, AUTO, AUTO, (-5.0, 0.0, 0.0)),
    # exit: hard ease-out beyond the upper-right corner
    (14, (1.04, 0.46, 2.35), R_EXIT, AUTO, AUTO, (-3.0, 0.0, 0.0)),
    # drop outside the right edge and under the frame, turning back to the grip
    (17, (1.16, 0.80, 1.90), (28.0, -35.0, 45.0), AUTO, AUTO, (0.0, 0.0, 0.0)),
    (20, (0.95, 1.30, 2.15), (40.0, 5.0, 78.0), AUTO, AUTO, (3.0, 0.0, 0.0)),
    # rise in from the bottom-right, wrist low
    (23, (0.74, 1.02, 2.50), (46.0, 30.0, 94.0), AUTO, AUTO, (3.0, 0.0, 0.0)),
    # overshoot a hair up-left of rest
    (27, (0.625, 0.795, 2.70), (41.0, 33.0, 89.0), (-0.02, 0.0, 0.01), Z3, (1.0, 0.0, 0.0)),
    # settle: nose-up tilt, knife swinging up on the ring
    (32, (0.645, 0.812, 2.74), _add(I["R_rot"], TILT_D), Z3, Z3, TILT_K),
    (35, (IDLE_SCR[0] - 0.002, IDLE_SCR[1] - 0.003, IDLE_SCR[2]), _add(I["R_rot"], (-0.3, -1.5, -0.4)),
     Z3, Z3, (-1.5, 0.0, 0.0)),
    (39, IDLE_SCR, I["R_rot"], Z3, Z3, Z3),
]
# the high exit keys aim the upper arm out to the right so the shoulder stays
# beyond the right edge (aiming at the idle shoulder would put it on screen)
TOWARD = {11: (1.2, -0.2, 0.0), 14: (2.0, -0.3, 0.0), 17: (1.5, -0.3, -0.5)}
KEYS = [(f, sp, rot, auto_shoulder(sp, rot, TOWARD.get(f, Z3)) if sh is AUTO else sh,
         EL_FREE if el is AUTO else el, kn)
        for f, sp, rot, sh, el, kn in _KEYS]

T_SWING = 3 * FR
T_HIT = 7 * FR
CAM = [  # t, rot (pitch, roll, yaw) deg - kicks up and to the right with the rip
    (T_SWING, Z3),
    (T_HIT + 3 * FR, (0.30, 0.45, -0.55)),
    (0.30, (-0.08, -0.08, 0.10)),
    (0.42, Z3),
]


def build():
    a = Anim("kr_attack2", "karambit", length=LENGTH, priority="Action",
             description="Karambit light slash 2: rising backhand hook left to right, drops off right, rises into idle")
    C.key_idle(a, 0.0)
    C.key_idle(a, LENGTH)
    key_path(a, KEYS, LENGTH)
    key_cam(a, CAM)
    a.marker(T_SWING, "Sound", "swing")
    a.marker(T_HIT, "Hit", "light")
    return a
