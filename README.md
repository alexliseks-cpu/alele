# Ножи для Roblox: Butterfly и Karambit (модели + анимации в стиле CS2)

Готовый набор для твоего Roblox-режима:

* **Модели ножей** — реалистичные Butterfly Knife «Black Marble» и Karambit (чёрный клинок, карбоновая рукоять, стальное кольцо). Каждый нож разбит на отдельные части (у бабочки двигаются обе ручки, клинок и защёлка). PBR-текстуры (Color / Normal / Roughness / Metalness) подготовлены под `SurfaceAppearance`.
* **Анимации от первого лица** в стиле CS2 для **рук R15 твоего аватара** (пальцы и свои руки не нужны: нож держит блочная `RightHand`, как в твоём режиме). Для каждого ножа есть 6 клипов: `Draw` (взятие), `Idle` (цикл), `Inspect` (осмотр), `Attack1` и `Attack2` (лёгкие удары, чередуются), `Heavy` (сильный удар).
* **Blender-проект** со всеми анимациями (`export/KnifeViewmodels.blend`) и скрипты, которые полностью пересобирают модели и анимации (`blender/`).
* **Roblox-скрипты**: проигрыватель анимаций (воспроизводит `KeyframeSequence` напрямую, без публикации), сборщик вьюмодели из рук игрока, контроллер ножа (взятие, удары, осмотр, качание при ходьбе и повороте, тряска камеры, события попадания и звуков) и скрипт установки для Studio.

Превью всех анимаций лежат в папке [`previews/`](previews/).

---

## Что где лежит

| Путь | Что это |
|---|---|
| `export/meshes/Butterfly.fbx`, `Karambit.fbx` (+ `.glb`) | меши ножей для 3D Importer в Roblox Studio (с вшитыми текстурами) |
| `export/textures/*.png` | PBR-текстуры: `<Нож>_<Blade/Handle>_<Color/Normal/Roughness/Metalness>.png` |
| `export/roblox/KnifeSystem.rbxmx` | папка `KnifeSystem` для **ReplicatedStorage**: модули + все анимации |
| `export/roblox/KnifeAnimations.rbxmx` | только анимации (`KeyframeSequence`), если у тебя своя система |
| `export/roblox/KnifeClientExample.rbxmx` | пример LocalScript для **StarterPlayerScripts** |
| `export/roblox/SetupKnifeViewmodels.lua` | скрипт установки (вставить в Command Bar) |
| `export/KnifeViewmodels.blend` | Blender-файл: риг, ножи, все анимации (Actions + NLA-дорожки) |
| `roblox/src/` | исходники Lua-модулей (то же, что внутри `.rbxmx`) |
| `blender/` | Python-сборка всего проекта (модели, анимации, экспорт) |
| `previews/*.mp4` | превью каждой анимации (камера = вид игрока, FOV 70) |

---

## Установка в Roblox Studio (5 минут)

1. **Модули и анимации.** ПКМ по `ReplicatedStorage` → *Insert from File…* → `export/roblox/KnifeSystem.rbxmx`.
2. **Меши.** *Home → Import 3D* (3D Importer) → выбери `export/meshes/Butterfly.fbx`, затем `Karambit.fbx`. Настройки по умолчанию; модели попадут в `Workspace`. Текстуры из FBX импортируются как `SurfaceAppearance`. Размеры и оси не важны — скрипт установки сам выставит правильный размер каждой детали.
3. **Сборка.** Открой `export/roblox/SetupKnifeViewmodels.lua`, скопируй весь текст в **Command Bar** (View → Command Bar) и нажми Enter. Скрипт:
   * соберёт `ReplicatedStorage.KnifeSystem.Knives.Butterfly` и `.Karambit` (детали + Motor6D + сварка мешей),
   * создаст в Workspace `KnifeAnimRig_Butterfly` / `KnifeAnimRig_Karambit` — риги для Animation Editor (если захочешь посмотреть или опубликовать анимации).
   После этого импортированные модели из шага 2 можно удалить.
4. **Проверка.** Вставь `export/roblox/KnifeClientExample.rbxmx` в `StarterPlayer → StarterPlayerScripts`, запусти Play:
   `1` — бабочка, `2` — керамбит, `ЛКМ` — удар, `ПКМ` — сильный удар, `F` — осмотр, `Q` — убрать.

> Если текстуры не подтянулись при импорте: загрузи PNG из `export/textures` (Asset Manager → Import), впиши их `rbxassetid://…` в таблицу `Textures` в модуле `KnifeSystem.RigData` и снова запусти скрипт установки — он создаст `SurfaceAppearance` сам.

---

## Подключение к твоему режиму

### Вариант A — использовать готовый контроллер (проще всего)

```lua
local KnifeViewmodel = require(game.ReplicatedStorage.KnifeSystem.KnifeViewmodel)

local knife = KnifeViewmodel.new("Butterfly")   -- или "Karambit"
knife:Equip()          -- Draw, затем Idle по кругу
knife:Attack()         -- лёгкий удар (Attack1/Attack2 по очереди), учитывает кулдаун
knife:HeavyAttack()    -- сильный удар
knife:Inspect()        -- осмотр (прерывается ударом)
knife:Unequip()        -- убрать (или knife:Destroy())

knife.Hit:Connect(function(kind, raycastResult)
	-- kind = "light" | "heavy"; срабатывает в момент удара из анимации (маркер Hit)
	-- здесь вызывай свой RemoteEvent урона
end)
knife.Marker:Connect(function(clipName, markerName, value) end) -- все маркеры (Sound: flip/spin/swing…)
knife.StateChanged:Connect(function(state) end) -- Drawing / Idle / Attacking / Heavy / Inspecting / Unequipped
```

Вьюмодель строится из **рук аватара игрока** (`RightUpperArm`, `RightLowerArm`, `RightHand` и левые): клонируются его части, цвета и рубашка. Суставы ставятся по `RigAttachment`-ам аватара, поэтому анимации подходят к любому R15-телу. Если у персонажа нет R15-рук (R6 или ещё не загрузился), подставляются блочные руки с цветами из `KnifeConfig`.

Все настройки (кулдауны, звуки, качание, тряска камеры, смещение вьюмодели, дальность удара) — в модуле `KnifeSystem.KnifeConfig`. Звуки: впиши `SoundId` в `Config.Sounds` (`flip`, `latch`, `spin`, `catch`, `swing`, `swing_heavy`, `deploy`).

### Вариант B — своя система анимаций / свой вьюмодель

Анимации — обычные `KeyframeSequence` (`KnifeSystem.Animations.Butterfly.Butterfly_Draw` и т.д.). Иерархия Pose (= имена частей) у них такая:

```
HumanoidRootPart                (= камера)
├─ CameraBone                   (тряска камеры, необязательно)
└─ LowerTorso ─ UpperTorso       (не анимируются)
   ├─ RightUpperArm ─ RightLowerArm ─ RightHand ─ нож
   └─ LeftUpperArm  ─ LeftLowerArm  ─ LeftHand
нож бабочка:  BF_HandleA ─ BF_Blade ─ BF_HandleB ─ BF_Latch
нож керамбит: KR_Handle
```

* Motor6D называются как в R15 (`RightShoulder`, `RightElbow`, `RightWrist`, …), Transform анимаций = поворот в суставе, как у обычных R15-анимаций.
* Камера стоит в `HumanoidRootPart` вьюмодели; плечи — в точках `(±1, -1.69, -1.9)` studs от камеры (Roblox-оси: X вправо, Y вверх, -Z вперёд). Если у тебя вьюмодель стоит иначе — подвинь `KnifeConfig.ViewmodelOffset` или `UpperTorso`.
* Можно проигрывать их моим `KnifeAnimator` (без публикации — работает и в Studio, и в опубликованной игре), а можно открыть `KnifeAnimRig_*` в Animation Editor, загрузить нужную `KeyframeSequence` и опубликовать, чтобы получить `rbxassetid` для своего `Animator`.
* Маркеры в клипах: `Hit` (`light`/`heavy`) — момент удара; `Sound` (`deploy`, `flip`, `latch`, `spin`, `catch`, `swing`, `swing_heavy`).

---

## Blender

* Открой `export/KnifeViewmodels.blend` (Blender 5.x). Арматура `VM_Rig`; каждая анимация — отдельный Action (и отдельная NLA-дорожка с тем же именем). Камера `VM_Camera` = вид игрока (FOV 70 как в Roblox).
* Единицы сцены — **studs** (1 единица Blender = 1 stud), оси: камера смотрит вдоль +Y, Z вверх.
* Руки в Blender — это стандартные блоки R15 (только для превью). В Roblox используются руки игрока.
* Анимации описаны кодом (`blender/vm/anim/<нож>/<клип>.py`): ключевые позы кисти, поворот ножа, состояние ручек бабочки, IK считает плечо и локоть. Поменял ключи → пересобрал → получил новые `.rbxmx`, `.blend` и превью.

### Пересборка

```bash
pip install bpy==5.2.3          # Blender как Python-модуль (или запускай внутри Blender)
python blender/build.py         # всё: текстуры, анимации, .blend, FBX/GLB, .rbxmx, превью
python blender/build.py --no-preview --no-bake   # быстро: только анимации и экспорт
# превью рендерятся через Workbench, на Linux без экрана: xvfb-run -a python blender/build.py
```

Отдельные инструменты: `blender/tools/render_anim.py <клип>` (видео + раскадровка одной анимации), `blender/tools/model_preview.py <нож>` (рендер модели), `blender/tools/grip_check.py` (крупные планы хвата).

### Проверки

`roblox/tests/run_tests.sh` — офлайн-проверки Roblox-части без Roblox:

1. все Luau-скрипты компилируются;
2. сквозной тест рига: позы из Blender → данные рига + Transform → Motor6D-цепочка Roblox (мок API) → сравнение положения каждого сустава (погрешность ~1e-5 stud), плюс интерполяция, маркеры, затухание и зацикливание в `KnifeAnimator`;
3. экспортированный `KnifeAnimations.rbxmx` разбирается и проигрывается `KnifeAnimator` — результат сравнивается с исходными позами из Blender.

```bash
cargo build --release --manifest-path roblox/tests/luaurun/Cargo.toml   # Luau-раннер (mlua + Luau)
LUAURUN=roblox/tests/luaurun/target/release/luaurun BPY_PYTHON=python roblox/tests/run_tests.sh
```

---

## Ограничения

* Проверить работу в самом Roblox Studio отсюда нельзя: формат `.rbxmx`, сборка рига и проигрыватель проверены офлайн-тестами, но сам импорт FBX и вид в игре проверь у себя (шаги выше).
* Слоёная одежда (layered clothing) на руках не переносится во вьюмодель — только цвета тела и классическая рубашка.
* Если у тебя нестандартный пакет тела (Rthro и т.п.), руки будут другой длины — суставы берутся из аватара, позы останутся правильными, но кисть может стоять чуть иначе на экране.
