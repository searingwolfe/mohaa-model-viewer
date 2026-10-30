# Development workflow

How changes to this project are made and checked. None of it needs special tooling
beyond Python 3, Node.js and a headless browser.

## Before shipping a change

1. **Static checks.** `python -m py_compile` (or `ast.parse`) on every `bin/*.py` file.
   Extract each `<script>` block from `_HTML_TEMPLATE` in `mohaa_view.py` and from
   `HTML_TEMPLATE` in `mohaa_map_page.py` and run `node --check` on it.
2. **Runtime check.** Static checks miss temporal-dead-zone errors (a `const` read before
   its line runs) and most behaviour. Build a real page and load it headlessly
   (Playwright, or jsdom with stubbed canvas/`requestAnimationFrame`); run the launcher
   under Xvfb on Linux to catch Tk errors. Watch the console for exceptions.
3. **Both render paths.** Pages use WebGL by default and the 2D canvas when it's selected
   (launcher View > Viewer renderer, or the page's Display > WebGL) or WebGL is unavailable. Headless Chromium runs WebGL with
   `--use-angle=swiftshader --enable-unsafe-swiftshader`, and `--disable-3d-apis` forces the
   2D path. A synthetic `.skd` (a couple of textured quads, one wound each way) is enough
   to compare culling, texture orientation and shading between the two. Particles are
   always drawn in 2D.
4. **Compare with the game.** For anything visual, compare against in-game footage frame
   by frame, and measure numerically where possible (particle counts, sizes, roll per
   frame, pixel counts). [sprite-roll-rules.md](sprite-roll-rules.md) has examples of
   such probes.
5. **Regression pass.** Spot-check the fixes most likely to be undone by an edit or a
   merge:
   - additive sprite premultiply compensation (`_gl1_lut` in mohaa_textures.py);
   - attach-to-bone rotation (`ATT_BASE_ANG`) and engine-unit offsets;
   - FIPS-safe cache ids (`_cache_id`);
   - pak path confinement (`_safe_target`);
   - TikiScript comment stripping order (`_strip_tik_comments`);
   - movement-slot donors and on-demand leg IK;
   - morph track resampling (`morph_track`) and driven helper bones;
   - two-sided surfaces skipping the back-face cull;
   - forced rebuilds recreating the WebView2 pane (a hash-only navigation doesn't reload);
   - the game cvars at their defaults: a page draws pixel for pixel as the build before
     it, in both renderers (`r_uselod` 0 leaves the triangles alone);
   - the camera stopping in both viewers: X, a `blur`, the tab hidden, the page without
     the focus while a key is held, the launcher's click (`stopCamera()`), and a drag whose
     next mouse move comes with its button up. After a stop, a key still held must not
     start the camera again from its auto-repeats (only a new press does), and
     `releaseCameraKeys()` must leave a drag and a fly-to going. On Windows, in the
     launcher: hold W in the viewer, right-click the launcher, keep holding W (the camera
     stops), then let go of W (it stays stopped); the same with a left and a middle click,
     and with a right-click on the page's own side panel (the browser's menu opens and the
     camera stops; a right-click on the Map Viewer's 3D view opens none and doesn't stop it).
6. **Model Viewer game cvars.** On a human (allied_airborne_soldier: five parts, each with
   a `.lod`), a player model, a weapon, a bare `.skd` and an emitter: `sv_showbboxes 9`
   and 10 to 27 (the spheres on the Bip01 bones, in both renderers), 1 / 2 / 7 / 8 (an AI,
   the dog included, and a player model boxed ( -15 -15 0 ) ( 15 15 94 ) whatever their
   setsize, also with the setsize pencil on), the negative values on the player;
   `r_shownormals 1`; `r_uselod 1` with the LOD slider swept from end to end, its
   triangle counts compared with a straight port of
   `TIKI_SortLOD` and `RB_SkelMesh` run on the page's own payload; `cg_showemitters`,
   `cg_showtempmodels` and `vss_showsources 2` on a continuous emitter (tanksmoke).
7. **Map Viewer.** Rebuild a spread of retail maps (single-player, `dm`, `obj`) and compare
   the decompiled `.map` files byte for byte with the previous build: the decompiler is
   deterministic, so every changed byte needs a reason. Load the pages headlessly, switch
   between the In-game and Editor looks, and check the console stays clean and
   `gl.getError()` is 0 after a draw. Spot-check:
   - a mapper's own `.map` beside a `.bsp` is never replaced (`output_map_path`), and
     Clear built maps touches only its own files (`_is_built_file`);
   - see-through editor brushes drawn one-sided, and their inner sides from inside;
   - caulk's half-unit depth push, and the sky at the far end of the depth range;
   - looking around with the camera tilted (`lookBy`); Q tilts the view to the left (the
     horizon's right end drops on screen, Copy ang gives a negative roll) and E to the
     right, the same way round as the Model Viewer's Q / E, and U levels it;
   - `r_showtris 2` inside a room with its door shut and a step outside it (the PVS and
     the areas), with `cm_noAreas 1`; `ai_showroutes 1` on a map whose `.pth` is in the
     paks (m5l1a), Spearhead's (t1l1) included, and a `.map` page (r_showtris greyed out).
     Headless Chromium draws with SwiftShader, which drops a GL line with one end behind
     the camera; the cvars' lines are cut at the near plane for it (`clipEnd`).
   - `r_shownormals 1`: the foot's line count is the drawn faces' points plus the patch
     points kept plus the models' vertices; a face's lines square to its edges; a
     static prop's lines 2 x .tik scale x scale long, an entity's 2; a door turned
     before and after the cvar is first on; the patch normals agree with the `.bsp`'s
     own control-point normals at the grid's corners.
   - `sv_showbboxes 1` and `sv_showentnums 1` by the AI of a single-player map (m4l3, its
     dogs included): every AI boxed ( -15 -15 0 ) ( 15 15 94 ), its number on top.
   - the Find lists on mohdm1: clicking `armchairposh` under Textures selects its nine
     armchairs and turns the row green, Shift+click its square hides them (red, `9 / 9`)
     and again shows them; a brush texture selects its brushes; Enter in the search box
     turns every result green; the Entities tab lists the numbered entities in order
     (as many as `sv_showentnums` numbers) and follows a change of skill or g_gametype;
     the two looks light up while their settings hold.
   - keys with `$` or `#` in front: on m1l1, entity number 33 in the Entities tab is
     `$mg42guy` and .map entity 136 under info_pathnode is `$enemyspawnerdestination`,
     and `#set` stays a key of its own; m4l0's path nodes with both `targetname` and
     `$targetname` take the first written, m4l3's sentries (actors) the plain one; the
     path node colours don't change (a node named only by `$targetname` stays green).
   - Open door on a double door from both sides (both leaves swing away from the camera),
     an `alwaysaway 0` door (the same way from both sides), a sliding `func_door` and a
     TOGGLE door; it closes itself after `wait`; with `r_showtris 1` the room behind a
     door that joins two areas is drawn only while it is open. A test can drive the doors
     with its own clock: stop the frame loop, set `performance.now`, call `doorsAdvance`.

## Things that must change together

| When you change | Also update |
|---|---|
| Page output or sidecar format | `VIEWER_REV` (mohaa_view.py) and `VIEWER_REV_REQUIRED` (mohaa_launcher.py) to the same number, plus a line in [CHANGELOG.md](CHANGELOG.md) |
| Map page output (mohaa_map_page.py, or the payload mohaa_map_view.py packs) | `MAP_VIEWER_REV` (mohaa_map_view.py) and `MAP_VIEWER_REV_REQUIRED` (mohaa_map_launcher.py) to the same number, plus a line in [CHANGELOG.md](CHANGELOG.md) |
| The cached shader / entity-definition index | `INDEX_VERSION` (mohaa_map_view.py) |
| A release | `VERSION` (mohaa_launcher.py) and `docs/version.txt`, then tag the commit `v<version>` (the updater downloads that tag). Both viewers ship together. |
| The privacy notice | `docs/PRIVACY.md` and `PRIVACY_TEXT` (mohaa_launcher.py), with the date; then check every left-hand text in `_PRIVACY_SWAPS` (mohaa_map_launcher.py) still matches |
| Viewer hotkeys | One table per viewer feeds both its page's `H` window and the launcher's `F1` window: `VIEWER_KEYS` (mohaa_view.py) and `MAP_VIEWER_KEYS` (mohaa_map_view.py); bump that viewer's page rev so cached pages pick it up. The launchers' own keys are `KEYS_LAUNCHER` (mohaa_launcher.py) and `MAP_KEYS_LAUNCHER` (mohaa_map_launcher.py). `kx_check(table)` (mohaa_view.py) lists any chord that names no key. A new key on a Display or Show button also goes in that button's label or tooltip |
| The keyboard map's look or behaviour | Both versions: the page's (`KEYS_JS` / `KEYS_CSS`, mohaa_view.py, used by both viewer pages) and the launcher's (`KeyMapWindow`, mohaa_launcher.py), then both viewers' page revs |
| The Map Viewer's legend | `LEGEND` (mohaa_map_view.py) only: the page and the launcher's Help > Legend both read it |
| The Model Viewer's game cvars | `CVAR_DEFAULTS` and `CVAR_ROWS` in the page's script (`_HTML_TEMPLATE`, mohaa_view.py); data a cvar needs from the model goes in `build_payload` (`game`, `lods`, `normals`, a surface's `lc` / `li`, an animation's `rad`), so `VIEWER_REV` goes up. A cvar must do nothing at its default |
| The Map Viewer's game cvars | `CVAR_DEFAULTS` and `CVAR_ROWS` in the page's script (mohaa_map_page.py); a cvar that draws something gets `LEGEND` rows (a `lines` swatch), and data it needs from the `.bsp` or the paks goes in the build's payload (`vis_payload`, `paths_payload`), so the page rev goes up |
| Package requirements | `docs/requirements.txt`, both RUN .bat files and `python_installer_updater.bat` (`Pillow>=10.3.0`, `pywebview==4.4.1`) |

## Engine references

- [OpenMOHAA](https://github.com/openmoh/openmohaa) is the reference for engine
  behaviour. Any parser or renderer rule taken from the engine gets a comment citing the
  file and line range (e.g. `cg_tempmodels.cpp:601-602`), so the next person can check it.
- Files consulted most: `cgame/cg_tempmodels.cpp`, `cgame/cg_commands.cpp`,
  `cgame/cg_volumetricsmoke.cpp`, `renderergl1/tr_sprite.c`, `renderergl1/tr_shader.c`,
  `renderergl1/tr_shade_calc.c`, `renderergl1/tr_shade.c`, `skeletor/skeletorbones.cpp`,
  `tiki/tiki_parse.cpp`, `tiki/tiki_skel.cpp`, `tiki/tiki_files.cpp`, `qcommon/q_math.c`,
  `fgame/entity.cpp`. For the Map Viewer: `qcommon/qfiles.h`, `qcommon/cm_load.c`,
  `qcommon/cm_terrain.c`, `qcommon/cm_patch.c`, `renderergl1/tr_bsp.c`,
  `renderergl1/tr_light.c`, `renderergl1/tr_sky.c`, `renderergl1/tr_terrain.c`,
  `renderergl1/tr_staticmodels.cpp` and `fgame/navigate.cpp`, plus the map compiler's
  `polylib.c` and `map.c` (q3map). For the game cvars: `renderergl1/tr_world.c`,
  `renderergl1/tr_shade.c` (`DrawTris`, `DrawNormals`), `renderergl1/tr_curve.c`
  (`MakeMeshNormals`), `renderergl1/tr_surface.c` (`RB_SurfaceFace`, `RB_SurfaceGrid`),
  `renderergl1/tr_model.cpp` (`RB_SkelMesh`, `RB_StaticMesh`), `qcommon/cm_test.c`
  (areas and PVS), `server/sv_snapshot.c`, `fgame/archive.cpp` and `corepp/lz77.cpp` (the
  `.pth` file).
  For doors: `fgame/doors.cpp`, `fgame/mover.cpp`, `fgame/g_spawn.cpp` (keys are read after
  the constructor, in order), `server/sv_world.c` (`SV_LinkEntity`) and `qcommon/cm_test.c`.
  For the Model Viewer's game cvars: `fgame/entity.cpp` (`DrawBoundingBox`, `setModel`),
  `fgame/actor.cpp` (`EventStart`) with `bg_pmove.cpp` / `bg_public.h` (`MINS` / `MAXS`),
  `fgame/debuglines.cpp`, `qcommon/cm_trace_lbd.cpp` (the hit locations),
  `renderergl1/tr_model.cpp` (`R_CalcLod`, `GetLodCutoff`, `RB_SkelMesh`),
  `tiki/tiki_skel.cpp` (`GetLODFile`, `TIKI_CalcLodConsts`, `TIKI_SortLOD`),
  `tiki/tiki_files.cpp` (the idle bounds), `skeletor/skeletor.cpp` (the frame radius),
  `cgame/cg_commands.cpp`, `cgame/cg_tempmodels.cpp` and `cgame/cg_volumetricsmoke.cpp`.
- Single files can be read from
  `https://raw.githubusercontent.com/openmoh/openmohaa/main/code/<dir>/<file>`; a sparse
  clone is easier for searching.
- Line numbers drift as OpenMOHAA changes; when a citation no longer matches, search for
  the function name and update the range.

## Comments and history

- Comments describe what the code does now and why, with engine citations. How it used
  to work, and which bug a change fixed, goes in [CHANGELOG.md](CHANGELOG.md).
- Keep changes to the smallest thing that solves the problem, and call out anything
  added beyond it so it can be reviewed separately.

## Batch-file pitfalls

A syntax error makes cmd abort the whole script, which in a double-clicked `.bat` looks like
the window closing instantly; run it from a Command Prompt to see the message.

- cmd has no `\"` escape. Inside `for /f ... in ('...')`, keep every `(` and `)` within
  double quotes or escape it as `^(` / `^)`, since an unquoted `)` ends the command list.
- Inside a parenthesised block, escape parentheses in `echo` text (`^(...^)`).
- Parenthesise every multi-command `if` body: `if X cmd1 & cmd2` runs `cmd2` unconditionally.
- With delayed expansion on, `!` is special; `%~` in any line, even a `REM`, must be a valid
  parameter modifier.
- `for /f` runs its command through `cmd /c`, which strips the quotes off a quoted program
  path containing `(`, `)` or `&`. To read a program's output, run it directly, redirect it
  to a temp file and read that back with `set /p` (`:consider` in the .bat files does).
- Each side of a pipe runs in a new cmd without delayed expansion, so `echo !VAR! | find`
  sees the literal text `!VAR!`. Use a `%`-expanded value, such as `%~1`, on a pipe.

## Handy tools

- Python 3 with Tkinter and Pillow; pythonnet, pywebview 4.4.1 and tkwebview2 for the
  embedded pane on Windows.
- Node.js for `node --check` and harnesses; `@napi-rs/canvas` gives a real 2D canvas for
  replaying the page's drawing code outside a browser.
- Playwright (Chromium) for driving built pages headlessly.
