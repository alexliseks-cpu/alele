"""Preview renders (Workbench needs an X server: run the build under xvfb-run)."""

import os
import shutil
import subprocess

import bpy

from . import rig as rigmod


def setup_workbench(res=(640, 360)):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_specular_highlight = True
    sc.display.render_aa = "8"
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "Standard"


def setup_eevee(res=(1280, 720), samples=32):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.eevee.taa_render_samples = samples
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"


def render_action(rig, act, out_path, fps=30, every=1, frames=None, label=None):
    """Render an action to <out_path>.mp4 (and keep PNG frames in a dir)."""
    rigmod.assign_action(rig, act)
    sc = bpy.context.scene
    tmp = out_path + "_frames"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    end = sc.frame_end
    flist = frames if frames is not None else list(range(0, end + 1, every))
    for i, f in enumerate(flist):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(tmp, f"f_{i:04d}.png")
        bpy.ops.render.render(write_still=True)
    if frames is None:
        cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", str(fps / every), "-i", os.path.join(tmp, "f_%04d.png"),
               "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", out_path + ".mp4"]
        subprocess.run(cmd, check=True)
    return tmp
