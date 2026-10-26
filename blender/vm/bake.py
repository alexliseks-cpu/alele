"""
Bake the procedural knife materials into PBR texture atlases for Roblox
SurfaceAppearance (ColorMap, NormalMap, RoughnessMap, MetalnessMap).

Per knife, objects are grouped by obj["tex_group"] ("blade" / "handle");
every group gets one atlas (all its objects' UV islands packed together into
a UV layer "AtlasUV").  Procedural textures must use Object/Generated
coordinates, so re-packing UVs does not change the look.

After baking, every object gets an "export" material that only uses the baked
images through AtlasUV (that is what the FBX carries and what EEVEE previews
show); the original procedural material is kept on obj["proc_material"].
"""

import os

import bpy

MAPS = ("Color", "Normal", "Roughness", "Metalness")


def _select_only(objs, active):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def _ensure_atlas_uv(objs, margin=0.004):
    for o in objs:
        me = o.data
        if not me.uv_layers:
            me.uv_layers.new(name="UVMap")
            _select_only([o], o)
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
            bpy.ops.object.mode_set(mode="OBJECT")
        src = me.uv_layers.get("UVMap") or me.uv_layers[0]
        at = me.uv_layers.get("AtlasUV")
        if at is None:
            at = me.uv_layers.new(name="AtlasUV")
        for d, s in zip(at.data, src.data):
            d.uv = s.uv
        me.uv_layers.active = at
    _select_only(objs, objs[0])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    try:
        bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=True, margin_method="SCALED", margin=margin)
    except TypeError:
        bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def _new_image(name, size, non_color):
    img = bpy.data.images.get(name)
    if img:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    return img


def _materials(o):
    return [s.material for s in o.material_slots if s.material]


def _bsdf(mat):
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def _output(mat):
    for n in mat.node_tree.nodes:
        if n.type == "OUTPUT_MATERIAL" and n.is_active_output:
            return n
    for n in mat.node_tree.nodes:
        if n.type == "OUTPUT_MATERIAL":
            return n
    return None


def _set_target(objs, img):
    for o in objs:
        for m in _materials(o):
            nt = m.node_tree
            node = nt.nodes.get("__bake_target")
            if node is None:
                node = nt.nodes.new("ShaderNodeTexImage")
                node.name = "__bake_target"
            node.image = img
            for n in nt.nodes:
                n.select = False
            node.select = True
            nt.nodes.active = node


def _emit_input(objs, input_name, on):
    """Temporarily route a Principled input (Base Color / Metallic) into an
    Emission shader so EMIT bakes its raw value (DIFFUSE colour bakes black
    for metals)."""
    for o in objs:
        for m in _materials(o):
            nt = m.node_tree
            bsdf, out = _bsdf(m), _output(m)
            if bsdf is None or out is None:
                continue
            if on:
                link = out.inputs["Surface"].links[0] if out.inputs["Surface"].links else None
                m["__surface_from"] = link.from_node.name if link else ""
                m["__surface_socket"] = link.from_socket.name if link else ""
                em = nt.nodes.new("ShaderNodeEmission")
                em.name = "__bake_emit"
                sock = bsdf.inputs[input_name]
                if sock.links:
                    nt.links.new(sock.links[0].from_socket, em.inputs["Color"])
                else:
                    v = sock.default_value
                    em.inputs["Color"].default_value = (v, v, v, 1) if isinstance(v, float) else tuple(v)
                em.inputs["Strength"].default_value = 1.0
                nt.links.new(em.outputs[0], out.inputs["Surface"])
            else:
                em = nt.nodes.get("__bake_emit")
                if em:
                    nt.nodes.remove(em)
                src = nt.nodes.get(m.get("__surface_from", ""))
                if src:
                    nt.links.new(src.outputs[m["__surface_socket"]], out.inputs["Surface"])


def _bake(objs, kind, img, margin_px):
    _set_target(objs, img)
    sc = bpy.context.scene
    for i, o in enumerate(objs):
        _select_only([o], o)
        kw = dict(type=kind, margin=margin_px, use_clear=(i == 0), target="IMAGE_TEXTURES")
        if kind == "DIFFUSE":
            kw["pass_filter"] = {"COLOR"}
        if kind == "NORMAL":
            kw["normal_space"] = "TANGENT"
        bpy.ops.object.bake(**kw)


def export_material(name, imgs):
    """Principled material driven only by the baked maps (AtlasUV)."""
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "AtlasUV"
    x = -700
    nodes = {}
    for i, k in enumerate(MAPS):
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = imgs[k]
        tn.location = (x, 300 - 280 * i)
        tn.name = "Map_" + k
        nt.links.new(uv.outputs["UV"], tn.inputs["Vector"])
        nodes[k] = tn
    nt.links.new(nodes["Color"].outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(nodes["Roughness"].outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(nodes["Metalness"].outputs["Color"], bsdf.inputs["Metallic"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.uv_map = "AtlasUV"
    nt.links.new(nodes["Normal"].outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    # viewport / Workbench colour = average of the baked maps
    try:
        import numpy as np
        for k, attr in (("Color", "diffuse_color"), ("Roughness", "roughness"), ("Metalness", "metallic")):
            px = np.empty(len(imgs[k].pixels), dtype=np.float32)
            imgs[k].pixels.foreach_get(px)
            px = px.reshape(-1, 4)[:, :3]
            px = px[px.sum(axis=1) > 0.003] if attr == "diffuse_color" else px   # ignore empty atlas space
            mean = px.mean(axis=0) if len(px) else np.array([0.5, 0.5, 0.5])
            if attr == "diffuse_color":
                m.diffuse_color = (float(mean[0]), float(mean[1]), float(mean[2]), 1.0)
            else:
                setattr(m, attr, float(mean.mean()))
    except Exception as e:
        print("[bake] viewport colour skipped:", e)
    return m


def bake_knife(objs, knife, out_dir, size=1024, samples=24, margin_px=8):
    """Bake every tex_group of a knife.  Returns {group: {map: path}}."""
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    prev_engine = sc.render.engine
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.render.bake.margin = margin_px
    groups = {}
    for o in objs:
        g = o.get("tex_group") or ("blade" if "Blade" in o.name else "handle")   # same rule as build.tex_group
        groups.setdefault(g, []).append(o)
    result = {}
    for g, gobjs in groups.items():
        _ensure_atlas_uv(gobjs)
        base = f"{knife.capitalize()}_{g.capitalize()}"
        imgs = {k: _new_image(f"{base}_{k}", size, k != "Color") for k in MAPS}
        _bake(gobjs, "ROUGHNESS", imgs["Roughness"], margin_px)
        _bake(gobjs, "NORMAL", imgs["Normal"], margin_px)
        for inp, key in (("Base Color", "Color"), ("Metallic", "Metalness")):
            _emit_input(gobjs, inp, True)
            try:
                _bake(gobjs, "EMIT", imgs[key], margin_px)
            finally:
                _emit_input(gobjs, inp, False)
        paths = {}
        for k, img in imgs.items():
            p = os.path.join(out_dir, f"{base}_{k}.png")
            img.filepath_raw = p
            img.file_format = "PNG"
            img.save()
            paths[k] = p
        mat = export_material(f"{base}_PBR", imgs)
        for o in gobjs:
            procs = _materials(o)
            if procs:
                o["proc_material"] = procs[0].name
            o.data.materials.clear()
            o.data.materials.append(mat)
            o["surface_appearance"] = base
        result[g] = paths
        print(f"[bake] {base}: {len(gobjs)} objects -> {size}px")
    sc.render.engine = prev_engine
    return result
