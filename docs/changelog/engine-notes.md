# Engine notes

Findings about MOHAA's formats and renderer that were expensive to learn. Engine
references are to [OpenMOHAA](https://github.com/openmoh/openmohaa) (`code/cgame`,
`code/renderergl1`, `code/skeletor`, `code/tiki`). The source comments cite exact files
and line numbers next to the code that depends on them.

## Verifying against the real pipeline

- A Python or `.obj` render of a pose can look right while the JS viewer is wrong. The
  only reliable check is to replay the page's own math: take the real `DATA` payload
  from a built page, run the same quaternion/skinning code, and compare with numeric
  metrics (vertex distances, angles), not by eye.
- Python's `round()` rounds half to even; JavaScript's `Math.round` rounds half up. Any
  value computed on both sides (quantised angles, indices) must use the same rule, e.g.
  floor division with an explicit offset.
- Back faces: for front-sided shaders the engine keeps OpenGL's default CCW front face and
  culls `GL_FRONT` (`GL_Cull`, tr_backend.c:137-175), so visible faces run clockwise on
  screen. On the 2D path's y-down screen that's positive area (`_a2 > 0`); the WebGL path
  uses `cullFace(FRONT)`. A synthetic `.skd` with one clockwise and one counter-clockwise
  quad checks both renderers without game assets.

## Skeleton, animation and IK

- Leg IK must resolve on first demand, before any bone that depends on it (helper, Toe0,
  tags) is composed, matching the engine's lazy evaluation in `skeletorbones.cpp`. An
  FK-then-IK batch pass displaces helper origins on upper-body animations that borrow
  their legs from a movement-slot donor.
- `HoseRot` / `AvRot` helper bones must be solved, not folded into their ancestors, or
  ankles, knees and shoulders deform. The ankle helper also needs a 180-degree flip about
  its target's local Y, so its X axis points up the shin.
- Thigh and calf share one bend-plane frame (a port of `skelBone_IKshoulder` / `IKelbow` /
  `IKwrist`); a shortest-arc swing per bone twists the shin.
- When baking IK-solved world matrices into local quaternions, use the local-space
  conversion (`mat_to_localquat`); plain `mat_to_quat` stores the transpose.
- SKD vertices can carry `skeletorMorph_t` blocks (16 bytes each, after the 28-byte vertex
  and before the weights). They are the facial blend shapes; skipping them loses all face
  animation.
- Validate every count and offset in `.skc` / `.skd` headers against the file size before
  looping. The older ProtoAnimations v11 `.skc` format inserts a 64-byte name after the
  version field, shifting every offset.
- Humanoid `.skd` files have no usable rest pose (identity lays the rig along +X), and
  shared idle `.skc` frames are posed actions. A neutral A-pose template (allied_pilot)
  gives a clean default.

## TikiScript (.tik) parsing

- Expand `$include` before any parsing (grenade models keep `setup{}` in an included
  `_base.txt`), and write the expanded text back to disk before the builder subprocess
  reads the file.
- Strip `//` line comments before `/* */` blocks. Banner lines like `//******` contain a
  `/*` that otherwise pairs with a later `*/` and swallows whole `animations{}` blocks.
- `case <key> <values> { ... }` is a switch (`TIKI_LoadSetupCase`): only the matching
  branch's `skelmodel`s load.
- `tagemitter` takes a tag that may be a quoted string with spaces
  (`tagemitter "smoke emitter" heavysmoke`).
- Emitter parameters that go through `SetBaseAndAmplitude` accept `crandom` / `random` /
  `range` per component, including `avelocity` and `angles`.
- `life` on a volumetric emitter doesn't time out puffs; it scales the spawn count.
  `accel` / `smokeparms` share one slot, which for volumetric smoke means
  `[typeInfo, fadeMult, scaleMult]`, not an acceleration.
- A stale `skelmodel foo.skb` resolves to the shipped `foo.skd`, as the engine's loader
  does.
- The full list of emitter commands the viewer understands is in
  [emitter-commands.md](emitter-commands.md).

## Level of detail, bounds and hit locations

- A skelmodel's level of detail is per part: `GetLODFile` (tiki_skel.cpp) gives an `.skd`
  a control only if some surface's collapse index differs between its first and last
  vertex, and reads it from the `.lod` beside the `.skd` (96 bytes, or 48 with no
  constants; `TIKI_CalcLodConsts` recomputes them). An `.skb` never loses detail.
- Without a `.lod`, the default curve's far end is `lodIndex[10]`, one past the array,
  which in `skelHeaderGame_t` is `numBoxes`, usually 0: a model with no `.lod` is reduced
  at mid range and whole again far away.
- 88 of the retail `.lod` files (the `animate/bodies` corpses among them) have a curve that
  starts above 0, so the game never draws those models whole, even with `r_uselod 0`.
- `RB_SkelMesh` keeps a surface's vertices down to the first whose collapse index is under
  the cutoff (a binary search from vertex 3), skips the surface when its third vertex is
  already under it, folds the rest through the collapse map and stops at the first
  triangle that folds flat. `TIKI_SortLOD` sorted the triangles at load so that this
  equals dropping every flat triangle.
- `R_CalcLod` measures a model by radius x 100 / fov_x over its distance. The radius is
  92 for a `.tik` with `ischaracter` (players and humans get it through `$include`), else
  the skeletor's frame radius (at least 2, the `.skc` frame's own) times `load_scale`.
  OpenMoHAA widens fov_x on a wide screen; the original game's is `cg_fov`.
- A model's bounds (`TIKI_CalculateBounds`, `sv_showbboxes 7`) are the union of the frame
  bounds of the animation aliased `idle`, the last one loaded winning (`TIKI_InitTiki`),
  times `load_scale` and the entity's scale: they don't follow the animation playing.
  An entity whose `.tik` declares no `setsize` takes them as its size (`Entity::setModel`);
  a player sizes itself in code (the pmove box), and so does an AI as it starts:
  `Actor::EventStart` (`actor.cpp`) calls `setSize(MINS, MAXS)`, the standing player's
  box ( -15 -15 0 ) ( 15 15 94 ) (`bg_pmove.cpp:52-53`, from `MINS_X`...`MAXS_Z` in
  `bg_public.h`), whatever its `setsize` key or `.tik` setsize, since the start comes after
  the spawn args (`SpawnArgs::Spawn` runs the pending events first; a map's args are posted
  at -7, `EV_Entity_Start` at -1). The dog too. OpenMoHAA marks the call `//notsure`;
  `bg_pmove.cpp` isn't among the uploaded files, only on OpenMoHAA's GitHub.
- The hit spheres (`cm_trace_lbd.cpp`) sit on tag positions times `load_scale`, offset
  along the tag's own axes; the secondary sphere uses the primary's tag frame. In
  `Entity::DrawBoundingBox` a missing tag ends the loop, and 10 + i shows location i only
  for i up to 17, so the left foot never shows alone.
- A bone's animation channels are the names stored with the bone in the `.skd`
  (`ofsChannelNames`, `LoadBoneFromBuffer2`), compared exactly: bone `m1garand ` (with a
  space) is driven by `m1garand  rot`.

## Shaders and sprites

- `model <name>.spr` in an emitter is a shader name, not a file: the shader named by the
  path minus the extension (e.g. `mortar_dirthit` in `effects.shader`), whose first stage
  `map` / `clampmap` is the actual `.tga`. The `.spr` files themselves are not needed.
- Shader name lines can carry a trailing `//` comment; the block scanner must allow it or
  the whole index fails.
- `greasefire` and similar volumetric model names are VSS types (`VST_GREASEFIRE`) drawn
  through `VSSSource.spr`, not sprite or `.tik` references.
- A shader with no `spritegen` is `SPRITE_PARALLEL`, which ignores roll. See
  [sprite-roll-rules.md](sprite-roll-rules.md).
- Emitter `color` is converted to a byte with wrap-around (`(int)(c*255)` stored in a
  byte), not clamped: `color 4.5 0.2 0` becomes (123, 51, 0).
- `blendFunc GL_ONE GL_ONE` in a canvas needs premultiply compensation (alpha = max(R,G,B),
  RGB divided by it). Keeping the texture's own alpha under-lights it, and forcing alpha
  to 255 punches opaque black squares through the backdrop with canvas `'lighter'`.

## Map entities

- A spawn key that starts with `$` or `#` (`SpawnArgs::SpawnInternal`, fgame/g_spawn.cpp)
  goes to the class's setter event of the same name (`Event::FindSetterEventNum`, an
  `EV_SETTER` the class responds to), so `"$targetname" "x"` names an entity just as
  `"targetname" "x"` does. `#` passes the value as a whole number (`atoi`; as a float only
  when the key's own name has a `.` in it). Without such a setter the key only sets a
  script variable of that name on the object: `"#set" "1"` is `self.set`, `"$type"` is
  `self.type`. SimpleEntity's setters are `origin`, `targetname`, `target`, `angles` and
  `angle`, so every map entity takes `$targetname`; `SETTER_KEYS` in mohaa_bsp.py lists
  the setters of the classes a map spawns.
- An entity's spawn keys are posted as events due at one moment (`EV_SPAWNARG`, -7 s;
  `model` at `EV_PRIORITY_SPAWNARG`, -8), and `Listener::PostEventInternal`
  (corepp/listener.cpp) links each new event in front of the first queued one due at the
  same time or later (`LL_Add` inserts before its node, corepp/Linklist.h). So events due
  together run last posted first, and of a key written twice, or of `targetname` and
  `$targetname`, the first written stays. A plain `model` is due before the rest, so a
  `$model` outlasts it wherever it is written. An actor's plain keys are due later
  (`EV_SPAWNACTOR`, -2; its `model` at `EV_PRIORITY_SPAWNACTOR`, -3) than its `$` and `#`
  ones, so on an actor the plain key wins.

## Browser, WebView2 and file URLs

- A WebGL2 context doesn't offer `OES_standard_derivatives` to GLSL ES 1.00 shaders, so
  `dFdx` / `dFdy` fail to compile there. The renderer compiles its shaders as GLSL ES 3.00
  on WebGL2 and as 1.00 with the extension on WebGL1.

- Navigating WebView2 to the same `file:` URL with only the `#hash` changed is an in-page
  hash change, not a reload. To force a reload, close and recreate the pane.
- Don't cache-bust `file:` URLs with a query string (`?v=<mtime>`): `System.Uri` treats it
  as part of the file name and the load fails with `ERR_FILE_NOT_FOUND`.
- Build `file:` URLs with `pathlib.Path.as_uri()`. Hand-built `"file://" + path` breaks on
  Windows drive letters and on `#`, `%` or non-ASCII characters.
- WebView2 needs a writable folder for its browser files (the "user data folder").
  tkwebview2 passes none, so WebView2 would create `pythonw.exe.WebView2` beside the
  Python executable, which fails in a read-only install such as `C:\Program Files` and
  leaves the pane blank with no error the launcher sees. `mohaa_launcher.py` sets the
  documented `WEBVIEW2_USER_DATA_FOLDER` environment variable to `output/webview2`, which
  overrides that default. pywebview 4.4.1 starts it in private mode (its default), so a
  page's local storage lasts only while the launcher is open.
- A map page needs WebGL2 and `DecompressionStream` (its data is gzipped); both are in
  every current browser and WebView2 runtime.
