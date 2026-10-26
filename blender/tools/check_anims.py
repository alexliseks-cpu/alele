"""Consistency checks over every animation in the catalog.

usage (repo root): <python-with-bpy> blender/tools/check_anims.py [names...]

Checks per clip:
  * non-idle clips end on the knife's base idle pose (world pose of hand,
    knife parts and camera); non-draw clips also start on it
  * idle loops: first frame == last frame
  * attack / heavy clips carry a "Hit" marker
  * butterfly handle states stay inside [0, 1]
  * wrist-limit warnings, length
Exit code 1 if a hard check fails.
"""
import importlib
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402,F401

from vm import spec, skeleton  # noqa: E402
from vm.anim import catalog  # noqa: E402

POS_TOL = 0.01    # studs
ROT_TOL = 1.0     # degrees
CHECK_BONES = ("RightHand", "LeftHand", "CameraBone")


def idle_world(knife):
    common = importlib.import_module(f"vm.anim.{knife}.common")
    from vm.anim.core import Anim
    a = Anim("probe", knife, 0.1)
    common.key_idle(a, 0.0)
    return skeleton.evaluate(a.controls(0.0), a.knife_rot_order, knife)


def diff(Wa, Wb, bones):
    worst_p, worst_r, where = 0.0, 0.0, ""
    for b in bones:
        dp = (Wa[b].translation - Wb[b].translation).length
        dr = math.degrees(Wa[b].to_quaternion().rotation_difference(Wb[b].to_quaternion()).angle)
        dr = min(dr, 360 - dr)
        if dp > worst_p or dr > worst_r:
            where = b if (dp > POS_TOL or dr > ROT_TOL) else where
        worst_p, worst_r = max(worst_p, dp), max(worst_r, dr)
    return worst_p, worst_r, where


def main():
    names = sys.argv[1:] or catalog.available()
    fails = 0
    idle_cache = {}
    print(f"{'clip':12} {'len':>5} {'start dp/dr':>16} {'end dp/dr':>16} {'markers':30} notes")
    for n in names:
        a = catalog.build(n)
        knife = a.kind
        bones = list(CHECK_BONES) + spec.KNIFE_BONES[knife]
        if knife not in idle_cache:
            idle_cache[knife] = idle_world(knife)
        I = idle_cache[knife]
        frames = a.sample()
        notes = []
        s = diff(frames[0], I, bones)
        e = diff(frames[-1], I, bones)
        is_idle = n.endswith("_idle")
        is_draw = n.endswith("_draw")
        if is_idle:
            loop = diff(frames[0], frames[-1], bones)
            if loop[0] > POS_TOL or loop[1] > ROT_TOL:
                notes.append(f"LOOP SEAM {loop[0]:.3f}/{loop[1]:.1f} at {loop[2]}")
                fails += 1
        else:
            if e[0] > POS_TOL or e[1] > ROT_TOL:
                notes.append(f"END OFF IDLE at {e[2]}")
                fails += 1
            if not is_draw and (s[0] > POS_TOL or s[1] > ROT_TOL):
                notes.append(f"START OFF IDLE at {s[2]}")
                fails += 1
        mk = sorted({f"{m[1]}:{m[2]}" for m in a.markers})
        if any(n.endswith(x) for x in ("_attack1", "_attack2", "_heavy")) and not any(m[1] == "Hit" for m in a.markers):
            notes.append("NO Hit MARKER")
            fails += 1
        if knife == "butterfly" and "bf" in a.ch:
            lo, hi = 1e9, -1e9
            for f in range(a.nframes()):
                v = a.ch["bf"].eval(f / a.fps)
                lo, hi = min(lo, v[0], v[1]), max(hi, v[0], v[1])
            if lo < -0.02 or hi > 1.02:
                notes.append(f"BF RANGE {lo:.2f}..{hi:.2f}")
                fails += 1
        if a.warnings:
            notes.append(f"{len(a.warnings)} wrist warnings")
        print(f"{n:12} {a.length:5.2f} {s[0]:7.3f}/{s[1]:5.1f}deg {e[0]:7.3f}/{e[1]:5.1f}deg {','.join(mk)[:30]:30} {'; '.join(notes)}")
    print("FAILED checks:", fails)
    sys.exit(1 if fails else 0)


main()
