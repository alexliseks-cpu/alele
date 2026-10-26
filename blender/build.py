"""
Build everything: Blender scene, baked knife textures, all animations,
.blend file, knife meshes (FBX + GLB), Roblox KeyframeSequences (.rbxmx),
rig data for the Lua runtime and preview videos.

Run (needs Blender 5.x Python - either the pip `bpy` module or Blender itself):
    python blender/build.py [options]
    blender -b --python blender/build.py -- [options]
Previews need an X server for Workbench: prefix with `xvfb-run -a` on Linux.

Options:
    --no-bake        skip texture baking (faster, keeps procedural materials)
    --no-preview     skip preview videos
    --anims a,b,c    only these animations (catalog names)
    --beauty         also render EEVEE showcase videos (<anim>_hq.mp4, slow)
    --placeholders   use placeholder knife models
    --out DIR        output root (default: repo root)
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402

from vm import spec, skeleton, scene, rig as rigmod, preview  # noqa: E402
from vm.anim import catalog  # noqa: E402
from vm.export import roblox  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        return ARGS[i + 1] if i + 1 < len(ARGS) and not ARGS[i + 1].startswith("--") else True
    return default


REPO = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(opt("--out", REPO))
EXPORT = os.path.join(ROOT, "export")
ROBLOX_SRC = os.path.join(ROOT, "roblox", "src", "KnifeSystem")
PREVIEWS = os.path.join(ROOT, "previews")


def tex_group(o):
    return o.get("tex_group") or ("blade" if "Blade" in o.name else "handle")


def knife_objects(groups, knife):
    return [o for o in groups[knife] if o.type == "MESH"]


def export_knife_meshes(groups, knife, out_dir):
    """Write <Knife>.fbx / .glb in knife MODEL space (studs, Y-up) and return
    mesh info for the rig data."""
    frame = roblox.knife_model_frame(knife)
    inv = frame.inverted()
    tmp_col = bpy.data.collections.new(f"EXPORT_{knife}")
    bpy.context.scene.collection.children.link(tmp_col)
    copies, info = [], []
    rig = bpy.data.objects[rigmod.RIG_NAME]
    rig.data.pose_position = "REST"                 # meshes at their bind pose
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    originals = knife_objects(groups, knife)
    real_names = {o: o.name for o in originals}
    for o in originals:
        ev = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        me.transform(inv @ o.matrix_world)
        o.name = real_names[o] + "__orig"          # free the exact name for the export copy
        me.name = real_names[o]
        c = bpy.data.objects.new(real_names[o], me)
        tmp_col.objects.link(c)
        copies.append(c)
        xs = [v.co for v in me.vertices]
        mn = [min(v[i] for v in xs) for i in range(3)]
        mx = [max(v[i] for v in xs) for i in range(3)]
        cen = [(a + b) / 2 for a, b in zip(mn, mx)]
        size = [b - a for a, b in zip(mn, mx)]
        # Roblox axes: (x, y, z) = (x, z, -y)
        info.append(dict(name=c.name, bone=spec.mesh_bone(c.name), group=tex_group(o),
                         center=(cen[0], cen[2], -cen[1]), size=(size[0], size[2], size[1]),
                         tris=sum(len(p.vertices) - 2 for p in me.polygons)))
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for c in copies:
        c.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    base = os.path.join(out_dir, knife.capitalize())
    bpy.ops.export_scene.fbx(filepath=base + ".fbx", use_selection=True, object_types={"MESH"},
                             axis_forward="-Z", axis_up="Y", global_scale=1.0, apply_unit_scale=False,
                             apply_scale_options="FBX_SCALE_NONE", bake_space_transform=False,
                             use_mesh_modifiers=True, mesh_smooth_type="FACE", use_tspace=True,
                             path_mode="COPY", embed_textures=True, add_leaf_bones=False)
    try:
        bpy.ops.export_scene.gltf(filepath=base + ".glb", export_format="GLB", use_selection=True,
                                  export_yup=True, export_apply=True)
    except Exception as e:  # glTF add-on missing in some builds
        print("[export] glb skipped:", e)
    for c in copies:
        bpy.data.objects.remove(c)
    bpy.data.collections.remove(tmp_col)
    for o, n in real_names.items():
        o.name = n
    rig.data.pose_position = "POSE"
    bpy.context.view_layer.update()
    return info


def main():
    os.makedirs(EXPORT, exist_ok=True)
    os.makedirs(os.path.join(EXPORT, "roblox"), exist_ok=True)
    os.makedirs(ROBLOX_SRC, exist_ok=True)
    use_final = not opt("--placeholders", False)
    rig, cam, groups = scene.build_scene(use_final=use_final)

    # ---- textures --------------------------------------------------------------
    tex_info = {}
    if not opt("--no-bake", False):
        from vm import bake
        for knife in ("butterfly", "karambit"):
            res = bake.bake_knife(knife_objects(groups, knife), knife, os.path.join(EXPORT, "textures"))
            for g in res:
                tex_info[f"{knife.capitalize()}_{g.capitalize()}"] = res[g]

    # ---- animations ------------------------------------------------------------
    names = catalog.available()
    only = opt("--anims")
    if isinstance(only, str):
        names = [n for n in names if n in only.split(",")]
    report = {}
    acts = {}
    bakes = {}
    for knife in ("butterfly", "karambit"):
        for n in names:
            a = catalog.build(n)
            if a.kind != knife:
                continue
            frames, baked = a.bake()
            act, _ = rigmod.write_action(rig, a, baked)
            acts[n] = (act, a)
            bakes[n] = baked

    def write_anim_folders(rbx):
        rbx.open("Folder", [("string", "Name", "Animations")])
        for knife in ("butterfly", "karambit"):
            rbx.open("Folder", [("string", "Name", knife.capitalize())])
            for n, (act, a) in acts.items():
                if a.kind != knife:
                    continue
                nk = roblox.write_kfs(rbx, a, bakes[n])
                report[n] = dict(roblox=a.roblox_name, length=a.length, loop=a.loop, keyframes=nk,
                                 markers=[list(m) for m in a.markers], warnings=a.warnings[:20])
                print(f"[anim] {n}: {a.length:.2f}s -> {nk} keyframes, {len(a.warnings)} warnings")
            rbx.close()
        rbx.close()

    rbx_anims = roblox.Rbx()
    write_anim_folders(rbx_anims)
    with open(os.path.join(EXPORT, "roblox", "KnifeAnimations.rbxmx"), "w") as f:
        f.write(rbx_anims.text())

    # NLA: one muted track per action so every clip is easy to find in Blender
    ad = rig.animation_data or rig.animation_data_create()
    for n, (act, a) in acts.items():
        tr = ad.nla_tracks.new()
        tr.name = n
        st = tr.strips.new(n, 0, act)
        tr.mute = True
    if acts:
        rigmod.assign_action(rig, next(iter(acts.values()))[0])

    # ---- meshes + rig data -------------------------------------------------------
    mesh_dir = os.path.join(EXPORT, "meshes")
    os.makedirs(mesh_dir, exist_ok=True)
    knife_meshes = {}
    for knife in ("butterfly", "karambit"):
        knife_meshes[knife] = export_knife_meshes(groups, knife, mesh_dir)
    idle_grips = {}
    for n, (act, a) in acts.items():
        if n.endswith("_idle"):
            root = spec.KNIFE_BONES[a.kind][0]
            idle_grips[a.kind] = bakes[n][0][root]
    with open(os.path.join(ROBLOX_SRC, "RigData.lua"), "w") as f:
        f.write(roblox.rig_data_lua(knife_meshes, tex_info, idle_grips))

    # ---- Roblox package: ReplicatedStorage.KnifeSystem (modules + clips) -------
    pkg = roblox.Rbx()
    pkg.open("Folder", [("string", "Name", "KnifeSystem")])
    for mod in ("RigData", "KnifeConfig", "KnifeAnimator", "KnifeBuilder", "KnifeViewmodel"):
        src_dir = ROBLOX_SRC if mod == "RigData" else os.path.join(REPO, "roblox", "src", "KnifeSystem")
        with open(os.path.join(src_dir, mod + ".lua")) as f:
            pkg.open("ModuleScript", [("string", "Name", mod), ("source", "Source", f.read())])
            pkg.close()
    write_anim_folders(pkg)
    pkg.open("Folder", [("string", "Name", "Knives")])
    pkg.close()
    pkg.close()
    with open(os.path.join(EXPORT, "roblox", "KnifeSystem.rbxmx"), "w") as f:
        f.write(pkg.text())
    client = roblox.Rbx()
    with open(os.path.join(REPO, "roblox", "src", "KnifeClientExample.client.lua")) as f:
        client.open("LocalScript", [("string", "Name", "KnifeClientExample"), ("source", "Source", f.read())])
    client.close()
    with open(os.path.join(EXPORT, "roblox", "KnifeClientExample.rbxmx"), "w") as f:
        f.write(client.text())
    shutil.copy(os.path.join(REPO, "roblox", "SetupKnifeViewmodels.lua"), os.path.join(EXPORT, "roblox", "SetupKnifeViewmodels.lua"))
    with open(os.path.join(EXPORT, "build_report.json"), "w") as f:
        json.dump(dict(animations=report, meshes=knife_meshes, textures=tex_info), f, indent=1, default=str)

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "KnifeViewmodels.blend"), compress=True)

    # ---- previews ---------------------------------------------------------------
    if not opt("--no-preview", False) and acts:
        os.makedirs(PREVIEWS, exist_ok=True)
        preview.setup_workbench(res=(960, 540))
        for n, (act, a) in acts.items():
            scene.show_knife(groups, a.kind)
            preview.render_action(rig, act, os.path.join(PREVIEWS, n), fps=30, every=2)
            shutil.rmtree(os.path.join(PREVIEWS, n + "_frames"), ignore_errors=True)
            print(f"[preview] {n}.mp4")
    if opt("--beauty", False) and acts:
        os.makedirs(PREVIEWS, exist_ok=True)
        preview.setup_beauty(res=(640, 360), samples=12)
        for o in bpy.data.objects:
            if o.name.startswith("ENV_"):
                o.hide_render = False
        for n, (act, a) in acts.items():
            scene.show_knife(groups, a.kind)
            preview.render_action(rig, act, os.path.join(PREVIEWS, n + "_hq"), fps=30, every=2)
            shutil.rmtree(os.path.join(PREVIEWS, n + "_hq_frames"), ignore_errors=True)
            print(f"[beauty] {n}_hq.mp4")
    print("[build] done ->", ROOT)


main()
