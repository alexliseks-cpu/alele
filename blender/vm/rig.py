"""Blender side: armature, mesh placement, actions."""

import bpy
from bpy_extras import anim_utils
from mathutils import Matrix

from . import spec, skeleton

RIG_NAME = "VM_Rig"


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 30
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0


def collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def build_armature():
    arm = bpy.data.armatures.new(RIG_NAME)
    arm.display_type = "STICK"
    obj = bpy.data.objects.new(RIG_NAME, arm)
    collection("Rig").objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    ebs = {}
    for name, parent in spec.BONES:
        eb = arm.edit_bones.new(name)
        eb.head = (0, 0, 0)
        eb.tail = (0, 0.01, 0)
        eb.matrix = skeleton.REST[name]
        eb.length = skeleton.BONE_LEN[name]
        if parent:
            eb.parent = ebs[parent]
            eb.use_connect = False
        eb.use_deform = True
        ebs[name] = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in obj.pose.bones:
        pb.rotation_mode = "QUATERNION"
    # bone collections for the knives so they can be hidden in the UI
    for knife, bones in spec.KNIFE_BONES.items():
        bc = arm.collections.new(knife)
        for b in bones:
            bc.assign(arm.bones[b])
    return obj


def bone_tail_frame(rig, bone):
    """armature-space frame a bone-parented object is relative to (rest)."""
    b = rig.data.bones[bone]
    return b.matrix_local @ Matrix.Translation((0, b.length, 0))


def attach(rig, obj, bone, local=Matrix.Identity(4)):
    """Place `obj` (modelled in the bone's local frame) at the bone's rest
    and parent it to the bone."""
    obj.parent = rig
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = bone_tail_frame(rig, bone).inverted() @ skeleton.REST[bone] @ local


def write_action(rig, anim, baked):
    """baked: list of {bone: (loc, quat)} per frame at anim.fps.  Creates an
    Action keyed every frame (scene runs at 30 fps, keys at fractional frames
    when baking at 60)."""
    name = anim.name
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if rig.animation_data is None:
        rig.animation_data_create()
    slot = act.slots.new(id_type="OBJECT", name=rig.name)
    layer = act.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    bag = strip.channelbag(slot, ensure=True)
    scene_fps = bpy.context.scene.render.fps
    step = scene_fps / anim.fps
    bones = list(baked[0].keys())
    for b in bones:
        dp_l = f'pose.bones["{b}"].location'
        dp_r = f'pose.bones["{b}"].rotation_quaternion'
        curves_l = [bag.fcurves.new(dp_l, index=i) for i in range(3)]
        curves_r = [bag.fcurves.new(dp_r, index=i) for i in range(4)]
        grp = bag.groups.new(b)
        for fc in curves_l + curves_r:
            fc.group = grp
        n = len(baked)
        for i, fc in enumerate(curves_l):
            fc.keyframe_points.add(n)
            co = []
            for f in range(n):
                co += [f * step, baked[f][b][0][i]]
            fc.keyframe_points.foreach_set("co", co)
            fc.keyframe_points.foreach_set("interpolation", [1] * n)  # LINEAR
            fc.update()
        for i, fc in enumerate(curves_r):
            fc.keyframe_points.add(n)
            co = []
            for f in range(n):
                co += [f * step, baked[f][b][1][i]]
            fc.keyframe_points.foreach_set("co", co)
            fc.keyframe_points.foreach_set("interpolation", [1] * n)
            fc.update()
    for t, mname, val in anim.markers:
        pm = act.pose_markers.new(f"{mname}:{val}" if val else mname)
        pm.frame = int(round(t * scene_fps))
    act["knife"] = anim.kind
    act["loop"] = anim.loop
    act["length_s"] = anim.length
    act.frame_range = (0, anim.length * scene_fps)
    act.use_frame_range = True
    return act, slot


def assign_action(rig, act):
    rig.animation_data.action = act
    rig.animation_data.action_slot = act.slots[0]
    sc = bpy.context.scene
    sc.frame_start = 0
    sc.frame_end = int(round(act["length_s"] * sc.render.fps))
