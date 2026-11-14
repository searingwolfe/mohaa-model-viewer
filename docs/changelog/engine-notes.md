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
- A `HoseRot` bone comes in three variants, chosen by an int 36 bytes into its base data
  (read as `parent[ofsBaseData + 4]`, `LoadBoneFromBuffer2`, tiki_skel.cpp:49-57): 0
  `HOSEROT`, 1 `HOSEROTPARENT` (the parent's X and Z axes turned round before the bend) and 2
  `HOSEROTBOTH` (the parent's and the target's), skeletorbones.cpp:1095-1131. The retail
  human rigs' ankle helpers are BOTH and their hip helpers PARENT; MOHAA Reborn's
  re-exported `allied_pilot.skd` has plain HOSEROT everywhere, and its cuff verts are skinned
  to match. Posing a plain one as a BOTH turns the cuff's lower ring half way round, which
  pinches the cuff into an hourglass.
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
- Each `.skc` frame header (48 bytes) holds its bounds (6 floats), its radius (at 0x18) and
  then its movement delta (`skelAnimFileFrame_t.delta`, 3 floats at 0x1C, in the actor's own
  space: x ahead, y left): how far the engine moves the entity as the clip reaches that
  frame. `parse_skc` returns them as `fdelta`. The run and walk clips carry their pace in
  them, and the corner clips (`_wall_alert_left` ...) a sideways step of about 28 units, so
  an actor leans out round the wall and back.
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
- An entity spawned with only a model (`spawn models/human/german_wehrmact_soldier.tik`
  in a script, or a map entity whose classname the game has no class for) is created as the
  class the `.tik`'s server init commands name with `classname` (`SpawnArgs::getClassDef`,
  g_spawn.cpp: `Actor` for a human), else as a plain `Object`. The `/*QUAKED*/` header's
  name (`ai_german_wehrmact_soldier`) is the editor's class for that model, which is what
  the Map Viewer shows and counts it as.

## How an actor walks a path

What the Map Viewer's Simulate follows when it runs or walks a man (fgame/actor.cpp,
actorpath.cpp, navigate.cpp, g_mmove.cpp):

- **Choosing the route** (`Actor::MoveToPatrolCurrentNode`): a goal that is an
  `info_waypoint` is walked to in a straight line (`SetDest`, `FaceMotion`; no path search,
  and only the physics stop him at a wall). Any other goal goes through `SetPath`, which is
  `PathSearch::FindPath`: the nearest path node he can see (`NearestStartNode`, else just
  the nearest), the nearest node the goal can see (`NearestEndNode`, which has no
  fallback), and an A* over the nodes' links, leaving out links that drop further than
  `ai_fallheight`. If that finds nothing ("Path not found", printed with `g_patherror`),
  the path is cleared and he stays where he is.
- **Following it** (`ActorPath::UpdatePos`): he doesn't walk to each corner. He aims at a
  point a look-ahead further along the path (`PathLookAhead`: an area swept between him and
  the path that grows by 1024 a frame up to 256², while a 30 x 30 x 60 box trace to that
  point is clear, and shrinks when it isn't), so he cuts and rounds corners. The path ends
  when he is within 16 units of its end in x and y.
- **Facing** (`FaceMotion`, `UpdateAngles`): his yaw turns to his velocity or, when that
  agrees, to the way he has moved over the last 375-500 ms (the four 125 ms slots of
  `m_vOriginHistory`), at `m_fAngleYawSpeed`, 360 degrees a second.
- **Doors** (fgame/doors.cpp): see [doors-notes.md](doors-notes.md), *Actors and doors*.

## The sun and its flare

- The game draws no sun disc: `RB_DrawSun` (tr_backend.c) is inside `#if 0`. The sun
  shows only as a lens flare. `R_DrawLensFlares` (tr_sun_flare.cpp) draws it after each
  3D view's surfaces, except the HUD's (`RDF_HUD`), in a 2D pass (`qglOrtho(-1, 1, -1, 1)`
  over the view) with `tess.no_global_fog` set.
- The sun comes from the entity string (`R_Sphere_InitLights`, tr_sphere_shade.cpp).
  - Key names are compared case for case (`strcmp`), and only up to the first entity
    whose classname isn't worldspawn.
  - `suncolor` or `sunlight` makes a sun, as does `sundirection`, whose forward vector
    (`AngleVectorsLeft`) becomes the flare's direction unless `sunflaredirection` set it
    first.
  - `sunflarename` names the flare: "sun" when a sun has none, none at all for "none".
  - The retail maps' `sunflare`, `sundiffuse`, `sundiffusecolor`, `sunangle` and
    `sunflare_inportalsky` keys are read by neither OpenMOHAA's renderer nor its game
    code (`fgame/worldspawn.cpp` takes `sunflarename` and `sunflaredirection` and does
    nothing with them).
- The flare is a section of `global/lensflaredefs.txt` (`lens_flare::Init`): `begin
  <name>` to `end`, any case.
  - Each `flare <size> <where> <shader> [alphascale]` must have its words on its own
    line (`COM_ParseExt` without line breaks).
  - With no flare the game draws nothing. The defaults are `dot_min` .8, `fullscale` .7,
    no `fullscreen` and `fullfade` 0.
  - "sun" is one flare of size 1.4 at 0 (`textures/sprites/sunflare_main`: the 24-bit
    128 x 128 `flare_main.tga`, added with `GL_SRC_ALPHA GL_ONE` and alpha from the
    client), `dot_min` .55, `fullscale` .6, `fullscreen textures/jack/whitefade` and
    `fullfade` 600.
- Each frame (`sun_flare_class::SunTry`, then `lens_flare::ScreenBlend`):
  - `dot` is the view's forward · the flare direction. Nothing is drawn unless
    `dot > dot_min`.
  - While the sun is seen, the flare is drawn at alpha `(dot - dot_min) / (1 - dot_min)`
    and `lastbright` becomes that alpha to the 4th power times `fullscale`.
  - When it isn't seen, and there is a fullscreen shader and the blend is on, the flare is
    drawn at the fading `(fullfade - t) / fullfade * lastbright`, where t is the time
    since it was last seen. So the flare drops to the glare's brightness at once.
  - The fullscreen shader (`whitefade`: `$whiteimage`, `GL_SRC_ALPHA GL_ONE`, rgbGen
    identityLighting, which is 1 with `r_overBrightBits` 0) is drawn over the whole view
    at that same fading alpha, until the fade ends.
- A flare's quad is ±size in normalized screen units. A size of 1 is half the view's width
  and half its height, so the picture stretches with the window. Its middle is the screen
  position of the point 128 units toward the sun, moved by `where` × −2 × that position
  (`where` 1 is the mirror image through the screen's middle). Texture coordinates run
  (0, 0) at the top left to (1, 1) at the bottom right.
- Is the sun seen (`SunCheckRay`)? A trace runs only when one of these holds:
  - the camera's leaf (`R_PointInLeaf`) has area -1;
  - the map has no vis;
  - no leaf lists the sun;
  - the leaf's light list starts with it.

  Any other leaf never sees the sun. The trace is `CM_BoxTrace` from the eye to 16384
  units toward the sun: a point, the world model (`CONTENTS_SOLID`). The sun is seen when
  what the trace first meets has `SURF_SKY`. A point trace meets solid brushes (not
  `CONTENTS_FENCE` ones), solid patches from the front (`cm_playerCurveClip` 1) and the
  terrain, but not brush entities or models.
- Which leafs see the sun: the sphere-light vis lump (`LUMP_SPHERELIGHTVIS`, 20; 21 in
  versions 17-18) lists, for each leaf in order, the lights it sees, ended by -1
  (`R_LoadSphereLightVis`, tr_bsp.c). A list starting with -2 means the sun.
  - A lump with exactly one entry per leaf is the old format, with no lists.
  - On mohdm1, 710 of the 1893 leafs list the sun. m5l2b has the old format. m6l3c's
    lists never name it, and it has no sky faces anyway.

## Baked light

The map compiler bakes every light into the `.bsp` (lightmaps, vertex colours, the light
grid, the static props' vertex light) as one sum. MOHAA's own compiler isn't public;
OpenMOHAA's `code/tools/ommap/light.c` is id's q3map, and the retail lightmaps match its
point-light formula. These notes are what Lights off (map-viewer.md) is built on.

- Lights are the entities whose classname starts with `light` (`CreateEntityLights`).
  - Intensity: `light`, else `_light`, else 300. Colour: `_color` (or `color`), scaled so
    its largest channel is 1 (`ColorNormalize`).
  - Spawnflags (MOHAA's light definition): 1 LINEAR, 2 NO_ENTITIES (lights the world
    only), 8 ENTITY_ONLY (lights only models and the grid).
  - A light with a `target` (found by `targetname` as written; the compiler doesn't know
    `$targetname`) is a spot aimed at the target's origin. One with an `angles` key is a
    spot aimed along it, 64 units on. The cone's radius per unit of distance is
    `tan(spot_angle)` when `spot_angle` is set, else `(radius + 16) / distance`
    (`radius` 64 by default).
- What a light adds at a sample, in raw lightmap units (q3map, `photons` = intensity x
  7500; samples sit 1 unit off the surface; `dist` is at least 16):
  - point: `photons / dist^2 x cos`;
  - LINEAR: `cos x photons / 8000 - dist x falloff`;
  - spot: the point formula inside the cone, fading over its last 32 units, nothing
    behind it;
  - nothing when the add is 1 or less, or when the light is behind the surface.
  - Measured where one light dominates, raw byte / add has a median of 0.87 on m6l3d
    and 0.98 on m4l3, so the stored bytes are the adds themselves, not halved.
- Shadows: q3map's trace stops in the tree's solid leafs (`TraceLine_r`) and at the
  drawn surfaces it tests. The page stops light at every solid brush but the sky's
  (structural and detail, every side) and at opaque drawn surfaces. Alpha-tested
  surfaces (fences, grates) and `CONTENTS_TRANSLUCENT` ones let it through, and patches
  cast no shadow (q3map traces them only with `-patchshadows`). The page's shares (from
  distance cubes) agree with the same formula ray-traced exactly on 91-95% of m6l3d's
  covered texels.
- The sun (`SunToPoint`): the trace from the sample toward the sun has to end inside a
  sky brush (any brush with a `SURF_SKY` side). Measured on the retail maps:
  - its add is about `suncolor x cos` (m4l3, m4l0, m1l1), `sunlight` standing in when
    `suncolor` is missing;
  - the open sky adds a diffuse light, about `sundiffuse x sundiffusecolor` (default:
    the sun's colour) on a fully open floor;
  - a map without `sundiffuse` still has it: on m4l0 an open floor in shade gets about
    two thirds of `suncolor`, so the page takes 1;
  - mohdm1 has both `suncolor` (65 60 45) and `sunlight` (255 243 171). Its shaded open
    ground (medians 46-73, not clipped) fits `suncolor`; `sunlight` would clip it.
- The ambient floor: every texel gets at least `ambientlight`, floored to whole numbers
  (raw units), whatever lights it.
- Raw lightmap bytes top out at 127; the renderer shifts them up by one
  (`r_mapOverBrightBits`). Most sunlit texels are clipped at 127, so their bytes can't
  say how much each light added.
- Of the 44 retail Allied Assault maps with light entities, 42 have sky faces and sun
  keys. m6l3c and m6l3d have the keys but no sky face, so no sun reaches them.

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
- On Windows, WebView2 draws WebGL with ANGLE on Direct3D 11, which turns the shaders into
  HLSL. A shader that never finishes there makes Windows reset the graphics driver: every
  screen goes black for a few seconds. A software renderer just finishes. The page's
  shaders keep their loops of fixed length, with nothing read inside them deciding when
  they stop.
