"""Builds the whole Blender scene: rig, meshes, camera, preview environment."""

import importlib
import math

import bpy
from mathutils import Matrix

from . import spec, skeleton, rig as rigmod
from . import mesh_utils as mu
from .models import placeholders

MODEL_MODULES = {"arms": "vm.models.arms", "butterfly": "vm.models.butterfly", "karambit": "vm.models.karambit"}


def load_models(kind, use_final=True):
    """Return list of mesh objects for 'arms' | 'butterfly' | 'karambit'."""
    if use_final:
        try:
            mod = importlib.import_module(MODEL_MODULES[kind])
            objs = mod.build()
            print(f"[scene] {kind}: final model ({len(objs)} objects)")
            return objs, True
        except ModuleNotFoundError as e:
            if e.name != MODEL_MODULES[kind]:
                raise
    objs = getattr(placeholders, kind)()
    print(f"[scene] {kind}: placeholder ({len(objs)} objects)")
    return objs, False


def placeholder_materials(objs, kind):
    if kind == "arms":
        sleeve = mu.material("R15_Shirt", (0.025, 0.025, 0.03), 0.0, 0.85)
        skin = mu.material("R15_Skin", (0.80, 0.42, 0.16), 0.0, 0.6)
        for o in objs:
            mu.assign_material(o, skin if "Hand" in o.name else sleeve)
    elif kind == "butterfly":
        steel = mu.material("PH_BF_Handle", (0.45, 0.46, 0.48), 1.0, 0.45)
        blade = mu.material("PH_BF_Blade", (0.12, 0.12, 0.13), 1.0, 0.25)
        for o in objs:
            mu.assign_material(o, blade if "Blade" in o.name else steel)
    else:
        dark = mu.material("PH_KR_Dark", (0.06, 0.06, 0.065), 0.3, 0.5)
        steel = mu.material("PH_KR_Steel", (0.5, 0.5, 0.52), 1.0, 0.35)
        for o in objs:
            mu.assign_material(o, steel if "Ring" in o.name else dark)


def build_scene(use_final=True, preview_env=True):
    rigmod.clear_scene()
    rig = rigmod.build_armature()
    groups = {}
    for kind in ("arms", "butterfly", "karambit"):
        objs, final = load_models(kind, use_final)
        if not final:
            placeholder_materials(objs, kind)
        col = rigmod.collection(f"Model_{kind}")
        for o in objs:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            col.objects.link(o)
        if kind == "arms":
            left = []
            for o in objs:
                if o.name.startswith("Right"):
                    left.append(mu.mirror_x_object(o, "Left" + o.name[5:]))
            objs = objs + left
        else:
            # knives are modelled in metres -> studs
            for o in objs:
                o.data.transform(Matrix.Scale(spec.KNIFE_SCALE, 4))
                o["knife_scale"] = spec.KNIFE_SCALE
        for o in objs:
            bone = spec.mesh_bone(o.name)
            if bone not in skeleton.REST:
                raise ValueError(f"mesh {o.name}: no bone {bone}")
            rigmod.attach(rig, o, bone)
        groups[kind] = objs
    cam = add_camera(rig)
    if preview_env:
        add_preview_env()
    return rig, cam, groups


def add_camera(rig):
    cd = bpy.data.cameras.new("VM_Camera")
    cd.sensor_fit = "VERTICAL"
    cd.angle_y = math.radians(70.0)          # Roblox default FieldOfView
    cd.clip_start = 0.1                      # Roblox near plane
    cd.clip_end = 200
    cam = bpy.data.objects.new("VM_Camera", cd)
    rigmod.collection("Rig").objects.link(cam)
    rigmod.attach(rig, cam, "CameraBone")   # Roblox camera axes == Blender camera axes
    bpy.context.scene.camera = cam
    return cam


def add_preview_env():
    """Checker floor + back wall so motion reads in Workbench previews."""
    import bmesh
    col = "PreviewEnv"
    a = mu.material("ENV_A", (0.42, 0.40, 0.37), 0, 0.9)
    b = mu.material("ENV_B", (0.33, 0.31, 0.29), 0, 0.9)
    w = mu.material("ENV_Wall", (0.62, 0.58, 0.50), 0, 0.9)
    bm = bmesh.new()
    n, s, z = 30, 0.8, -1.5
    mat_idx = []
    for i in range(-n // 2, n // 2):
        for j in range(-4, n):
            vs = [bm.verts.new((i * s, j * s, z)), bm.verts.new(((i + 1) * s, j * s, z)),
                  bm.verts.new(((i + 1) * s, (j + 1) * s, z)), bm.verts.new((i * s, (j + 1) * s, z))]
            f = bm.faces.new(vs)
            f.material_index = (i + j) % 2
    floor = mu.obj_from_bm("ENV_Floor", bm, col, smooth=False)
    floor.data.materials.append(a)
    floor.data.materials.append(b)
    bm = bmesh.new()
    mu.box(bm, (-12, 9, -1.5), (12, 9.4, 4))
    mu.box(bm, (-4.2, 1.5, -1.5), (-3.8, 9, 3))
    mu.box(bm, (1.5, 3.0, -1.5), (2.5, 4.0, -0.5))
    wall = mu.obj_from_bm("ENV_Wall", bm, col, smooth=False)
    wall.data.materials.append(w)
    world = bpy.data.worlds.new("World")
    world.color = (0.55, 0.65, 0.78)
    bpy.context.scene.world = world


def show_knife(groups, knife):
    for kind, objs in groups.items():
        if kind == "arms":
            continue
        hide = kind != knife
        for o in objs:
            o.hide_render = hide
            o.hide_viewport = hide
