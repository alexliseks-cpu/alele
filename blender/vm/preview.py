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


def setup_beauty(res=(960, 540), samples=24):
    """EEVEE look-dev for showcase videos: sun + sky, soft shadows, AgX."""
    import math
    sc = bpy.context.scene
    setup_eevee(res, samples)
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.get("BeautyWorld") or bpy.data.worlds.new("BeautyWorld")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    sky = nt.nodes.get("Sky") or nt.nodes.new("ShaderNodeTexSky")
    sky.name = "Sky"
    try:
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(38)
        sky.sun_rotation = math.radians(150)
        sky.sun_disc = False
    except Exception:
        pass
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.6
    sc.world = world
    sun = bpy.data.objects.get("BeautySun")
    if sun is None:
        ld = bpy.data.lights.new("BeautySun", "SUN")
        ld.energy = 2.0
        ld.angle = math.radians(3)
        sun = bpy.data.objects.new("BeautySun", ld)
        sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    fill = bpy.data.objects.get("BeautyFill")
    if fill is None:
        ld = bpy.data.lights.new("BeautyFill", "AREA")
        ld.energy = 120
        ld.size = 4
        fill = bpy.data.objects.new("BeautyFill", ld)
        sc.collection.objects.link(fill)
    fill.location = (-2.5, -1.0, 1.5)
    fill.rotation_euler = (math.radians(70), 0, math.radians(-110))
    # nicer environment materials
    for name, col, rough in (("ENV_A", (0.30, 0.27, 0.23), 0.8), ("ENV_B", (0.24, 0.22, 0.19), 0.8),
                             ("ENV_Wall", (0.42, 0.37, 0.30), 0.9)):
        m = bpy.data.materials.get(name)
        if m and m.node_tree:
            b = m.node_tree.nodes.get("Principled BSDF")
            if b:
                b.inputs["Base Color"].default_value = (*col, 1)
                b.inputs["Roughness"].default_value = rough
