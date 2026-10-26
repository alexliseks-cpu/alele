"""
Knife grips for the blocky R15 hand (tuned against spec.py geometry) and
handy reference hand placements.

Knife grip = knife link pos/rot in the HAND SEMANTIC frame: origin at the
hand block centre, +X radial (thumb side), +Y distal (bottom of the block),
+Z palmar.  The R15 hand block spans radial/palmar -0.5..0.5 and distal
-0.15..0.15 around that origin; the knife handle passes through it.
"""

import math

from mathutils import Matrix, Vector


def axes_euler(xk, yk, order="XYZ"):
    """Knife orientation from the knife's X / Y axes given in hand coords."""
    x = Vector(xk).normalized()
    y = Vector(yk)
    y = (y - x * y.dot(x)).normalized()
    z = x.cross(y)
    m = Matrix((x, y, z)).transposed()
    return tuple(round(math.degrees(a), 3) for a in m.to_euler(order))


# ---------------------------------------------------------------------------
# Butterfly: open knife in a hammer grip, handles through the hand block,
# pins just above the thumb side, blade up, edge facing the "fingers" side.
# ---------------------------------------------------------------------------
BF_GRIP = dict(pos=(0.60, 0.0, 0.0), rot=axes_euler(xk=(0, 0, -1), yk=(1, 0.0, 0)), anchor="A")

# ---------------------------------------------------------------------------
# Karambit: CS2 reverse grip - ring above the thumb side of the hand block,
# handle through the hand, hawkbill blade out of the pinky side curving
# forward (towards the hand's distal side).
# ---------------------------------------------------------------------------
KR_GRIP = dict(pos=(0.62, 0.0, 0.0), rot=axes_euler(xk=(0, 0, 1), yk=(-1, 0, 0)), anchor="KNIFE")

GRIPS = {"butterfly": BF_GRIP, "karambit": KR_GRIP}

# reference hand placements (viewmodel space, studs / deg) - starting points
# found by sweeps; vm/anim/<knife>/common.py owns the final idle pose.
BF_IDLE_START = dict(pos=(0.90, 3.00, -1.15), rot=(35.0, 20.0, 50.0))
KR_IDLE_START = dict(pos=(0.80, 3.00, -1.05), rot=(15.0, 35.0, 90.0), elbow=(0.5, -0.2, -0.2))
R_IDLE_POS, R_IDLE_ROT = BF_IDLE_START["pos"], BF_IDLE_START["rot"]

# left hand parked out of view: the R15 rest pose (arm hanging straight down)
from .. import skeleton as _sk  # noqa: E402
L_HIDDEN_POS = tuple(round(x, 4) for x in _sk.ARM_REST["L"]["hand_c"])
L_HIDDEN_ROT = (-90.0, 0.0, 0.0)
