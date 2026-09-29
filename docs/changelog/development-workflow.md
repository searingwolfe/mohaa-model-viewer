# Development workflow

How changes to this project are made and checked. None of it needs special tooling
beyond Python 3, Node.js and a headless browser.

## Before shipping a change

1. **Static checks.** `python -m py_compile` (or `ast.parse`) on all three `bin/*.py`
   files. Extract each `<script>` block from `_HTML_TEMPLATE` in `mohaa_view.py` and run
   `node --check` on it.
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

## Things that must change together

| When you change | Also update |
|---|---|
| Page output or sidecar format | `VIEWER_REV` (mohaa_view.py) and `VIEWER_REV_REQUIRED` (mohaa_launcher.py) to the same number, plus a line in [CHANGELOG.md](CHANGELOG.md) |
| A release | `VERSION` (mohaa_launcher.py) and `docs/version.txt`, then tag the commit `v<version>` (the updater downloads that tag) |
| The privacy notice | `docs/PRIVACY.md` and `PRIVACY_TEXT` (mohaa_launcher.py), with the date |
| Viewer hotkeys | the page's `#helpCard` table and `HOTKEYS_VIEWER` (mohaa_launcher.py) |
| Package requirements | `docs/requirements.txt`, the RUN .bat and `python_installer_updater.bat` (`Pillow>=10.3.0`, `pywebview==4.4.1`) |

## Engine references

- [OpenMOHAA](https://github.com/openmoh/openmohaa) is the reference for engine
  behaviour. Any parser or renderer rule taken from the engine gets a comment citing the
  file and line range (e.g. `cg_tempmodels.cpp:601-602`), so the next person can check it.
- Files consulted most: `cgame/cg_tempmodels.cpp`, `cgame/cg_commands.cpp`,
  `cgame/cg_volumetricsmoke.cpp`, `renderergl1/tr_sprite.c`, `renderergl1/tr_shader.c`,
  `renderergl1/tr_shade_calc.c`, `renderergl1/tr_shade.c`, `skeletor/skeletorbones.cpp`,
  `tiki/tiki_parse.cpp`, `tiki/tiki_skel.cpp`, `tiki/tiki_files.cpp`, `qcommon/q_math.c`,
  `fgame/entity.cpp`.
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

## Handy tools

- Python 3 with Tkinter and Pillow; pythonnet, pywebview 4.4.1 and tkwebview2 for the
  embedded pane on Windows.
- Node.js for `node --check` and harnesses; `@napi-rs/canvas` gives a real 2D canvas for
  replaying the page's drawing code outside a browser.
- Playwright (Chromium) for driving built pages headlessly.
