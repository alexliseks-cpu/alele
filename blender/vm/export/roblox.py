"""
Roblox export: KeyframeSequences (.rbxmx), rig data (Lua), mesh FBX.

Rig model built in Roblox by the setup script (see roblox/SetupKnifeViewmodels.lua):
  * one invisible, tiny "joint part" per bone, named like the bone, placed at
    the bone's rest pivot (orientation = bone axes);
  * Motor6D (named like the bone) in the parent joint part:
        Part0 = parent joint part, Part1 = joint part,
        C0 = parentPivot:Inverse() * pivot, C1 = identity
    so Motor6D.Transform == the bone's local basis (exactly what the Pose
    CFrames below contain);
  * every imported MeshPart "<Bone>_Mesh..." is welded to its joint part.
"""

import math
import os
from xml.sax.saxutils import escape

from mathutils import Matrix, Quaternion, Vector

from .. import spec, skeleton

S = spec.STUDS_PER_UNIT
K = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))      # blender -> roblox axes


def world_cf(m):
    """Blender viewmodel-space frame -> Roblox (rotation K*R, pos S*K*t)."""
    r = K @ m.to_3x3()
    t = (K @ m.translation) * S
    return (t.x, t.y, t.z, r[0][0], r[0][1], r[0][2], r[1][0], r[1][1], r[1][2], r[2][0], r[2][1], r[2][2])


def local_cf(loc, quat):
    """Local basis (bone axes) -> Roblox CFrame components (pos in studs)."""
    r = quat.to_matrix()
    t = Vector(loc) * S
    return (t.x, t.y, t.z, r[0][0], r[0][1], r[0][2], r[1][0], r[1][1], r[1][2], r[2][0], r[2][1], r[2][2])


def fmt(x):
    if abs(x) < 5e-8:
        return "0"
    s = f"{x:.6g}"
    return s


# ----------------------------------------------------------------------------
# keyframe reduction (Douglas-Peucker over all joints, world-space error)
# ----------------------------------------------------------------------------
# lever arm (studs) used to turn a joint's rotation error into a distance
LEVER = {b: 0.5 for b, _ in spec.BONES}
LEVER.update({"RightUpperArm": 2.6, "RightLowerArm": 2.0, "RightHand": 1.6,
              "LeftUpperArm": 2.0, "LeftLowerArm": 1.4, "LeftHand": 0.5,
              "BF_HandleA": 1.5, "BF_Blade": 1.3, "BF_HandleB": 1.5, "BF_Latch": 0.25,
              "KR_Handle": 1.8, "CameraBone": 12.0})


def _seg_error(baked, bones, i0, i1):
    """max error (m) of linear interpolation between frames i0 and i1."""
    worst, wi = 0.0, -1
    a, b = baked[i0], baked[i1]
    n = i1 - i0
    for i in range(i0 + 1, i1):
        u = (i - i0) / n
        fr = baked[i]
        e = 0.0
        for bn in bones:
            la, qa = a[bn]
            lb, qb = b[bn]
            l, q = fr[bn]
            li = la.lerp(lb, u)
            qi = qa.slerp(qb, u)
            ang = qi.rotation_difference(q).angle
            if ang > math.pi:
                ang = 2 * math.pi - ang
            err = (li - l).length + ang * LEVER.get(bn, 0.05)
            if err > e:
                e = err
        if e > worst:
            worst, wi = e, i
    return worst, wi


def reduce_keyframes(baked, bones, tol=0.004, force=()):
    n = len(baked)
    keep = {0, n - 1, *force}
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 - i0 < 2:
            continue
        inner = [k for k in keep if i0 < k < i1]
        if inner:
            pts = [i0] + sorted(inner) + [i1]
            for x, y in zip(pts[:-1], pts[1:]):
                stack.append((x, y))
            continue
        err, wi = _seg_error(baked, bones, i0, i1)
        # also guard against > 170 deg between keys (slerp would take the short way)
        if err > tol or i1 - i0 > 30:
            if wi < 0:
                wi = (i0 + i1) // 2
            keep.add(wi)
            stack.append((i0, wi))
            stack.append((wi, i1))
    return sorted(keep)


# ----------------------------------------------------------------------------
# rbxmx writer
# ----------------------------------------------------------------------------
class Rbx:
    def __init__(self):
        self.n = 0
        self.out = []

    def ref(self):
        self.n += 1
        return f"RBX{self.n:08X}"

    def open(self, cls, props):
        self.out.append(f'<Item class="{cls}" referent="{self.ref()}"><Properties>')
        for kind, name, val in props:
            if kind == "string":
                self.out.append(f'<string name="{name}">{escape(val)}</string>')
            elif kind == "bool":
                self.out.append(f'<bool name="{name}">{"true" if val else "false"}</bool>')
            elif kind == "float":
                self.out.append(f'<float name="{name}">{fmt(val)}</float>')
            elif kind == "token":
                self.out.append(f'<token name="{name}">{int(val)}</token>')
            elif kind == "cf":
                c = [fmt(x) for x in val]
                self.out.append(f'<CoordinateFrame name="{name}"><X>{c[0]}</X><Y>{c[1]}</Y><Z>{c[2]}</Z>'
                                f'<R00>{c[3]}</R00><R01>{c[4]}</R01><R02>{c[5]}</R02>'
                                f'<R10>{c[6]}</R10><R11>{c[7]}</R11><R12>{c[8]}</R12>'
                                f'<R20>{c[9]}</R20><R21>{c[10]}</R21><R22>{c[11]}</R22></CoordinateFrame>')
            elif kind == "source":
                safe = val.replace("]]>", "]]]]><![CDATA[>")
                self.out.append(f'<ProtectedString name="{name}"><![CDATA[{safe}]]></ProtectedString>')
            else:
                raise ValueError(kind)
        self.out.append("</Properties>")

    def close(self):
        self.out.append("</Item>")

    def text(self):
        return ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">\n'
                + "\n".join(self.out) + "\n</roblox>\n")


PRIORITY = {"Idle": 0, "Movement": 1, "Action": 2, "Action2": 3, "Action3": 4, "Action4": 5, "Core": 1000}


def children_map(bones):
    ch = {b: [] for b in bones}
    for b in bones:
        p = spec.BONE_PARENT[b]
        if p is not None and p in ch:
            ch[p].append(b)
    return ch


def write_kfs(rbx, anim, baked, tol=0.004):
    """Append one KeyframeSequence for `anim` (baked local bases at anim.fps)."""
    bones = spec.bones_for(anim.kind)
    fps = anim.fps
    force = set()
    marker_at = {}
    for t, name, val in anim.markers:
        i = min(len(baked) - 1, max(0, int(round(t * fps))))
        force.add(i)
        marker_at.setdefault(i, []).append((name, val))
    keep = reduce_keyframes(baked, [b for b in bones if b != spec.ROOT], tol, force)
    ch = children_map(bones)
    rbx.open("KeyframeSequence", [("string", "Name", anim.roblox_name), ("bool", "Loop", anim.loop),
                                  ("token", "Priority", PRIORITY[anim.priority]),
                                  ("float", "AuthoredHipHeight", 2.0)])

    def pose(fr, b):
        if b == spec.ROOT:
            cf = (0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1)
            w = 0.0
        else:
            cf = local_cf(*fr[b])
            w = 1.0
        rbx.open("Pose", [("string", "Name", b), ("cf", "CFrame", cf), ("token", "EasingDirection", 0),
                          ("token", "EasingStyle", 0), ("float", "Weight", w)])
        for c in ch[b]:
            pose(fr, c)
        rbx.close()

    for i in keep:
        t = i / fps
        rbx.open("Keyframe", [("string", "Name", "Keyframe"), ("float", "Time", t)])
        pose(baked[i], spec.ROOT)
        for name, val in marker_at.get(i, []):
            rbx.open("KeyframeMarker", [("string", "Name", name), ("string", "Value", val)])
            rbx.close()
        rbx.close()
    rbx.close()
    return len(keep)


# ----------------------------------------------------------------------------
# rig data (Lua module) for the setup script / runtime
# ----------------------------------------------------------------------------
def lua_cf(c):
    return "CFrame.new(" + ", ".join(fmt(x) for x in c) + ")"


def lua_v3(v):
    return f"Vector3.new({fmt(v[0])}, {fmt(v[1])}, {fmt(v[2])})"


def offset_cf(parent, bone):
    """Pivot of `bone` relative to the pivot of `parent` (parent bone axes =
    Roblox part axes) - directly usable as a Motor6D C0 piece."""
    m = skeleton.REST[parent].inverted() @ skeleton.REST[bone]
    loc, q, _ = m.decompose()
    return local_cf(loc, q)


def rig_data_lua(knife_meshes, textures=None, idle_grips=None):
    """knife_meshes: {knife: [ {name, bone, group, center, size} ]} with
    center/size already in knife MODEL space Roblox coords (studs).
    idle_grips: {knife: (loc, quat)} Transform of the knife root joint in the
    idle pose (used to weld world models to the character's hand)."""
    textures = textures or {}
    idle_grips = idle_grips or {}
    L = ["-- AUTO-GENERATED by blender/build.py - do not edit by hand.",
         "-- Rig description of the knife viewmodels (studs, Roblox axes).", "return {", "\tVersion = 1,"]
    L.append("\tBones = {")
    for b, p in spec.BONES:
        off = lua_cf(offset_cf(p, b)) if p else "CFrame.new()"
        L.append(f'\t\t{{ Name = "{b}", Parent = {("nil" if p is None else chr(34) + p + chr(34))}, '
                 f'Joint = "{spec.JOINT_NAME.get(b, b)}", Offset = {off} }},')
    L.append("\t},")
    r = spec.R15
    L.append("\t-- default R15 block-rig attachments (used when the avatar part lacks them)")
    L.append("\tR15 = {")
    for side, pre in (("R", "Right"), ("L", "Left")):
        sg = 1 if side == "R" else -1
        us = (r["upper_shoulder"][0] * sg, r["upper_shoulder"][1], r["upper_shoulder"][2])
        L.append(f"\t\t{pre}UpperArm = {{ {pre}ShoulderRigAttachment = {lua_v3(us)}, {pre}ElbowRigAttachment = {lua_v3(r['upper_elbow'])} }},")
        L.append(f"\t\t{pre}LowerArm = {{ {pre}ElbowRigAttachment = {lua_v3(r['lower_elbow'])}, {pre}WristRigAttachment = {lua_v3(r['lower_wrist'])} }},")
        L.append(f"\t\t{pre}Hand = {{ {pre}WristRigAttachment = {lua_v3(r['hand_wrist'])} }},")
    L.append("\t\tSizes = { UpperArm = " + lua_v3(r["upper_size"]) + ", LowerArm = " + lua_v3(r["lower_size"])
             + ", Hand = " + lua_v3(r["hand_size"]) + " },")
    L.append("\t},")
    L.append("\tKnives = {")
    for knife, meshes in knife_meshes.items():
        kb = spec.KNIFE_BONES[knife]
        rest_frame = knife_model_frame(knife)
        L.append(f"\t\t{knife.capitalize()} = {{")
        L.append("\t\t\tBones = { " + ", ".join(f'"{b}"' for b in kb) + " },")
        g = idle_grips.get(knife)
        L.append("\t\t\t-- Transform of the knife root joint in the idle pose (3rd-person grip)")
        L.append(f"\t\t\tIdleGrip = {lua_cf(local_cf(*g)) if g else 'CFrame.new()'},")
        L.append("\t\t\t-- joint pivots in knife model space (rest = open butterfly)")
        L.append("\t\t\tPivots = {")
        for b in kb:
            L.append(f"\t\t\t\t{b} = {lua_cf(world_cf(rest_frame.inverted() @ skeleton.REST[b]))},")
        L.append("\t\t\t},")
        L.append("\t\t\tMeshes = {")
        for m in meshes:
            L.append(f'\t\t\t\t{{ Name = "{m["name"]}", Bone = "{m["bone"]}", Group = "{m["group"]}", '
                     f'Center = {lua_v3(m["center"])}, Size = {lua_v3(m["size"])} }},')
        L.append("\t\t\t},")
        L.append("\t\t},")
    L.append("\t},")
    L.append("\t-- fill in the rbxassetid:// of the uploaded PNGs (see README) or leave empty")
    L.append("\tTextures = {")
    for name in sorted(textures):
        L.append(f'\t\t{name} = {{ ColorMap = "", NormalMap = "", RoughnessMap = "", MetalnessMap = "" }},')
    L.append("\t},")
    L.append("}")
    return "\n".join(L) + "\n"


def knife_model_frame(knife):
    """Blender rest frame that defines knife MODEL space (FBX export space)."""
    if knife == "butterfly":
        return skeleton.REST["BF_HandleA"] @ skeleton.T(-skeleton.PIN_A)
    return skeleton.REST["KR_Handle"]
