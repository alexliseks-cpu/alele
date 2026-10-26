"""Stand-in geometry that obeys spec.py exactly.

arms(): R15 block-rig arms (studs, part frames) - preview only, never exported
        (in Roblox the player's own avatar arms are used).
butterfly() / karambit(): low-detail knives (metres, knife frames) used until
        the final models exist.
"""

import math

import bmesh
from mathutils import Matrix, Vector

from .. import spec
from .. import mesh_utils as mu


def rounded_box(name, size, center, bevel=0.08):
    bm = bmesh.new()
    sx, sy, sz = (s / 2 for s in size)
    cx, cy, cz = center
    mu.box(bm, (cx - sx, cy - sy, cz - sz), (cx + sx, cy + sy, cz + sz))
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=3, affect="EDGES", profile=0.5)
    return mu.obj_from_bm(name, bm, smooth=True, auto_smooth_deg=40)


def arms():
    """Right arm only (left is mirrored by the builder)."""
    r = spec.R15
    up_c = -Vector(r["upper_shoulder"])
    lo_c = -Vector(r["lower_elbow"])
    ha_c = -Vector(r["hand_wrist"])
    return [
        rounded_box("RightUpperArm_Mesh", r["upper_size"], up_c, 0.1),
        rounded_box("RightLowerArm_Mesh", r["lower_size"], lo_c, 0.1),
        rounded_box("RightHand_Mesh", r["hand_size"], ha_c, 0.07),
    ]


def butterfly():
    out = []
    T, W, L = spec.BF_HANDLE_THICK, spec.BF_HANDLE_WIDTH, spec.BF_HANDLE_LEN
    pa, pb = Vector(spec.BF_PIN_A), Vector(spec.BF_PIN_B)
    bm = bmesh.new()
    mu.box(bm, (-T / 2, -L, 0.0), (T / 2, spec.BF_HANDLE_FRONT, W), Matrix.Translation(-pa))
    out.append(mu.obj_from_bm("BF_HandleA_Mesh", bm, smooth=False))
    bm = bmesh.new()
    mu.box(bm, (-T / 2, -L, -W), (T / 2, spec.BF_HANDLE_FRONT, 0.0), Matrix.Translation(-pb))
    out.append(mu.obj_from_bm("BF_HandleB_Mesh", bm, smooth=False))
    hw, bl = spec.BF_BLADE_HALF_WIDTH, spec.BF_BLADE_LEN
    prof = [(-spec.BF_TANG_BACK, -hw * 0.8), (0.012, -hw), (bl * 0.75, -hw * 0.8), (bl, 0.002),
            (bl * 0.72, hw * 0.75), (0.01, hw), (-spec.BF_TANG_BACK, hw * 0.8)]
    bm = bmesh.new()
    mu.extrude_profile(bm, prof, -spec.BF_BLADE_THICK / 2, spec.BF_BLADE_THICK / 2, Matrix.Translation(-pa))
    out.append(mu.obj_from_bm("BF_Blade_Mesh", bm, smooth=False))
    bm = bmesh.new()
    mu.box(bm, (-0.003, -spec.BF_LATCH_LEN, -0.002), (0.003, 0.0, 0.002))
    out.append(mu.obj_from_bm("BF_Latch_Mesh", bm, smooth=False))
    return out


def karambit():
    out = []
    bm = bmesh.new()
    R = (spec.KR_RING_OUTER_R + spec.KR_RING_INNER_R) / 2
    r = (spec.KR_RING_OUTER_R - spec.KR_RING_INNER_R) / 2
    path = [Vector((0, math.cos(2 * math.pi * i / 24) * R, math.sin(2 * math.pi * i / 24) * R)) for i in range(25)]
    mu.tube(bm, path, r, segs=8, up=Vector((1, 0, 0)), cap=False)
    out.append(mu.obj_from_bm("KR_Handle_Mesh_Ring", bm))
    bm = bmesh.new()
    mu.box(bm, (-spec.KR_HANDLE_THICK / 2, spec.KR_HANDLE_START, -0.012), (spec.KR_HANDLE_THICK / 2, spec.KR_HANDLE_END, 0.010))
    out.append(mu.obj_from_bm("KR_Handle_Mesh", bm, smooth=False))
    n = 12
    pts_top, pts_bot = [], []
    rad = spec.KR_BLADE_ARC_LEN / math.radians(spec.KR_BLADE_CURVE_DEG)
    cy, cz = spec.KR_HANDLE_END, -rad
    for i in range(n + 1):
        a = math.radians(spec.KR_BLADE_CURVE_DEG) * i / n
        w = 0.011 * (1 - i / n) + 0.0008
        y = cy + math.sin(a) * rad
        z = cz + math.cos(a) * rad
        nz, ny = math.cos(a), math.sin(a)
        pts_top.append((y, z))
        pts_bot.append((y - ny * w, z - nz * w))
    prof = pts_top + list(reversed(pts_bot))
    bm = bmesh.new()
    mu.extrude_profile(bm, prof, -spec.KR_BLADE_THICK / 2, spec.KR_BLADE_THICK / 2)
    out.append(mu.obj_from_bm("KR_Handle_Mesh_Blade", bm, smooth=False))
    return out
