"""Registry of all animations.  Each module exposes build() -> Anim.

Roblox names (KeyframeSequence names) are <Knife>_<Action>, e.g. Butterfly_Draw.
"""

import importlib

ANIMS = {
    # name            module                         roblox name
    "bf_idle":    ("vm.anim.butterfly.idle",    "Butterfly_Idle"),
    "bf_draw":    ("vm.anim.butterfly.draw",    "Butterfly_Draw"),
    "bf_inspect": ("vm.anim.butterfly.inspect", "Butterfly_Inspect"),
    "bf_attack1": ("vm.anim.butterfly.attack1", "Butterfly_Attack1"),
    "bf_attack2": ("vm.anim.butterfly.attack2", "Butterfly_Attack2"),
    "bf_heavy":   ("vm.anim.butterfly.heavy",   "Butterfly_Heavy"),
    "kr_idle":    ("vm.anim.karambit.idle",     "Karambit_Idle"),
    "kr_draw":    ("vm.anim.karambit.draw",     "Karambit_Draw"),
    "kr_inspect": ("vm.anim.karambit.inspect",  "Karambit_Inspect"),
    "kr_attack1": ("vm.anim.karambit.attack1",  "Karambit_Attack1"),
    "kr_attack2": ("vm.anim.karambit.attack2",  "Karambit_Attack2"),
    "kr_heavy":   ("vm.anim.karambit.heavy",    "Karambit_Heavy"),
}


def available():
    out = []
    for name, (mod, _) in ANIMS.items():
        try:
            importlib.import_module(mod)
            out.append(name)
        except ModuleNotFoundError as e:
            if e.name != mod:
                raise
    return out


def build(name):
    mod, rbx = ANIMS[name]
    m = importlib.reload(importlib.import_module(mod))
    a = m.build()
    a.name = name
    a.roblox_name = rbx
    return a
