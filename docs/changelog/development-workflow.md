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
   - forced rebuilds recreating the WebView2 pane (a hash-only navigation doesn't reload).
6. **Map Viewer.** Rebuild a spread of retail maps (single-player, `dm`, `obj`) and compare
   the decompiled `.map` files byte for byte with the previous build: the decompiler is
   deterministic, so every changed byte needs a reason. Load the pages headlessly, switch
   between the In-game and Editor looks, and check the console stays clean and
   `gl.getError()` is 0 after a draw. Spot-check:
   - a mapper's own `.map` beside a `.bsp` is never replaced (`output_map_path`), and
     Clear built maps touches only its own files (`_is_built_file`);
   - see-through editor brushes drawn one-sided, and their inner sides from inside;
   - caulk's half-unit depth push, and the sky at the far end of the depth range;
   - looking around with the camera tilted (`lookBy`);
   - `r_showtris 2` inside a room with its door shut and a step outside it (the PVS and
     the areas), with `cm_noAreas 1`; `ai_showroutes 1` on a map whose `.pth` is in the
     paks (m5l1a), Spearhead's (t1l1) included, and a `.map` page (r_showtris greyed out).
     Headless Chromium draws with SwiftShader, which drops a GL line with one end behind
     the camera; the cvars' lines are cut at the near plane for it (`clipEnd`).

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
  `renderergl1/tr_shade.c` (`DrawTris`), `renderergl1/tr_curve.c`,
  `renderergl1/tr_surface.c` (`RB_SurfaceGrid`), `qcommon/cm_test.c` (areas and PVS),
  `server/sv_snapshot.c`, `fgame/archive.cpp` and `corepp/lz77.cpp` (the `.pth` file).
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
