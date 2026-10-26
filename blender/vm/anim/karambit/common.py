"""
Karambit shared base pose + helpers (import this from every kr_* clip).

HOW CLIPS START / END ON THE BASE POSE
--------------------------------------
Every non-idle karambit clip starts and ends EXACTLY on IDLE:

    from .common import IDLE, key_idle, key_left_hidden, key_settle
    a = Anim("kr_attack1", "karambit", length=1.0)
    key_idle(a, 0.0)                       # every channel, flat tangent = a hold
    ... your keys ...
    key_settle(a, 0.72, 1.0, dpos=(0.03, 0, 0.04), drot=(4, 0, -2))   # soft land
    # (key_settle ends with key_idle(a, 1.0); or call key_idle yourself)

key_idle keys ALL channels the idle uses (right hand pos/rot/elbow/shoulder,
knife pos/rot, left hand, camera = 0), so a channel you never touch in the
middle stays exactly on the base pose, and the first/last frames match the
kr_idle loop bit-for-bit (the runtime blends into the idle loop).  Give the
last 0.15-0.3 s a soft landing: key_settle() keys a tiny overshoot past
IDLE (offsets you choose, usually continuing the incoming motion) and then
IDLE with a flat tangent.  CS2 itself lands with a clean exponential settle
(residual x0.7 per 1/15 s, no bounce, settled ~0.5 s after the last action
key) - keep overshoots small (<= 0.05 stud / 5 deg).  Draws start from
OFFSCREEN instead (key_pose(a, 0, OFFSCREEN) + key_left_hidden + key_cam_zero)
and end with key_idle / key_settle.

NOTE: IDLE uses a small SHOULDER OFFSET (R_shoulder) to bring the whole arm
0.3 stud closer / 0.25 higher than the rig default (bigger, CS2-like fist
without a bent wrist).  key_idle keys it; if you key R.shoulder yourself
(lunges), add your offset to IDLE["R_shoulder"], do not replace it by zeros.

THE BASE POSE (what it looks like)
----------------------------------
CS2 karambit idle adapted to the blocky R15 hand: fist low at the centre-right
(knuckles at screen ~ (0.63, 0.79), ring ~ (0.60, 0.86), blade claw tip
~ (0.77, 0.64); x right / y down, 0..1), pronated 90 deg (palm down) and pitched 40 deg
knuckles-up so the forearm runs from the bottom-right corner up-left into the
fist with a straight wrist (flex ~5, dev ~-9 deg).  Reverse grip: the faceted
ring sticks out of the thumb side (screen left) with its hole facing the
camera, the handle runs through the hand block, and the hawkbill blade comes
out of the pinky side and curls up behind the wrist (only its claw shows).
Viewmodel space at IDLE: hand centre (1.0, 2.75, -1.25), ring centre ~(0.54,
2.31, -1.15), blade tip ~(2.05, 2.97, -0.6) studs.  Left arm parked (hidden).
Knife spins: GRIP rot is XYZ euler, rot[0] is a spin about the ring axis;
on screen, increasing rot[0] swings the blade end down (and right).

API (stable - other animators rely on it)
-----------------------------------------
IDLE                dict(R_pos, R_rot, R_elbow, R_shoulder, knife_pos, knife_rot,
                    anchor, L_pos, L_rot, L_elbow, L_shoulder)
GRIP                dict(pos, rot, anchor): the idle knife grip in the hand frame
                    (= IDLE knife).  rot is XYZ euler, so rot[0] + n*360 spins
                    the knife about its own ring axis (finger-ring spins).
OFFSCREEN           right-hand pose below/right of the view for draws (knife in GRIP;
                    has its own lowered R_shoulder - key_pose keys it)
TILT                CS2 "tilted" pose (ref f_0012 / f_0112): ring + knuckles lifted,
                    wrist a bit right, knife pivoted 6 deg on the ring (far end up).
                    knife_rot[0] NEGATIVE = blade end up / forward (towards the screen top).
                    Light attacks / inspects settle THROUGH it into IDLE.
grip_rot(curl, tilt, swing)   knife euler for variations of the reverse grip
pose_offset(base=IDLE, **d)   copy of a pose with additive offsets, e.g.
                    pose_offset(R_pos=(0, 0, .1), R_rot=(5, 0, 0), knife_rot=(10, 0, 0))
lerp_pose(p0, p1, w)          linear blend of two poses (numbers only)
key_pose(a, t, pose, interp="smooth", tangent="auto", knife=True, left=True)
                    key every channel present in pose (sets the knife anchor once)
key_idle(a, t, interp="smooth", tangent="flat", knife=True, left=True)
key_left_hidden(a, t, interp="smooth", tangent="flat")
key_cam_zero(a, t, interp="smooth", tangent="flat")
key_settle(a, t0, t1, dpos, drot, knife_drot=(0,0,0), delbow=(0,0,0), interp="out_soft")
                    overshoot pose (IDLE + offsets on R pos/rot/elbow + knife rot)
                    at t0, then key_idle(a, t1) (all channels, flat)
screen_xy(p)        viewmodel point (studs) -> normalized screen (x right, y down),
                    FOV 70 vertical, 16:9 - handy to check framing numerically
"""

import math

from mathutils import Matrix, Vector

from .. import poses

# ---------------------------------------------------------------------------
# knife grip
# ---------------------------------------------------------------------------


def grip_rot(curl=0.0, tilt=0.0, swing=0.0):
    """Reverse-grip knife orientation in the hand semantic frame.

    Base (all 0) = poses.KR_GRIP: ring axis = palmar, handle from the ring
    towards the ulnar side, blade curling towards distal.
    curl : roll about the handle (deg) - the blade's curl turns from distal
           towards dorsal (the claw rises on a pronated hand); also turns the
           ring hole towards the camera.
    tilt : the handle's blade end rises towards dorsal (deg).
    swing: the handle's blade end swings towards proximal / the wrist (deg),
           which tucks the blade behind the wrist.
    """
    c = math.radians(curl)
    xk = Vector((0.0, math.sin(c), math.cos(c)))
    yk = Vector((-1.0, 0.0, 0.0))
    rot = Matrix.Rotation(math.radians(swing), 3, "Z") @ Matrix.Rotation(math.radians(-tilt), 3, "Y")
    return poses.axes_euler(tuple(rot @ xk), tuple(rot @ yk))


GRIP = dict(pos=(0.62, -0.04, -0.16), rot=grip_rot(curl=33.0, tilt=8.0, swing=14.0), anchor="KNIFE")

# ---------------------------------------------------------------------------
# base idle pose
# ---------------------------------------------------------------------------
_SHOULDER = (0.0, -0.30, 0.25)

IDLE = dict(
    R_pos=(1.00, 2.75, -1.25),
    R_rot=(40.0, 32.0, 90.0),
    R_elbow=(0.50, 0.0, -0.40),
    R_shoulder=_SHOULDER,
    knife_pos=GRIP["pos"],
    knife_rot=GRIP["rot"],
    anchor=GRIP["anchor"],
    L_pos=poses.L_HIDDEN_POS,
    L_rot=poses.L_HIDDEN_ROT,
    L_elbow=(0.0, 0.0, 0.0),
    L_shoulder=(0.0, 0.0, 0.0),
)

# draw start: hand dropped below / right of the view (nothing on screen, the
# shoulder pulled down too), knuckles down, knife in grip.  Wrist flex -13 /
# dev 14 here and straight all the way along a plain lerp to IDLE.
OFFSCREEN = dict(
    R_pos=(1.60, 2.30, -2.90),
    R_rot=(-5.0, 15.0, 70.0),
    R_elbow=(0.50, 0.0, -0.40),
    R_shoulder=(0.15, -0.20, -0.25),
    knife_pos=GRIP["pos"],
    knife_rot=GRIP["rot"],
)

# channel name mapping (pose-dict key -> Anim channel)
_CH = {
    "R_pos": "R.pos", "R_rot": "R.rot", "R_elbow": "R.elbow", "R_shoulder": "R.shoulder",
    "L_pos": "L.pos", "L_rot": "L.rot", "L_elbow": "L.elbow", "L_shoulder": "L.shoulder",
    "knife_pos": "knife.pos", "knife_rot": "knife.rot",
}
_KNIFE_KEYS = ("knife_pos", "knife_rot")
_LEFT_KEYS = ("L_pos", "L_rot", "L_elbow", "L_shoulder")


def pose_offset(base=None, **d):
    """Copy of `base` (default IDLE) with additive offsets: pose_offset(R_pos=(0, 0, .1))."""
    p = dict(IDLE if base is None else base)
    for k, v in d.items():
        if k not in _CH:
            raise KeyError(f"pose_offset: unknown key {k}")
        p[k] = tuple(a + b for a, b in zip(p[k], v))
    return p


def lerp_pose(p0, p1, w):
    """Blend the numeric entries both poses share (w = 0 -> p0, 1 -> p1)."""
    out = dict(p0)
    for k in _CH:
        if k in p0 and k in p1:
            out[k] = tuple(a + (b - a) * w for a, b in zip(p0[k], p1[k]))
    return out


# CS2 "tilted" pose (ref f_0012 / f_0112), fitted to the measured screen
# deltas at 720p: ring rises ~14 px, knuckles ~6 px, wrist drifts right and the
# blade's far end rises ~30 px (knife pivots 6 deg on the ring, far end up).
TILT = pose_offset(R_pos=(0.03, 0.0, 0.03), R_rot=(-1.0, -5.0, -1.5), knife_rot=(-6.0, 0.0, 0.0))


def _has_anchor(a):
    ch = a.ch.get("knife.anchor")
    return bool(ch and ch.keys)


def key_pose(a, t, pose, interp="smooth", tangent="auto", knife=True, left=True):
    """Key every channel present in `pose` at time t."""
    for k, chn in _CH.items():
        if k not in pose:
            continue
        if not knife and k in _KNIFE_KEYS:
            continue
        if not left and k in _LEFT_KEYS:
            continue
        a.set(chn, t, pose[k], interp, tangent)
    if knife and "anchor" in pose and not _has_anchor(a):
        a.knife(t, anchor=pose["anchor"])
    return a


def key_cam_zero(a, t, interp="smooth", tangent="flat"):
    a.cam(t, rot=(0.0, 0.0, 0.0), pos=(0.0, 0.0, 0.0), interp=interp, tangent=tangent)
    return a


def key_left_hidden(a, t, interp="smooth", tangent="flat"):
    """Left arm parked out of view (R15 rest pose, hanging straight down)."""
    for k in _LEFT_KEYS:
        a.set(_CH[k], t, IDLE[k], interp, tangent)
    return a


def key_idle(a, t, interp="smooth", tangent="flat", knife=True, left=True):
    """Key the full base idle pose at t (right arm, knife, left arm, camera 0)."""
    key_pose(a, t, IDLE, interp, tangent, knife=knife, left=left)
    if not knife and not _has_anchor(a):
        a.knife(t, anchor=IDLE["anchor"])
    key_cam_zero(a, t, interp, tangent)
    return a


def key_settle(a, t0, t1, dpos=(0.0, 0.0, 0.0), drot=(0.0, 0.0, 0.0), knife_drot=(0.0, 0.0, 0.0),
               delbow=(0.0, 0.0, 0.0), interp="out_soft"):
    """Soft landing: IDLE + small offsets at t0 (the overshoot), IDLE at t1
    (flat tangent).  Typical: dpos ~0.02-0.05 stud, drot ~2-5 deg over
    0.15-0.3 s.  Keys the right hand (+ knife rot) only."""
    p = pose_offset(R_pos=dpos, R_rot=drot, R_elbow=delbow, knife_rot=knife_drot)
    for k in ("R_pos", "R_rot", "R_elbow", "knife_rot"):
        a.set(_CH[k], t0, p[k], interp, "auto")
    key_idle(a, t1)
    return a


def screen_xy(p, fov_y=70.0, aspect=16.0 / 9.0):
    """Viewmodel point -> normalized screen coords (0..1, x right, y down)."""
    x, y, z = p
    t = math.tan(math.radians(fov_y) / 2)
    return (0.5 + 0.5 * x / (y * t * aspect), 0.5 - 0.5 * z / (y * t))
