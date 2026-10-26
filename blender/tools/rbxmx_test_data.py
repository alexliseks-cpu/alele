"""Turn the exported KeyframeSequences (.rbxmx) into Luau test data.

usage: <python-with-bpy> blender/tools/rbxmx_test_data.py <KnifeAnimations.rbxmx> <out_dir> [clip names...]

Writes <out_dir>/kfs_data.luau: every KeyframeSequence parsed from the XML
(name, loop, keyframes with the Pose tree and markers) plus, for each clip,
the reference Motor6D transforms re-computed from the Blender source at
several times - roblox/tests/test_kfs.luau plays the parsed clips with
KnifeAnimator and compares.
"""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402,F401

from vm import spec  # noqa: E402
from vm.anim import catalog  # noqa: E402
from vm.export import roblox  # noqa: E402


def props(item):
    out = {}
    p = item.find("Properties")
    for el in p:
        name = el.get("name")
        if el.tag == "CoordinateFrame":
            out[name] = [float(el.find(t).text) for t in ("X", "Y", "Z", "R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22")]
        elif el.tag in ("float", "token"):
            out[name] = float(el.text)
        elif el.tag == "bool":
            out[name] = el.text == "true"
        else:
            out[name] = el.text or ""
    return out


def lua(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(float(v))
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "{" + ", ".join(lua(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join(f"[{lua(k)}] = {lua(x)}" for k, x in v.items()) + "}"
    raise TypeError(v)


def pose_tree(item):
    p = props(item)
    return {"Name": p["Name"], "CFrame": p["CFrame"], "Weight": p.get("Weight", 1.0),
            "Children": [pose_tree(c) for c in item.findall("Item") if c.get("class") == "Pose"]}


def main():
    src, out = sys.argv[1], sys.argv[2]
    want = set(sys.argv[3:])
    root = ET.parse(src).getroot()
    clips = []
    for kfs in root.iter("Item"):
        if kfs.get("class") != "KeyframeSequence":
            continue
        p = props(kfs)
        if want and p["Name"] not in want:
            continue
        kfs_data = {"Name": p["Name"], "Loop": p["Loop"], "Keyframes": []}
        for kf in kfs.findall("Item"):
            if kf.get("class") != "Keyframe":
                continue
            kp = props(kf)
            kfs_data["Keyframes"].append({
                "Time": kp["Time"],
                "Poses": [pose_tree(c) for c in kf.findall("Item") if c.get("class") == "Pose"],
                "Markers": [{"Name": props(m)["Name"], "Value": props(m)["Value"]}
                            for m in kf.findall("Item") if m.get("class") == "KeyframeMarker"],
            })
        clips.append(kfs_data)
    # reference transforms from the Blender source
    by_rbx = {catalog.ANIMS[n][1]: n for n in catalog.available()}
    refs = {}
    for c in clips:
        n = by_rbx.get(c["Name"])
        if not n:
            continue
        a = catalog.build(n)
        frames, baked = a.bake()
        samples = []
        nf = len(baked)
        for fi in sorted({0, nf // 7, nf // 3, nf // 2, (2 * nf) // 3, (6 * nf) // 7, nf - 1}):
            samples.append({"t": fi / a.fps, "T": {b: list(roblox.local_cf(*baked[fi][b]))
                                                     for b in spec.bones_for(a.kind) if b != spec.ROOT}})
        refs[c["Name"]] = {"samples": samples, "markers": [[m[0], m[1], m[2]] for m in a.markers]}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "kfs_data.luau"), "w") as f:
        f.write("return " + lua({"clips": clips, "refs": refs}) + "\n")
    print(f"wrote {len(clips)} clips, {len(refs)} with references")


main()
