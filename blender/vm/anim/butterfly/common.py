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
    GRIP              dict(pos, rot, anchor) = the idle knife grip (open
                      knife, anchor "A"): poses.GRIPS["butterfly"] tilted 20 deg
                      towards the "fingers" side (the handle crosses the fist
                      diagonally, like a natural hammer grip) and rolled 150 deg
                      about the knife's long axis so that, with the pronated
                      fist of IDLE, the EDGE faces down / towards the curled
                      fingers, the SPINE faces up and the blade flat faces the
                      camera (CS2 look; the handle pack then lies inside the
                      0.3-stud hand slab).  Pins 0.6 stud from the hand centre,
                      the handle passes through the block centre.  Use GRIP (not
                      poses.GRIPS) whenever the knife returns to the hand.
                      Euler XYZ (0, -120, -70): no gimbal singularity; knife
                      rot X is a spin about the knife's own pin axis, so
                      spinning X 0 -> 360 * n about the pins is safe.
                      Directions seen from the game camera at IDLE: knife rot
                      X + turns the tip up (clockwise on screen: left -> up ->
                      right), bf a + swings the blade (and handle B) up over
                      the fist the same way into the closed position, hand
                      roll + (pronation) drops the tip, hand pitch barely
                      moves it (the knife lies across the view).
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
    pose_controls(pose) -> skeleton control dict of a pose dict
    idle_controls()   -> skeleton control dict of IDLE (for probes / math)
    knife_rot_for_order(order, rot=IDLE knife_rot) -> same rotation in another
                      euler order.  Pose dicts always store knife_rot in XYZ;
                      key_idle / key_pose convert it to the clip's
                      Anim.knife_rot_order automatically (knife_turns are
                      added in the clip's order).
    probe(pose_or_controls) -> dict: screen (x, y in 0..1, 16:9, 70 deg FOV)
                      and depth of hand / pins / tip / handle butt / wrist /
                      elbow, wrist flex & dev, stretched flag, min distance to
                      the camera, screen share covered by the forearm and upper
                      arm.  Pure math (no render): use it to tune key poses.

COMPOSITION (70 deg vertical FOV game camera, 16:9), matched to the CS2
butterfly idle footprint (ref_specs/butterfly_idle.md: tip (0.44, 0.64),
pivot (0.605, 0.76), butt (0.835, 0.88), knife ~19 deg above horizontal,
lying across the view): hand block centre (0.685, 0.80) at 2.95 studs,
pins (0.605, 0.75), blade tip (0.46, 0.65), handle butt (0.81, 0.88); the
open knife lies across the view pointing left and ~20 deg up, tip a touch
deeper than the pins, edge down, flat towards the camera.  The pronated
fist shows its back / top, the forearm goes down to the bottom-right edge
(elbow just below the frame), nothing is closer than ~2.4 studs to the
camera.  Wrist at idle: flex ~+6, dev ~-11 (warning limits 85 / 45) - plenty
of headroom for flicks; for big wrist motions still move the elbow
(R_elbow) and the hand position instead of bending the blocky hand further.
The left arm is parked out of view (CS2 shows a relaxed left hand bottom
left; with 1x1-stud R15 blocks that only adds a black block, so it is off).

REACH (read before posing attacks): the right shoulder pivot sits at
(1.0, 1.90, -1.69), i.e. below / right of the camera, and the arm is only
~1.6 studs long.  Highest screen y the hand centre can reach (arm straight,
0 = top of the screen), per hand depth and screen x:
             x=0.35  0.45  0.55  0.65  0.75  0.85  0.95
    d=1.6      --    0.78  0.62  0.54  0.52  0.54  0.61
    d=2.0      --    0.72  0.57  0.51  0.50  0.56  0.70
    d=2.4      --    0.74  0.57  0.52  0.54  0.65   --
    d=2.8      --    0.89  0.60  0.56  0.61   --    --
    d=3.2      --     --   0.68  0.63  0.79   --    --
(idle: x 0.685, y 0.80, d 2.95 - comfortably inside, elbow bent).
Higher / further than that the solver drags the hidden shoulder along with a
locked straight arm (probe()["stretched"]) - acceptable for a frame or two
of a fast extension, but for a held high / left reach key a small R_shoulder
offset in and out smoothly (a few tenths of a stud: + z up, + y forward,
- x towards the centre for left-side follow-throughs).
The arm parts are 1x1-stud black blocks: the closer the hand comes, the more
of the screen the forearm / upper arm cover (probe()["arm_cover"]; idle is
~0.05) - keep the forearm pointing into the screen (foreshortened) on wind-ups
and keep hand depth >= ~2.2 for anything held longer than a few frames.
"""

import math

from mathutils import Euler

from ..core import Anim
from .. import poses

# ---------------------------------------------------------------------------
# grip / base pose
# ---------------------------------------------------------------------------
# idle grip: poses.GRIPS["butterfly"] tilted 20 deg towards distal, rolled
# 150 deg about the knife's long axis (see the module docstring)
GRIP = dict(pos=(0.5638, 0.2052, 0.0), rot=(0.0, -120.0, -70.0), anchor="A")

IDLE = dict(
    R_pos=(1.3587, 2.95, -1.2394),
    R_rot=(60.0, 0.0, 90.0),
    R_elbow=(0.20, -0.30, -0.50),
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
    R_pos=(1.70, 2.30, -2.65),
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


def _krot(a, rot, turns=(0.0, 0.0, 0.0)):
    """XYZ knife euler -> the clip's knife_rot_order (+ whole turns)."""
    if rot is None:
        return None
    if a.knife_rot_order != "XYZ":
        rot = knife_rot_for_order(a.knife_rot_order, rot)
    return _turned(rot, turns)


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
        a.knife(t, pos=pose.get("knife_pos"), rot=_krot(a, pose.get("knife_rot")), interp=interp, tangent=tangent)
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
        a.knife(t, pos=IDLE["knife_pos"], rot=_krot(a, IDLE["knife_rot"], knife_turns), interp=interp, tangent=tangent)
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
def pose_controls(pose):
    """Pose dict (IDLE format) -> skeleton control dict."""
    c = idle_controls()
    for k, ck in (("R_pos", "R.pos"), ("R_rot", "R.rot"), ("R_elbow", "R.elbow"), ("R_shoulder", "R.shoulder"),
                  ("L_pos", "L.pos"), ("L_rot", "L.rot"), ("knife_pos", "knife.pos"), ("knife_rot", "knife.rot"),
                  ("anchor", "knife.anchor"), ("bf", "bf"), ("cam_rot", "cam.rot"), ("cam_pos", "cam.pos")):
        if k in pose:
            c[ck] = tuple(pose[k]) if isinstance(pose[k], (tuple, list)) else pose[k]
    return c


def idle_controls():
    """IDLE as a skeleton control dict (skeleton.evaluate(idle_controls(), ...))."""
    return {"R.pos": IDLE["R_pos"], "R.rot": IDLE["R_rot"], "R.elbow": IDLE["R_elbow"],
            "R.shoulder": IDLE["R_shoulder"], "L.pos": IDLE["L_pos"], "L.rot": IDLE["L_rot"],
            "knife.pos": IDLE["knife_pos"], "knife.rot": IDLE["knife_rot"], "knife.anchor": IDLE["anchor"],
            "bf": IDLE["bf"], "cam.pos": (0.0, 0.0, 0.0), "cam.rot": (0.0, 0.0, 0.0)}


_TAN_HALF_FOV = math.tan(math.radians(35.0))
_ASPECT = 16.0 / 9.0


def _screen(p):
    """viewmodel point -> (x, y, depth); x, y in 0..1 (0, 0 = top left)."""
    if p.y < 1e-3:
        return (float("nan"), float("nan"), p.y)
    return (0.5 + 0.5 * p.x / (p.y * _TAN_HALF_FOV * _ASPECT), 0.5 - 0.5 * p.z / (p.y * _TAN_HALF_FOV), p.y)


def probe(pose_or_controls=None, knife_rot_order="XYZ"):
    """Quick numeric check of a pose (IDLE-format dict, or a control dict as
    returned by Anim.controls(t); default IDLE).  Camera shake is ignored."""
    from mathutils import Vector
    from ... import skeleton, spec
    src = IDLE if pose_or_controls is None else pose_or_controls
    c = dict(src) if "R.pos" in src else pose_controls(src)
    c["cam.rot"], c["cam.pos"] = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    info = {}
    W = skeleton.evaluate(c, knife_rot_order, "butterfly", info)
    ks = spec.KNIFE_SCALE
    hand = W["RightHand"]
    hc = hand.translation + hand.to_3x3() @ skeleton.V_HAND
    blade = W["BF_Blade"] @ skeleton.T(-skeleton.PIN_A)
    link_a = W["BF_HandleA"] @ skeleton.T(-skeleton.PIN_A)
    tip = blade @ Vector((0.0, spec.BF_BLADE_LEN * ks, 0.0))
    pins = blade @ Vector((0.0, 0.0, 0.0))
    butt = link_a @ Vector((0.0, -spec.BF_HANDLE_LEN * ks, 0.0))
    r15 = spec.R15
    blocks = {"RightUpperArm": (r15["upper_size"], -Vector(r15["upper_shoulder"])),
              "RightLowerArm": (r15["lower_size"], -Vector(r15["lower_elbow"])),
              "RightHand": (r15["hand_size"], -Vector(r15["hand_wrist"]))}
    corners, cover = [], 0.0
    for bone, (size, centre) in blocks.items():
        cs = [W[bone] @ (centre + Vector((sx * size[0], sy * size[1], sz * size[2])))
              for sx in (-0.5, 0.5) for sy in (-0.5, 0.5) for sz in (-0.5, 0.5)]
        corners += cs
        if bone != "RightHand":
            ss = [_screen(p) for p in cs if p.y > 0.05]
            if ss:
                x0, x1 = max(0.0, min(q[0] for q in ss)), min(1.0, max(q[0] for q in ss))
                y0, y1 = max(0.0, min(q[1] for q in ss)), min(1.0, max(q[1] for q in ss))
                cover += max(0.0, x1 - x0) * max(0.0, y1 - y0) * 0.5   # ~half a bbox is block
    return dict(
        hand=_screen(hc), pins=_screen(pins), tip=_screen(tip), butt=_screen(butt),
        wrist=_screen(W["RightHand"].translation), elbow=_screen(W["RightLowerArm"].translation),
        wrist_flex=info["R"]["wrist_flex"], wrist_dev=info["R"]["wrist_dev"], stretched=info["R"]["stretched"],
        min_cam_dist=min(p.length for p in corners + [tip, pins, butt]),
        arm_cover=min(1.0, cover),
    )


def knife_rot_for_order(order, rot=None):
    """The knife rotation `rot` (XYZ euler deg, default the idle grip) in
    another Blender euler order."""
    rot = IDLE["knife_rot"] if rot is None else rot
    m = Euler([math.radians(x) for x in rot], "XYZ").to_matrix()
    return tuple(round(math.degrees(x), 4) for x in m.to_euler(order))
