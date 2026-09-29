# Project overview

MOHAA Model Viewer opens any *Medal of Honor: Allied Assault* model, including emitters,
FX scripts, explosions, animated characters, projectiles, weapons, vehicles and static
props, and shows it the way the game draws it. The goal is in-game parity, not an
approximation: behaviour is taken from the engine source
([OpenMOHAA](https://github.com/openmoh/openmohaa)) and checked frame by frame against
in-game footage. Where the two disagree, the footage wins and the notes say why.

## Repository layout

| Path | Role |
|---|---|
| `RUN -- Medal of Honor Model Viewer.bat` | Windows entry point. Uses the py launcher's default Python if it's 3.8+ with tkinter, else the newest suitable one on PATH or in the default install folders (Store aliases skipped); if there is none, asks Y/N to run the installer below. Then installs Pillow and the embedded-pane packages if missing, reports a missing WebView2 Runtime, and starts the launcher with the matching `pythonw.exe` so no console stays open. A `.skd` / `.tik` dropped on it is opened directly. |
| `bin/mohaa_launcher.py` | Tkinter desktop app: pak loading and tree, build orchestration, embedded WebView2 pane, on-demand animation and attachment builds, settings, updater. |
| `bin/mohaa_view.py` | Model builder. Parses `.skd` / `.skb` / `.skc` / `.tik` / `.map`, solves the skeleton and IK, writes an `.obj`, and fills the page template (`_HTML_TEMPLATE`, all of the viewer's HTML/CSS/JS) with the model payload. |
| `bin/mohaa_textures.py` | Pak virtual filesystem (`Vfs`), `.shader` index and render hints, texture resolution and `data:` URL encoding, `$include` expansion, and the animation catalogue (`build_anim_catalog`). |
| `bin/python_installer_updater.bat` | Windows setup: installs a Python suited to the Windows version and CPU, then the packages. Run by the RUN .bat on request (`/fromrun` skips its closing pause), or on its own. |
| `docs/` | Privacy, security and licensing notices, `requirements.txt`, `version.txt` (read by the updater) and these notes. |
| `output/` | Created at runtime beside `bin/`: config, console log, built pages. Git-ignored. |

## How a model gets built

1. **Paks.** The launcher merges the chosen `.pk3` files into one case-insensitive
   `Vfs` (later paks override earlier ones), then indexes shaders, shader render hints
   and `.tik` files in the background.
2. **Open.** The model is extracted to a temp workspace (`%TEMP%/mohaaview_*`). A `.tik`
   has its `$include`s expanded and is written back so the builder sees the full text; a
   matching `.map` is extracted for the `setsize` box. The launcher writes a texture
   manifest (`--textures=`), the emitter sprite table (`--emittertex=`) and the animation
   catalogue (`--animcat=`).
3. **Build.** `mohaa_view.py <model> --no-open [...]` runs as a subprocess and writes
   `<stem>_skd_view.html` or `<stem>_tik_view.html` (plus `<stem>.obj`). The page is
   self-contained: textures are `data:` URLs and the model is an inline `DATA` object.
4. **Show.** The launcher loads the page in its WebView2 pane with
   `#embed&theme=...&renderer=...&ang=...` in the URL (read by a boot script in `<head>`), or in the
   default browser without the hash.
5. **On demand.** The page and launcher talk over `chrome.webview.postMessage`:

   | Page sends | Launcher does |
   |---|---|
   | `mohaa-anim <id> <name>` | runs `--animbuild=`, writes `<stem>_view/a<id>.js`, calls `MOHAA_ANIM_LOAD` (or `MOHAA_ANIM_FAIL`) |
   | `mohaa-attach-models` | replies with `MOHAA_ATTACH_MODELS` (the model list for attach-to-bone) |
   | `mohaa-attach <path>` | runs `--attachbuild=`, writes `at<key>.js`, calls `MOHAA_ATTACH_LOAD` / `MOHAA_ATTACH_FAIL` |
   | `mohaa-ang <p,y,r>` | saves the placement angles to the config |
   | `mohaa-renderer <gl\|2d>` | saves the renderer choice (the page's Display > WebGL toggle) and updates View > Viewer renderer |
   | `mohaa-close` | returns the pane to the start page |

   In the other direction the launcher runs page functions: `MOHAA_*` for built sidecars,
   `setTheme`, `setViewerAngles` and `setViewerRenderer`. A page opened in a normal browser
   has no host, so these features hide themselves.

## Caching and versions

- `VIEWER_REV` (mohaa_view.py) is baked into each page as `<!--mohaa-viewer-rev:N-->`.
  `VIEWER_REV_REQUIRED` (mohaa_launcher.py) is the oldest rev the launcher will reuse.
  Raise both together whenever the page or its sidecars change in a way a cached copy
  must pick up. History is in [CHANGELOG.md](CHANGELOG.md).
- A cached page is also rebuilt when any of the three `.py` files is newer than it.
- Sidecar folders carry a `.rev` stamp; a mismatch with `VIEWER_REV_REQUIRED` clears the
  cached `a<id>.js` / `at<key>.js` files once.
- `VERSION` (mohaa_launcher.py) and `docs/version.txt` must match on each release; Help →
  Check for updates compares them.

## The renderer in brief

- **Hybrid.** WebGL draws the grid and skinned mesh with a depth buffer; a 2D canvas on
  top draws particles, autosprite billboards, tag/bone nodes, labels and the setsize box.
  The launcher's View > Viewer renderer (or the page's Display > WebGL toggle) switches to
  the 2D renderer; with that selected or WebGL unavailable, `GLR` is null and
  `draw2DScene()` draws everything. Both paths are supported and need testing.
- **Particles.** Emitters are simulated on the CPU following `cg_tempmodels.cpp` /
  `cg_commands.cpp`: 10 Hz physics with interpolation, engine spawn shapes and velocity
  order, fade/scale/roll rules, `T_SWARM`, friction, collision. Volumetric smoke follows
  `cg_volumetricsmoke.cpp` (density ramp and decay, radius growth, wind, repulsion).
- **Sprites.** Sprite types follow `tr_sprite.c` (parallel, parallel_oriented, oriented,
  upright); world-space quads are drawn with perspective-correct strips and near-plane
  clipping. See [sprite-roll-rules.md](sprite-roll-rules.md).
- **Shaders.** Resolved in Python into render hints (additive, alphaFunc, animMap,
  nextbundle + tcMod, deformVertexes autosprite/autosprite2/lightglow, distFade, spriteGen,
  spriteScale, rgbGen vertex) that the JS applies.

## Current state

- Version 1.0.000 (pre-release), `VIEWER_REV` 67.
- Windows is the main platform (embedded pane); macOS and Linux run the launcher and open
  pages in the browser.

## Known issues and open work

- **WebGL is new in practice.** Until rev 66 the WebGL renderer never ran in a WebGL2
  browser (its shaders didn't compile there), so every page drew with the 2D renderer.
  WebGL now matches 2D on synthetic test models (culling, texture orientation, shading),
  but real models have only been checked in 2D. If something differs, compare with
  View > Viewer renderer > 2D canvas.
- **No map data.** Map-placed effects' placement rotation and light grid aren't available,
  so the corona orbit is synthetic (off by default) and volumetric smoke lighting is
  fixed at the engine-neutral 1.0.
- **Idea:** fold the Setsizes toggle and its edit pencil into one Display control.
