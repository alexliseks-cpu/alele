"""
Pure-math skeleton (R15 avatar arms + knives): rest pose and pose evaluation.

Every frame is a 4x4 in viewmodel (Blender armature) space, studs.  Bone
frames are Roblox joint frames (pivot position + Roblox part axes), so a
bone's local basis IS the Roblox Motor6D.Transform.

Control dictionary (what the animation channels evaluate to at time t):
    "R.pos"   (x, y, z)  centre of the RightHand block, viewmodel space, studs
    "R.rot"   (pitch, yaw, roll) deg, see hand_rotation()
    "R.elbow" (x, y, z)  offset added to the automatic elbow pole (studs)
    "R.shoulder" (x, y, z) shoulder pivot offset (studs, keep small)
    same with "L." for the left arm
    "knife.pos" (x, y, z) studs, knife link frame in the HAND SEMANTIC frame
                (origin = hand block centre, +X radial, +Y distal, +Z palmar)
    "knife.rot" (x, y, z) deg euler (Anim.knife_rot_order, default XYZ)
    "knife.anchor" "A" | "B" | "BLADE" | "KNIFE"
    "bf"  (a, b, latch)  butterfly: 0 = handle open, 1 = handle closed
    "cam.pos" (x, y, z) studs, "cam.rot" (x, y, z) deg: camera shake
"""

import math

from mathutils import Matrix, Vector, Euler

from . import spec

I4 = Matrix.Identity(4)
KS = spec.KNIFE_SCALE

# Roblox (x, y, z) -> Blender (x, -z, y)
KT = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))


def conv(v):
    return KT @ Vector(v)


def T(v):
    return Matrix.Translation(Vector(v))


def R3(axis, deg):
    return Matrix.Rotation(math.radians(deg), 3, axis)


def R4(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def frame(rot3, origin):
    m = rot3.to_4x4()
    m.translation = Vector(origin)
    return m


def side_sign(side):
    return 1.0 if side == "R" else -1.0


def mirror_x(v, side):
    x, y, z = v
    return (x * side_sign(side), y, z)


def euler_matrix(xyz, order="XYZ"):
    return Euler([math.radians(a) for a in xyz], order).to_matrix()


# ----------------------------------------------------------------------------
# hand orientation
# ----------------------------------------------------------------------------
# semantic frame (columns radial|ulnar, distal, palmar) in the neutral
# "handshake" pose: fingers forward, thumb up, palm towards the centre line
R_NEUTRAL = {
    "R": Matrix(((0, 0, -1), (0, 1, 0), (1, 0, 0))),
    "L": Matrix(((0, 0, 1), (0, 1, 0), (-1, 0, 0))),
}
# part-local axes expressed in the semantic frame (columns = part X, Y, Z)
PART_IN_SEM = {
    "R": Matrix(((0, 0, -1), (0, -1, 0), (-1, 0, 0))),
    "L": Matrix(((0, 0, 1), (0, -1, 0), (1, 0, 0))),
}


def hand_rotation(side, pyr):
    """Semantic hand frame in viewmodel space.
    pitch + : fingers (bottom of the hand block) tilt up
    yaw   + : fingers point towards the centre line
    roll  + : pronation (palm turns down)
    applied roll -> pitch -> yaw on top of the neutral handshake pose;
    mirrored for 'L' so equal numbers give mirrored poses."""
    p, y, r = pyr
    if side == "L":
        y, r = -y, -r
    # right hand: pronation (palm down, thumb towards the centre) = -Y rotation
    return R3("Z", y) @ R3("X", p) @ R3("Y", -r) @ R_NEUTRAL[side]


# ----------------------------------------------------------------------------
# R15 rest geometry (Blender coords, studs)
# ----------------------------------------------------------------------------
R15 = spec.R15
UPPER_TORSO = Vector(spec.UPPER_TORSO_POS)
WAIST = UPPER_TORSO + conv(R15["waist_in_upper"])
LOWER_TORSO = WAIST - conv(R15["waist_in_lower"])


def arm_rest(side):
    S = UPPER_TORSO + conv(mirror_x(R15["torso_shoulder"], side))
    up_c = S - conv(mirror_x(R15["upper_shoulder"], side))
    E = up_c + conv(R15["upper_elbow"])
    lo_c = E - conv(R15["lower_elbow"])
    W = lo_c + conv(R15["lower_wrist"])
    hand_c = W - conv(R15["hand_wrist"])
    return dict(shoulder=S, upper_c=up_c, elbow=E, lower_c=lo_c, wrist=W, hand_c=hand_c)


ARM_REST = {"R": arm_rest("R"), "L": arm_rest("L")}
# segment vectors in part-local (Roblox) coords
V_UPPER = {s: Vector(R15["upper_elbow"]) - Vector(mirror_x(R15["upper_shoulder"], s)) for s in ("R", "L")}
V_LOWER = Vector(R15["lower_wrist"]) - Vector(R15["lower_elbow"])
V_HAND = -Vector(R15["hand_wrist"])                       # wrist -> hand centre
L_UPPER = V_UPPER["R"].length
L_LOWER = V_LOWER.length

KNIFE_REST_IN_HAND = I4.copy()     # knife link frame at the hand centre at rest


# ----------------------------------------------------------------------------
# butterfly links
# ----------------------------------------------------------------------------
PIN_A = Vector(spec.BF_PIN_A) * KS
PIN_B = Vector(spec.BF_PIN_B) * KS
LATCH_PIVOT = Vector(spec.BF_LATCH_PIVOT) * KS


def bf_joint_a(a):
    return T(PIN_A) @ R4("X", spec.BF_A_CLOSED_DEG * a) @ T(-PIN_A)


def bf_joint_b(b):
    return T(PIN_B) @ R4("X", spec.BF_B_CLOSED_DEG * b) @ T(-PIN_B)


def bf_link_frames(anchor_world, anchor, a, b):
    """World frames of links A, BLADE, B given the anchored one."""
    ja, jb = bf_joint_a(a), bf_joint_b(b)
    if anchor in ("A", "KNIFE"):
        A = anchor_world
    elif anchor == "BLADE":
        A = anchor_world @ ja.inverted()
    elif anchor == "B":
        A = anchor_world @ (ja @ jb).inverted()
    else:
        raise ValueError(f"bad anchor {anchor}")
    blade = A @ ja
    return A, blade, blade @ jb


# ----------------------------------------------------------------------------
# arm IK
# ----------------------------------------------------------------------------
def _basis_from(a, b):
    """orthonormal 3x3 with col0 = a (unit), col1 = b orthogonalised."""
    a = a.normalized()
    b = (b - a * b.dot(a))
    if b.length < 1e-6:
        b = Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))
        b = b - a * b.dot(a)
    b.normalize()
    return Matrix((a, b, a.cross(b))).transposed()


def solve_arm(side, hand_c, sem_rot, elbow_bias=(0, 0, 0), shoulder_off=(0, 0, 0)):
    """-> (upper_world, lower_world, hand_world, info) joint frames."""
    sg = side_sign(side)
    rest = ARM_REST[side]
    S = rest["shoulder"] + Vector(shoulder_off)
    hand_rot = sem_rot @ PART_IN_SEM[side]          # part axes in world
    W = Vector(hand_c) - hand_rot @ V_HAND          # wrist pivot
    Lu, Lf = L_UPPER, L_LOWER
    info = {"stretched": False}
    d = W - S
    dist = d.length
    max_r = (Lu + Lf) * 0.998
    min_r = abs(Lu - Lf) + 0.15
    if dist > max_r:                   # pull the (hidden) shoulder towards the hand
        S = W - d.normalized() * max_r
        info["stretched"] = True
    elif dist < min_r:
        S = W - d.normalized() * min_r
    d = W - S
    dist = d.length
    u = d / dist

    distal = sem_rot.col[1].copy()
    hang = Vector((0.35 * sg, 0.45, 0.82)).normalized()     # elbow low and outside
    fore_pref = (distal * 0.80 + hang * 0.20).normalized()   # elbow -> wrist direction
    E_pref = W - fore_pref * Lf + Vector(elbow_bias)
    a = (Lu * Lu - Lf * Lf + dist * dist) / (2 * dist)
    h = math.sqrt(max(Lu * Lu - a * a, 0.0))
    C = S + u * a
    pv = E_pref - C
    pv = pv - u * pv.dot(u)
    if pv.length < 1e-6:
        pv = Vector((0.4 * sg, 0, -1))
        pv = pv - u * pv.dot(u)
    E = C + pv.normalized() * h

    # lower arm: +Y from wrist to elbow, X follows the hand (no wrist twist)
    yl = (E - W).normalized()
    lo = _basis_from(yl, hand_rot.col[0].copy())    # cols: Y, X, -Z  (reorder below)
    xl = lo.col[1]
    zl = xl.cross(yl)
    lower_rot = Matrix((xl, yl, zl)).transposed()
    # upper arm: part-local segment vector maps onto (E - S), X follows lower arm
    a_loc = V_UPPER[side].normalized()
    loc_b = _basis_from(a_loc, Vector((1, 0, 0)))
    wld_b = _basis_from((E - S).normalized(), lower_rot.col[0].copy())
    upper_rot = wld_b @ loc_b.transposed()

    rel = lower_rot.transposed() @ hand_rot
    ry = -rel.col[1]                                   # distal in lower-arm coords
    # flex: distal towards palmar; dev: towards radial
    pal = -Vector((sg, 0, 0))                          # palmar in part coords (-X right / +X left)
    rad = Vector((0, 0, -1))
    down = Vector((0, -1, 0))
    info["wrist_flex"] = math.degrees(math.atan2(ry.dot(pal), ry.dot(down)))
    info["wrist_dev"] = math.degrees(math.atan2(ry.dot(rad), ry.dot(down)))
    return frame(upper_rot, S), frame(lower_rot, E), frame(hand_rot, W), info


# ----------------------------------------------------------------------------
# full evaluation
# ----------------------------------------------------------------------------
def hand_semantic_frame(W, side="R"):
    """Knife reference frame: hand block centre + semantic axes (radial,
    distal, palmar) - what "knife.pos"/"knife.rot" are relative to."""
    hp = W[spec.ARM_CHAIN[side][2]]
    hand_c = hp.translation + hp.to_3x3() @ V_HAND
    return frame(hp.to_3x3() @ PART_IN_SEM[side].transposed(), hand_c)


DEFAULT_CTRL = {
    "R.pos": tuple(ARM_REST["R"]["hand_c"]), "R.rot": (-90, 0, 0), "R.elbow": (0, 0, 0), "R.shoulder": (0, 0, 0),
    "L.pos": tuple(ARM_REST["L"]["hand_c"]), "L.rot": (-90, 0, 0), "L.elbow": (0, 0, 0), "L.shoulder": (0, 0, 0),
    "knife.pos": (0, 0, 0), "knife.rot": (0, 0, 0), "knife.anchor": "A",
    "bf": (0, 0, 0), "cam.pos": (0, 0, 0), "cam.rot": (0, 0, 0),
}

PART_REST_ROT = KT.copy()      # every Roblox part frame at rest (identity in Roblox)


def evaluate(ctrl, knife_rot_order="XYZ", which_knife=None, info_out=None, rest=False):
    c = dict(DEFAULT_CTRL)
    c.update(ctrl)
    W = {spec.ROOT: frame(PART_REST_ROT, (0, 0, 0))}
    W["CameraBone"] = T(c["cam.pos"]) @ euler_matrix(c["cam.rot"], "XYZ").to_4x4() @ frame(PART_REST_ROT, (0, 0, 0))
    W["LowerTorso"] = frame(PART_REST_ROT, LOWER_TORSO)
    W["UpperTorso"] = frame(PART_REST_ROT, WAIST)
    for side in ("R", "L"):
        up, lo, ha = spec.ARM_CHAIN[side]
        if rest:
            r = ARM_REST[side]
            W[up] = frame(PART_REST_ROT, r["shoulder"])
            W[lo] = frame(PART_REST_ROT, r["elbow"])
            W[ha] = frame(PART_REST_ROT, r["wrist"])
            continue
        sem = hand_rotation(side, c[f"{side}.rot"])
        u, l, h, info = solve_arm(side, c[f"{side}.pos"], sem, c[f"{side}.elbow"], c[f"{side}.shoulder"])
        if info_out is not None:
            info_out[side] = info
        W[up], W[lo], W[ha] = u, l, h

    hand_sem = hand_semantic_frame(W)
    kp = T(c["knife.pos"]) @ euler_matrix(c["knife.rot"], knife_rot_order).to_4x4()
    rest_anchor = hand_sem @ KNIFE_REST_IN_HAND
    anchor_world = hand_sem @ kp
    a, b, latch = c["bf"]
    if which_knife in (None, "butterfly") and not rest:
        A, blade, B = bf_link_frames(anchor_world, c["knife.anchor"], a, b)
    else:
        A, blade, B = bf_link_frames(rest_anchor, "A", 0, 0)
        latch = 0.0
    W["BF_HandleA"] = A @ T(PIN_A)
    W["BF_Blade"] = blade @ T(PIN_A)
    W["BF_HandleB"] = B @ T(PIN_B)
    W["BF_Latch"] = B @ T(LATCH_PIVOT) @ R4("X", -spec.BF_LATCH_OPEN_DEG * latch)
    W["KR_Handle"] = anchor_world if (which_knife in (None, "karambit") and not rest) else rest_anchor
    return W


REST = evaluate({}, rest=True)
REST_INV = {k: v.inverted() for k, v in REST.items()}

BONE_LEN = {spec.ROOT: 0.3, "CameraBone": 0.25, "LowerTorso": 0.3, "UpperTorso": 0.5,
            "BF_HandleA": 0.25, "BF_Blade": 0.4, "BF_HandleB": 0.25, "BF_Latch": 0.12, "KR_Handle": 0.4}
for _s in ("R", "L"):
    _u, _l, _h = spec.ARM_CHAIN[_s]
    BONE_LEN[_u], BONE_LEN[_l], BONE_LEN[_h] = 0.6, 0.5, 0.25


def local_basis(world):
    """{bone: world} -> {bone: basis relative to the parent and the rest pose}."""
    out = {}
    for name, parent in spec.BONES:
        if parent is None:
            out[name] = REST_INV[name] @ world[name]
        else:
            ref = world[parent] @ REST_INV[parent] @ REST[name]
            out[name] = ref.inverted() @ world[name]
    return out
