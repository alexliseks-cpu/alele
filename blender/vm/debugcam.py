"""Orbit 'inspection' cameras for checking hand/knife contact."""
import math
import bpy
from mathutils import Vector, Matrix


def look_at_cam(name, target, direction, dist, lens=50.0):
    cd = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 0.005
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, cd)
        bpy.context.scene.collection.objects.link(cam)
    target = Vector(target)
    d = Vector(direction).normalized()
    loc = target - d * dist
    cam.location = loc
    up = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((0, 1, 0))
    z = -d
    x = up.cross(z).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = loc
    cam.matrix_world = m
    return cam


def render_views(target, out_prefix, views=None, dist=0.35, lens=50, res=(480, 360)):
    """views: dict name -> direction vector (camera looks along it)."""
    sc = bpy.context.scene
    views = views or {"front": (0, 1, 0), "side": (-1, 0, 0), "top": (0, 0.2, -1), "back": (0, -1, 0), "below": (0, 0.3, 1)}
    old_cam = sc.camera
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    sc.render.resolution_x, sc.render.resolution_y = res
    paths = []
    for n, d in views.items():
        cam = look_at_cam("DBG_" + n, target, d, dist, lens)
        sc.camera = cam
        sc.render.filepath = f"{out_prefix}_{n}.png"
        bpy.ops.render.render(write_still=True)
        paths.append(sc.render.filepath)
    sc.camera = old_cam
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    return paths
