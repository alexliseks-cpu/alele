# Limited Packs - Blender -> Roblox contract

Two packs, each authored by one module:
* `blender/packs/lava.py`: Lava_AR (assault rifle), Lava_Deagle (pistol), Lava_Karambit (knife skin), Lava_Stand
* `blender/packs/ice.py`:  Ice_Sniper, Ice_Revolver, Ice_Butterfly (knife skin), Ice_Stand

Each module exposes `build()` which builds its items into the CURRENT scene and
returns nothing. Run headless with the pip `bpy` (Blender 5.2):
`python -c "import sys; sys.path.insert(0,'blender'); import bpy; from packs import lava; lava.build()"`.

## Scene units / axes
* 1 Blender unit = 1 stud. +Z up, +Y = forward (barrel / blade direction), +X = right.
* Weapon item origin = the GRIP point (where the right hand holds it).
  Target sizes: AR ~4.2 studs long, Sniper ~5.6, Deagle ~1.5, Revolver ~1.6.
* Knife skins reuse the existing knife models: `from vm.models import karambit, butterfly`
  (`build()` returns mesh objects in bone-local frames, METRES; scale by
  `vm.spec.KNIFE_SCALE` (11) to get studs). Knife skin items are laid out OPEN, in
  knife MODEL space = the frame used by `vm.export.roblox.knife_model_frame`:
  for the karambit simply the KR_Handle frame (ring centre at origin); for the
  butterfly the BF_HandleA frame shifted by -PIN_A (pin centre at origin), i.e.
  place the butterfly parts with `tools/model_preview.pose_butterfly(objs, 0, 0)`
  logic and multiply translations by 11. Keep each base part's object NAME
  unchanged (e.g. `KR_Handle_Mesh_Blade`) - give it the skin's material.
* Stands: origin at floor centre, footprint about 10 x 10 studs, top display
  height ~3-4 studs. Put `MOUNT_<ItemName>` empties where each weapon of the pack
  sits (empty orientation = weapon orientation: its local +Y = weapon forward).

## Collections
Every item goes in its own collection `ITEM_<ItemName>` (e.g. `ITEM_Lava_AR`) linked
to the scene collection. Everything of that item lives inside it.

## Mesh objects (inside ITEM_ collections)
* Unique names, prefixed with the item name, e.g. `Lava_AR_Receiver`, `Lava_AR_Glow1`.
  Exception: knife-skin base parts keep their base name (see above).
  Knife-skin EXTRA pieces (glow overlays, spikes...) are named `<Bone>_Skin_<Part>`
  e.g. `KR_Handle_Skin_Cracks`, `BF_Blade_Skin_Frost` (Bone = the knife bone the
  piece rides on: KR_Handle | BF_HandleA | BF_Blade | BF_HandleB | BF_Latch).
* <= 8000 triangles per object, <= 40000 per item. Apply/bake everything into
  mesh data (no live modifiers needed by the exporter, it evaluates them anyway).
* Custom properties (exporter + Roblox read them):
  * `rbx_material`: Roblox Material: "Neon" for glowing parts (cracks, runes,
    energy lines - Neon is what glows in Roblox), "Glass" / "ForceField" for
    translucent ice, otherwise "SmoothPlastic" or "Metal".
  * `rbx_color`: (r, g, b) 0..1 - the Roblox Color (important for Neon/Glass parts).
  * `rbx_transparency`: 0..1 (optional, e.g. 0.3 for ice glass).
  * `bake`: True for opaque detailed parts -> their Blender material is baked to a
    PBR SurfaceAppearance (Color/Normal/Roughness/Metalness, 1024 px). Neon/Glass
    parts should NOT be baked (they glow / refract in Roblox by material).
    Baked materials: one Principled BSDF, procedural textures in OBJECT or
    GENERATED coordinates only, every baked object needs a clean UV map "UVMap".
  * `pulse`: float (optional) - Neon part brightness pulse speed in Hz (Roblox script animates).
* Blender materials should look great in EEVEE for the preview video (emission for glow parts).

## VFX empties (inside ITEM_ collections)
Empties named `VFX_<Preset>[_n]` mark where Roblox effects are spawned
(Attachment + emitter preset). Presets implemented in Roblox (roblox/src/PackSystem/SkinVFX.lua):
`Embers` (rising sparks), `Smoke` (dark heat smoke), `Fire` (small flames),
`HeatGlow` (orange PointLight), `Frost` (cold mist), `Snow` (falling flakes),
`Sparkle` (glints), `IceGlow` (cyan PointLight), `Drip` (lava drops).
Optional custom props on the empty: `rate` (multiplier), `size` (multiplier), `color` (r,g,b).
Emitters emit from the empty position; give a few per weapon (muzzle, along the body, stock).

## Preview video (Blender, for the user)
Each module also provides `render_showcase(out_dir)` that renders its 4 items
(turntable ~5 s each + one close-up of the effects) with EEVEE at 960x540 30 fps
on a dark studio backdrop, glowing materials and Blender particles approximating
the VFX presets, and writes `<out_dir>/<ItemName>.mp4`.
