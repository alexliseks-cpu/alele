"""Render close-up views of a hand pose / grip to check contact.

usage (from repo root):
  xvfb-run -a python blender/tools/grip_check.py <butterfly|karambit> <out_prefix> [--placeholders] [--anim NAME --t SECONDS]
Writes <out_prefix>_grid.png (front/side/top/below/back + game camera).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402

from vm import scene, rig as rigmod, preview, skeleton, debugcam  # noqa: E402
from vm.anim.core import Anim  # noqa: E402
from vm.anim import poses  # noqa: E402


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    knife, out = args[0], args[1]
    use_final = "--placeholders" not in args
    r, cam, groups = scene.build_scene(use_final=use_final)
    scene.show_knife(groups, knife)
    if "--anim" in args:
        from vm.anim import catalog
        name = args[args.index("--anim") + 1]
        t = float(args[args.index("--t") + 1]) if "--t" in args else 0.0
        a = catalog.build(name)
        c = a.controls(t)
        a2 = Anim("check", knife, 0.1)
        for k, v in c.items():
            if k == "knife.anchor":
                a2.knife(0, anchor=v)
            else:
                a2.set(k, 0, v)
        a = a2
    else:
        kg = poses.GRIPS[knife]
        a = Anim("check", knife, 0.1)
        a.hand("R", 0, pos=poses.R_IDLE_POS, rot=poses.R_IDLE_ROT)
        a.hand("L", 0, pos=poses.L_HIDDEN_POS, rot=poses.L_HIDDEN_ROT)
        a.knife(0, pos=kg["pos"], rot=kg["rot"], anchor=kg["anchor"])
    frames, baked = a.bake()
    act, _ = rigmod.write_action(r, a, baked)
    rigmod.assign_action(r, act)
    bpy.context.scene.frame_set(0)
    preview.setup_workbench()
    W = frames[0]
    tgt = W["RightHand"] @ skeleton.Vector((0, -0.125, 0))
    paths = debugcam.render_views(tgt, out, dist=4.0, lens=40, res=(400, 300),
                                  views={"front": (0, 1, 0), "side_out": (-1, 0, 0), "side_in": (1, 0.2, 0),
                                         "top": (0, 0.25, -1), "below": (0, 0.3, 1), "back": (0, -1, 0.1)})
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 400, 300
    sc.render.filepath = out + "_game.png"
    bpy.ops.render.render(write_still=True)
    paths.append(sc.render.filepath)
    inputs = sum([["-i", p] for p in paths], [])
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                    "[0][1][2][3][4][5][6]xstack=inputs=7:layout=0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0|0_h0+h1[v];[v]pad=1200:900[o]",
                    "-map", "[o]", out + "_grid.png"], check=True)
    print("wrote", out + "_grid.png")


main()
