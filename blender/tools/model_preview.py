"""Beauty preview of a knife model (Cycles, CPU) - the modeller's feedback loop.

usage (repo root):
  <python-with-bpy> blender/tools/model_preview.py <butterfly|karambit> --out <dir> [--samples 48] [--res 960x540] [--quick]

Writes <dir>/<knife>_turntable.png (6 views on a grid: side, 3/4, edge-on, back,
top-down, close-up of the hilt) and for the butterfly also <knife>_closed.png
(handles closed over the blade) and <knife>_half.png (half open).  Also prints
triangle counts per object (Roblox MeshPart limit: 20k, aim for < 6k).
The knife is shown in its own frame, metres, without the arm.
"""
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from vm import spec, skeleton, debugcam  # noqa: E402
from vm import rig as rigmod  # noqa: E402
from vm.scene import load_models  # noqa: E402


def setup_cycles(samples, res):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    sky = nt.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(35)
        sky.sun_rotation = math.radians(60)
    except Exception:
        pass
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.25
    sc.world = world
    # studio lights
    for name, loc, energy, size in (("Key", (0.45, -0.3, 0.35), 7, 0.3), ("Rim", (-0.4, 0.3, 0.25), 5, 0.25),
                                    ("Fill", (0.3, 0.35, -0.3), 2, 0.5)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        d = -Vector(loc).normalized()
        lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    # backdrop
    bpy.ops.mesh.primitive_plane_add(size=6, location=(-0.6, 0, 0))
    bpy.context.active_object.rotation_euler = (0, math.radians(90), 0)
    bd = bpy.context.active_object
    m = bpy.data.materials.new("Backdrop")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.08, 0.085, 0.09, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.7
    bd.data.materials.append(m)


def pose_butterfly(objs, a, b, latch=0.0):
    """Place butterfly parts (bone-local meshes) in the knife frame for state a, b."""
    A, blade, B = skeleton.bf_link_frames(Matrix.Identity(4), "A", a, b)
    s = 1.0 / spec.KNIFE_SCALE
    m = {"BF_HandleA": A @ skeleton.T(skeleton.PIN_A), "BF_Blade": blade @ skeleton.T(skeleton.PIN_A),
         "BF_HandleB": B @ skeleton.T(skeleton.PIN_B),
         "BF_Latch": B @ skeleton.T(skeleton.LATCH_PIVOT) @ skeleton.R4("X", -spec.BF_LATCH_OPEN_DEG * latch)}
    for o in objs:
        bone = spec.mesh_bone(o.name)
        w = m[bone].copy()
        w.translation *= s          # frames are in studs, the preview is in metres
        o.matrix_world = w


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    knife = args[0]
    out = args[args.index("--out") + 1]
    samples = int(args[args.index("--samples") + 1]) if "--samples" in args else 48
    res = tuple(int(x) for x in args[args.index("--res") + 1].split("x")) if "--res" in args else (960, 540)
    if "--quick" in args:
        samples, res = 16, (640, 360)
    os.makedirs(out, exist_ok=True)
    rigmod.clear_scene()
    objs, final = load_models(knife, True)
    tris = 0
    for o in objs:
        o.data.calc_loop_triangles()
        n = len(o.data.loop_triangles)
        tris += n
        print(f"[tris] {o.name}: {n}  materials={[m.name for m in o.data.materials if m]}  uv={[u.name for u in o.data.uv_layers]}")
    print(f"[tris] total {tris}")
    setup_cycles(samples, res)
    sc = bpy.context.scene
    if knife == "butterfly":
        pose_butterfly(objs, 0, 0)
        center = Vector((0, -0.01, 0))
        length = 0.24
    else:
        for o in objs:
            o.matrix_world = Matrix.Identity(4)
        center = Vector((0, 0.07, -0.02))
        length = 0.2
    dist = length * 1.9
    # camera looks ALONG these directions; the knife flat faces +-X, spine +Z
    views = {"side": (-1, 0, 0), "three_q": (-0.8, 0.3, -0.45), "spine": (-0.2, 0, -1), "other_side": (1, 0.05, 0.05),
             "edge": (-0.25, 0.05, 1), "hilt": (-0.85, -0.25, -0.3)}
    paths = []
    for n, d in views.items():
        cam = debugcam.look_at_cam("C_" + n, center + (Vector((0, -0.05, 0)) if n == "hilt" else Vector()), d,
                                   dist * (0.45 if n == "hilt" else 1.0), lens=50)
        sc.camera = cam
        sc.render.filepath = os.path.join(out, f"{knife}_{n}.png")
        bpy.ops.render.render(write_still=True)
        paths.append(sc.render.filepath)
    inputs = sum([["-i", p] for p in paths], [])
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                    "xstack=inputs=6:layout=0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0",
                    os.path.join(out, f"{knife}_turntable.png")], check=True)
    if knife == "butterfly":
        for tag, (a, b, l) in {"closed": (1, 1, 0), "half": (0.45, 0.7, 0.6)}.items():
            pose_butterfly(objs, a, b, l)
            cam = debugcam.look_at_cam("C_" + tag, Vector((0, 0.05 if tag == "closed" else 0.0, 0)), (-0.85, 0.2, -0.4), dist * 0.85, lens=50)
            sc.camera = cam
            sc.render.filepath = os.path.join(out, f"{knife}_{tag}.png")
            bpy.ops.render.render(write_still=True)
    print("wrote", os.path.join(out, f"{knife}_turntable.png"))


main()
