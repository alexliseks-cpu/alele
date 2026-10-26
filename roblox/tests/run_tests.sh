#!/usr/bin/env bash
# Offline checks of the Roblox scripts:
#   1. every .lua/.luau compiles with Luau (syntax)
#   2. end-to-end rig test: Blender pose -> RigData/Transforms -> Roblox joint tree
# needs: a Luau runner (see README "Tests") as $LUAURUN, and Blender's python as $BPY_PYTHON
set -euo pipefail
cd "$(dirname "$0")/../.."
LUAURUN=${LUAURUN:-luaurun}
BPY_PYTHON=${BPY_PYTHON:-python3}
OUT=$(mktemp -d)
"$LUAURUN" --check roblox/src/KnifeSystem/*.lua roblox/src/*.lua roblox/SetupKnifeViewmodels.lua
"$BPY_PYTHON" blender/tools/export_test_vectors.py "$OUT"
printf 'TEST_DIR = "%s"\n' "$OUT" > "$OUT/env.luau"
"$LUAURUN" "$OUT/env.luau" roblox/tests/test_rig.luau
