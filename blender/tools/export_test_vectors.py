"""Export reference vectors for the offline Roblox rig test (roblox/tests).

For a synthetic butterfly and karambit animation, writes per sampled frame:
  * transforms[bone]: the Motor6D.Transform the KeyframeSequence carries
  * world[bone]: the expected joint pivot CFrame relative to the viewmodel root
plus RigData.lua for the same build, so the test checks the whole chain
Blender basis -> Roblox C0/C1/Transform -> part CFrames.

usage: <python-with-bpy> blender/tools/export_test_vectors.py <out_dir>
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402,F401

from vm import spec, skeleton  # noqa: E402
from vm.anim.core import Anim  # noqa: E402
from vm.anim import poses  # noqa: E402
from vm.export import roblox  # noqa: E402


def synth(knife):
    a = Anim("test_" + knife, knife, 1.0)
    g = poses.GRIPS[knife]
    a.hand("R", 0.0, pos=(0.9, 3.0, -1.15), rot=(35, 20, 50))
    a.hand("R", 0.5, pos=(0.6, 2.6, -0.7), rot=(-20, 60, 120), elbow=(0.3, 0, 0.2), shoulder=(0.1, 0.2, 0.3))
    a.hand("R", 1.0, pos=(0.95, 3.2, -1.0), rot=(10, -30, -40))
    a.hand("L", 0.0, pos=poses.L_HIDDEN_POS, rot=poses.L_HIDDEN_ROT)
    a.hand("L", 0.6, pos=(-0.8, 2.6, -1.0), rot=(20, 30, 40))
    a.knife(0.0, pos=g["pos"], rot=g["rot"], anchor=g["anchor"])
    a.knife(0.5, pos=(0.3, 0.2, 0.1), rot=(200, 30, -20))
    if knife == "butterfly":
        a.bf(0.0, a=1, b=1, latch=1)
        a.bf(0.4, a=0.3, b=0.8, latch=0.5)
        a.bf(0.7, a=0, b=0, latch=0)
        a.switch_anchor(0.55, "B")
        a.knife(0.9, pos=(0.5, 0.0, 0.0), rot=(30, 10, 90))
    a.cam(0.3, rot=(2, -1, 0.5))
    a.cam(0.8, rot=(0, 0, 0))
    return a


def lua_list(c):
    return "{" + ", ".join(roblox.fmt(x) for x in c) + "}"


def main():
    out = sys.argv[-1]
    os.makedirs(out, exist_ok=True)
    lines = ["return {"]
    for knife in ("butterfly", "karambit"):
        a = synth(knife)
        frames, baked = a.bake()
        lines.append(f"\t{knife.capitalize()} = {{")
        for fi in (0, 13, 30, 33, 47, 60):
            W = frames[fi]
            B = baked[fi]
            lines.append(f"\t\t{{ t = {fi / a.fps}, transforms = {{")
            for b in spec.bones_for(knife):
                if b == spec.ROOT:
                    continue
                lines.append(f"\t\t\t{b} = {lua_list(roblox.local_cf(*B[b]))},")
            lines.append("\t\t}, world = {")
            for b in spec.bones_for(knife):
                loc, q, _ = (skeleton.REST[spec.ROOT].inverted() @ W[b]).decompose()
                lines.append(f"\t\t\t{b} = {lua_list(roblox.local_cf(loc, q))},")
            lines.append("\t\t} },")
        lines.append("\t},")
    lines.append("}")
    with open(os.path.join(out, "vectors.luau"), "w") as f:
        f.write("\n".join(lines) + "\n")
    # rig data with dummy mesh lists (sizes irrelevant for the joint test)
    meshes = {k: [] for k in ("butterfly", "karambit")}
    with open(os.path.join(out, "RigData.lua"), "w") as f:
        f.write(roblox.rig_data_lua(meshes, {}))
    print("wrote", out)


main()
