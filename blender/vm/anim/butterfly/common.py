"""
Butterfly knife - the shared BASE IDLE POSE and helpers for every butterfly clip.

HOW CLIPS START / END ON THE BASE POSE
    Every butterfly clip except the draw starts and ends EXACTLY on IDLE: call
    key_idle(a, 0.0) first and key_idle(a, a.length) last (flat tangents, so
    the runtime can cross-fade into / out of the bf_idle loop with no pop; the
    idle loop itself is exactly IDLE at t = 0).  The draw starts from OFFSCREEN
    (key_offscreen(a, 0.0): hand below / right of the view, knife closed) and
    ends with key_idle.  Leave the last ~0.15-0.3 s for a soft settle: either
    key a tiny overshoot yourself (pose_from(d_pos=..., d_rot=...) + key_pose)
    or call settle_into_idle(a, a.length, dur=0.25), which keys a small
    overshoot past IDLE in the direction you were moving and then IDLE (flat).
    If the knife made full turns during the clip (e.g. knife rot X 0 -> 720),
    end with key_idle(a, t, knife_turns=(720, 0, 0)) so the euler curve does
    not unwind backwards.  Do the same for hand roll turns with hand_turns.

UNITS / CONVENTIONS: see vm/anim/core.py (studs, degrees, hand pos = centre
of the R15 hand block in viewmodel space, hand rot = (pitch, yaw, roll) on top
of the "handshake" pose, knife pos/rot = anchored link in the hand semantic
frame, euler XYZ so knife rot X = spin about the pin axis / blade flat normal).

STABLE API
    IDLE              dict: R_pos, R_rot, R_elbow, R_shoulder, knife_pos,
                      knife_rot, anchor, bf, L_pos, L_rot  (the base pose)
    GRIP              dict(pos, rot, anchor) = the idle knife grip.  It is
                      poses.GRIPS["butterfly"] rotated -15 deg about the pin
                      axis (knife rot X 90 -> 75, pins shifted so the handle
                      still crosses the hand block centre): the handle lies
                      diagonally in the fist, blade tilted towards the
                      "fingers" side like a natural hammer grip.  Use GRIP
                      (not poses.GRIPS) whenever the knife returns to the hand.
                      Note XYZ euler: rot Y = 90 is a gimbal singularity (X and
                      Z both turn about the pin axis) - spin with X; if you
                      need other axes use knife_rot_for_order() and
                      Anim(..., knife_rot_order=...).
    CLOSED            knife-only pose dict for the closed knife held by the
                      safe handle A in the same grip (bf = (1, 1, 0)).
    OFFSCREEN         pose dict to start the draw: hand low right, outside
                      the 70 deg FOV, knife CLOSED, elbow tucked.
    key_idle(a, t, interp="smooth", tangent="flat", knife=True, left=True,
             knife_turns=(0, 0, 0), hand_turns=(0, 0, 0))
                      keys every channel of IDLE at t: R pos/rot/elbow/
                      shoulder, knife pos/rot (+ anchor "A" if the clip has no
                      anchor key yet), bf open (0, 0, 0), cam rot/pos = 0,
                      left arm hidden.  The open knife's links coincide, so the
                      knife keys are valid whatever link is anchored (after a
                      switch_anchor to "B" / "BLADE" too).
    key_left_hidden(a, t, interp="smooth")   left arm parked out of view
    key_pose(a, t, pose, interp="smooth", tangent="auto", knife=True, left=True)
                      keys any dict in the IDLE format (missing keys skipped;
                      "cam_rot" / "cam_pos" entries are keyed too)
    pose_from(base=IDLE, d_pos=, d_rot=, d_elbow=, d_shoulder=, d_knife_pos=,
              d_knife_rot=, **override) -> new pose dict (offsets added)
    key_offscreen(a, t, interp="smooth", tangent="flat")  keys OFFSCREEN
    settle_into_idle(a, t_end, dur=0.25, overshoot=0.18, max_pos=0.05,
                     max_rot=3.0, knife_turns=(0, 0, 0), hand_turns=(0, 0, 0))
                      soft landing: reads where the right hand is at
                      t_end - dur (keys must already exist up to there), keys a
                      small overshoot past IDLE at t_end - 0.45 * dur and IDLE
                      (flat) at t_end.
    new_anim(name, length, **kw) -> Anim(name, "butterfly", length, **kw)
    idle_controls() -> skeleton control dict of IDLE (for probes / math)
    knife_rot_for_order(order, rot=IDLE knife_rot) -> same rotation in another
                      euler order (compatible with Anim(knife_rot_order=...))

COMPOSITION (70 deg vertical FOV game camera, 16:9): hand block centre at
screen ~(0.66, 0.79), pins ~(0.60, 0.72), blade tip ~(0.46, 0.57) - the open
knife points up-left ~31 deg above horizontal with its flat towards the
camera, the forearm enters diagonally from the bottom-right corner (elbow
just below the bottom edge), nothing closer than ~1.9 studs to the camera.
Wrist at idle: flex ~-7, dev ~-23 (limits 85 / 45), i.e. headroom for
flicks; for big wrist motions move the elbow (R_elbow) and the hand position
instead of bending the blocky R15 hand further.
"""

import math

from mathutils import Euler

from ..core import Anim
from .. import poses

# ---------------------------------------------------------------------------
# grip / base pose
# ---------------------------------------------------------------------------
_TILT = 15.0          # deg, knife rotated about its pin axis towards distal
_PIN_R = 0.60         # studs, pins from the hand block centre (as poses.BF_GRIP)

GRIP = dict(
    pos=(round(_PIN_R * math.cos(math.radians(_TILT)), 4), round(_PIN_R * math.sin(math.radians(_TILT)), 4), 0.0),
    rot=(90.0 - _TILT, 90.0, 0.0),
    anchor="A",
)

IDLE = dict(
    R_pos=(1.235, 3.10, -1.259),
    R_rot=(55.0, -15.0, 55.0),
    R_elbow=(0.40, -0.20, -0.30),
    R_shoulder=(0.0, 0.0, 0.0),
    knife_pos=GRIP["pos"],
    knife_rot=GRIP["rot"],
    anchor=GRIP["anchor"],
    bf=(0.0, 0.0, 0.0),
    L_pos=poses.L_HIDDEN_POS,
    L_rot=poses.L_HIDDEN_ROT,
)

# closed knife in the same grip (held by the safe handle A, blade folded
# between the handles): only the handle state differs.
CLOSED = dict(knife_pos=GRIP["pos"], knife_rot=GRIP["rot"], anchor="A", bf=(1.0, 1.0, 0.0))

# start of the draw: hand low right outside the view, wrist dropped, knife closed
OFFSCREEN = dict(
    R_pos=(1.75, 2.35, -2.45),
    R_rot=(-10.0, -5.0, 80.0),
    R_elbow=(0.30, -0.20, -0.30),
    R_shoulder=(0.0, 0.0, 0.0),
    knife_pos=CLOSED["knife_pos"],
    knife_rot=CLOSED["knife_rot"],
    anchor="A",
    bf=CLOSED["bf"],
    L_pos=poses.L_HIDDEN_POS,
    L_rot=poses.L_HIDDEN_ROT,
)


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _turned(v, turns):
    return tuple(x + t for x, t in zip(v, turns))


def new_anim(name, length, **kw):
    return Anim(name, "butterfly", length, **kw)


def _has_anchor(a):
    ch = a.ch.get("knife.anchor")
    return bool(ch and ch.keys)


# ---------------------------------------------------------------------------
# keying helpers
# ---------------------------------------------------------------------------
def key_left_hidden(a, t, interp="smooth"):
    """Left arm parked out of view (R15 rest pose, arm hanging down)."""
    a.hand("L", t, pos=IDLE["L_pos"], rot=IDLE["L_rot"], elbow=(0.0, 0.0, 0.0), shoulder=(0.0, 0.0, 0.0),
           interp=interp, tangent="flat")


def key_pose(a, t, pose, interp="smooth", tangent="auto", knife=True, left=True):
    """Key every entry of a pose dict in the IDLE format (missing entries are
    skipped).  Extra optional entries: cam_rot, cam_pos."""
    a.hand("R", t, pos=pose.get("R_pos"), rot=pose.get("R_rot"), elbow=pose.get("R_elbow"),
           shoulder=pose.get("R_shoulder"), interp=interp, tangent=tangent)
    if knife:
        if "anchor" in pose and not _has_anchor(a):
            a.knife(t, anchor=pose["anchor"])
        a.knife(t, pos=pose.get("knife_pos"), rot=pose.get("knife_rot"), interp=interp, tangent=tangent)
        if "bf" in pose:
            a.bf(t, *pose["bf"], interp=interp, tangent=tangent)
    if "cam_rot" in pose or "cam_pos" in pose:
        a.cam(t, rot=pose.get("cam_rot"), pos=pose.get("cam_pos"), interp=interp, tangent=tangent)
    if left and "L_pos" in pose:
        a.hand("L", t, pos=pose["L_pos"], rot=pose.get("L_rot"), interp=interp, tangent=tangent)


def key_idle(a, t, interp="smooth", tangent="flat", knife=True, left=True,
             knife_turns=(0.0, 0.0, 0.0), hand_turns=(0.0, 0.0, 0.0)):
    """Key every channel of the base idle pose at t (camera zeroed, knife open,
    left arm hidden).  knife_turns / hand_turns add whole turns (multiples of
    360) to the knife / hand euler so spins do not unwind."""
    a.hand("R", t, pos=IDLE["R_pos"], rot=_turned(IDLE["R_rot"], hand_turns), elbow=IDLE["R_elbow"],
           shoulder=IDLE["R_shoulder"], interp=interp, tangent=tangent)
    if knife:
        if not _has_anchor(a):
            a.knife(t, anchor=IDLE["anchor"])
        a.knife(t, pos=IDLE["knife_pos"], rot=_turned(IDLE["knife_rot"], knife_turns), interp=interp, tangent=tangent)
        a.bf(t, *IDLE["bf"], interp=interp, tangent=tangent)
    a.cam(t, rot=(0.0, 0.0, 0.0), pos=(0.0, 0.0, 0.0), interp=interp, tangent=tangent)
    if left:
        key_left_hidden(a, t, interp)


def key_offscreen(a, t, interp="smooth", tangent="flat", left=True):
    """Draw start: hand out of view low right, knife closed, camera zeroed."""
    key_pose(a, t, OFFSCREEN, interp=interp, tangent=tangent, left=False)
    a.cam(t, rot=(0.0, 0.0, 0.0), pos=(0.0, 0.0, 0.0), interp=interp, tangent=tangent)
    if left:
        key_left_hidden(a, t, interp)


def pose_from(base=None, d_pos=None, d_rot=None, d_elbow=None, d_shoulder=None,
              d_knife_pos=None, d_knife_rot=None, **override):
    """New pose dict = base (default IDLE) + offsets; keyword overrides
    replace entries (e.g. bf=(1, 1, 0))."""
    p = dict(IDLE if base is None else base)
    for k, d in (("R_pos", d_pos), ("R_rot", d_rot), ("R_elbow", d_elbow), ("R_shoulder", d_shoulder),
                 ("knife_pos", d_knife_pos), ("knife_rot", d_knife_rot)):
        if d is not None:
            p[k] = _add(p[k], d)
    p.update(override)
    return p


def settle_into_idle(a, t_end, dur=0.25, overshoot=0.18, max_pos=0.05, max_rot=3.0,
                     knife_turns=(0.0, 0.0, 0.0), hand_turns=(0.0, 0.0, 0.0), left=True):
    """Soft landing on IDLE at t_end with a tiny overshoot.  The right hand's
    pose at t_end - dur (from the keys already in the clip) gives the travel
    direction; the overshoot pose (IDLE + overshoot * (IDLE - that pose),
    clamped to max_pos studs / max_rot deg per axis) is keyed at
    t_end - 0.45 * dur, then IDLE with flat tangents at t_end."""
    t0 = t_end - dur
    c = a.controls(t0)
    idle_rot = _turned(IDLE["R_rot"], hand_turns)

    def over(target, cur, lim):
        return tuple(tv + max(-lim, min(lim, (tv - cv) * overshoot)) for tv, cv in zip(target, cur))

    t_os = t_end - 0.45 * dur
    a.hand("R", t_os,
           pos=over(IDLE["R_pos"], c.get("R.pos", IDLE["R_pos"]), max_pos),
           rot=over(idle_rot, c.get("R.rot", idle_rot), max_rot),
           elbow=over(IDLE["R_elbow"], c.get("R.elbow", IDLE["R_elbow"]), max_pos * 2))
    key_idle(a, t_end, knife_turns=knife_turns, hand_turns=hand_turns, left=left)


# ---------------------------------------------------------------------------
# math helpers
# ---------------------------------------------------------------------------
def idle_controls():
    """IDLE as a skeleton control dict (skeleton.evaluate(idle_controls(), ...))."""
    return {"R.pos": IDLE["R_pos"], "R.rot": IDLE["R_rot"], "R.elbow": IDLE["R_elbow"],
            "R.shoulder": IDLE["R_shoulder"], "L.pos": IDLE["L_pos"], "L.rot": IDLE["L_rot"],
            "knife.pos": IDLE["knife_pos"], "knife.rot": IDLE["knife_rot"], "knife.anchor": IDLE["anchor"],
            "bf": IDLE["bf"], "cam.pos": (0.0, 0.0, 0.0), "cam.rot": (0.0, 0.0, 0.0)}


def knife_rot_for_order(order, rot=None):
    """The knife rotation `rot` (XYZ euler deg, default the idle grip) in
    another Blender euler order."""
    rot = IDLE["knife_rot"] if rot is None else rot
    m = Euler([math.radians(x) for x in rot], "XYZ").to_matrix()
    return tuple(round(math.degrees(x), 4) for x in m.to_euler(order))
