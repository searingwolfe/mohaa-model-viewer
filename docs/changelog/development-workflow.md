# Development workflow

How changes to this project are made and checked. None of it needs special tooling
beyond Python 3, Node.js and a headless browser.

## Before shipping a change

1. **Static checks.** `python -m py_compile` (or `ast.parse`) on every `bin/*.py` file.
   Extract each `<script>` block from `_HTML_TEMPLATE` in `mohaa_view.py` and from
   `HTML_TEMPLATE` in `mohaa_map_page.py` and run `node --check` on it. Then the
   hardening checks in `tests/` (they need tkinter): `test_hardening.py`,
   `check_batch_files.py`, `check_privacy_sync.py`, `check_init_attrs.py`, `test_map_actor.py`
   (set `MOHAA_GAMEFOLDER` to a folder of the game's files to run its real-data tests) and
   `fuzz_parsers.py bin 1`; each prints OK or what failed, and exits nonzero on failure.
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
   - Sun flare on mohdm1 and m4l0:
     - From an open spot (mohdm1's axis start at ( 896 -584 64 )), facing the sun
       (`D.sun.d`), the flare sits on the sun and moves with the view. The screen
       whitens more the closer the view faces the sun.
     - With the flare off the page is pixel for pixel as before.
     - m1l1's button is greyed out with `sunflarename none` in its tooltip, and J says
       the same.
     - A `.map` page (m4l0.map) sees the sun from the same spots as the `.bsp`.
     - A test can drive the fade with its own clock: set `sunNow` and replace
       `requestDraw` with a counter. While the sun is seen, the flare's alpha is
       `(dot - .55) / .45` and the glare's is that to the 4th power times .6. After it,
       even following a long idle, both fall from the glare's alpha over 600 ms. The
       redraw requests stop when the fade ends.
   - Lights off on m6l3d, mohdm1 and m4l3:
     - `0` turns every light off: m6l3d's rooms go black (no sky), mohdm1's houses go
       dark while its courtyards stay sunlit, m4l3 keeps its moonlight. Models darken
       with the rooms (the props by their probes, grid-lit models at their slot).
     - `0` again, or Turn on for each light turned off, gives the page as it opened,
       pixel for pixel; with no light ever turned off the page is pixel for pixel as
       rev 30.
     - Selection shows Turn off / Turn on for a light; each is greyed out when there is
       nothing to do, and Lights off gets a dashed border while some lights are off.
     - On a `.map` page (m4l0.map) both are greyed out with the reason as their tooltip,
       and `0` flashes it.
     - The console stays empty (no `readPixels` stall) and `gl.getError()` is 0. A test
       waits for `!LT.busy && !LT.queue.length`.
     - The sun's share comes from 17 directions; `LT.sun.length` is 0 only on a map
       without sky faces or sun keys. A sky brush must not shadow the sun (the solid
       brush list leaves them out).
     - After a change to the lights' shaders, read back `LT.lmOut` and `LT.pOut` (all lights
       off, and one light off) in SwiftShader and in llvmpipe (`--use-angle=gl-egl`) and
       compare them with the previous version's, byte for byte.
     - Step notes: `WEBGL_lose_context` while lights are being turned off gives the reset
       message with the names of the steps in flight and keeps the note. After a reload the first press only
       warns, a second within 6 s runs one step at a time (`LT.batch` 1), and the note is
       gone once it has finished.
     - Sun light (`-`): off on mohdm1 takes the open ground down to the ambient light while
       the rooms keep their lamps; on m4l3 the moonlight goes and the lamps' pools stay.
       With Lights off too, only the floor is left. The sun back on with Lights off on
       gives the Lights off picture; everything back on gives the page as it opened. The
       button is greyed out on m6l3d (no sky faces) and on a `.map` page, and the Sky
       filter doesn't change whether a map has a sun (`ltHasSky`).
     - The cap: with mohdm1's light 108 (200, at ( 1256 232 488 )) off, only a few dozen
       texels more than 512 units away darken by more than 16 levels, and all lights off
       leaves its sunny courtyards without hard black patches in the buildings' shade.
       Read the relit pages back from `LT.lmOut` and compare with `B.lmTex`.
   - Decals (`=`) on m2l1: `DCL.n` 147 vertices in 8 textures, every texture loaded
     (`GLT`), the barracks' letters and the eagle poster drawn on their walls, white with
     Full Brightness, gone with `=`. The button is greyed out (and not on) on a map
     without a `.dcl`.
   - Leak (`P`) on NormandyBridge_V1 (`.map` and `.bak`): the red line from below the
     terrain to the `light` (entity 1), the card's entity link selects it and the hole's
     Go flies along the trail. A `.bak` holding a `.bsp` (a copy of m2l1.bsp) builds
     `m2l1_bak.map` and `m2l1_bak_view.html`, with the paks' m2l1.dcl.
   - Level script: a map with a test `.scr` beside it (spawn lines with literal origins,
     `local.x.origin = $name.origin + ( 0 64 0 )`, an `exec` of a second map script, a
     spawn in a `for` loop): the placed ones are drawn with their links, the loop's is
     listed as not placed, `Ctrl+E` hides them, the stats line opens the Level script card,
     and an entity's card shows its script lines. Retail m3l1a: 70 of 76 placed, 20 `$world` lines. A `for` loop of `$("name" + local.q).target = $("name" + (local.q + 1))` links every waypoint but the last; a map entity's `.target` set by script shows on its card. A `$gun thread bipod` / `local.g thread bipod 1` / `thread bipod NULL ( x y z ) ( p y r )` test puts a bipod under each gun (`self`) and at the given place (parameters). Reading every retail map script takes about a second with none stopped at the statement limit. Editing
     the `.scr` and opening the map again in the launcher rebuilds the page.
   - Weather on m6l1a (snow0 to snow11 at density .2, from 4 of its 30 func_rain boxes at
     the start) and m5l1a (rain, global/weather.scr's density 3): the list's foot counts
     the beams; `cg_weather snow` with `cg_rain_wholemap 1` on a map without func_rain
     reaches 4096 beams and counts the drops not started; beams put in front of the camera
     draw as flakes (autoSprite) and faint streaks (textures/rain at .2). Screenshots of a
     page with falling weather need the frame loop stopped first (`wxActive=()=>false`).
   - Thunder: `cg_thunder 1` on m5l1a hides its 15 `$weatherF` windows; with `THU.next` set
     to now the flickers follow weather.scr's patterns (a fake clock through `thTick` gives
     0.1 / 0.1 / 0.2 / 0.5 / 0.1 s for its third), and a flash draws no sky (white with the
     map's farplane). Leaves: on m6l1a the static trees' shaders carry `dv` and two frames
     2.5 s apart with `r_static_shadermultiplier1 4` differ.
   - Open door on a double door from both sides (both leaves swing away from the camera),
     an `alwaysaway 0` door (the same way from both sides), a sliding `func_door` and a
     TOGGLE door; it closes itself after `wait`; with `r_showtris 1` the room behind a
     door that joins two areas is drawn only while it is open. A test can drive the doors
     with its own clock: stop the frame loop, set `performance.now`, call `doorsAdvance`.
   - Simulate's actor (in the launcher, with paks): Spawn on a CORNER_LEFT, CORNER_RIGHT,
     CRATE, SNIPER and DUCK node, Simulate each (the corner clips lean about 28 units to
     the side and back), Respawn; Run path along a node's `target` chain, Run to a node
     across the map and to a spot with no path node near it ("Path not found", he stays);
     a walk through a shut wood door (it opens as he reaches its field; a TARGETED door
     stops him); Trace path, Pause / Resume, Fly to and Follow; deselecting the node takes
     him away. `python tests/test_map_actor.py` with `MOHAA_GAMEFOLDER` set checks the
     skinning and a solved clip against the Model Viewer's pose.
   - Modify: Delete on one of the map's path nodes marks it DEL and its links go; Save as
     .bsp, then open the copy: the node is gone and the entity count is one less; Restore
     and Undo bring it back. The Spawnflags list sets and clears bits (each an Undo step).

## Things that must change together

| When you change | Also update |
|---|---|
| Page output or sidecar format | `VIEWER_REV` (mohaa_view.py) and `VIEWER_REV_REQUIRED` (mohaa_launcher.py) to the same number, plus a line in [CHANGELOG.md](CHANGELOG.md) |
| Map page output (mohaa_map_page.py, or the payload mohaa_map_view.py packs) | `MAP_VIEWER_REV` (mohaa_map_view.py) and `MAP_VIEWER_REV_REQUIRED` (mohaa_map_launcher.py) to the same number, plus a line in [CHANGELOG.md](CHANGELOG.md) |
| The cached shader / entity-definition index | `INDEX_VERSION` (mohaa_map_view.py) |
| A release | `VERSION` (mohaa_launcher.py) and `docs/version.txt`, then tag the commit `v<version>` (the updater downloads that tag). Both viewers ship together. |
| The privacy notice | `PRIVACY_TEXT` (mohaa_launcher.py), with the date, then `python tests/check_privacy_sync.py --write` to copy it into `docs/PRIVACY.md`; the same check (without `--write`) fails if any left-hand text in `_PRIVACY_SWAPS` (mohaa_map_launcher.py) no longer matches |
| Viewer hotkeys | One table per viewer feeds both its page's `H` window and the launcher's `F1` window: `VIEWER_KEYS` (mohaa_view.py) and `MAP_VIEWER_KEYS` (mohaa_map_view.py); bump that viewer's page rev so cached pages pick it up. The launchers' own keys are `KEYS_LAUNCHER` (mohaa_launcher.py) and `MAP_KEYS_LAUNCHER` (mohaa_map_launcher.py). `kx_check(table)` (mohaa_view.py) lists any chord that names no key. A new key on a Display or Show button also goes in that button's label or tooltip |
| The keyboard map's look or behaviour | Both versions: the page's (`KEYS_JS` / `KEYS_CSS`, mohaa_view.py, used by both viewer pages) and the launcher's (`KeyMapWindow`, mohaa_launcher.py), then both viewers' page revs |
| The Map Viewer's legend | `LEGEND` (mohaa_map_view.py) only: the page and the launcher's Help > Legend both read it |
| The Model Viewer's game cvars | `CVAR_DEFAULTS` and `CVAR_ROWS` in the page's script (`_HTML_TEMPLATE`, mohaa_view.py); data a cvar needs from the model goes in `build_payload` (`game`, `lods`, `normals`, a surface's `lc` / `li`, an animation's `rad`), so `VIEWER_REV` goes up. A cvar must do nothing at its default |
| The Map Viewer's game cvars | `CVAR_DEFAULTS` and `CVAR_ROWS` in the page's script (mohaa_map_page.py); a cvar that draws something gets `LEGEND` rows (a `lines` swatch), and data it needs from the `.bsp` or the paks goes in the build's payload (`vis_payload`, `paths_payload`), so the page rev goes up |
| Package requirements | `REQUIRED` / `OPTIONAL_EMBED` in `bin/mohaa_envcheck.py` (what the RUN files install), `PILLOW_MIN` in `bin/mohaa_common.py` (the run-time floor) and `docs/requirements.txt` (`Pillow>=10.3.0`, `pywebview==4.4.1`) |
| A new `bin/` script the Map Viewer needs | Its name in `PROGRAMS["map"]["FILES"]` (tools/make_launchers.py: the RUN files check it is there), the `ours` tuple of `_own_pycache` (mohaa_map_launcher.py), then regenerate the launchers |
| A RUN launcher (.bat or .sh) | The generator template (see [hardening-notes.md](hardening-notes.md)), so the Model and Map files stay twins; then `python tests/check_batch_files.py` |
| A file the RUN launchers require | `PROGRAMS` (per program) or `COMMON` (needed before the menu) in `tools/make_launchers.py`, then run it |
| An attribute set in `App.__init__` | The same in `MapApp.__init__` (it repeats App's start-up); `python tests/check_init_attrs.py` lists any gap |

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
- CRLF line endings on every line: cmd mis-parses LF-only files, most visibly when a
  `goto` / `call` looks for a label. Two of the three `.bat` files were LF-only before
  1.0.001.
- Never put `>` inside a double-quoted string, even in `echo` or `set`: write `^>` or move
  the logic into Python. Redirections are written `1>"file"`.
- One `pause`, at the very end; no `timeout`. Every failure sets `EXIT_CODE` and jumps to
  `:end`.
- Version checks, installs and anything with real branching live in Python
  (`mohaa_envcheck.py`); a `.bat` only finds Python, calls it, and pauses.
- `python tests/check_batch_files.py` checks the first three rules at the byte level.

## Handy tools

- Python 3 with Tkinter and Pillow; pythonnet, pywebview 4.4.1 and tkwebview2 for the
  embedded pane on Windows.
- Node.js for `node --check` and harnesses; `@napi-rs/canvas` gives a real 2D canvas for
  replaying the page's drawing code outside a browser.
- Playwright (Chromium) for driving built pages headlessly.
