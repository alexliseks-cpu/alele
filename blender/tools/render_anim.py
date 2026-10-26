"""Render preview(s) of animation(s) - the animator's main feedback loop.

usage (repo root):
  xvfb-run -a -s "-screen 0 1280x720x24" <python-with-bpy> blender/tools/render_anim.py \
      <anim_name> [<anim_name> ...] --out <dir> [--every 2] [--placeholders] [--sheet] [--views]

Writes <dir>/<anim>.mp4 (30 fps game-camera preview), <dir>/<anim>_frames/*.png,
with --sheet a contact sheet <dir>/<anim>_sheet.png (every 0.1 s, time-stamped),
with --views also a 3rd-person orbit view video <dir>/<anim>_orbit.mp4,
and prints IK / wrist warnings.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402

from vm import scene, rig as rigmod, preview, debugcam  # noqa: E402
from vm.anim import catalog  # noqa: E402


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    out = args[args.index("--out") + 1]
    every = int(args[args.index("--every") + 1]) if "--every" in args else 1
    names = [a for a in args if not a.startswith("--") and a not in (out, str(every))]
    os.makedirs(out, exist_ok=True)
    r, cam, groups = scene.build_scene(use_final="--placeholders" not in args)
    preview.setup_workbench(res=(640, 360))
    sc = bpy.context.scene
    for name in names:
        a = catalog.build(name)
        frames, baked = a.bake()
        print(f"[{name}] {a.length:.2f}s, {len(frames)} frames @{a.fps}")
        for w in a.warnings[:40]:
            print(f"[{name}] WARN {w}")
        act, _ = rigmod.write_action(r, a, baked)
        scene.show_knife(groups, a.kind)
        base = os.path.join(out, name)
        preview.render_action(r, act, base, fps=30, every=every)
        if "--sheet" in args:
            fr_dir = base + "_frames"
            step = max(1, round(3 / every))   # every 0.1 s
            files = sorted(os.listdir(fr_dir))[::step]
            lst = os.path.join(out, name + "_sheetlist.txt")
            with open(lst, "w") as f:
                for fn in files:
                    f.write(f"file '{os.path.join(fr_dir, fn)}'\n")
            cols = 6
            rows = (len(files) + cols - 1) // cols
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                            "-vf", f"scale=320:-1,drawtext=text='%{{n}}':x=4:y=4:fontsize=18:fontcolor=yellow,tile={cols}x{rows}",
                            "-frames:v", "1", base + "_sheet.png"], check=False)
            print(f"[{name}] sheet: {base}_sheet.png  (tile n -> t = n*{step * every / 30:.3f} s)")
        if "--views" in args:
            cam_o = debugcam.look_at_cam("DBG_orbit", (0.6, 1.6, -0.9), (-0.8, 0.45, -0.25), 4.5, lens=28)
            sc.camera = cam_o
            preview.render_action(r, act, base + "_orbit", fps=30, every=max(every, 2))
            sc.camera = cam
        print(f"[{name}] video: {base}.mp4")


main()
