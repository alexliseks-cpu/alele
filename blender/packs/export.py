"""
Export the Limited Packs (see CONTRACT.md) for Roblox.

usage (repo root):  python blender/packs/export.py [--no-bake] [--out DIR]
  builds packs.lava + packs.ice into a fresh scene, then writes
  export/packs/meshes/<Item>.fbx       (MeshParts, item space, studs, Y-up)
  export/packs/textures/<Item>_<Group>_<Map>.png
  roblox/src/PackSystem/PackData.lua (parts, materials, VFX attachments, mounts)
  export/packs/PackSystem.rbxmx      (ReplicatedStorage.PackSystem package)
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from vm.export import roblox as rx  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ARGS = sys.argv[1:]
OUT = os.path.abspath(ARGS[ARGS.index("--out") + 1]) if "--out" in ARGS else REPO
EXP = os.path.join(OUT, "export", "packs")
SRC = os.path.join(REPO, "roblox", "src", "PackSystem")
KNIFE_BASE = {"Lava_Karambit": "Karambit", "Ice_Butterfly": "Butterfly"}
KNIFE_BONES = ("KR_Handle", "BF_HandleA", "BF_Blade", "BF_HandleB", "BF_Latch")


def conv(v):
    """Blender item space -> Roblox (x, y, z) = (x, z, -y)."""
    return (v[0], v[2], -v[1])


def cf_of(m):
    """Blender 4x4 (item space) -> Roblox CFrame components with Roblox-axis
    local frame (object +Y forward maps to Roblox -Z, +Z up to +Y)."""
    K = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))
    r = K @ m.to_3x3().normalized() @ K.transposed()
    t = K @ m.translation
    return (t.x, t.y, t.z, r[0][0], r[0][1], r[0][2], r[1][0], r[1][1], r[1][2], r[2][0], r[2][1], r[2][2])


def lua(v):
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return rx.fmt(float(v))
    if isinstance(v, str):
        return '"' + v + '"'
    raise TypeError(v)


def export_name(item, name):
    return name if name.startswith(item) else f"{item}__{name}"


def skin_bone(name):
    for b in KNIFE_BONES:
        if name.startswith(b + "_"):
            return b
    return None


def collect():
    items = {}
    for col in bpy.data.collections:
        if col.name.startswith("ITEM_"):
            items[col.name[5:]] = col
    return items


def export_item(item, col, tex_dir, mesh_dir, bake=True):
    meshes = [o for o in col.all_objects if o.type == "MESH"]
    empties = [o for o in col.all_objects if o.type == "EMPTY"]
    textures = {}
    baked = [o for o in meshes if o.get("bake")]
    if bake and baked:
        from vm import bake as bk
        for o in baked:
            o["tex_group"] = o.get("tex_group", "main")
        res = bk.bake_knife(baked, item, tex_dir, size=1024, samples=16, prefix=item)
        for g, paths in res.items():
            textures[f"{item}_{g.capitalize()}"] = paths
    dg = bpy.context.evaluated_depsgraph_get()
    tmp = bpy.data.collections.new("EXPORT_" + item)
    bpy.context.scene.collection.children.link(tmp)
    parts, copies, renamed = [], [], {}
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        me.transform(o.matrix_world)
        name = export_name(item, o.name)
        renamed[o] = o.name
        o.name = o.name + "__src"
        c = bpy.data.objects.new(name, me)
        tmp.objects.link(c)
        copies.append(c)
        vs = [v.co for v in me.vertices]
        if not vs:
            continue
        mn = [min(v[i] for v in vs) for i in range(3)]
        mx = [max(v[i] for v in vs) for i in range(3)]
        cen = [(a + b) / 2 for a, b in zip(mn, mx)]
        size = [max(b - a, 0.01) for a, b in zip(mn, mx)]
        col_ = tuple(o.get("rbx_color", (0.8, 0.8, 0.8)))
        parts.append(dict(name=name, src=renamed[o], center=conv(cen), size=(size[0], size[2], size[1]),
                          material=o.get("rbx_material", "SmoothPlastic"), color=col_[:3],
                          transparency=float(o.get("rbx_transparency", 0.0)), pulse=float(o.get("pulse", 0.0)),
                          textures=(f"{item}_{o.get('tex_group', 'main').capitalize()}" if o.get("bake") and bake else None),
                          bone=skin_bone(renamed[o]) if item in KNIFE_BASE else None,
                          base=(item in KNIFE_BASE and "_Skin_" not in renamed[o])))
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for c in copies:
        c.select_set(True)
    if copies:
        bpy.context.view_layer.objects.active = copies[0]
        bpy.ops.export_scene.fbx(filepath=os.path.join(mesh_dir, item + ".fbx"), use_selection=True,
                                 object_types={"MESH"}, axis_forward="-Z", axis_up="Y", global_scale=1.0,
                                 apply_unit_scale=False, apply_scale_options="FBX_SCALE_NONE",
                                 use_mesh_modifiers=True, mesh_smooth_type="FACE", use_tspace=True,
                                 path_mode="COPY", embed_textures=True)
    for c in copies:
        bpy.data.objects.remove(c)
    bpy.data.collections.remove(tmp)
    for o, n in renamed.items():
        o.name = n
    atts, mounts = [], []
    for e in empties:
        mw = e.matrix_world
        if e.name.startswith("VFX_"):
            preset = e.name[4:].split("_")[0].split(".")[0]
            colr = e.get("color")
            atts.append(dict(name=e.name, preset=preset, pos=conv(mw.translation), rate=float(e.get("rate", 1.0)),
                             size=float(e.get("size", 1.0)), color=tuple(colr)[:3] if colr else None,
                             bone=e.get("bone") or None))
        elif e.name.startswith("MOUNT_"):
            mounts.append(dict(name=e.name, item=e.name[6:].split(".")[0], cf=cf_of(mw)))
    kind = "knife_skin" if item in KNIFE_BASE else ("stand" if item.endswith("_Stand") else "weapon")
    return dict(kind=kind, parts=parts, atts=atts, mounts=mounts, textures=textures, knife=KNIFE_BASE.get(item))


def pack_data_lua(data):
    L = ["-- AUTO-GENERATED by blender/packs/export.py - do not edit by hand.", "return {", "\tItems = {"]
    for item, d in data.items():
        L.append(f"\t\t{item} = {{ Kind = {lua(d['kind'])}, Knife = {lua(d['knife'])},")
        L.append("\t\t\tParts = {")
        for p in d["parts"]:
            c = p["color"]
            L.append(f"\t\t\t\t{{ Name = {lua(p['name'])}, Src = {lua(p['src'])}, Center = {rx.lua_v3(p['center'])}, "
                     f"Size = {rx.lua_v3(p['size'])}, Material = {lua(p['material'])}, "
                     f"Color = Color3.new({rx.fmt(c[0])}, {rx.fmt(c[1])}, {rx.fmt(c[2])}), "
                     f"Transparency = {lua(p['transparency'])}, Pulse = {lua(p['pulse'])}, "
                     f"Textures = {lua(p['textures'])}, Bone = {lua(p['bone'])}, Base = {lua(p['base'])} }},")
        L.append("\t\t\t},")
        L.append("\t\t\tAttachments = {")
        for a in d["atts"]:
            colr = f"Color3.new({rx.fmt(a['color'][0])}, {rx.fmt(a['color'][1])}, {rx.fmt(a['color'][2])})" if a["color"] else "nil"
            L.append(f"\t\t\t\t{{ Name = {lua(a['name'])}, Preset = {lua(a['preset'])}, Position = {rx.lua_v3(a['pos'])}, "
                     f"Rate = {lua(a['rate'])}, Size = {lua(a['size'])}, Color = {colr}, Bone = {lua(a['bone'])} }},")
        L.append("\t\t\t},")
        L.append("\t\t\tMounts = {")
        for m in d["mounts"]:
            L.append(f"\t\t\t\t{{ Name = {lua(m['name'])}, Item = {lua(m['item'])}, CFrame = {rx.lua_cf(m['cf'])} }},")
        L.append("\t\t\t},")
        L.append("\t\t},")
    L.append("\t},")
    L.append("\t-- rbxassetid:// of the uploaded PNGs (only needed if the FBX import did not create SurfaceAppearances)")
    L.append("\tTextures = {")
    for d in data.values():
        for t in sorted(d["textures"]):
            L.append(f'\t\t{t} = {{ ColorMap = "", NormalMap = "", RoughnessMap = "", MetalnessMap = "" }},')
    L.append("\t},")
    L.append("}")
    return "\n".join(L) + "\n"


def main():
    bake = "--no-bake" not in ARGS
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for mod in ("packs.lava", "packs.ice"):
        try:
            importlib.import_module(mod).build()
        except ModuleNotFoundError as e:
            print("[packs] missing", mod, e)
    tex_dir = os.path.join(EXP, "textures")
    mesh_dir = os.path.join(EXP, "meshes")
    os.makedirs(tex_dir, exist_ok=True)
    os.makedirs(mesh_dir, exist_ok=True)
    os.makedirs(SRC, exist_ok=True)
    data = {}
    for item, col in sorted(collect().items()):
        data[item] = export_item(item, col, tex_dir, mesh_dir, bake)
        d = data[item]
        print(f"[packs] {item}: {d['kind']}, {len(d['parts'])} parts, {len(d['atts'])} vfx, {len(d['mounts'])} mounts")
    with open(os.path.join(SRC, "PackData.lua"), "w") as f:
        f.write(pack_data_lua(data))
    pkg = rx.Rbx()
    pkg.open("Folder", [("string", "Name", "PackSystem")])
    for mod in ("PackData", "SkinVFX", "PackBuilder"):
        with open(os.path.join(SRC, mod + ".lua")) as f:
            pkg.open("ModuleScript", [("string", "Name", mod), ("source", "Source", f.read())])
            pkg.close()
    with open(os.path.join(SRC, "PackStandsRuntime.server.lua")) as f:
        pkg.open("Script", [("string", "Name", "PackStandsRuntime"), ("bool", "Disabled", False), ("source", "Source", f.read())])
        pkg.close()
    pkg.open("Folder", [("string", "Name", "Models")])
    pkg.close()
    pkg.close()
    with open(os.path.join(EXP, "PackSystem.rbxmx"), "w") as f:
        f.write(pkg.text())
    import shutil
    shutil.copy(os.path.join(REPO, "roblox", "SetupPacks.lua"), os.path.join(EXP, "SetupPacks.lua"))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXP, "LimitedPacks.blend"), compress=True)
    print("[packs] done ->", EXP)


if __name__ == "__main__":
    main()
