"""
Butterfly INSPECT - CS2 variant A on the blocky R15 hand (4.40 s, priority Action).

Reference: CS2 butterfly inspect variant A (master take f72-f136; measured
frame by frame on take #1 f9-f71 in ref_specs/butterfly_inspect.md, sub-frame
samples from takes #2-#4).  Clip time = CS2 take-1 time + 0.067 s: the clip
starts exactly on common.IDLE one CS2 frame before the onset.

BEATS (clip time, s)
  0.00-0.07  wind-up: the knife rolls edge-on in the fist (slight dip)
  0.07-0.20  FAN OUT: the fist flies up / right and supinates; the free safe
             handle A drops out of the fist and whips clockwise over the top
             onto the spine ("flip"), the blade swings round to point right
  0.20-0.33  drape: A + blade hang straight down beside the thumb, weightless
  0.33-0.53  swing back: the hand pronates, A + blade whip back counter-
             clockwise over the top and land blade-up in a V ("catch")
  0.53-0.80  palm tricks: the knife stands up, rolls flat across the hand
             pointing right (handles clack together), pivots up to ~56 deg
  0.80-1.13  grab and drop: the fist closes on both handles, blade straight up
             and edge-on, dips low-left, rises and turns broadside
  1.13-1.33  present: rises up-right, tilts the blade to 48 deg, the handles
             splay into a narrow V
  1.33-3.07  HOLD / look (subtle breathing only)
  3.07-3.33  anticipation dip down-left, rebound up-right, A is let go
  3.33-3.60  TOSS-CLOSE: A whips clockwise over the top onto the spine, the
             blade folds onto B, the knife snaps shut over the fist ("latch")
  3.60-3.73  FLICK OPEN low: blade + A swing counter-clockwise over the top,
             blade points left at the bottom of the view ("flip", "catch")
  3.73-3.87  bottom out (follow-through of the flick)
  3.87-4.40  glide up / right into idle, tiny overshoot, flat landing on IDLE

RIG USAGE
  * The bite handle B stays in the fist for the whole clip (anchor "B" from
    t = 0, when the knife is open and the links coincide with the idle grip):
    bf b = blade relative to B, bf a = A relative to the blade - exactly the
    CS2 hierarchy (A = free handle on the spine side, B = held handle).
  * In-hand knife motion = common.GRIP rolled about the handle's long axis
    (KROLL) and tilted in the knife plane about the hand-block centre
    (KTILT); the held handle always passes through the centre of the hand
    block (no fingers: the hand turns around the knife / rolls it in the
    fist).  These two values are sampled every frame into knife.pos / rot.
  * knife_rot_order = "YXZ": the grip variations used here stay >= 20 deg
    away from that order's gimbal lock (XYZ locks at a 30 deg roll).
  * Key poses were solved numerically against the CS2 screen measurements
    (pivot, blade / handle screen angles, broadside vs edge-on, depth) under
    reach, wrist (|flex| <= 50, |dev| <= 28) and forearm-cover limits, then
    hand-tuned.  CS2 positions above mid-screen are lowered
    (y + 0.1 * (0.9 - y) / 0.5): the R15 shoulder sits low and close, so
    reaching them would put a large black forearm block across the view.
"""

import math

from mathutils import Euler, Vector

from ..core import Channel
from ... import skeleton
from . import common

LENGTH = 4.40
ORDER = "YXZ"
HAND_TURNS = (0.0, 0.0, 360.0)   # the fist ends one full roll on (same pose as IDLE)

# idle grip as a matrix and the hand-block centre in knife coordinates
_GRIP_M = skeleton.T(common.GRIP["pos"]) @ skeleton.euler_matrix(common.GRIP["rot"], "XYZ").to_4x4()
_HAND_IN_KNIFE = _GRIP_M.inverted() @ Vector((0.0, 0.0, 0.0))


def grip_pose(kroll, ktilt, kslide=0.0, compat=None):
    """knife (pos, rot in ORDER) = idle grip rolled about the knife's long axis
    by kroll, tilted about the knife X axis through the hand centre by ktilt
    and slid along the handle by kslide studs (- = pivot towards the hand)."""
    ph = _HAND_IN_KNIFE
    M = (_GRIP_M @ skeleton.T(ph) @ skeleton.R4("Y", kroll) @ skeleton.R4("X", ktilt)
         @ skeleton.T(-ph) @ skeleton.T((0.0, kslide, 0.0)))
    if compat is None:
        e = M.to_3x3().to_euler(ORDER)
    else:
        e = M.to_3x3().to_euler(ORDER, Euler([math.radians(x) for x in compat], ORDER))
    return tuple(M.translation), tuple(math.degrees(x) for x in e)


# ---------------------------------------------------------------------------
# key poses: t, hand pos, hand rot (pitch, yaw, roll), elbow, shoulder,
#            knife (kroll, ktilt), handles (a, b)
# ---------------------------------------------------------------------------
# @@KEYS@@
KEYS = [
    dict(t=0.067, name="windup", pos=(1.4800, 3.1348, -1.4251), rot=(85.13, 14.67, 81.23),
         elbow=(0.1476, -0.2757, -0.5114), sh=(0.0088, 0.0284, -0.0124), k=(-45.50, 7.19, 0.000), ab=(0.000, 0.000)),
    dict(t=0.100, name="f73", pos=(1.0156, 2.5233, -1.4581), rot=(85.36, -18.36, 150.22),
         elbow=(0.1472, -0.2758, -0.5115), sh=(0.0037, 0.0119, -0.0053), k=(-56.73, 36.16, 0.000), ab=(0.310, 0.000)),
    dict(t=0.133, name="f10", pos=(0.9038, 2.5229, -1.0098), rot=(85.58, -37.52, 177.76),
         elbow=(0.0759, -0.2917, -0.5059), sh=(0.0174, -0.0051, -0.0064), k=(-13.41, 65.68, 0.000), ab=(0.330, 0.030)),
    dict(t=0.150, name="f74", pos=(0.7593, 2.6210, -0.7497), rot=(85.28, -45.66, 213.07),
         elbow=(0.0432, -0.3019, -0.4897), sh=(0.0297, -0.0727, -0.1106), k=(18.55, 65.40, 0.000), ab=(0.440, 0.010)),
    dict(t=0.187, name="f174", pos=(1.1718, 2.6674, -0.5756), rot=(85.13, -54.80, 245.12),
         elbow=(0.0451, -0.2934, -0.5209), sh=(-0.0368, -0.1308, -0.2017), k=(33.44, 56.49, 0.000), ab=(0.780, 0.190)),
    dict(t=0.200, name="f11", pos=(1.2172, 2.7275, -0.5935), rot=(81.14, -64.10, 236.77),
         elbow=(0.0641, -0.3169, -0.5238), sh=(-0.0245, -0.0627, -0.2237), k=(35.79, 36.73, 0.000), ab=(0.940, 0.180)),
    dict(t=0.267, name="f12", pos=(1.4025, 2.9193, -0.4322), rot=(78.86, -83.37, 216.81),
         elbow=(-0.1702, -0.3443, -0.5019), sh=(0.0193, 0.3009, -0.1152), k=(39.13, 26.11, 0.000), ab=(0.990, 0.700)),
    dict(t=0.333, name="f13", pos=(1.4332, 3.0582, -0.4245), rot=(78.61, -84.08, 220.43),
         elbow=(-0.2789, -0.3485, -0.5105), sh=(0.0389, 0.3425, -0.0734), k=(37.51, 24.88, 0.000), ab=(0.990, 0.700)),
    dict(t=0.400, name="f14", pos=(1.3118, 2.9768, -0.6472), rot=(85.23, -77.85, 229.05),
         elbow=(-0.4332, -0.4064, -0.4553), sh=(0.0301, 0.2114, -0.1614), k=(39.01, 56.73, 0.000), ab=(0.970, 0.660)),
    dict(t=0.467, name="f15", pos=(0.5495, 2.9140, -1.0376), rot=(85.35, -83.20, 266.83),
         elbow=(-0.4331, -0.4063, -0.4552), sh=(0.0126, 0.0883, -0.0673), k=(58.98, 61.08, 0.000), ab=(0.680, 0.280)),
    dict(t=0.500, name="f257", pos=(0.9113, 2.8172, -0.9407), rot=(85.29, -69.13, 281.65),
         elbow=(-0.4227, -0.3939, -0.4674), sh=(0.0119, 0.0367, -0.0374), k=(63.17, 65.03, 0.000), ab=(0.500, 0.240)),
    dict(t=0.533, name="f16", pos=(0.9572, 2.7716, -0.9898), rot=(36.73, 13.73, 371.63),
         elbow=(-0.3398, -0.3939, -0.4320), sh=(0.1168, -0.1988, -0.1047), k=(63.06, 58.30, 0.000), ab=(0.380, 0.210)),
    dict(t=0.600, name="f17", pos=(1.7114, 2.3405, -0.9064), rot=(26.02, 27.31, 376.55),
         elbow=(-0.2795, -0.0756, -0.6264), sh=(0.0849, -0.0911, -0.1089), k=(40.45, 43.75, 0.000), ab=(0.170, 0.280)),
    dict(t=0.667, name="f18", pos=(1.6776, 2.9149, -0.4542), rot=(72.34, 6.47, 294.21),
         elbow=(-0.3951, 0.0778, -0.4610), sh=(0.2114, 0.3349, -0.1159), k=(53.51, -31.21, 0.000), ab=(0.000, 0.000)),
    dict(t=0.733, name="f19", pos=(1.5152, 3.0029, -0.5383), rot=(85.16, 9.25, 307.22),
         elbow=(-0.4046, 0.0989, -0.4121), sh=(0.1427, 0.3421, -0.1250), k=(59.93, -20.84, 0.000), ab=(0.090, 0.020)),
    dict(t=0.800, name="f20", pos=(1.6961, 2.9135, -0.8821), rot=(73.69, 19.15, 311.01),
         elbow=(-0.3696, 0.0938, -0.4120), sh=(0.0524, 0.1058, -0.0941), k=(39.85, 20.49, 0.000), ab=(0.000, 0.000)),
    dict(t=0.867, name="f21", pos=(0.7371, 2.9645, -1.2981), rot=(51.85, -4.75, 354.41),
         elbow=(-0.3693, 0.0934, -0.4122), sh=(0.0220, 0.0444, -0.0393), k=(8.78, 33.13, 0.000), ab=(0.000, 0.000)),
    dict(t=0.933, name="f22", pos=(0.5193, 2.6820, -1.4775), rot=(50.05, 3.93, 376.65),
         elbow=(-0.3695, 0.0935, -0.4119), sh=(0.0091, 0.0185, -0.0165), k=(35.78, 28.90, 0.000), ab=(0.000, 0.000)),
    dict(t=1.000, name="f23", pos=(0.3148, 2.6562, -1.4763), rot=(48.41, 8.56, 376.97),
         elbow=(-0.3693, 0.0935, -0.4121), sh=(0.0038, 0.0078, -0.0069), k=(35.82, 28.77, 0.000), ab=(0.000, 0.000)),
    dict(t=1.067, name="f24", pos=(0.3482, 2.8831, -1.4558), rot=(48.16, 9.14, 377.75),
         elbow=(-0.3694, 0.0936, -0.4119), sh=(0.0015, 0.0032, -0.0029), k=(35.20, 28.84, 0.000), ab=(0.000, 0.000)),
    dict(t=1.133, name="f25", pos=(0.3165, 2.9886, -1.3559), rot=(47.99, 14.24, 357.47),
         elbow=(-0.3693, 0.0937, -0.4120), sh=(0.0007, 0.0014, -0.0012), k=(34.13, 28.19, 0.000), ab=(0.000, 0.000)),
    dict(t=1.200, name="f26", pos=(0.5048, 3.0012, -1.0280), rot=(51.29, 21.84, 337.55),
         elbow=(-0.3694, 0.0937, -0.4120), sh=(0.0003, 0.0006, -0.0005), k=(35.36, 23.95, 0.000), ab=(0.050, 0.000)),
    dict(t=1.267, name="f27", pos=(0.6982, 2.9260, -0.8797), rot=(59.89, 30.20, 325.45),
         elbow=(-0.3629, 0.0968, -0.4153), sh=(0.0098, -0.0178, -0.0359), k=(14.87, 23.36, 0.000), ab=(0.160, 0.000)),
    dict(t=1.333, name="hold", pos=(0.7637, 2.8655, -0.7168), rot=(66.03, 42.02, 323.84),
         elbow=(-0.3063, 0.1117, -0.4235), sh=(0.0250, -0.0369, -0.1172), k=(7.86, 25.42, 0.000), ab=(0.110, 0.083)),
    dict(t=3.133, name="f55", pos=(0.3863, 2.8213, -1.0356), rot=(51.72, 45.62, 337.73),
         elbow=(-0.2719, 0.1388, -0.4299), sh=(0.0210, -0.0276, -0.0479), k=(17.37, 37.33, 0.000), ab=(0.140, 0.080)),
    dict(t=3.200, name="f56", pos=(0.0749, 2.7838, -1.4502), rot=(30.12, 51.20, 354.26),
         elbow=(-0.2674, 0.1433, -0.4306), sh=(0.0154, -0.0166, -0.0159), k=(35.47, 39.97, 0.000), ab=(0.120, 0.040)),
    dict(t=3.267, name="f57", pos=(0.4024, 2.8728, -1.0294), rot=(48.50, 46.45, 356.97),
         elbow=(-0.2529, 0.1528, -0.4327), sh=(0.0178, -0.0234, -0.0052), k=(33.76, 35.47, 0.000), ab=(0.230, 0.020)),
    dict(t=3.333, name="f58", pos=(0.7855, 2.8231, -0.8078), rot=(64.92, 54.87, 352.68),
         elbow=(-0.4148, 0.0688, -0.3814), sh=(0.0450, -0.1015, -0.0728), k=(14.37, 36.37, 0.000), ab=(0.330, 0.030)),
    dict(t=3.400, name="f59", pos=(1.3493, 2.7470, -0.7157), rot=(78.76, 60.54, 367.35),
         elbow=(-0.2459, 0.0237, -0.4802), sh=(0.0136, -0.0845, -0.2162), k=(-7.65, 14.01, 0.000), ab=(0.700, 0.010)),
    dict(t=3.467, name="f60", pos=(1.2743, 2.8549, -0.7994), rot=(73.16, 63.75, 367.63),
         elbow=(-0.2290, 0.0384, -0.4742), sh=(-0.0010, -0.0772, -0.1363), k=(-4.61, 7.08, 0.000), ab=(0.840, 0.260)),
    dict(t=3.533, name="f61", pos=(0.8534, 2.9573, -1.1121), rot=(51.92, 65.20, 381.24),
         elbow=(-0.2288, 0.0383, -0.4742), sh=(-0.0003, -0.0323, -0.0571), k=(35.22, 26.05, 0.000), ab=(0.910, 0.690)),
    dict(t=3.600, name="f62", pos=(0.8670, 3.1035, -1.1362), rot=(21.05, 53.83, 435.58),
         elbow=(-0.3209, 0.0469, -0.4559), sh=(0.0140, 0.0274, -0.1089), k=(65.89, 41.78, 0.000), ab=(1.000, 1.000)),
    dict(t=3.667, name="f63", pos=(0.9787, 2.8467, -1.4711), rot=(2.60, 71.67, 407.33),
         elbow=(-0.1901, -0.0152, -0.3011), sh=(-0.0164, -0.0368, -0.0572), k=(48.16, 39.26, 0.000), ab=(0.880, 0.240)),
    dict(t=3.733, name="f64", pos=(1.0898, 2.9003, -1.4525), rot=(12.29, 52.31, 456.53),
         elbow=(-0.1902, -0.0149, -0.3010), sh=(-0.0068, -0.0153, -0.0240), k=(36.83, 35.23, 0.000), ab=(0.050, 0.020)),
    dict(t=3.800, name="f65", pos=(1.0679, 2.8872, -1.4556), rot=(11.38, 46.26, 452.68),
         elbow=(-0.1903, -0.0148, -0.3010), sh=(-0.0028, -0.0064, -0.0100), k=(38.17, 26.65, 0.000), ab=(0.000, 0.000)),
    dict(t=3.867, name="f66", pos=(1.1344, 2.8211, -1.4592), rot=(18.80, 40.96, 452.45),
         elbow=(-0.1907, -0.0148, -0.3012), sh=(-0.0012, -0.0027, -0.0043), k=(36.29, 22.29, 0.000), ab=(0.000, 0.000)),
    dict(t=4.000, name="f68", pos=(1.2097, 2.7204, -1.4532), rot=(19.07, 27.16, 459.82),
         elbow=(-0.1806, -0.0200, -0.2955), sh=(-0.0017, -0.0012, -0.0018), k=(36.45, 29.24, 0.000), ab=(0.000, 0.000)),
    dict(t=4.133, name="f70", pos=(1.2625, 2.7719, -1.4310), rot=(28.31, 23.42, 472.52),
         elbow=(-0.1806, -0.0200, -0.2954), sh=(-0.0007, -0.0005, -0.0008), k=(26.17, 27.69, 0.000), ab=(0.000, 0.000)),
]
# @@END@@


# ---------------------------------------------------------------------------
# secondary layers
# ---------------------------------------------------------------------------
HOLD_T0, HOLD_T1 = 1.333, 3.067      # CS2 f28 .. f54
# breathing during the hold: (t, d_pos, d_pitch) on top of the hold key
HOLD_BREATH = [(1.70, (0.000, 0.004, -0.018), -0.25), (2.25, (0.004, -0.004, 0.022), 0.30),
               (2.75, (-0.002, 0.000, -0.010), -0.12)]
# handle extras (t, a, b): bounces at the stops / the V settling in the hold
BF_EXTRA = [(1.40, 0.095, 0.075), (1.47, 0.118, 0.085), (3.767, 0.0, 0.0), (3.80, 0.03, 0.0)]
# camera micro kicks (t, rot deg): flicks / catches, always back to zero
CAM = [(0.000, (0.0, 0.0, 0.0)), (0.100, (0.0, 0.0, 0.0)), (0.150, (0.30, 0.0, -0.20)), (0.230, (-0.10, 0.0, 0.08)),
       (0.320, (0.0, 0.0, 0.0)), (0.440, (0.0, 0.0, 0.0)), (0.533, (-0.22, 0.0, 0.12)), (0.640, (0.0, 0.0, 0.0)),
       (3.330, (0.0, 0.0, 0.0)), (3.420, (0.28, 0.0, -0.18)), (3.520, (0.0, 0.0, 0.0)), (3.600, (-0.20, 0.0, 0.10)),
       (3.650, (0.05, 0.0, 0.0)), (3.740, (-0.32, 0.0, -0.12)), (3.840, (0.08, 0.0, 0.04)), (3.960, (0.0, 0.0, 0.0))]
MARKERS = [(0.090, "Sound", "flip"),     # A drops out of the fist and whips over the top
           (0.400, "Sound", "flip"),     # swing back over the top
           (0.533, "Sound", "catch"),    # lands blade-up in the V
           (0.667, "Sound", "catch"),    # handles clack together, knife laid flat
           (3.300, "Sound", "flip"),     # A released for the toss-close
           (3.600, "Sound", "latch"),    # knife snaps shut
           (3.633, "Sound", "flip"),     # flick open
           (3.733, "Sound", "catch")]    # handles slap together in the fist, open


def _key_hand(a, t, k, interp="smooth", tangent="auto", d_pos=(0.0, 0.0, 0.0), d_pitch=0.0):
    pos = tuple(x + d for x, d in zip(k["pos"], d_pos))
    rot = (k["rot"][0] + d_pitch, k["rot"][1], k["rot"][2])
    a.hand("R", t, pos=pos, rot=rot, elbow=k["elbow"], shoulder=k["sh"], interp=interp, tangent=tangent)


def build():
    a = common.new_anim("bf_inspect", LENGTH, knife_rot_order=ORDER,
                        description="Butterfly inspect (CS2 variant A): fan-out pendulum, palm roll, vertical "
                                    "display, 1.8 s hold, toss-close, low flick-open, settle")
    a.knife(0.0, anchor="B")           # B (bite handle) stays in the fist
    common.key_idle(a, 0.0)
    hold = None
    for k in KEYS:
        _key_hand(a, k["t"], k)
        if k["name"] == "hold":
            hold = k
    # hold / look: the pose arrives at HOLD_T0, breathes, is back at HOLD_T1
    for t, dp, dpitch in HOLD_BREATH:
        _key_hand(a, t, hold, d_pos=dp, d_pitch=dpitch)
    _key_hand(a, HOLD_T1, hold)
    # knife grip variation, sampled every frame
    g = Channel("grip", 3)
    g.add(0.0, (0.0, 0.0, 0.0), tangent="flat")
    for k in KEYS:
        g.add(k["t"], k["k"])
        if k["name"] == "hold":
            g.add(HOLD_T1, k["k"])
    g.add(LENGTH, (0.0, 0.0, 0.0), tangent="flat")
    compat = common.knife_rot_for_order(ORDER)
    n = int(round(LENGTH * a.fps))
    for f in range(1, n):
        t = f / a.fps
        kr, kt, ks = g.eval(t)
        pos, rot = grip_pose(kr, kt, ks, compat)
        compat = rot
        a.knife(t, pos=pos, rot=rot, interp="linear")
    # handles: CS2 handle angles per key + bounces at the stops
    for k in KEYS:
        a.bf(k["t"], a=k["ab"][0], b=k["ab"][1])
        if k["name"] == "hold":
            a.bf(HOLD_T1, a=k["ab"][0], b=k["ab"][1])
    for t, ha, hb in BF_EXTRA:
        a.bf(t, a=ha, b=hb)
    for t, r in CAM:
        a.cam(t, rot=r, pos=(0.0, 0.0, 0.0))
    for t, nm, val in MARKERS:
        a.marker(t, nm, val)
    # soft landing: tiny overshoot past IDLE, flat on IDLE at LENGTH
    common.settle_into_idle(a, LENGTH, dur=LENGTH - KEYS[-1]["t"], overshoot=0.15, max_pos=0.03, max_rot=2.5,
                            hand_turns=HAND_TURNS)
    return a
