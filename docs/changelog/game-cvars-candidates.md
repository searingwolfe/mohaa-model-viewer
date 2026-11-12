# Game cvars: candidates for the viewers

Debugging cvars from MOHAA 1.11 (the user's `cvarlist` / `cmdlist`, 859 cvars), EA's own
developer configs in the game's main folder (`development.cfg`, `jason.cfg`, `nate.cfg`,
`earl.cfg`, `av.cfg`, `decapitator.cfg`, `powzer.cfg`, `configs/*.cfg`) and OpenMoHAA's
source, which says what each one really does.

## Status (30 October 2026)

- **Map Viewer** (in the page since rev 25; the list's "Render distance" group since
  rev 34): `r_showtris 1/2/3`, `r_shownormals`, `r_lockpvs`, `r_novis`, `cm_noAreas`,
  `r_showsky`, `r_showstaticbboxes`, `r_farplane` (+ `_color`, `_nocull`, `_nofog`),
  `r_lightmap 1/2`, `r_light_showgrid`, `sv_showentnums`, `sv_showbboxes 1-8`,
  `g_entinfo 1-4` (+ `g_entinfo_max`), `sv_showcameras`, `g_showflypath`,
  `cg_rain_drawcoverage`, `ai_showroutes` (+ `_distance`, which the viewer starts at 8200
  where the game's default is 1000, and `ai_fallheight`),
  `ai_shownodenums`, `ai_shownode` (+ `ai_showallnode`), `g_nodecheck`, and the settings
  `g_gametype`, `skill`, `developer`, `sv_maxclients`. Entities the level script spawns
  (page rev 37) have no entity number in these: the game gives them one as the script runs.
  Weather (page rev 40): `cg_rain` and the level's rain settings as `cg_rain_*`
  (`density`, `speed`, `speed_vary`, `slant`, `length`, `width`, `min_dist`, `shader`,
  `numshaders`), `vss_wind_x` / `_y`, `com_maxfps`, `com_target_game`, with the viewer's
  `cg_weather` presets and `cg_rain_wholemap`; rev 41 adds `cg_thunder` (viewer) and
  `r_static_shadermultiplier0` .. `3`.
- **Model Viewer** (page rev 72): `sv_showbboxes 1/2/3/4/7/8` and the hit spheres 9-27
  (negative for a player model), `r_shownormals`, `r_uselod` (+ `r_lodscale`, `r_lodcap`,
  `cg_fov`, and a LOD distance slider with triangle counts), `cg_showemitters`,
  `cg_showtempmodels`, `vss_showsources 1/2`.
- Still open: the "bigger jobs" and skipped rows below (`ai_showpath`, terrain LOD,
  `r_light_lines`, `r_light_sun_line`, `r_showcull`, `r_showstaticlod`), and the
  `r_subdivisions` / `r_lodCurveError` number boxes for r_showtris.

Findings while implementing:
- `r_showsky`: in game the walls are drawn after the sky and still cover it, unless the
  sky shader has a solid cloud layer; the page draws the sky blocks in front.
- `sv_showcameras`: `func_camera.tik` isn't in the game's files, so the page draws a wire
  stand-in for the camera.
- `sv_showbboxes 7` is the bounds of the `.tik`'s `idle` animation (the union of its
  frames, the last `idle` loaded winning), times the scale: it does not follow the
  animation playing.
- An AI's box: `Actor::EventStart` gives every Actor, the dog too, the standing player's
  box ( -15 -15 0 ) ( 15 15 94 ) as it starts (`setSize(MINS, MAXS)`, after its spawn
  args; `MINS` / `MAXS` are in `bg_pmove.cpp`, on OpenMoHAA's GitHub, not in the uploaded
  source), whatever its setsize. Both viewers box it so since Model Viewer rev 72 and Map
  Viewer rev 23 (all 98 AI on m4l3 have other .tik setsizes). OpenMoHAA marks the call
  `//notsure`; on a dog (.tik setsize 48 tall) it is worth checking in game:
  `devmap m4l3`, `sv_showbboxes 1`, then walk up to a dog.
- `r_shownormals` in a map: in game a face or curve fills its normals in only when its
  shader uses them (`needsNormal`: environment maps, `deformVertexes`, dot alphaGen /
  rgbGen, `tcMod macro`), `needsLSpherical`, or a dynamic light is in the scene
  (`RB_SurfaceFace`, `RB_SurfaceGrid`); otherwise its lines show whatever the batch before
  left (stale, pointing anywhere). Terrain never has any (`tr_terrain.c`). Models always
  do. The Map Viewer (rev 24) draws every face's and curve's own normal.
- `r_uselod`: 88 retail `.lod` curves start above 0, so those models are never drawn
  whole in game, even with `r_uselod 0`. The Model Viewer starts at `r_uselod 0` and draws
  every triangle.
- Bone names ending in a space (15 models, the garands among them) don't get their
  animation channels in the Model Viewer: the garand stands upright instead of lying along
  X. Its boxes are right; the pose is an older viewer bug (match channels through the
  `.skd`'s per-bone channel names, `ofsChannelNames`).

## Testing in game

- Cheat cvars need cheats on: `devmap <map>` (or `set cheats 1`, then load the map).
  `r_showtris` and `r_shownormals` also need `developer 1` (`tr_shade.c`).
- `sv_showentnums`, `sv_showbboxes` and `sv_showtags` work only in single player or with
  cheats (`g_main.cpp`).
- `r_lightmap 2`, `r_fullbright`, `r_subdivisions` take effect when the map loads.
- EA's developers bound F8 to cycle `r_showtris` 0-3 (every dev config), `u` to
  `toggle r_lockpvs` (nate), `j` to `toggle g_entinfo` (earl), used `ai_showallnode 1`
  (jason) and `g_numdebuglinedelays 30; g_showbullettrace 1` ("bulleton"), and opened
  the `lodtool`, `camera` and `aipaths` menus with `togglemenu`.

## Finding: patch detail in game differs from the page's

The game's High preset (`high.cfg`) sets `r_subdivisions 4`; safemode sets 20. The engine
default, which `r_showtris` in the page uses, is 3 (`tr_init.c`). The user's config also had
`r_lodCurveError 225` (default 250). Patches in game can therefore have fewer rows than the
page's outlines. Fix: `r_subdivisions` and `r_lodCurveError` as number boxes in the list
(`r_lodCurveError` is applied in the page; `r_subdivisions` needs the patch grids built in
the page, or for a few values at build time).

## Map Viewer

Visibility and culling (`renderergl1/tr_world.c`, `tr_main.c`, `tr_sky.c`):

| Cvar | In game | In the page | Effort |
|---|---|---|---|
| `r_lockpvs 1` | Freezes the PVS and areas where you are ("lets designers walk around to determine the extent of the current pvs", `R_MarkLeaves`) | **Done (rev 22)** | Small |
| `r_novis 1` | Ignores the vis data: every leaf, no area check | **Done (rev 22)** | Small |
| `r_showcluster 1` | Prints `cluster:N area:M` when it changes | Already in the list's foot; could be a HUD line | Tiny |
| `r_showsky 1` | Sky box drawn in front of everything (`qglDepthRange(0,0)`): how much sky is drawn from here | **Done (rev 22)** | Small |
| `r_farplane N` (with `r_farplane_color`, `r_farplane_nocull 1`), `r_farplane_nofog 1` | Overrides the map's farplane distance, colour and culling (the last two only with r_farplane set); no fog | **Done (rev 22)**; its own group at the top of the list since rev 34 | Small |
| `r_shownormals 1` | 2-unit white lines along the normal of every vertex drawn, through walls (with `developer 1`); stale on surfaces whose shader doesn't use normals unless a dynamic light is in view | **Done (rev 24)**: faces' planes, curves' grid normals, models' vertex normals; none on terrain | Small |
| `r_nocull 1`, `r_facePlaneCull 0`, `r_nocurves 1` | No culling; no back-face culling; no patches | Options of r_showtris / Show buttons | Tiny |
| `r_drawworld`, `r_drawbrushes`, `r_drawterrain`, `r_drawstaticmodels`, `r_drawentities`, `r_drawbrushmodels`, `r_drawsprites` 0 | Hide parts of the scene | Console names for the existing Show buttons | Tiny |
| `r_speeds 1`, `r_infoworldtris`, `r_infostaticmodels`, `farplane_info` (commands) | Counts; tris of every model drawn; static models per TIKI; fog settings | Per-model triangle counts in the stats | Small |
| `r_lodCurveError N`, `r_subdivisions N` | Patch detail (see the finding above) | Number boxes for r_showtris | Small / medium |
| `ter_error`, `ter_maxlod`, `ter_lock 1` | Terrain LOD (`tr_terrain.c`); `ter_lock` freezes it | Needs the ROAM terrain LOD ported (r_showtris draws terrain at full detail now) | Large |

Lighting (`tr_bsp.c`, `tr_shade.c`, `tr_scene.c`, `tr_sphere_shade.cpp`):

| Cvar | In game | In the page | Effort |
|---|---|---|---|
| `r_lightmap 1` | Lightmaps only, no textures | **Done (rev 22)** | Small |
| `r_lightmap 2` | Lightmaps colour-coded by intensity (`HSVtoRGB`), brightest value printed | **Done (rev 22)** | Small |
| `r_fullbright 1` | Textures without lightmaps | Close to Full Brightness | Tiny |
| `r_light_showgrid 1` | Draws the light grid's points | **Done (rev 22)** | Small |
| `r_light_lines 1/2` | Lines from each lit model to the lights reaching it (2: in the light's colour x falloff) | Needs the game's entity light gathering | Medium |
| `r_light_sun_line 1` | Each model's trace toward the sun (sunlit or shaded) | Needs traces against the .bsp | Medium |

Entities (`fgame/g_main.cpp`, `entity.cpp`, `actor.cpp`, `camera.cpp`, `scriptslave.cpp`):

| Cvar | In game | In the page | Effort |
|---|---|---|---|
| `sv_showentnums 1` | Each entity's number (yellow) over its box | **Done (rev 22)**: the game's numbering, spawn order, `g_gametype` / `skill` / `developer` / `sv_maxclients` | Small-medium |
| `sv_showbboxes 1/2/3/4/7/8` | Boxes within 1000 units: 1 solid (rotated), 2 solid absmin/absmax, 3 models, 4 all, 7 the model's idle-animation bounds (cyan), 8 models + an 8-unit origin box | **Done (rev 22)**; an AI boxed as the game boxes it since rev 23 | Small |
| `g_entinfo 1/2/3/4` | The entity you look at: `entnum:radnum:targetname:health`. Actors also show think state, enemy and anim thread; 1 adds leash (green), mindist (red) and maxdist (blue) circles; 2 hearing (red) and sight (blue); 3 text only; 4 every actor the server sends you, not only the one looked at (`g_entinfo_max`, 2048, is the range) | **Done (rev 22)** | Small-medium |
| `sv_showcameras 1` | Cameras drawn as `func_camera.tik`, and the B-spline a camera follows (yellow) | **Done (rev 22)**, the camera a wire stand-in (no `func_camera.tik` in the paks) | Medium |
| `g_showflypath 1` | A flying script_object's path: 64-unit boxes and the curve | **Done (rev 22)** | Medium |
| `r_showstaticbboxes 1` | Static props' rotated boxes (magenta), .tik bounds x scale | **Done (rev 22)** | Tiny |
| `r_showstaticlod 1` | Static props' LOD % and rendered triangle count | The model LOD port now exists (Model Viewer `r_uselod`) | Medium |
| `r_showcull 1/2/4/8` | Models' cull box / sphere (green in, red out); 4/8 static props | Frustum test per model | Small |
| `cg_rain_drawcoverage 1` | The rectangle a func_rain spawns drops in (red) | **Done (rev 22)** | Small |
| `sv_showtags *` or a prefix (Spearhead / BT only) | Tag names, circles and axes on models within 1000 units | The Model Viewer has tags already | - |

AI (`fgame/navigate.cpp`):

| Cvar | In game | In the page | Effort |
|---|---|---|---|
| `ai_shownodenums 1` | Node numbers (yellow) 14 units over each node, within ai_showroutes_distance | **Done (rev 22)** | Tiny |
| `ai_shownode N` (with `ai_showallnode 1`) | The N nearest nodes in your map cell that a trace reaches (with ai_showallnode, the N nearest at your height, `DebugNearestNodeList2`) as 31 x 31 x 36 player boxes with a 16-unit facing line, in the game's type colours (`GetPathnodeColor`) | **Done (rev 22)** | Small |
| `ai_showpath 1`, `2`, `3` | Start and end at your feet, then the route an actor takes (red, 32 up) | **Done for Simulate's actor** (1.0.003): his route from `PathSearch::FindPath`, drawn by **Trace path** as `ShowNodes` draws it (the whole way blue, the rest to go red, a yellow line to his next point). Not yet as a cvar from the camera's spot | Medium |
| `g_nodecheck 1` | Rebuilds the nodes to report errors (more than the max paths per node...) and stops with "Node check failed" | **Done (rev 22)**: the `.pth`'s flag and the nodes with 48+ connections | Tiny |

## Model Viewer

| Cvar | In game | In the viewer | Effort |
|---|---|---|---|
| `sv_showbboxes 9` (10-27 one at a time; negative for the player) | The 19 hit-location spheres of a human (head x2, neck, spine2/1/0, pelvis, arms, thighs, forearms, calves, hands, feet) on Bip01 bones, plus the secondary ones (`cm_trace_lbd.cpp`: fixed radius and offset per bone) | **Done (rev 71)** | Small |
| `sv_showbboxes 7` | The bounds of the model's `idle` animation (`TIKI_CalculateBounds`), cyan; fixed, not following the animation | **Done (rev 71)**, with 1/2/3/4/8 (an AI's box since rev 72) | Small |
| `r_showSkeleton 1/2` | Bones as white lines (2: with joint markers) | Bones / Nodes already shown | - |
| `r_shownormals 1` | 2-unit white normal lines on every drawn vertex, through walls | **Done (rev 71)**, from the normals stored in the `.skd` / `.skb` | Small |
| `r_uselod 0`, `r_lodscale`, `r_lodcap`, `lod_tool` + `togglemenu lodtool` | Model LOD: `R_CalcLod` / `GetLodCutoff` drop triangles with distance; EA's LOD tool edits the curve | **Done (rev 71)**: `r_uselod`, `r_lodscale`, `r_lodcap`, `cg_fov`, a LOD slider and triangle counts (curve editing not done) | Medium |
| `cg_showemitters 1`, `cg_showtempmodels 1`, `vss_showsources 1/2` | Console counts per emitter; smoke sources as sprites (2: count) | **Done (rev 71)**: a console box over the stage; rings for the sources | Small |
| `cg_shadowdebug 1` | Blob shadow foot lines | Only if blob shadows are added | - |
| `tiki`, `animlist`, `tikilist`, `tikianimlist` (commands) | Print TIKI / animation info | Mostly shown already | - |

## Not worth it (gameplay-only, prints only, or nothing to show)

`g_showbullettrace`, `g_showawareness`, `g_showlookat`, `ai_debugpath`,
`ai_debug_grenades`, `g_showdamage`, `g_debugdamage`, `sv_drawtrace`, `sv_traceinfo`,
`cg_traceinfo`, `g_timeents`, `g_showplayeranim`, `g_showplayerstate`, `s_show_sounds`,
`whereami` and `ui_drawcoords` (the page shows the camera position already), `g_showaxis`
(weapon axes, mostly commented out), `r_showhbox` (registered, used nowhere),
`r_showportal` (needs the compiler's `.prt` file, not in the paks), `r_debugSurface`
(collision debug of one chosen patch), `cm_FCMdebug` (writes fence masks as text files).
